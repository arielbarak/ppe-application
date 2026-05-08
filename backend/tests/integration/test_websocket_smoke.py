"""WebSocket smoke tests using TestClient.websocket_connect."""

import time

import pytest

from app.api.websocket import manager


pytestmark = pytest.mark.websocket


def _wait_for(predicate, timeout=1.0, interval=0.01):
    """Poll until predicate returns True or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_connection_established_message(client):
    with client.websocket_connect("/ws/sid-1?node_id=A&role=responder") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connection.established"
        assert msg["data"]["node_id"] == "A"
        assert msg["data"]["role"] == "responder"


def test_ping_pong(client):
    with client.websocket_connect("/ws/sid-1?node_id=A&role=responder") as ws:
        ws.receive_json()  # connection.established
        ws.send_json({"type": "ping", "data": {}})
        pong = ws.receive_json()
        assert pong["type"] == "pong"


def test_relay_forwards_payload_to_target_node(client):
    with client.websocket_connect("/ws/sid-1?node_id=A&role=responder") as ws_a, \
            client.websocket_connect("/ws/sid-1?node_id=B&role=responder") as ws_b:
        ws_a.receive_json()
        ws_b.receive_json()

        ws_a.send_json({
            "type": "ppe.relay",
            "data": {"target_node": "B", "payload": {"hello": "world"}},
        })

        msg = ws_b.receive_json()
        assert msg["type"] == "ppe.message"
        assert msg["data"]["from_node"] == "A"
        assert msg["data"]["payload"] == {"hello": "world"}


def test_disconnect_cleans_up_manager(client):
    with client.websocket_connect("/ws/sid-1?node_id=A&role=responder") as ws:
        ws.receive_json()
        assert "A" in manager.get_connected_nodes("sid-1")

    # The server-side disconnect handler runs in the ASGI loop, so poll briefly
    cleaned = _wait_for(lambda: "A" not in manager.get_connected_nodes("sid-1"))
    assert cleaned is True
