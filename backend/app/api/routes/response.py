"""Protocol 4: Vote submission with peer signatures."""

import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.models import VoteRequest, VoteResponse
from app.storage import storage
from .helpers import get_session_or_404, require_status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{session_id}/vote", response_model=VoteResponse)
async def submit_vote(session_id: str, request: VoteRequest):
    """Accept a vote with collected PPE signatures from certified peers."""
    session = get_session_or_404(session_id)
    require_status(session, "voting", "submit vote")

    registered_nodes = storage.get_registered_nodes(session_id)
    node_ids = [node.node_id for node in registered_nodes]

    if request.node_id not in node_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Node {request.node_id} not registered in this poll"
        )

    question_ids = {q['id'] for q in session.questions}
    vote_question_ids = set(request.vote.keys())

    if not vote_question_ids.issubset(question_ids):
        raise HTTPException(
            status_code=400,
            detail="Vote contains invalid question IDs"
        )

    success = storage.add_vote(
        session_id=session_id,
        node_id=request.node_id,
        vote=request.vote,
        signatures=[sig.model_dump() for sig in request.signatures],
        self_signature=request.signature
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Vote already submitted or submission failed"
        )

    vote_id = str(uuid.uuid4())
    logger.info(
        f"Vote submitted for node {request.node_id} in session {session_id} "
        f"with {len(request.signatures)} signatures"
    )

    return VoteResponse(
        accepted=True,
        vote_id=vote_id
    )


@router.get("/{session_id}/votes/count")
async def get_vote_count(session_id: str):
    """Get count of submitted votes (for monitoring)."""
    get_session_or_404(session_id)

    votes = storage.get_votes(session_id)

    return {
        "session_id": session_id,
        "total_votes": len(votes),
        "total_registered": len(storage.get_registered_nodes(session_id))
    }
