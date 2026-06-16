"""
End-to-end test that walks all 6 phases of the PPE protocol:

  Create -> Register -> Certify -> Vote -> Publish -> Verify

Uses m=4, p=1.0 (K4) so every pair is an edge and the deterministic graph
has all 12 directed edges. Effort threshold is loose (0.5) so unanimous
verification produces a clean ACCEPT.
"""

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    register_n_nodes,
    signed_vote_payload,
)


def test_full_six_phase_flow_m4_p_high(client, responder_keypairs, app_storage):
    # Phase 1: Announcement -- pollster creates the poll
    payload = build_small_poll_payload(
        edge_probability=1.0,
        effort_threshold=0.5,
        validity_threshold=0.5,
    )
    create_resp = client.post("/api/poll/create", json=payload)
    assert create_resp.status_code == 200
    sid = create_resp.json()["session_id"]

    # Phase 2: Registration -- 4 responders solve CAPTCHA and register pubkeys
    node_ids = register_n_nodes(client, sid, 4, responder_keypairs)
    assert len(node_ids) == 4

    # Transition to certification phase
    transition = client.post(f"/api/poll/{sid}/status", json={"new_status": "certification"})
    assert transition.status_code == 200

    # Phase 3: Certification -- seed all ideal edges as verified (real signatures)
    keypairs = responder_keypairs[:4]
    edges_seeded = complete_certification_for_all(
        app_storage, sid, node_ids, edge_probability=1.0, keypairs=keypairs
    )
    assert edges_seeded == 12  # K4: 4 nodes * 3 neighbors

    # Threshold endpoint reports all 4 certified
    threshold = client.get(f"/api/poll/{sid}/certification/threshold").json()
    assert threshold["threshold_met"] is True
    assert len(threshold["certified_nodes"]) == 4

    # Transition to voting phase (cert threshold met)
    voting_resp = client.post(f"/api/poll/{sid}/status", json={"new_status": "voting"})
    assert voting_resp.status_code == 200

    # Phase 4: Response -- every node votes opt0 on q1, opt0 on q2 (real signatures)
    for kp in keypairs:
        vote_resp = client.post(
            f"/api/poll/{sid}/vote",
            json=signed_vote_payload(kp, {"q1": "opt0", "q2": "opt0"}),
        )
        assert vote_resp.status_code == 200

    # Phase 5: Results -- pollster publishes the bulletin
    publish_resp = client.post(f"/api/poll/{sid}/publish")
    assert publish_resp.status_code == 200

    results_resp = client.get(f"/api/poll/{sid}/results")
    assert results_resp.status_code == 200
    results = results_resp.json()
    assert results["session_id"] == sid
    assert len(results["responses"]) == 4
    assert len(results["certification_graph"]["edges"]) == 12
    assert set(results["certification_graph"]["nodes"]) == set(node_ids)

    # Phase 6: Verification -- global ACCEPT with unanimous tally
    global_verify = client.post(f"/api/poll/{sid}/verify", json={"mode": "global"})
    assert global_verify.status_code == 200
    body = global_verify.json()
    assert body["verification"] == "ACCEPT"
    assert body["tally"] == {
        "q1": {"opt0": 4, "opt1": 0},
        "q2": {"opt0": 4, "opt1": 0},
    }
    assert body["details"]["fabricated_edge_count"] == 0
    assert body["details"]["omitted_edge_count"] == 0

    # Local verification for an arbitrary node
    local_verify = client.post(
        f"/api/poll/{sid}/verify",
        json={"mode": "local", "node_id": node_ids[0]},
    )
    assert local_verify.status_code == 200
    assert local_verify.json()["verification"] == "ACCEPT"
