"""
Hostile-pollster scenarios: each test simulates a different way a pollster
could try to manipulate published results, and asserts that Protocol 6
verification catches it.
"""

from app.crypto.verification import _edge_should_exist

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    register_n_nodes,
    signed_vote_payload,
)


def _walk_to_published(
    client, responder_keypairs, app_storage,
    n=4, p=1.0, effort_threshold=0.5, validity_threshold=0.5,
    skip_certification_for=None,
):
    """Drive a poll through all phases up to published. Returns (sid, node_ids)."""
    payload = build_small_poll_payload(
        edge_probability=p,
        effort_threshold=effort_threshold,
        validity_threshold=validity_threshold,
    )
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    node_ids = register_n_nodes(client, sid, n, responder_keypairs)
    keypairs = responder_keypairs[:n]
    app_storage.update_session_status(sid, "certification")
    complete_certification_for_all(
        app_storage, sid, node_ids, edge_probability=p, keypairs=keypairs
    )

    if skip_certification_for is not None:
        # Overwrite a node's outgoing edges as unverified to force exclusion via η_E
        for neighbor in node_ids:
            if neighbor != skip_certification_for:
                app_storage.add_certification_edge(
                    sid, skip_certification_for, neighbor,
                    verified=False, signature=None,
                )

    app_storage.update_session_status(sid, "voting")
    for kp in keypairs:
        client.post(
            f"/api/poll/{sid}/vote",
            json=signed_vote_payload(kp, {"q1": "opt0", "q2": "opt0"}),
        )
    client.post(f"/api/poll/{sid}/publish")
    return sid, node_ids


def test_pollster_fabricates_absent_edge_at_p_half_rejects(
    client, responder_keypairs, app_storage
):
    """At p=0.5 there is almost certainly an absent ideal edge. Inject it -> REJECT."""
    sid, node_ids = _walk_to_published(
        client, responder_keypairs, app_storage,
        p=0.5, effort_threshold=0.5,
    )

    absent_pair = next(
        ((a, b) for a in node_ids for b in node_ids
         if a != b and not _edge_should_exist(a, b, 0.5)),
        None,
    )
    assert absent_pair is not None, "Expected at least one ideal-absent edge at p=0.5"

    sess = app_storage.get_session(sid)
    sess.published_results["certification_graph"]["edges"].append({
        "from": absent_pair[0],
        "to": absent_pair[1],
        "verified": True,
        "signature": "forged",
        "timestamp": "2024-01-01T12:00:00",
    })

    body = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"}).json()
    assert body["verification"] == "REJECT"
    assert body["details"]["fabricated_edge_count"] >= 1


def test_pollster_drops_voter_from_node_list_rejects(
    client, responder_keypairs, app_storage
):
    """A voter whose node_id is missing from cert_graph['nodes'] is a critical issue."""
    sid, node_ids = _walk_to_published(client, responder_keypairs, app_storage)

    sess = app_storage.get_session(sid)
    # Drop the first voter from the published nodes list
    sess.published_results["certification_graph"]["nodes"] = [
        n for n in sess.published_results["certification_graph"]["nodes"]
        if n != node_ids[0]
    ]

    body = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"}).json()
    assert body["verification"] == "REJECT"
    assert body["details"]["missing_node_count"] >= 1


def test_too_many_exclusions_returns_invalid(client, responder_keypairs, app_storage):
    """With η_V tight and one node forced into exclusion, validity check fails."""
    sid, node_ids = _walk_to_published(
        client, responder_keypairs, app_storage,
        effort_threshold=0.2,       # strict η_E -> 1/3 failures excludes a node
        validity_threshold=0.01,    # max_allowed = 0.04, 1 exclusion exceeds it
        skip_certification_for=None,
    )

    # Mark all of node_ids[0]'s outgoing edges as unverified so the verifier
    # excludes that node, then re-publish results.
    for neighbor in node_ids:
        if neighbor != node_ids[0]:
            app_storage.add_certification_edge(
                sid, node_ids[0], neighbor, verified=False,
            )

    # Mutate the already-published_results to reflect the unverified edges
    sess = app_storage.get_session(sid)
    for edge in sess.published_results["certification_graph"]["edges"]:
        if edge["from"] == node_ids[0]:
            edge["verified"] = False

    body = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"}).json()
    assert body["verification"] == "INVALID"


def test_omitted_edge_accepted_under_loose_eta_e_with_count(
    client, responder_keypairs, app_storage
):
    """Drop one published edge: still ACCEPT with η_E loose, but omitted_edge_count > 0."""
    sid, node_ids = _walk_to_published(
        client, responder_keypairs, app_storage,
        effort_threshold=0.5,  # tolerate the resulting 1/3 failure rate
        validity_threshold=0.5,
    )

    sess = app_storage.get_session(sid)
    # Remove A->B from the published edge list, keep B->A
    a, b = node_ids[0], node_ids[1]
    sess.published_results["certification_graph"]["edges"] = [
        e for e in sess.published_results["certification_graph"]["edges"]
        if not (e["from"] == a and e["to"] == b)
    ]

    body = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"}).json()
    assert body["verification"] == "ACCEPT"
    assert body["details"]["omitted_edge_count"] == 1
