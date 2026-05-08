"""Integration tests for app.api.routes.certification (Protocol 3)."""

from app.crypto.graph import determine_neighbors

from tests.fixtures import (
    build_small_poll_payload,
    complete_certification_for_all,
    register_n_nodes,
)


def _setup_poll_in_certification(client, responder_keypairs, app_storage, n=4, p=0.5):
    payload = build_small_poll_payload(edge_probability=p)
    sid = client.post("/api/poll/create", json=payload).json()["session_id"]
    node_ids = register_n_nodes(client, sid, n, responder_keypairs)
    app_storage.update_session_status(sid, "certification")
    return sid, node_ids


def test_neighbors_requires_x_node_id_header(client, responder_keypairs, app_storage):
    sid, _ = _setup_poll_in_certification(client, responder_keypairs, app_storage)
    resp = client.get(f"/api/poll/{sid}/neighbors")
    assert resp.status_code == 400
    assert "x-node-id" in resp.json()["detail"].lower()


def test_neighbors_unregistered_node_403(client, responder_keypairs, app_storage):
    sid, _ = _setup_poll_in_certification(client, responder_keypairs, app_storage)
    resp = client.get(f"/api/poll/{sid}/neighbors", headers={"X-Node-ID": "ghost"})
    assert resp.status_code == 403


def test_neighbors_returns_deterministic_set(client, responder_keypairs, app_storage):
    sid, node_ids = _setup_poll_in_certification(
        client, responder_keypairs, app_storage, n=4, p=0.5
    )
    me = node_ids[0]
    expected = sorted(determine_neighbors(me, node_ids, 0.5))

    resp = client.get(f"/api/poll/{sid}/neighbors", headers={"X-Node-ID": me})
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body["neighbors"]) == expected
    assert body["graph_parameters"]["edge_probability"] == 0.5


def test_neighbors_detailed_includes_pubkeys_and_status(client, responder_keypairs, app_storage):
    sid, node_ids = _setup_poll_in_certification(
        client, responder_keypairs, app_storage, n=4, p=1.0
    )
    me = node_ids[0]
    resp = client.get(f"/api/poll/{sid}/neighbors/detailed", headers={"X-Node-ID": me})
    assert resp.status_code == 200
    body = resp.json()
    # Every neighbor entry has node_id, public_key, and status fields
    for n in body["neighbors"]:
        assert {"node_id", "public_key", "status"} <= set(n.keys())
        assert n["status"] == "pending"  # no edges seeded yet


def test_certification_graph_unavailable_in_registration_phase(client, responder_keypairs):
    sid = client.post("/api/poll/create", json=build_small_poll_payload()).json()["session_id"]
    register_n_nodes(client, sid, 2, responder_keypairs)
    resp = client.get(f"/api/poll/{sid}/certification/graph")
    assert resp.status_code == 400


def test_neighbors_wrong_phase_400(client, responder_keypairs):
    """Calling /neighbors during registration phase is rejected."""
    sid = client.post("/api/poll/create", json=build_small_poll_payload()).json()["session_id"]
    node_ids = register_n_nodes(client, sid, 1, responder_keypairs)
    resp = client.get(f"/api/poll/{sid}/neighbors", headers={"X-Node-ID": node_ids[0]})
    assert resp.status_code == 400


def test_neighbors_with_detailed_query_returns_pubkey_status(
    client, responder_keypairs, app_storage
):
    """?detailed=True branch returns the same shape as /neighbors/detailed."""
    sid, node_ids = _setup_poll_in_certification(
        client, responder_keypairs, app_storage, n=4, p=1.0
    )
    me = node_ids[0]
    resp = client.get(
        f"/api/poll/{sid}/neighbors?detailed=true",
        headers={"X-Node-ID": me},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "my_public_key" in body
    for n in body["neighbors"]:
        assert {"node_id", "public_key", "status"} <= set(n.keys())


def test_certification_graph_success_returns_edges(
    client, responder_keypairs, app_storage
):
    """After seeding edges, /certification/graph returns the deduped edge list."""
    sid, node_ids = _setup_poll_in_certification(
        client, responder_keypairs, app_storage, n=4, p=1.0
    )
    complete_certification_for_all(app_storage, sid, node_ids, edge_probability=1.0)

    resp = client.get(f"/api/poll/{sid}/certification/graph")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_nodes"] == 4
    # K4 has 6 unique undirected edges; the route dedupes by sorted endpoint pair
    assert body["total_edges"] == 6
    assert body["verified_edges"] == 6


def test_certification_status_returns_completion_metrics(client, responder_keypairs, app_storage):
    sid, node_ids = _setup_poll_in_certification(
        client, responder_keypairs, app_storage, n=4, p=1.0
    )
    me = node_ids[0]
    resp = client.get(
        f"/api/poll/{sid}/certification/status",
        headers={"X-Node-ID": me},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_id"] == me
    assert body["total_neighbors"] == 3  # K4: every other node
    assert body["verified_edges"] == 0
