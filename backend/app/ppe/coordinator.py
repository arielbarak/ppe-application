"""
PPE Coordinator: state machine for the symmetric PPE protocol (Protocol 3).

Two matched peers exchange challenges, commit solutions, reveal, and swap
signatures. States: initiated -> committed -> solved -> verified | failed.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PPESession:
    """Tracks a single symmetric PPE handshake between two nodes."""
    id: str
    initiator: str
    responder: str

    challenge_i_to_j: str   # initiator -> responder
    challenge_j_to_i: str   # responder -> initiator

    commitment_i: Optional[str] = None
    commitment_j: Optional[str] = None

    solution_i: Optional[str] = None
    solution_j: Optional[str] = None

    signature_i: Optional[str] = None
    signature_j: Optional[str] = None

    status: str = "initiated"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    edge_label: Optional[str] = None


class PPECoordinator:
    """Manages PPE sessions for Protocol 3 certification graph construction."""

    def __init__(self):
        self.sessions: Dict[str, PPESession] = {}

    def create_session_id(self, node_a: str, node_b: str) -> str:
        """Deterministic session ID so only one session exists per node pair."""
        nodes = sorted([node_a, node_b])
        session_string = f"{nodes[0]}:{nodes[1]}"
        session_hash = hashlib.sha256(session_string.encode()).hexdigest()[:16]
        return f"ppe-{session_hash}"

    def initiate_ppe(
        self,
        initiator: str,
        responder: str,
        captcha_generator
    ) -> PPESession:
        """Start a symmetric PPE session, reusing or replacing stale ones."""
        session_id = self.create_session_id(initiator, responder)

        if session_id in self.sessions:
            existing = self.sessions[session_id]
            if existing.status in ["failed", "verified"]:
                logger.info(f"PPE session {session_id} was {existing.status}, creating new session")
                del self.sessions[session_id]
            else:
                age = (datetime.now() - existing.created_at).total_seconds()
                if age > 120:  # stale after 2 min in non-terminal state
                    logger.info(f"PPE session {session_id} is stale ({age:.0f}s old, status: {existing.status}), creating new session")
                    del self.sessions[session_id]
                else:
                    logger.warning(f"PPE session {session_id} already exists (status: {existing.status})")
                    return existing

        challenge_1 = captcha_generator.generate()
        challenge_2 = captcha_generator.generate()
        edge_label = f"{min(initiator, responder)}-{max(initiator, responder)}"

        session = PPESession(
            id=session_id,
            initiator=initiator,
            responder=responder,
            challenge_i_to_j=challenge_1['question'],
            challenge_j_to_i=challenge_2['question'],
            edge_label=edge_label
        )

        self.sessions[session_id] = session
        logger.info(f"PPE session {session_id} initiated: {initiator} <-> {responder}")
        return session

    def submit_commitment(self, session_id: str, node_id: str, commitment: str) -> bool:
        """Record a commit-reveal commitment hash."""
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"PPE session {session_id} not found")
            return False

        if session.status != "initiated":
            logger.warning(f"PPE session {session_id} not in initiated state (status: {session.status})")
            return False

        if node_id == session.initiator:
            session.commitment_i = commitment
            logger.debug(f"Initiator commitment recorded for session {session_id}")
        elif node_id == session.responder:
            session.commitment_j = commitment
            logger.debug(f"Responder commitment recorded for session {session_id}")
        else:
            logger.warning(f"Node {node_id} not part of session {session_id}")
            return False

        if session.commitment_i and session.commitment_j:
            session.status = "committed"
            session.updated_at = datetime.now()
            logger.info(f"PPE session {session_id} transitioned to committed")

        return True

    def submit_solution(self, session_id: str, node_id: str, solution: str, signature: str) -> bool:
        """Record a node's solution and edge signature."""
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"PPE session {session_id} not found")
            return False

        if session.status != "committed":
            logger.warning(f"PPE session {session_id} not in committed state (status: {session.status})")
            return False

        if node_id == session.initiator:
            session.solution_i = solution
            session.signature_i = signature
            logger.debug(f"Initiator solution recorded for session {session_id}")
        elif node_id == session.responder:
            session.solution_j = solution
            session.signature_j = signature
            logger.debug(f"Responder solution recorded for session {session_id}")
        else:
            logger.warning(f"Node {node_id} not part of session {session_id}")
            return False

        if session.solution_i and session.solution_j:
            session.status = "solved"
            session.updated_at = datetime.now()
            logger.info(f"PPE session {session_id} transitioned to solved")

        return True

    def verify_and_finalize(self, session_id: str, captcha_validator) -> Optional[dict]:
        """Verify both solutions and transition to verified or failed."""
        session = self.sessions.get(session_id)
        if not session:
            logger.warning(f"PPE session {session_id} not found")
            return None

        if session.status != "solved":
            logger.warning(f"PPE session {session_id} not in solved state (status: {session.status})")
            return None

        # TODO: verify hash(solution) == commitment in production
        i_correct = captcha_validator.validate(
            session.challenge_j_to_i,
            session.solution_i
        )
        j_correct = captcha_validator.validate(
            session.challenge_i_to_j,
            session.solution_j
        )

        if i_correct and j_correct:
            session.status = "verified"
            session.updated_at = datetime.now()

            logger.info(
                f"PPE session {session_id} verified successfully: "
                f"{session.initiator} <-> {session.responder}"
            )

            return {
                "success": True,
                "session_id": session_id,
                "initiator": session.initiator,
                "responder": session.responder,
                "signature_for_initiator": session.signature_j,
                "signature_for_responder": session.signature_i,
                "edge_label": session.edge_label
            }

        session.status = "failed"
        session.updated_at = datetime.now()

        logger.warning(
            f"PPE session {session_id} failed: "
            f"initiator_correct={i_correct}, responder_correct={j_correct}"
        )

        return {
            "success": False,
            "session_id": session_id,
            "initiator": session.initiator,
            "responder": session.responder,
            "initiator_correct": i_correct,
            "responder_correct": j_correct
        }

    def get_session(self, session_id: str) -> Optional[PPESession]:
        """Get a PPE session by ID"""
        return self.sessions.get(session_id)

    def get_node_sessions(self, node_id: str) -> list:
        """Get all PPE sessions involving a node"""
        return [
            session for session in self.sessions.values()
            if node_id in (session.initiator, session.responder)
        ]

    def cleanup_expired_sessions(self, max_age_seconds: int = 600):
        """Evict terminal sessions older than max_age_seconds."""
        now = datetime.now()
        expired = []

        for session_id, session in self.sessions.items():
            age = (now - session.created_at).total_seconds()
            if age > max_age_seconds and session.status in ["verified", "failed"]:
                expired.append(session_id)

        for session_id in expired:
            del self.sessions[session_id]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired PPE sessions")

    def get_statistics(self) -> dict:
        """Get coordinator statistics"""
        stats = {
            "total_sessions": len(self.sessions),
            "by_status": {}
        }

        for session in self.sessions.values():
            status = session.status
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        return stats
