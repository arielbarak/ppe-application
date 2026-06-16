"""Protocol 5: Publish poll results for public verification."""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Header, Body

from app.models import (
    PublishResultsResponse,
    ResultsResponse,
)
from app.storage import storage
from app.api.websocket import manager
from app.crypto.verification import verify_global, verify_local
from .helpers import get_session_or_404, require_status, get_session_with_published_results

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/{session_id}/publish", response_model=PublishResultsResponse)
async def publish_results(
    session_id: str,
    x_pollster_key: Optional[str] = Header(None, alias="X-Pollster-Key")
):
    """Freeze and publish all session data (votes, graph, signatures) as a public bulletin."""
    session = get_session_or_404(session_id)
    require_status(session, "voting", "publish results")

    # App-level access guard, NOT a security property. The session public key
    # is published in the bulletin, so anyone can supply it; this only catches
    # accidental cross-session calls, not a malicious caller. Real pollster
    # authentication would require a signature over the request under the
    # pollster's private key. The header is optional for legacy clients.
    if x_pollster_key is None:
        logger.warning("Publishing without pollster key check (header omitted)")
    elif x_pollster_key != session.public_key:
        logger.warning(
            f"Pollster key mismatch on publish for session {session_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="X-Pollster-Key does not match session public key",
        )

    published_results = storage.publish_results(session_id)

    if not published_results:
        raise HTTPException(
            status_code=500,
            detail="Failed to publish results"
        )

    results_url = f"/api/poll/{session_id}/results"

    await manager.notify_results_published(session_id, results_url)

    logger.info(f"Results published for session {session_id}")

    return PublishResultsResponse(
        published=True,
        results_url=results_url
    )


@router.get("/{session_id}/results", response_model=ResultsResponse)
async def get_results(session_id: str):
    """Fetch published results for independent verification (O(m) full verification)."""
    _, published_results = get_session_with_published_results(session_id)
    return ResultsResponse(**published_results)


@router.post("/{session_id}/verify")
async def verify_poll(
    session_id: str,
    mode: Literal["global", "local"] = Body(..., embed=True),
    node_id: Optional[str] = Body(None, embed=True),
):
    """
    Run verification on published poll results.

    Modes:
    - global: Full independent verification (Protocol 6). Reconstructs the ideal
              graph and validates all edges, exclusions, and vote tallies.
    - local: Single node verification. Checks if a specific node's vote and
             edges are correctly included.
    """
    session, published_results = get_session_with_published_results(session_id)

    if mode == "global":
        eta_e = session.effort_threshold
        eta_v = session.validity_threshold

        result = verify_global(published_results, eta_e=eta_e, eta_v=eta_v)

        logger.info(
            f"Global verification for {session_id}: {result['verification']}"
        )

        return result

    elif mode == "local":
        if not node_id:
            raise HTTPException(
                status_code=400,
                detail="node_id is required for local verification"
            )

        success, message, details = verify_local(node_id, published_results)

        logger.info(
            f"Local verification for {node_id} in {session_id}: "
            f"{'PASS' if success else 'FAIL'}"
        )

        return {
            'verification': 'ACCEPT' if success else 'REJECT',
            'node_id': node_id,
            'message': message,
            'details': details,
        }

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verification mode: {mode}. Use 'global' or 'local'."
        )
