"""WebSocket connection manager for real-time PPE signaling."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Per-session WebSocket hub. Routes messages between nodes for PPE coordination."""

    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}  # session -> {node: ws}

    async def connect(self, websocket: WebSocket, session_id: str, node_id: str, role: str):
        await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = {}

        self.active_connections[session_id][node_id] = websocket

        logger.info(f"WebSocket connected: session={session_id}, node={node_id}, role={role}")

        await self.send_to_node(session_id, node_id, {
            "type": "connection.established",
            "data": {
                "session_id": session_id,
                "node_id": node_id,
                "role": role,
                "message": "Connected to PPE polling system"
            }
        })

    def disconnect(self, session_id: str, node_id: str, websocket: Optional[WebSocket] = None):
        if session_id not in self.active_connections:
            return

        current = self.active_connections[session_id].get(node_id)
        if current is None:
            return

        # If a specific websocket is given, only remove if it's still the registered one.
        # This prevents a reconnect's close event from evicting the new connection.
        if websocket is not None and current is not websocket:
            logger.info(f"Stale disconnect ignored for {node_id} (new connection already registered)")
            return

        del self.active_connections[session_id][node_id]
        logger.info(f"WebSocket disconnected: session={session_id}, node={node_id}")

        if not self.active_connections[session_id]:
            del self.active_connections[session_id]
            logger.info(f"Session {session_id} removed (no active connections)")

    async def send_to_node(self, session_id: str, node_id: str, message: dict):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id].get(node_id)
            if websocket is not None:
                try:
                    await websocket.send_json(message)
                    logger.info(f"Sent to {node_id}: {message['type']}")
                except Exception as e:
                    logger.error(f"Error sending to {node_id}: {e}")
                    self.disconnect(session_id, node_id, websocket)
            else:
                logger.warning(f"Node {node_id} not found in session {session_id}. Connected nodes: {list(self.active_connections[session_id].keys())}")
        else:
            logger.warning(f"Session {session_id} not found in active connections")

    async def broadcast_to_session(self, session_id: str, message: dict, exclude: Optional[List[str]] = None):
        if session_id not in self.active_connections:
            logger.warning(f"No active connections for session {session_id}")
            return

        exclude = exclude or []
        sent_count = 0

        for node_id, websocket in list(self.active_connections[session_id].items()):
            if node_id not in exclude:
                try:
                    await websocket.send_json(message)
                    sent_count += 1
                    logger.info(f"Broadcast to {node_id}: {message['type']}")
                except Exception as e:
                    logger.error(f"Error broadcasting to {node_id}: {e}")
                    self.disconnect(session_id, node_id)

        logger.info(f"Broadcast complete: sent to {sent_count} nodes")

    def get_connected_nodes(self, session_id: str) -> List[str]:
        if session_id in self.active_connections:
            return list(self.active_connections[session_id].keys())
        return []

    def get_connection_count(self, session_id: str) -> int:
        if session_id in self.active_connections:
            return len(self.active_connections[session_id])
        return 0

    async def notify_ppe_complete(
        self, session_id: str, node_id: str, ppe_session_id: str,
        success: bool, signature: Optional[str] = None, edge_label: Optional[str] = None
    ):
        await self.send_to_node(session_id, node_id, {
            "type": "certification.complete",
            "data": {
                "ppe_session_id": ppe_session_id,
                "success": success,
                "signature": signature,
                "edge_label": edge_label
            }
        })

    async def notify_status_change(self, session_id: str, new_status: str):
        await self.broadcast_to_session(session_id, {
            "type": "poll.status_change",
            "data": {
                "status": new_status,
                "timestamp": datetime.now().isoformat()
            }
        })

    async def notify_registration_update(self, session_id: str, total_registered: int):
        await self.broadcast_to_session(session_id, {
            "type": "registration.update",
            "data": {
                "total_registered": total_registered
            }
        })

    async def notify_results_published(self, session_id: str, results_url: str):
        await self.broadcast_to_session(session_id, {
            "type": "results.published",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "url": results_url
            }
        })

    async def notify_certification_update(
        self, session_id: str, from_node: str, to_node: str,
        verified: bool, total_edges: int, verified_edges: int
    ):
        connected = self.get_connected_nodes(session_id)
        logger.info(f"Broadcasting certification update to {len(connected)} nodes: {connected}")

        await self.broadcast_to_session(session_id, {
            "type": "certification.edge_added",
            "data": {
                "from_node": from_node,
                "to_node": to_node,
                "verified": verified,
                "total_edges": total_edges,
                "verified_edges": verified_edges,
                "timestamp": datetime.now().isoformat()
            }
        })
        logger.info(f"Certification update sent: {from_node} -> {to_node}, verified={verified}")


manager = ConnectionManager()
