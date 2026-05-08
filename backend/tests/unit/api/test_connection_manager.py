"""Direct unit tests for app.api.websocket.ConnectionManager."""

import pytest

from app.api.websocket import ConnectionManager


def test_get_connection_count_empty():
    mgr = ConnectionManager()
    assert mgr.get_connection_count("sid-1") == 0


def test_get_connected_nodes_empty():
    mgr = ConnectionManager()
    assert mgr.get_connected_nodes("sid-1") == []


def test_disconnect_unknown_session_is_noop():
    mgr = ConnectionManager()
    mgr.disconnect("nonexistent", "node-a")
    assert mgr.get_connection_count("nonexistent") == 0


async def test_send_to_node_unknown_session_logs_and_returns():
    """Sending to an unknown session must not raise."""
    mgr = ConnectionManager()
    await mgr.send_to_node("sid-1", "node-a", {"type": "ping", "data": {}})


async def test_broadcast_to_empty_session_logs_and_returns():
    mgr = ConnectionManager()
    await mgr.broadcast_to_session("sid-1", {"type": "x", "data": {}})


async def test_notify_status_change_with_no_connections():
    """No-op when there are no active connections in the session."""
    mgr = ConnectionManager()
    await mgr.notify_status_change("sid-1", "voting")


async def test_notify_registration_update_with_no_connections():
    mgr = ConnectionManager()
    await mgr.notify_registration_update("sid-1", total_registered=2)


async def test_notify_results_published_with_no_connections():
    mgr = ConnectionManager()
    await mgr.notify_results_published("sid-1", "/api/poll/sid-1/results")


async def test_notify_certification_update_with_no_connections():
    mgr = ConnectionManager()
    await mgr.notify_certification_update(
        session_id="sid-1",
        from_node="A",
        to_node="B",
        verified=True,
        total_edges=1,
        verified_edges=1,
    )


async def test_notify_ppe_complete_with_no_connections():
    mgr = ConnectionManager()
    await mgr.notify_ppe_complete(
        session_id="sid-1",
        node_id="A",
        ppe_session_id="ppe-1",
        success=True,
        signature="sig",
        edge_label="A-B",
    )
