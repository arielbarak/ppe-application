"""Unit tests for app.crypto.params (real Theorem 4.4 / Appendix C compliance)."""

import math

import pytest

from app.crypto.params import (
    SecurityParams,
    compute_adversary_advantage,
    compute_free_nodes,
    compute_security_params,
    eta_v_min_completeness,
    min_degree_for_soundness,
    recommend_params_for_poll,
    soundness_precondition_holds,
    validate_params,
)


# ---------------------------------------------------------------------------
# Theorem 4.4 C* — anchored to the paper's Table 4 (Scenarios 1 and 2)
# ---------------------------------------------------------------------------

def test_c_star_matches_paper_table4_scenario1():
    """Scenario 1: m=5000, d=60, eta_V=0.025, eta_E=1/8 -> C* ~ 200."""
    c_star = compute_adversary_advantage(d=60, eta_v=0.025, eta_e=0.125, m=5000)
    assert c_star == pytest.approx(200, rel=0.02)


def test_c_star_matches_paper_table4_scenario2():
    """Scenario 2: doubling the degree to d=120 drops C* to ~10."""
    c_star = compute_adversary_advantage(d=120, eta_v=0.025, eta_e=0.125, m=5000)
    assert c_star == pytest.approx(10, rel=0.05)


def test_c_star_decreases_with_degree():
    """Higher degree (more PPEs per responder) yields a smaller advantage."""
    low_d = compute_adversary_advantage(d=60, eta_v=0.025, eta_e=0.125, m=5000)
    high_d = compute_adversary_advantage(d=120, eta_v=0.025, eta_e=0.125, m=5000)
    assert high_d < low_d


def test_c_star_unbounded_below_soundness_minimum():
    """Below the soundness-minimum degree the precondition fails and C* is +inf."""
    d_min = min_degree_for_soundness(eta_v=0.025, eta_e=0.125, m=5000)
    c_star = compute_adversary_advantage(d=d_min * 0.5, eta_v=0.025, eta_e=0.125, m=5000)
    assert math.isinf(c_star)


def test_c_star_infeasible_when_half_minus_thresholds_nonpositive():
    """If 1/2 - eta_V - eta_E <= 0 the bound cannot hold."""
    assert math.isinf(min_degree_for_soundness(eta_v=0.3, eta_e=0.25, m=1000))


# ---------------------------------------------------------------------------
# Soundness precondition / minimum degree (Appendix C.1 constraint 1)
# ---------------------------------------------------------------------------

def test_min_degree_matches_paper_scenario1():
    """d_min for Scenario 1 is ~58.3 (paper rounds the chosen degree up to 60)."""
    d_min = min_degree_for_soundness(eta_v=0.025, eta_e=0.125, m=5000)
    assert d_min == pytest.approx(58.3, abs=0.5)


def test_precondition_holds_above_minimum_and_fails_below():
    d_min = min_degree_for_soundness(eta_v=0.025, eta_e=0.125, m=5000)
    assert soundness_precondition_holds(d_min * 1.1, 0.025, 0.125, 5000)
    assert not soundness_precondition_holds(d_min * 0.9, 0.025, 0.125, 5000)


# ---------------------------------------------------------------------------
# Theorem 5.2 completeness lower bound — anchored to Table 4
# ---------------------------------------------------------------------------

def test_eta_v_min_matches_paper_scenario1():
    """Scenario 1's eta_V=0.025 is exactly the completeness minimum."""
    v_min = eta_v_min_completeness(
        kappa=40, m=5000, d=60, sigma=0.0, theta=1e-3, eta_e=0.125
    )
    assert v_min == pytest.approx(0.025, abs=1e-4)


def test_eta_v_min_matches_paper_scenario3():
    """Scenario 3 (noisy PPE): completeness minimum ~0.0275, within paper's 0.028."""
    v_min = eta_v_min_completeness(
        kappa=40, m=100000, d=165, sigma=1e-3, theta=1e-4, eta_e=0.23
    )
    assert v_min == pytest.approx(0.0275, abs=5e-4)
    assert v_min <= 0.028


# ---------------------------------------------------------------------------
# free nodes K (Theorem 4.4)
# ---------------------------------------------------------------------------

def test_free_nodes_grows_with_kappa():
    assert compute_free_nodes(128, 1000, 0.025) > compute_free_nodes(40, 1000, 0.025)


# ---------------------------------------------------------------------------
# compute_security_params
# ---------------------------------------------------------------------------

