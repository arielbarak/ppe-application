"""Tests for app.services.p2p_manager.P2PManager (async)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.p2p_manager import P2PManager


@pytest.fixture
def mock_manager(monkeypatch):
    mgr = AsyncMock()
    monkeypatch.setattr("app.services.p2p_manager.manager", mgr)
    return mgr


@pytest.fixture
def mock_storage(monkeypatch):
    s = MagicMock()
    s.get_certification_graph.return_value = {"edges": []}
    monkeypatch.setattr("app.services.p2p_manager.storage", s)
    return s


# ping / unknown


async def test_handle_ping_returns_pong():
    p2p = P2PManager()
    reply = await p2p.handle_message("ping", "sid", "node", {})
    assert reply == {"type": "pong", "data": {}}


async def test_handle_unknown_message_type_returns_none(caplog):
    p2p = P2PManager()
    reply = await p2p.handle_message("totally.unknown", "sid", "node", {})
    assert reply is None


# ppe.relay


async def test_handle_relay_forwards_to_target_node(mock_manager):
    p2p = P2PManager()
    await p2p.handle_message(
        "ppe.relay", "sid", "A",
        {"target_node": "B", "payload": {"x": 1}},
    )

    mock_manager.send_to_node.assert_awaited_once_with(
        "sid", "B",
        {"type": "ppe.message", "data": {"from_node": "A", "payload": {"x": 1}}},
    )


async def test_handle_relay_invalid_payload_no_send(mock_manager):
    """Missing target_node or payload -> no send."""
    p2p = P2PManager()
    await p2p.handle_message("ppe.relay", "sid", "A", {"target_node": None, "payload": None})
    mock_manager.send_to_node.assert_not_awaited()


# ppe.initiate


async def test_handle_initiate_creates_session_state_and_sends(mock_manager):
    p2p = P2PManager()
    await p2p.handle_message(
        "ppe.initiate", "sid", "alice",
        {"target_node": "bob"},
    )

    # Session state recorded for the deterministic ppe-session id
    assert any(
        state["initiator"] == "alice" and state["responder"] == "bob"
        for state in p2p.session_states.values()
    )
    # Both peers were notified (one ppe.request, one ppe.initiated)
    assert mock_manager.send_to_node.await_count == 2


async def test_handle_initiate_missing_target_no_send(mock_manager):
    p2p = P2PManager()
    await p2p.handle_message("ppe.initiate", "sid", "alice", {})
    mock_manager.send_to_node.assert_not_awaited()


# ppe.complete


async def test_handle_complete_records_edge_in_storage(mock_manager, mock_storage):
    p2p = P2PManager()
    await p2p.handle_message(
        "ppe.complete", "sid", "A",
        {
            "ppe_session_id": "ppe-1",
            "success": True,
            "peer_node": "B",
            "signature": "sig-ab",
        },
    )

    mock_storage.add_certification_edge.assert_called_once_with(
        session_id="sid",
        from_node="A",
        to_node="B",
        verified=True,
        signature="sig-ab",
    )
    mock_manager.notify_certification_update.assert_awaited_once()


async def test_handle_complete_invalid_payload_no_storage_call(mock_manager, mock_storage):
    p2p = P2PManager()
    await p2p.handle_message(
        "ppe.complete", "sid", "A",
        {"ppe_session_id": None, "peer_node": None},
    )
    mock_storage.add_certification_edge.assert_not_called()


async def test_handle_complete_updates_session_state_status(mock_manager, mock_storage):
    p2p = P2PManager()
    p2p.session_states["ppe-1"] = {
        "initiator": "A", "responder": "B", "status": "initiated", "poll_session_id": "sid",
    }
    await p2p.handle_message(
        "ppe.complete", "sid", "A",
        {"ppe_session_id": "ppe-1", "success": False, "peer_node": "B"},
    )

    assert p2p.session_states["ppe-1"]["status"] == "failed"
