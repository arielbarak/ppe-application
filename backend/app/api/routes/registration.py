"""Protocol 2: CAPTCHA-gated node registration."""

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.models import CaptchaResponse, RegisterRequest, RegisterResponse
from app.storage import storage
from app.crypto import compute_node_id
from app.api.websocket import manager
from app.ppe import get_ppe_provider
from app.ppe.base import derive_difficulty_from_eta_e
from .helpers import get_session_or_404, require_status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{session_id}/captcha", response_model=CaptchaResponse)
async def get_captcha(session_id: str):
    """Issue a CAPTCHA challenge for registration."""
    session = get_session_or_404(session_id)
    require_status(session, "registration", "get CAPTCHA")

    difficulty = derive_difficulty_from_eta_e(session.effort_threshold)
    captcha_generator = get_ppe_provider(session.ppe_type, difficulty=difficulty)
    captcha_data = captcha_generator.generate()
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(minutes=5)

    storage.store_captcha_challenge(
        session_id=session_id,
        token=token,
        question=captcha_data['question'],
        solution=captcha_data['solution'],
        expires_at=expires_at
    )

    logger.debug(f"Generated CAPTCHA for session {session_id}: {captcha_data['question']}")

    return CaptchaResponse(
        token=token,
        challenge=captcha_data['question'],
        expires_at=expires_at.isoformat()
    )


@router.post("/{session_id}/register", response_model=RegisterResponse)
async def register_node(session_id: str, request: RegisterRequest):
    """Validate CAPTCHA and register the node."""
    session = get_session_or_404(session_id)
    require_status(session, "registration", "register node")

    is_valid = storage.validate_and_consume_captcha(
        session_id=session_id,
        token=request.captcha_token,
        solution=request.captcha_solution
    )

    if not is_valid:
        logger.warning(f"Invalid CAPTCHA solution for session {session_id}")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired CAPTCHA solution"
        )

    node_id = compute_node_id(request.pseudonym)

    position = storage.add_registered_node(
        session_id=session_id,
        node_id=node_id,
        pseudonym=request.pseudonym
    )

    if position is None:
        raise HTTPException(
            status_code=400,
            detail="Node already registered or registration failed"
        )

    logger.info(f"Node {node_id} registered in session {session_id} at position {position}")

    await manager.notify_registration_update(
        session_id=session_id,
        total_registered=len(storage.get_registered_nodes(session_id))
    )

    return RegisterResponse(
        registered=True,
        node_id=node_id,
        registration_position=position
    )


@router.get("/{session_id}/registered")
async def get_registered_nodes(session_id: str):
    """List registered nodes (for pollster monitoring)."""
    get_session_or_404(session_id)

    nodes = storage.get_registered_nodes(session_id)

    return {
        "session_id": session_id,
        "total_registered": len(nodes),
        "nodes": [
            {
                "node_id": node.node_id,
                "position": node.position,
                "registration_time": node.registration_time.isoformat()
            }
            for node in nodes
        ]
    }
