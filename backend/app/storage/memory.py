"""Thread-safe in-memory storage for PPE poll sessions."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class CaptchaChallenge:
    token: str
    question: str
    solution: str
    expires_at: datetime
    used: bool = False


@dataclass
class RegisteredNode:
    node_id: str
    pseudonym: str  # public key
    registration_time: datetime
    position: int


@dataclass
class CertificationEdge:
    from_node: str
    to_node: str
    verified: bool
    signature: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class VoteRecord:
    node_id: str
    vote: Dict[str, Any]
    signatures: List[Dict[str, str]]
    self_signature: str
    timestamp: datetime


@dataclass
class PollSession:
    session_id: str
    public_key: str  # pollster's VK
    questions: List[Dict[str, Any]]
    edge_probability: float  # p parameter
    effort_threshold: float  # η_E parameter
    validity_threshold: float = 0.025      # η_V
    ppe_type: str = "math_captcha"
    status: str = "registration"            # registration -> certification -> voting -> results -> closed
    created_at: datetime = field(default_factory=datetime.now)

    registered_nodes: List[RegisteredNode] = field(default_factory=list)
    captcha_challenges: Dict[str, CaptchaChallenge] = field(default_factory=dict)
    certification_graph: Dict[str, List[CertificationEdge]] = field(default_factory=dict)
    votes: Dict[str, VoteRecord] = field(default_factory=dict)
    published_results: Optional[Dict[str, Any]] = None
    published_at: Optional[datetime] = None


class InMemoryStorage:
    """Central data store for all poll sessions. All protocol operations go through here."""

    def __init__(self):
        self._sessions: Dict[str, PollSession] = {}
        self._lock = threading.RLock()

    @property
    def sessions(self) -> Dict[str, 'PollSession']:
        """Expose sessions dict for testing. Use with caution."""
        return self._sessions

    def create_session(
        self,
        session_id: str,
        public_key: str,
        questions: List[Dict[str, Any]],
        edge_probability: float,
        effort_threshold: float,
        validity_threshold: float = 0.025,
        ppe_type: str = "math_captcha"
    ) -> PollSession:
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"Session {session_id} already exists")
            session = PollSession(
                session_id=session_id,
                public_key=public_key,
                questions=questions,
                edge_probability=edge_probability,
                effort_threshold=effort_threshold,
                validity_threshold=validity_threshold,
                ppe_type=ppe_type
            )
            self._sessions[session_id] = session
            logger.info(f"Created session {session_id}")
            return session

    def get_session(self, session_id: str) -> Optional[PollSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def update_session_status(self, session_id: str, new_status: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session.status = new_status
            logger.info(f"Session {session_id} status updated to {new_status}")
            return True

    def list_sessions(self) -> List[str]:
        with self._lock:
            return list(self._sessions.keys())

    # Registration (Protocol 2)

    def store_captcha_challenge(
        self,
        session_id: str,
        token: str,
        question: str,
        solution: str,
        expires_at: datetime
    ) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            challenge = CaptchaChallenge(
                token=token,
                question=question,
                solution=solution,
                expires_at=expires_at
            )
            session.captcha_challenges[token] = challenge
            return True

    def validate_and_consume_captcha(
        self,
        session_id: str,
        token: str,
        solution: str
    ) -> bool:
        """Validate CAPTCHA solution and mark the token as consumed."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                logger.warning(f"CAPTCHA validation failed: session {session_id} not found")
                return False

            challenge = session.captcha_challenges.get(token)
            if not challenge:
                logger.warning(f"CAPTCHA validation failed: token {token} not found in session {session_id}")
                return False

            if challenge.used:
                logger.warning(f"CAPTCHA validation failed: token {token} already used")
                return False

            if datetime.now() > challenge.expires_at:
                logger.warning(f"CAPTCHA validation failed: token {token} expired")
                return False

            # Normalize both solutions for comparison
            expected = challenge.solution.strip()
            provided = solution.strip() if solution else ""

            if expected != provided:
                logger.warning(
                    f"CAPTCHA validation failed: expected '{expected}', got '{provided}' "
                    f"for question '{challenge.question}'"
                )
                return False

            challenge.used = True
            logger.info(f"CAPTCHA validated successfully for session {session_id}")
            return True

    def add_registered_node(
        self,
        session_id: str,
        node_id: str,
        pseudonym: str
    ) -> Optional[int]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None

            if any(n.node_id == node_id for n in session.registered_nodes):
                logger.warning(f"Node {node_id} already registered in session {session_id}")
                return None

            position = len(session.registered_nodes)
            node = RegisteredNode(
                node_id=node_id,
                pseudonym=pseudonym,
                registration_time=datetime.now(),
                position=position
            )
            session.registered_nodes.append(node)
            logger.info(f"Node {node_id} registered in session {session_id} at position {position}")
            return position

    def get_registered_nodes(self, session_id: str) -> List[RegisteredNode]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            return session.registered_nodes.copy()

    # Certification Graph (Protocol 3)

    def add_certification_edge(
        self,
        session_id: str,
        from_node: str,
        to_node: str,
        verified: bool,
        signature: Optional[str] = None
    ) -> bool:
        """Add or update a directed edge in the certification graph."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            if from_node not in session.certification_graph:
                session.certification_graph[from_node] = []

            for edge in session.certification_graph[from_node]:
                if edge.to_node == to_node:
                    edge.verified = verified
                    edge.signature = signature
                    edge.timestamp = datetime.now()
                    logger.info(f"Updated edge {from_node} -> {to_node} in session {session_id}")
                    return True

            edge = CertificationEdge(
                from_node=from_node,
                to_node=to_node,
                verified=verified,
                signature=signature,
                timestamp=datetime.now()
            )
            session.certification_graph[from_node].append(edge)
            logger.info(f"Added edge {from_node} -> {to_node} in session {session_id}")
            return True

    def get_certification_graph(self, session_id: str) -> Dict[str, List[CertificationEdge]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return {}
            return {k: v.copy() for k, v in session.certification_graph.items()}

    def get_node_edges(self, session_id: str, node_id: str) -> List[CertificationEdge]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            return session.certification_graph.get(node_id, []).copy()

    # Voting (Protocol 4)

    def add_vote(
        self,
        session_id: str,
        node_id: str,
        vote: Dict[str, Any],
        signatures: List[Dict[str, str]],
        self_signature: str
    ) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            if node_id in session.votes:
                logger.warning(f"Node {node_id} already voted in session {session_id}")
                return False

            vote_record = VoteRecord(
                node_id=node_id,
                vote=vote,
                signatures=signatures,
                self_signature=self_signature,
                timestamp=datetime.now()
            )
            session.votes[node_id] = vote_record
            logger.info(f"Vote recorded for node {node_id} in session {session_id}")
            return True

    def get_votes(self, session_id: str) -> Dict[str, VoteRecord]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return {}
            return session.votes.copy()

    # Results (Protocol 5)

    def publish_results(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Assemble and freeze all session data for public verification."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None

            results = {
                'session_id': session_id,
                'public_key': session.public_key,
                'questions': session.questions,
                'parameters': {
                    'edge_probability': session.edge_probability,
                    'effort_threshold': session.effort_threshold,
                    'validity_threshold': session.validity_threshold,
                    'ppe_type': session.ppe_type
                },
                'responses': [
                    {
                        'node_id': vote.node_id,
                        'vote': vote.vote,
                        'signatures': vote.signatures,
                        'self_signature': vote.self_signature,
                        'timestamp': vote.timestamp.isoformat()
                    }
                    for vote in session.votes.values()
                ],
                'certification_graph': {
                    'nodes': [node.node_id for node in session.registered_nodes],
                    'edges': [
                        {
                            'from': edge.from_node,
                            'to': edge.to_node,
                            'verified': edge.verified,
                            'signature': edge.signature,
                            'timestamp': edge.timestamp.isoformat() if edge.timestamp else None
                        }
                        for edges in session.certification_graph.values()
                        for edge in edges
                    ]
                },
                'published_at': datetime.now().isoformat()
            }

            session.published_results = results
            session.published_at = datetime.now()
            session.status = "results"

            logger.info(f"Results published for session {session_id}")
            return results

    def get_published_results(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return session.published_results

    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None

            total_edges = sum(len(edges) for edges in session.certification_graph.values())
            verified_edges = sum(
                1 for edges in session.certification_graph.values()
                for edge in edges if edge.verified
            )

            return {
                'session_id': session_id,
                'status': session.status,
                'registered_nodes': len(session.registered_nodes),
                'total_edges': total_edges,
                'verified_edges': verified_edges,
                'votes_submitted': len(session.votes),
                'created_at': session.created_at.isoformat()
            }

    def clear(self):
        """Clear all sessions. Used for testing."""
        with self._lock:
            self._sessions.clear()


# Global storage instance
storage = InMemoryStorage()
