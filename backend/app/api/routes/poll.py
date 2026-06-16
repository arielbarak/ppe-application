"""Protocol 1: Poll creation and status management."""

import logging
import math
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Body, Query

from app.models import CreatePollRequest, CreatePollResponse, PollInfoResponse, PollQuestion
from app.storage import storage
from app.api.websocket import manager
from app.crypto import (
    generate_server_keypair,
    export_public_key,
    compute_security_params,
    recommend_params_for_poll,
    validate_params,
    determine_neighbors,
)
from .helpers import get_session_or_404

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/create", response_model=CreatePollResponse)
async def create_poll(request: CreatePollRequest):
    """Create a new poll session with questions and protocol parameters."""
    for question in request.questions:
        options_lower = [opt.lower().strip() for opt in question.options]
        if len(options_lower) != len(set(options_lower)):
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate options found in question '{question.text}'. Each option must be unique."
            )

    try:
        session_id = str(uuid.uuid4())
        _, public_key = generate_server_keypair()
        public_key_b64 = export_public_key(public_key)

        storage.create_session(
            session_id=session_id,
            public_key=public_key_b64,
            questions=[q.model_dump() for q in request.questions],
            edge_probability=request.edge_probability,
            effort_threshold=request.effort_threshold,
            validity_threshold=request.validity_threshold,
            ppe_type=request.ppe_type
        )

        logger.info(f"Created poll session {session_id} with {len(request.questions)} questions, ppe_type={request.ppe_type}")

        return CreatePollResponse(
            session_id=session_id,
            public_key=public_key_b64,
            questions=request.questions,
            parameters={
                "edge_probability": request.edge_probability,
                "effort_threshold": request.effort_threshold,
                "validity_threshold": request.validity_threshold,
                "ppe_type": request.ppe_type
            }
        )

    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/params/recommend")
