"""Integration tests for app.api.routes.poll (Protocol 1)."""

import pytest

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    register_n_nodes,
)


# /create


def test_create_poll_returns_session_id_and_pubkey(client):
    payload = build_small_poll_payload()
    resp = client.post("/api/poll/create", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["public_key"]
    assert len(body["questions"]) == 2


def test_create_poll_duplicate_options_rejected_400(client):
    payload = build_small_poll_payload()
    payload["questions"][0]["options"] = ["yes", "YES"]  # case-insensitive duplicate
    resp = client.post("/api/poll/create", json=payload)
    assert resp.status_code == 400
    assert "duplicate" in resp.json()["detail"].lower()


# /{session_id}


def test_get_poll_returns_info(client):
    create_resp = client.post("/api/poll/create", json=build_small_poll_payload())
    sid = create_resp.json()["session_id"]

    resp = client.get(f"/api/poll/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert body["status"] == "registration"
    assert body["registered_nodes_count"] == 0


def test_get_poll_unknown_returns_404(client):
    resp = client.get("/api/poll/no-such-session")
    assert resp.status_code == 404


# /params/*


def test_recommend_params_endpoint(client):
    resp = client.get("/api/poll/params/recommend?expected_responders=100&security_level=medium")
    assert resp.status_code == 200
    body = resp.json()
    assert body["security_level"] == "medium"
    assert body["recommended"]["kappa"] == 80


def test_validate_params_endpoint(client):
    resp = client.get(
        "/api/poll/params/validate"
        "?expected_responders=100&edge_probability=0.14"
        "&effort_threshold=0.15&validity_threshold=0.025&kappa=80"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True


def test_compute_params_endpoint_invalid_kappa_400(client):
    resp = client.get(
        "/api/poll/params/compute"
        "?kappa=0&expected_responders=10"
    )
    # kappa=0 fails Query(ge=1) -> 422 by default; route also uses ValueError -> 400.
    # FastAPI returns 422 for Pydantic validation; we accept either as a client error.
    assert resp.status_code in (400, 422)


def test_compute_params_endpoint_happy_path(client):
    resp = client.get("/api/poll/params/compute?kappa=80&expected_responders=100")
    assert resp.status_code == 200
    body = resp.json()
    assert body["params"]["kappa"] == 80


# /{session_id}/status


def test_status_to_voting_blocked_when_certification_unmet(client, responder_keypairs):
    """With effort_threshold=0.5 and no edges, certification rate < 50% -> 400."""
    payload = build_small_poll_payload(edge_probability=1.0, effort_threshold=0.5)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]

    register_n_nodes(client, sid, 2, responder_keypairs)
    client.post(f"/api/poll/{sid}/status", json={"new_status": "certification"})

    resp = client.post(f"/api/poll/{sid}/status", json={"new_status": "voting"})
    assert resp.status_code == 400
    assert "certif" in resp.json()["detail"].lower()


def test_status_to_voting_succeeds_when_certification_met(
    client, responder_keypairs, app_storage
):
    payload = build_small_poll_payload(edge_probability=1.0, effort_threshold=0.5)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]

    node_ids = register_n_nodes(client, sid, 2, responder_keypairs)
    client.post(f"/api/poll/{sid}/status", json={"new_status": "certification"})
    complete_certification_for_all(app_storage, sid, node_ids, edge_probability=1.0)

    resp = client.post(f"/api/poll/{sid}/status", json={"new_status": "voting"})
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "voting"


def test_status_invalid_value_rejected(client):
    sid = client.post("/api/poll/create", json=build_small_poll_payload()).json()["session_id"]
    resp = client.post(f"/api/poll/{sid}/status", json={"new_status": "elsewhere"})
    assert resp.status_code == 400


# /{session_id}/certification/threshold


def test_certification_threshold_endpoint(client, responder_keypairs):
    payload = build_small_poll_payload(edge_probability=1.0, effort_threshold=0.5)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    register_n_nodes(client, sid, 2, responder_keypairs)

    resp = client.get(f"/api/poll/{sid}/certification/threshold")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_nodes"] == 2
    assert body["threshold_met"] is False


# /{session_id}/node/{node_id}/certification


def test_node_certification_endpoint(client, responder_keypairs, app_storage):
    payload = build_small_poll_payload(edge_probability=1.0, effort_threshold=0.5)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    node_ids = register_n_nodes(client, sid, 2, responder_keypairs)

    # Without edges -> not certified
    not_yet = client.get(f"/api/poll/{sid}/node/{node_ids[0]}/certification")
    assert not_yet.status_code == 200
    assert not_yet.json()["is_certified"] is False

    complete_certification_for_all(app_storage, sid, node_ids, edge_probability=1.0)

    yes = client.get(f"/api/poll/{sid}/node/{node_ids[0]}/certification")
    assert yes.status_code == 200
    assert yes.json()["is_certified"] is True


def test_node_certification_unknown_node_404(client):
    sid = client.post("/api/poll/create", json=build_small_poll_payload()).json()["session_id"]
    resp = client.get(f"/api/poll/{sid}/node/no-such-node/certification")
    assert resp.status_code == 404


# /{session_id}/stats


def test_poll_stats_endpoint(client):
    sid = client.post("/api/poll/create", json=build_small_poll_payload()).json()["session_id"]
    resp = client.get(f"/api/poll/{sid}/stats")
    assert resp.status_code == 200
    assert resp.json()["status"] == "registration"


def test_poll_stats_unknown_session_404(client):
    resp = client.get("/api/poll/nope/stats")
    assert resp.status_code == 404
