"""Common helper functions for API routes."""

from fastapi import HTTPException
from app.storage import storage


def get_session_or_404(session_id: str):
    """Get a session by ID or raise 404 if not found."""
    session = storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Poll session {session_id} not found")
    return session


def require_status(session, required_status: str, action: str = "perform this action"):
    """Raise 400 if session is not in the required status."""
    if session.status != required_status:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot {action} (current status: {session.status})"
        )


def get_published_results_or_404(session_id: str):
    """Get published results or raise 404 if not found."""
    published_results = storage.get_published_results(session_id)
    if not published_results:
        raise HTTPException(
            status_code=404,
            detail="Published results not found"
        )
    return published_results


def get_session_with_published_results(session_id: str):
    """
    Get session and published results, validating that results are published.

    Returns tuple of (session, published_results).
    Raises HTTPException if session not found, not in results status, or results not found.
    """
    session = get_session_or_404(session_id)
    require_status(session, "results", "access results")
    published_results = get_published_results_or_404(session_id)
    return session, published_results
