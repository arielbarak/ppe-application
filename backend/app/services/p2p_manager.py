"""P2P relay manager for blind PPE signaling."""

import logging
from typing import Optional

from app.api.websocket import manager
from app.ppe import MathCaptchaPPE, coordinator
from app.storage import storage

logger = logging.getLogger(__name__)


class P2PManager:
    """Handles P2P message routing for PPE certification phase."""

    def __init__(self):
        self.session_states: dict = {}

    async def handle_message(
        self,
        msg_type: str,
        session_id: str,
        node_id: str,
        data: dict
    ) -> Optional[dict]:
        """
        Route incoming WebSocket message to appropriate handler.
        Returns response dict for messages that need immediate reply, None otherwise.
        """
        if msg_type == "ping":
            return {"type": "pong", "data": {}}

        if msg_type == "ppe.relay":
            await self._handle_relay(session_id, node_id, data)

        elif msg_type == "ppe.initiate":
            await self._handle_initiate(session_id, node_id, data)

        elif msg_type == "ppe.complete":
            await self._handle_complete(session_id, node_id, data)

        elif msg_type == "certification.reveal":
            await self._handle_reveal(session_id, node_id, data)

        else:
            logger.warning(f"Unknown message type: {msg_type}")

        return None

    async def _handle_relay(self, session_id: str, from_node: str, data: dict):
        """Blind relay: forward opaque PPE payload to target peer."""
        target_node = data.get("target_node")
        payload = data.get("payload")

        if not target_node or not payload:
            logger.warning(f"Invalid relay message from {from_node}")
            return

        logger.debug(f"Relaying PPE message: {from_node} -> {target_node}")

        await manager.send_to_node(session_id, target_node, {
            "type": "ppe.message",
            "data": {
                "from_node": from_node,
                "payload": payload
            }
        })

    async def _handle_initiate(self, session_id: str, node_id: str, data: dict):
        """Track PPE session initiation without generating challenges."""
        target_node = data.get("target_node")

        if not target_node:
            logger.warning("No target_node provided")
            return

        logger.info(f"PPE initiation (blind): {node_id} -> {target_node}")

        nodes = sorted([node_id, target_node])
        ppe_session_id = f"ppe-{nodes[0][:8]}-{nodes[1][:8]}"

        self.session_states[ppe_session_id] = {
            "initiator": node_id,
            "responder": target_node,
            "status": "initiated",
            "poll_session_id": session_id
        }

        await manager.send_to_node(session_id, target_node, {
            "type": "ppe.request",
            "data": {
                "ppe_session_id": ppe_session_id,
                "from_node": node_id,
            }
        })

        await manager.send_to_node(session_id, node_id, {
            "type": "ppe.initiated",
            "data": {
                "ppe_session_id": ppe_session_id,
                "target_node": target_node,
                "status": "initiated"
            }
        })

    async def _handle_complete(self, session_id: str, node_id: str, data: dict):
        """Record PPE result as an edge in the certification graph."""
        ppe_session_id = data.get("ppe_session_id")
        success = data.get("success", False)
        peer_node = data.get("peer_node")
        sig = data.get("signature")

        if not ppe_session_id or not peer_node:
            logger.warning(f"Invalid PPE complete from {node_id}")
            return

        logger.info(f"PPE complete: {node_id} <-> {peer_node}, success={success}")

        storage.add_certification_edge(
            session_id=session_id,
            from_node=node_id,
            to_node=peer_node,
            verified=success,
            signature=sig
        )

        if ppe_session_id in self.session_states:
            self.session_states[ppe_session_id]["status"] = "verified" if success else "failed"

        cert_graph = storage.get_certification_graph(session_id)
        total_edges = len(cert_graph.get('edges', []))
        verified_edges = len([e for e in cert_graph.get('edges', []) if e.get('verified', False)])

        await manager.notify_certification_update(
            session_id=session_id,
            from_node=node_id,
            to_node=peer_node,
            verified=success,
            total_edges=total_edges,
            verified_edges=verified_edges
        )

    async def _handle_reveal(self, session_id: str, node_id: str, data: dict):
        """Legacy: verify solutions and finalize edge."""
        ppe_session_id = data.get("ppe_session_id")
        solution = data.get("solution")
        signature = data.get("signature")

        if not all([ppe_session_id, solution, signature]):
            return

        success = coordinator.submit_solution(ppe_session_id, node_id, solution, signature)

        if not success:
            return

        ppe_session = coordinator.get_session(ppe_session_id)
        if not ppe_session or ppe_session.status != "solved":
            return

        captcha_validator = MathCaptchaPPE()
        result = coordinator.verify_and_finalize(ppe_session_id, captcha_validator)

        if result and result["success"]:
            storage.add_certification_edge(
                session_id=session_id,
                from_node=ppe_session.initiator,
                to_node=ppe_session.responder,
                verified=True,
                signature=ppe_session.signature_i
            )
            storage.add_certification_edge(
                session_id=session_id,
                from_node=ppe_session.responder,
                to_node=ppe_session.initiator,
                verified=True,
                signature=ppe_session.signature_j
            )

            await manager.notify_ppe_complete(
                session_id, ppe_session.initiator, ppe_session_id,
                True, ppe_session.signature_j, ppe_session.edge_label
            )
            await manager.notify_ppe_complete(
                session_id, ppe_session.responder, ppe_session_id,
                True, ppe_session.signature_i, ppe_session.edge_label
            )
        else:
            if result:
                storage.add_certification_edge(
                    session_id=session_id,
                    from_node=ppe_session.initiator,
                    to_node=ppe_session.responder,
                    verified=False
                )
                storage.add_certification_edge(
                    session_id=session_id,
                    from_node=ppe_session.responder,
                    to_node=ppe_session.initiator,
                    verified=False
                )

            await manager.notify_ppe_complete(
                session_id, ppe_session.initiator, ppe_session_id, False
            )
            await manager.notify_ppe_complete(
                session_id, ppe_session.responder, ppe_session_id, False
            )