def test_compute_security_params_invalid_kappa_raises():
    with pytest.raises(ValueError):
        compute_security_params(kappa=0, m=10)


def test_compute_security_params_invalid_m_raises():
    with pytest.raises(ValueError):
        compute_security_params(kappa=80, m=1)


def test_compute_security_params_returns_dataclass():
    params = compute_security_params(kappa=80, m=5000)
    assert isinstance(params, SecurityParams)
    assert params.kappa == 80
    assert params.m == 5000


def test_compute_security_params_p_consistent_with_d_and_m():
    """p * (m-1) == expected_degree by construction (p = d/(m-1))."""
    params = compute_security_params(kappa=80, m=5000)
    assert params.edge_probability * (params.m - 1) == pytest.approx(
        params.expected_degree, rel=1e-9
    )


def test_compute_security_params_meets_target_advantage_when_feasible():
    """With a large enough poll, medium level should reach its C* target of 20."""
    params = compute_security_params(
        kappa=80, m=5000, honest_failure_rate=0.0, max_adversary_advantage=20.0
    )
    assert params.adversary_advantage <= 20.0 + 1e-6
    assert params.soundness_precondition_ok


def test_compute_security_params_degree_at_least_soundness_minimum():
    params = compute_security_params(kappa=80, m=5000)
    d_min = min_degree_for_soundness(
        params.validity_threshold, params.effort_threshold, params.m
    )
    assert params.expected_degree >= d_min


def test_compute_security_params_infeasible_thresholds_raise():
    with pytest.raises(ValueError):
        compute_security_params(
            kappa=80, m=1000, effort_threshold=0.3, validity_threshold=0.25
        )


# ---------------------------------------------------------------------------
# recommend_params_for_poll
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level, kappa", [("low", 40), ("medium", 80), ("high", 128)])
def test_recommend_params_kappa_by_level(level, kappa):
    params = recommend_params_for_poll(expected_responders=5000, security_level=level)
    assert params.kappa == kappa


def test_recommend_params_unknown_level_raises():
    with pytest.raises(ValueError):
        recommend_params_for_poll(expected_responders=100, security_level="extreme")


def test_recommend_params_high_security_has_lower_or_equal_c_star_than_low():
    low = recommend_params_for_poll(expected_responders=5000, security_level="low")
    high = recommend_params_for_poll(expected_responders=5000, security_level="high")
    assert high.adversary_advantage <= low.adversary_advantage


# ---------------------------------------------------------------------------
# validate_params
# ---------------------------------------------------------------------------

def test_validate_params_clean_input_no_warnings():
    """A degree above the soundness minimum with a modest C* validates cleanly."""
    result = validate_params(
        m=5000,
        edge_probability=120 / 4999,  # d ~ 120 -> C* ~ 10
        effort_threshold=0.125,
        validity_threshold=0.025,
        kappa=80,
    )
    assert result["valid"] is True
    assert result["warnings"] == []


def test_validate_params_warns_on_low_degree():
    result = validate_params(
        m=5000,
        edge_probability=0.001,  # d ~ 5, far below soundness minimum
        effort_threshold=0.125,
        validity_threshold=0.025,
        kappa=80,
    )
    assert result["valid"] is False
    assert any("degree" in w.lower() or "unbounded" in w.lower() for w in result["warnings"])


def test_validate_params_warns_when_thresholds_infeasible():
    result = validate_params(
        m=1000,
        edge_probability=0.5,
        effort_threshold=0.3,
        validity_threshold=0.25,  # 1/2 - eta_V - eta_E = -0.05
        kappa=80,
    )
    assert result["valid"] is False
    assert any("1/2" in w or "unbounded" in w.lower() for w in result["warnings"])


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("edge_probability", 0.0),
        ("edge_probability", 1.5),
        ("effort_threshold", 0.0),
        ("effort_threshold", 1.0),
        ("validity_threshold", 0.0),
        ("validity_threshold", 1.0),
    ],
)
def test_validate_params_marks_invalid_ranges(field, bad_value):
    base = {
        "m": 5000,
        "edge_probability": 120 / 4999,
        "effort_threshold": 0.125,
        "validity_threshold": 0.025,
        "kappa": 80,
    }
    base[field] = bad_value
    result = validate_params(**base)
    assert result["valid"] is False
    assert any(field.replace("_", " ") in w.lower() or field in w.lower() for w in result["warnings"])
