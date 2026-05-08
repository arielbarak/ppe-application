"""Integration tests for app.api.routes.response (Protocol 4)."""

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    register_n_nodes,
)


def _setup_poll_in_voting(client, responder_keypairs, app_storage, n=4, p=1.0):
    payload = build_small_poll_payload(edge_probability=p, effort_threshold=0.5)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    node_ids = register_n_nodes(client, sid, n, responder_keypairs)
    app_storage.update_session_status(sid, "certification")
    complete_certification_for_all(app_storage, sid, node_ids, edge_probability=p)
    app_storage.update_session_status(sid, "voting")
    return sid, node_ids


def _vote_payload(node_id, **overrides):
    base = {
        "node_id": node_id,
        "vote": {"q1": "opt0", "q2": "opt0"},
        "signatures": [],
        "signature": "self-sig",
    }
    base.update(overrides)
    return base


def test_submit_vote_unregistered_node_403(client, responder_keypairs, app_storage):
    sid, _ = _setup_poll_in_voting(client, responder_keypairs, app_storage)
    resp = client.post(f"/api/poll/{sid}/vote", json=_vote_payload("ghost-node"))
    assert resp.status_code == 403


def test_submit_vote_invalid_question_id_400(client, responder_keypairs, app_storage):
    sid, node_ids = _setup_poll_in_voting(client, responder_keypairs, app_storage)
    resp = client.post(
        f"/api/poll/{sid}/vote",
        json=_vote_payload(node_ids[0], vote={"unknown_q": "opt0"}),
    )
    assert resp.status_code == 400
    assert "invalid question" in resp.json()["detail"].lower()


def test_submit_vote_duplicate_400(client, responder_keypairs, app_storage):
    sid, node_ids = _setup_poll_in_voting(client, responder_keypairs, app_storage)
    first = client.post(f"/api/poll/{sid}/vote", json=_vote_payload(node_ids[0]))
    assert first.status_code == 200

    second = client.post(f"/api/poll/{sid}/vote", json=_vote_payload(node_ids[0]))
    assert second.status_code == 400


def test_submit_vote_wrong_phase_400(client, responder_keypairs, app_storage):
    """Submitting a vote during certification phase is rejected."""
    payload = build_small_poll_payload(edge_probability=1.0, effort_threshold=0.5)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    node_ids = register_n_nodes(client, sid, 2, responder_keypairs)
    app_storage.update_session_status(sid, "certification")

    resp = client.post(f"/api/poll/{sid}/vote", json=_vote_payload(node_ids[0]))
    assert resp.status_code == 400


def test_vote_count_endpoint(client, responder_keypairs, app_storage):
    sid, node_ids = _setup_poll_in_voting(client, responder_keypairs, app_storage)
    client.post(f"/api/poll/{sid}/vote", json=_vote_payload(node_ids[0]))
    client.post(f"/api/poll/{sid}/vote", json=_vote_payload(node_ids[1]))

    resp = client.get(f"/api/poll/{sid}/votes/count")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_votes"] == 2
    assert body["total_registered"] == 4
