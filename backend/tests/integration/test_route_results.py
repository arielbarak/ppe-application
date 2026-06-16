"""Integration tests for app.api.routes.results (Protocols 5-6)."""

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    register_n_nodes,
    signed_vote_payload,
)


def _walk_to_results(client, responder_keypairs, app_storage, n=4, p=1.0):
    """Walk through registration -> certification -> voting -> publish, return (sid, node_ids)."""
    payload = build_small_poll_payload(
        edge_probability=p,
        effort_threshold=0.5,
        validity_threshold=0.5,
    )
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    node_ids = register_n_nodes(client, sid, n, responder_keypairs)
    keypairs = responder_keypairs[:n]
    app_storage.update_session_status(sid, "certification")
    complete_certification_for_all(
        app_storage, sid, node_ids, edge_probability=p, keypairs=keypairs
    )
    app_storage.update_session_status(sid, "voting")
    for kp in keypairs:
        client.post(
            f"/api/poll/{sid}/vote",
            json=signed_vote_payload(kp, {"q1": "opt0", "q2": "opt0"}),
        )
    client.post(f"/api/poll/{sid}/publish")
    return sid, node_ids


# /publish


def test_publish_wrong_phase_400(client, responder_keypairs, app_storage):
    sid = client.post(
        "/api/poll/create", json=build_small_poll_payload()
    ).json()["session_id"]
    register_n_nodes(client, sid, 2, responder_keypairs)
    # Still in registration -> publish must reject
    resp = client.post(f"/api/poll/{sid}/publish")
    assert resp.status_code == 400


def test_publish_in_voting_phase_succeeds(client, responder_keypairs, app_storage):
    sid, _ = _walk_to_results(client, responder_keypairs, app_storage, n=2)
    # Status should now be "results"
    assert app_storage.get_session(sid).status == "results"


# /results


def test_get_results_returns_published_payload(client, responder_keypairs, app_storage):
    sid, node_ids = _walk_to_results(client, responder_keypairs, app_storage)
    resp = client.get(f"/api/poll/{sid}/results")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert len(body["responses"]) == len(node_ids)


# /verify global


def test_verify_global_clean_path_accepts(client, responder_keypairs, app_storage):
    sid, _ = _walk_to_results(client, responder_keypairs, app_storage)
    resp = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification"] == "ACCEPT"
    assert body["tally"]["q1"]["opt0"] == 4


def test_verify_global_rejects_after_fabricated_edge_injection(
    client, responder_keypairs, app_storage
):
    sid, node_ids = _walk_to_results(client, responder_keypairs, app_storage)

    # Inject a fabricated edge into the published_results dict.
    # Target a non-registered node so the edge is never in the ideal graph.
    sess = app_storage.get_session(sid)
    sess.published_results["certification_graph"]["edges"].append({
        "from": node_ids[0],
        "to": "phantom-target-not-registered",
        "verified": True,
        "signature": "forged",
        "timestamp": "2024-01-01T12:00:00",
    })

    resp = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification"] == "REJECT"
    assert body["details"]["fabricated_edge_count"] >= 1


# /verify local


def test_verify_local_requires_node_id(client, responder_keypairs, app_storage):
    sid, _ = _walk_to_results(client, responder_keypairs, app_storage)
    resp = client.post(f"/api/poll/{sid}/verify", json={"mode": "local"})
    assert resp.status_code == 400


def test_verify_local_accepts_voting_node(client, responder_keypairs, app_storage):
    sid, node_ids = _walk_to_results(client, responder_keypairs, app_storage)
    resp = client.post(
        f"/api/poll/{sid}/verify",
        json={"mode": "local", "node_id": node_ids[0]},
    )
    assert resp.status_code == 200
    assert resp.json()["verification"] == "ACCEPT"


def test_verify_unknown_mode_400(client, responder_keypairs, app_storage):
    sid, _ = _walk_to_results(client, responder_keypairs, app_storage)
    # Pydantic Literal validation kicks in -> 422
    resp = client.post(f"/api/poll/{sid}/verify", json={"mode": "schmlobal"})
    assert resp.status_code in (400, 422)
