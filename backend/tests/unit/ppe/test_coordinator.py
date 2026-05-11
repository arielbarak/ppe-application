"""Unit tests for app.ppe.coordinator (PPE handshake state machine)."""

import hashlib
from datetime import datetime, timedelta

import pytest

from tests.fixtures import solve_math_captcha


def _commit(solution: str) -> str:
    """SHA-256 hex digest used as the commitment for a solution."""
    return hashlib.sha256(solution.encode("utf-8")).hexdigest()


# Helpers


def _solutions_for(session):
    """Return the (initiator-correct, responder-correct) solutions for a session.

    Each side solves the OTHER side's challenge: solution_i answers challenge_j_to_i.
    """
    return (
        solve_math_captcha(session.challenge_j_to_i),
        solve_math_captcha(session.challenge_i_to_j),
    )


def _drive_to_solved(coordinator, captcha_provider, init="alice", resp="bob",
                    sol_i=None, sol_j=None, sig_i="sig-i", sig_j="sig-j"):
    """Walk a session through initiated -> committed -> solved. Returns (session, sol_i, sol_j)."""
    session = coordinator.initiate_ppe(init, resp, captcha_provider)
    correct_i, correct_j = _solutions_for(session)
    submitted_i = sol_i if sol_i is not None else correct_i
    submitted_j = sol_j if sol_j is not None else correct_j
    # Commitments are SHA-256 of the solution we are about to submit so the
    # commit-reveal check in verify_and_finalize opens cleanly.
    coordinator.submit_commitment(session.id, init, _commit(submitted_i))
    coordinator.submit_commitment(session.id, resp, _commit(submitted_j))
    coordinator.submit_solution(session.id, init, submitted_i, sig_i)
    coordinator.submit_solution(session.id, resp, submitted_j, sig_j)
    return session


# create_session_id


def test_create_session_id_order_independent(coordinator):
    a, b = "alice", "bob"
    assert coordinator.create_session_id(a, b) == coordinator.create_session_id(b, a)


def test_create_session_id_different_pairs_distinct(coordinator):
    assert coordinator.create_session_id("a", "b") != coordinator.create_session_id("a", "c")


# initiate_ppe


def test_initiate_creates_session_with_two_challenges(coordinator, captcha_provider):
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)

    assert session.status == "initiated"
    assert session.initiator == "alice"
    assert session.responder == "bob"
    assert session.challenge_i_to_j.endswith("= ?")
    assert session.challenge_j_to_i.endswith("= ?")
    assert session.edge_label == "alice-bob"


def test_initiate_returns_existing_session_when_active(coordinator, captcha_provider):
    first = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    second = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert first is second


def test_initiate_replaces_failed_session(coordinator, captcha_provider):
    first = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    first.status = "failed"

    second = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert second is not first
    assert second.status == "initiated"


def test_initiate_replaces_verified_session(coordinator, captcha_provider):
    first = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    first.status = "verified"

    second = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert second is not first


def test_initiate_replaces_stale_session_over_120s(coordinator, captcha_provider):
    first = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    first.created_at = datetime.now() - timedelta(seconds=121)

    second = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert second is not first
    assert second.created_at > first.created_at


def test_initiate_returns_existing_when_within_120s(coordinator, captcha_provider):
    first = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    first.created_at = datetime.now() - timedelta(seconds=60)

    second = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert second is first


# submit_commitment


def test_submit_commitment_initiator_only_stays_initiated(coordinator, captcha_provider):
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    ok = coordinator.submit_commitment(session.id, "alice", "commit-i")

    assert ok is True
    assert session.commitment_i == "commit-i"
    assert session.status == "initiated"


def test_submit_commitment_both_transitions_to_committed(coordinator, captcha_provider):
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    coordinator.submit_commitment(session.id, "alice", "ci")
    coordinator.submit_commitment(session.id, "bob", "cj")
    assert session.status == "committed"


def test_submit_commitment_unknown_session_returns_false(coordinator):
    assert coordinator.submit_commitment("ppe-nonexistent", "alice", "x") is False


def test_submit_commitment_unknown_node_rejected(coordinator, captcha_provider):
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert coordinator.submit_commitment(session.id, "intruder", "x") is False


def test_submit_commitment_wrong_status_rejected(coordinator, captcha_provider):
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    coordinator.submit_commitment(session.id, "alice", "ci")
    coordinator.submit_commitment(session.id, "bob", "cj")
    # Already committed; further commit attempts are rejected
    assert coordinator.submit_commitment(session.id, "alice", "again") is False


# submit_solution


def test_submit_solution_requires_committed_status(coordinator, captcha_provider):
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    # Skip commitment phase
    assert coordinator.submit_solution(session.id, "alice", "ans", "sig") is False


def test_submit_solution_both_transitions_to_solved(coordinator, captcha_provider):
    session = _drive_to_solved(coordinator, captcha_provider)
    assert session.status == "solved"
    assert session.signature_i == "sig-i"
    assert session.signature_j == "sig-j"


