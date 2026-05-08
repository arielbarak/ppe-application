"""Unit tests for app.crypto.params (Theorem 4.4 compliance)."""

import math

import pytest

from app.crypto.params import (
    SecurityParams,
    compute_adversary_advantage,
    compute_edge_probability,
    compute_expected_degree,
    compute_security_params,
    compute_validity_threshold_from_advantage,
    recommend_params_for_poll,
    validate_params,
)


# compute_adversary_advantage / compute_validity_threshold_from_advantage


def test_compute_adversary_advantage_eta_v_zero_is_one():
    assert compute_adversary_advantage(0.0) == 1.0


def test_compute_adversary_advantage_eta_v_one_is_inf():
    assert math.isinf(compute_adversary_advantage(1.0))


def test_compute_adversary_advantage_formula():
    eta_v = 0.025
    expected = (1 + eta_v) / (1 - eta_v)
    assert compute_adversary_advantage(eta_v) == pytest.approx(expected, rel=1e-12)


def test_validity_threshold_from_advantage_below_one_is_zero():
    assert compute_validity_threshold_from_advantage(0.5) == 0.0
    assert compute_validity_threshold_from_advantage(1.0) == 0.0


@pytest.mark.parametrize("c_star", [1.05, 1.1, 1.25, 1.5])
def test_advantage_threshold_round_trip(c_star):
    eta_v = compute_validity_threshold_from_advantage(c_star)
    assert compute_adversary_advantage(eta_v) == pytest.approx(c_star, rel=1e-9)


# compute_expected_degree / compute_edge_probability


def test_compute_expected_degree_grows_with_kappa():
    base = compute_expected_degree(m=100, kappa=40)
    higher = compute_expected_degree(m=100, kappa=128)
    assert higher > base


def test_compute_expected_degree_grows_with_m():
    smaller = compute_expected_degree(m=10, kappa=80)
    larger = compute_expected_degree(m=1000, kappa=80)
    assert larger > smaller


def test_compute_expected_degree_m_le_one_returns_zero():
    assert compute_expected_degree(m=1, kappa=80) == 0.0
    assert compute_expected_degree(m=0, kappa=80) == 0.0


def test_compute_expected_degree_formula():
    """d = 2*ln(m) + kappa/16."""
    m, kappa = 100, 80
    expected = 2 * math.log(m) + kappa / 16
    assert compute_expected_degree(m, kappa) == pytest.approx(expected, rel=1e-12)


def test_compute_edge_probability_clamped_to_unit_interval():
    assert compute_edge_probability(expected_degree=999.0, m=10) == 1.0
    assert compute_edge_probability(expected_degree=-5.0, m=10) == 0.0
    assert compute_edge_probability(expected_degree=4.5, m=10) == pytest.approx(0.5)


def test_compute_edge_probability_m_le_one_returns_zero():
    assert compute_edge_probability(expected_degree=5.0, m=1) == 0.0


# compute_security_params


def test_compute_security_params_invalid_kappa_raises():
    with pytest.raises(ValueError):
        compute_security_params(kappa=0, m=10)


def test_compute_security_params_invalid_m_raises():
    with pytest.raises(ValueError):
        compute_security_params(kappa=80, m=1)


def test_compute_security_params_returns_dataclass():
    params = compute_security_params(kappa=80, m=100)
    assert isinstance(params, SecurityParams)
    assert params.kappa == 80
    assert params.m == 100


def test_compute_security_params_thresholds_in_clamped_ranges():
    """η_E clamped to [0.1, 0.5]; η_V clamped to [0.005, 0.1]."""
    params = compute_security_params(kappa=80, m=100)
    assert 0.1 <= params.effort_threshold <= 0.5
    assert 0.005 <= params.validity_threshold <= 0.1


def test_compute_security_params_p_consistent_with_d_and_m():
    """p * (m-1) ≈ expected_degree."""
    params = compute_security_params(kappa=80, m=100)
    assert params.edge_probability * (params.m - 1) == pytest.approx(
        params.expected_degree, rel=1e-9
    )


def test_compute_security_params_c_star_consistent_with_eta_v():
    params = compute_security_params(kappa=80, m=100)
    expected_c = (1 + params.validity_threshold) / (1 - params.validity_threshold)
    assert params.adversary_advantage == pytest.approx(expected_c, rel=1e-9)


@pytest.mark.parametrize(
    "kappa, m, expected_d, expected_p",
    [
        (40, 10, 7.1, 0.79),     # README small example
        (80, 100, 14.2, 0.14),   # README medium example
        (128, 1000, 21.8, 0.022),  # README large example
    ],
)
def test_compute_security_params_matches_readme_d_and_p(kappa, m, expected_d, expected_p):
    """Lock the README example values for d and p (tolerance 0.05)."""
    params = compute_security_params(kappa=kappa, m=m)
    assert params.expected_degree == pytest.approx(expected_d, abs=0.1)
    assert params.edge_probability == pytest.approx(expected_p, abs=0.01)


# recommend_params_for_poll


@pytest.mark.parametrize(
    "level, kappa",
    [("low", 40), ("medium", 80), ("high", 128)],
)
def test_recommend_params_kappa_by_level(level, kappa):
    params = recommend_params_for_poll(expected_responders=100, security_level=level)
    assert params.kappa == kappa


def test_recommend_params_unknown_level_raises():
    with pytest.raises(ValueError):
        recommend_params_for_poll(expected_responders=100, security_level="extreme")


def test_recommend_params_high_security_has_lower_c_star_than_low():
    low = recommend_params_for_poll(expected_responders=100, security_level="low")
    high = recommend_params_for_poll(expected_responders=100, security_level="high")
    # Higher security should bound adversary advantage more tightly
    assert high.adversary_advantage <= low.adversary_advantage


# validate_params


def test_validate_params_clean_input_no_warnings():
    result = validate_params(
        m=100,
        edge_probability=0.14,
        effort_threshold=0.15,
        validity_threshold=0.025,
        kappa=80,
    )
    assert result["valid"] is True


def test_validate_params_warns_on_high_c_star():
    result = validate_params(
        m=100,
        edge_probability=0.5,
        effort_threshold=0.3,
        validity_threshold=0.5,  # huge η_V → C* >> 1.5
        kappa=80,
    )
    assert any("adversary advantage" in w.lower() for w in result["warnings"])


def test_validate_params_warns_on_low_degree():
    result = validate_params(
        m=1000,
        edge_probability=0.001,  # very sparse
        effort_threshold=0.2,
        validity_threshold=0.025,
        kappa=80,
    )
    assert any("degree" in w.lower() for w in result["warnings"])


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
        "m": 100,
        "edge_probability": 0.14,
        "effort_threshold": 0.15,
        "validity_threshold": 0.025,
        "kappa": 80,
    }
    base[field] = bad_value
    result = validate_params(**base)
    assert result["valid"] is False
    assert any(field.replace("_", " ") in w.lower() or field in w.lower() for w in result["warnings"])