async def get_recommended_params(
    expected_responders: int = Query(..., ge=2, description="Expected number of participants"),
    security_level: Literal["low", "medium", "high"] = Query(
        "medium",
        description="Security level: low (κ=40), medium (κ=80), high (κ=128)"
    ),
):
    """
    Get recommended security parameters for a poll based on expected size.

    This implements Theorem 4.4 from the PPE paper, computing:
    - edge_probability (p): determines graph density
    - effort_threshold (η_E): max failure rate before node exclusion
    - validity_threshold (η_V): max exclusion rate before poll is invalid
    - adversary_advantage (C*): the multiplicative advantage from Theorem 4.4

    C* is a worst-case bound and is typically much larger than 1; a higher
    security level raises the degree to drive it down (low = minimum viable
    degree, medium targets C* ≤ 20, high targets C* ≤ 8).
    """
    try:
        params = recommend_params_for_poll(expected_responders, security_level)

        c_star = params.adversary_advantage
        c_star_msg = (
            "C* is unbounded: the chosen degree is below the Theorem 4.4 "
            "soundness minimum for this poll size"
            if math.isinf(c_star)
            else f"C*={c_star:.2f}: the adversary has no more influence than an "
                 f"honest user able to invest {c_star:.2f}x the effort"
        )

        return {
            "recommended": params.to_dict(),
            "security_level": security_level,
            "explanation": {
                "kappa": f"Security parameter κ={params.kappa} provides {2**params.kappa:.0e} adversary failure probability",
                "expected_degree": f"Each node will run ~{params.expected_degree:.1f} PPEs on average",
                "edge_probability": f"p={params.edge_probability:.4f} yields connected graph with high probability",
                "effort_threshold": f"Nodes failing >{params.effort_threshold*100:.1f}% of PPEs are excluded",
                "validity_threshold": f"Poll invalid if >{params.validity_threshold*100:.2f}% of nodes excluded",
                "adversary_advantage": c_star_msg,
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/params/validate")
async def validate_poll_params(
    expected_responders: int = Query(..., ge=2, description="Expected number of participants"),
    edge_probability: float = Query(..., gt=0, le=1, description="Edge probability p"),
    effort_threshold: float = Query(..., gt=0, lt=1, description="Effort threshold η_E"),
    validity_threshold: float = Query(..., gt=0, lt=1, description="Validity threshold η_V"),
    kappa: int = Query(80, ge=1, description="Security parameter κ for comparison"),
):
    """
    Validate user-provided parameters against Theorem 4.4 security requirements.

    Returns warnings if parameters may lead to security issues or poll failures.
    Also provides recommended parameters for comparison.
    """
    try:
        result = validate_params(
            m=expected_responders,
            edge_probability=edge_probability,
            effort_threshold=effort_threshold,
            validity_threshold=validity_threshold,
            kappa=kappa,
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/params/compute")
async def compute_params_for_kappa(
    kappa: int = Query(..., ge=1, le=256, description="Security parameter κ"),
    expected_responders: int = Query(..., ge=2, description="Expected number of participants"),
    honest_failure_rate: float = Query(0.0, ge=0, lt=1, description="Honest PPE failure rate σ"),
    max_adversary_advantage: float = Query(20.0, gt=1, description="Target upper bound on C*"),
):
    """
    Compute exact security parameters for a specific κ value.

    This is the raw Theorem 4.4 computation. Use /params/recommend for
    preset security levels.
    """
    try:
        params = compute_security_params(
            kappa=kappa,
            m=expected_responders,
            honest_failure_rate=honest_failure_rate,
            max_adversary_advantage=max_adversary_advantage,
        )

        c_star = params.adversary_advantage
        return {
            "params": params.to_dict(),
            "bounds": {
                "adversary_success_probability": f"≤ 2^(-{kappa}) ≈ {2**(-kappa):.2e}",
                "adversary_advantage_C_star": (
                    "unbounded" if math.isinf(c_star) else f"{c_star:.4f}"
                ),
                "soundness_precondition_ok": params.soundness_precondition_ok,
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{session_id}", response_model=PollInfoResponse)
async def get_poll(session_id: str):
    """Fetch poll configuration and current status."""
    session = get_session_or_404(session_id)

    return PollInfoResponse(
        session_id=session.session_id,
        status=session.status,
        questions=[PollQuestion(**q) for q in session.questions],
        public_key=session.public_key,
        parameters={
            "edge_probability": session.edge_probability,
            "effort_threshold": session.effort_threshold,
            "validity_threshold": session.validity_threshold,
            "ppe_type": session.ppe_type
        },
        registered_nodes_count=len(session.registered_nodes),
        created_at=session.created_at.isoformat()
    )


def check_certification_threshold(session_id: str) -> dict:
    """Check if enough nodes passed certification to advance to voting."""
    session = storage.get_session(session_id)
    if not session:
        return {
            "threshold_met": False,
            "certified_nodes": [],
            "total_nodes": 0,
            "message": "Session not found"
        }

    registered_nodes = storage.get_registered_nodes(session_id)
    all_node_ids = [node.node_id for node in registered_nodes]
    total_nodes = len(all_node_ids)

    if total_nodes == 0:
        return {
            "threshold_met": False,
            "certified_nodes": [],
            "total_nodes": 0,
            "message": "No registered nodes"
        }

    certified_nodes = []
    uncertified_nodes = []

    for node_id in all_node_ids:
        neighbors = determine_neighbors(
            node_id=node_id,
            all_node_ids=all_node_ids,
            probability=session.edge_probability
        )
        edges = storage.get_node_edges(session_id, node_id)
        verified_edges = [e for e in edges if e.verified]

        if len(neighbors) == 0 or len(verified_edges) >= len(neighbors):
            # Node with 0 neighbors is auto-certified (no PPE to complete)
            certified_nodes.append(node_id)
        else:
            uncertified_nodes.append(node_id)

    certification_rate = (len(certified_nodes) / total_nodes * 100) if total_nodes > 0 else 0

    # fall back to 50% if threshold not set
    required_threshold = session.effort_threshold * 100 if hasattr(session, 'effort_threshold') else 50

    threshold_met = certification_rate >= required_threshold

    return {
        "threshold_met": threshold_met,
        "certified_nodes": certified_nodes,
        "uncertified_nodes": uncertified_nodes,
        "total_nodes": total_nodes,
        "certification_rate": certification_rate,
        "required_threshold": required_threshold,
        "message": f"{len(certified_nodes)}/{total_nodes} nodes certified ({certification_rate:.1f}% >= {required_threshold}% required)"
    }


@router.post("/{session_id}/status")
async def update_poll_status(session_id: str, new_status: str = Body(..., embed=True)):
    """Advance the poll phase (pollster only). Blocks voting if certification threshold unmet."""
    get_session_or_404(session_id)

    valid_statuses = ["registration", "certification", "voting", "results", "closed", "cancelled"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    if new_status == "voting":
        cert_check = check_certification_threshold(session_id)
        if not cert_check["threshold_met"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot advance to voting: {cert_check['message']}. "
                       f"Only {len(cert_check['certified_nodes'])}/{cert_check['total_nodes']} nodes completed certification."
            )
        logger.info(f"Certification threshold met: {cert_check['message']}")

    success = storage.update_session_status(session_id, new_status)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update status")

    await manager.notify_status_change(session_id, new_status)

    logger.info(f"Poll {session_id} status updated to {new_status}")

    return {"success": True, "new_status": new_status}


@router.get("/{session_id}/certification/threshold")
async def get_certification_threshold_status(session_id: str):
    """Return certification threshold metrics."""
    get_session_or_404(session_id)
    return check_certification_threshold(session_id)


@router.get("/{session_id}/stats")
async def get_poll_stats(session_id: str):
    """Get poll statistics."""
    stats = storage.get_session_stats(session_id)

    if not stats:
        raise HTTPException(status_code=404, detail=f"Poll session {session_id} not found")

    return stats


@router.get("/{session_id}/node/{node_id}/certification")
async def check_node_certification(session_id: str, node_id: str):
    """Check if a specific node completed all its PPE challenges."""
    session = get_session_or_404(session_id)

    registered_nodes = storage.get_registered_nodes(session_id)
    all_node_ids = [node.node_id for node in registered_nodes]

    if node_id not in all_node_ids:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found in session")

    neighbors = determine_neighbors(
        node_id=node_id,
        all_node_ids=all_node_ids,
        probability=session.edge_probability
    )
    edges = storage.get_node_edges(session_id, node_id)
    verified_edges = [e for e in edges if e.verified]

    total_edges = len(neighbors)
    verified_count = len(verified_edges)
    is_certified = 0 < total_edges <= verified_count

    return {
        "is_certified": is_certified,
        "verified_edges": verified_count,
        "total_edges": total_edges,
        "message": f"Node {'is' if is_certified else 'is not'} certified ({verified_count}/{total_edges} edges verified)"
    }