# verify_and_finalize


def test_verify_and_finalize_correct_solutions_marks_verified(coordinator, captcha_provider):
    session = _drive_to_solved(coordinator, captcha_provider)
    result = coordinator.verify_and_finalize(session.id, captcha_provider)

    assert result is not None
    assert result["success"] is True
    assert session.status == "verified"


def test_verify_and_finalize_wrong_solutions_marks_failed(coordinator, captcha_provider):
    session = _drive_to_solved(
        coordinator, captcha_provider,
        sol_i="-9999", sol_j="-9999",
    )
    result = coordinator.verify_and_finalize(session.id, captcha_provider)

    assert result["success"] is False
    assert session.status == "failed"


def test_verify_and_finalize_signatures_are_swapped(coordinator, captcha_provider):
    """signature_for_initiator == signature provided by responder, and vice versa."""
    session = _drive_to_solved(coordinator, captcha_provider, sig_i="sig-from-i", sig_j="sig-from-j")
    result = coordinator.verify_and_finalize(session.id, captcha_provider)

    assert result["signature_for_initiator"] == "sig-from-j"
    assert result["signature_for_responder"] == "sig-from-i"


def test_verify_and_finalize_wrong_status_returns_none(coordinator, captcha_provider):
    """Calling on a session that hasn't reached 'solved' yet returns None."""
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    assert coordinator.verify_and_finalize(session.id, captcha_provider) is None


# get_node_sessions


def test_get_node_sessions_returns_only_involved(coordinator, captcha_provider):
    coordinator.initiate_ppe("alice", "bob", captcha_provider)
    coordinator.initiate_ppe("alice", "carol", captcha_provider)
    coordinator.initiate_ppe("bob", "carol", captcha_provider)

    alice_sessions = coordinator.get_node_sessions("alice")
    assert len(alice_sessions) == 2
    for s in alice_sessions:
        assert "alice" in (s.initiator, s.responder)


# cleanup_expired_sessions


def test_cleanup_removes_old_terminal_sessions(coordinator, captcha_provider):
    s = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    s.status = "verified"
    s.created_at = datetime.now() - timedelta(seconds=700)

    coordinator.cleanup_expired_sessions(max_age_seconds=600)
    assert s.id not in coordinator.sessions


def test_cleanup_keeps_active_sessions(coordinator, captcha_provider):
    s = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    s.created_at = datetime.now() - timedelta(seconds=700)
    # Status is "initiated" -> not terminal, not eligible for cleanup
    coordinator.cleanup_expired_sessions(max_age_seconds=600)
    assert s.id in coordinator.sessions


# get_statistics


def test_get_statistics_counts_by_status(coordinator, captcha_provider):
    s1 = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    s2 = coordinator.initiate_ppe("alice", "carol", captcha_provider)
    s2.status = "verified"

    stats = coordinator.get_statistics()
    assert stats["total_sessions"] == 2
    assert stats["by_status"]["initiated"] == 1
    assert stats["by_status"]["verified"] == 1


# Commit-reveal enforcement


def test_verify_and_finalize_rejects_solution_not_matching_commitment(coordinator, captcha_provider):
    """A solution that does not hash to the recorded commitment is rejected."""
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    correct_i, correct_j = _solutions_for(session)

    # Commit to a different value than what each side will reveal.
    coordinator.submit_commitment(session.id, "alice", _commit("not-the-real-solution"))
    coordinator.submit_commitment(session.id, "bob", _commit("also-not-real"))
    coordinator.submit_solution(session.id, "alice", correct_i, "sig-i")
    coordinator.submit_solution(session.id, "bob", correct_j, "sig-j")

    result = coordinator.verify_and_finalize(session.id, captcha_provider)
    assert result["success"] is False
    assert result["initiator_correct"] is False
    assert result["responder_correct"] is False
    assert session.status == "failed"


def test_verify_and_finalize_rejects_missing_commitment_payload(coordinator, captcha_provider):
    """If no commitment was recorded, finalize fails closed."""
    session = coordinator.initiate_ppe("alice", "bob", captcha_provider)
    correct_i, correct_j = _solutions_for(session)

    # Force the gate open without recording commitments, then submit solutions.
    session.status = "committed"
    coordinator.submit_solution(session.id, "alice", correct_i, "sig-i")
    coordinator.submit_solution(session.id, "bob", correct_j, "sig-j")

    result = coordinator.verify_and_finalize(session.id, captcha_provider)
    assert result["success"] is False


def test_verify_and_finalize_passes_when_both_sides_open_commitments(coordinator, captcha_provider):
    """Symmetric positive: real commitments + correct solutions -> verified."""
    session = _drive_to_solved(coordinator, captcha_provider)
    result = coordinator.verify_and_finalize(session.id, captcha_provider)
    assert result["success"] is True
    assert session.status == "verified"
