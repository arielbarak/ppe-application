"""
Security Parameter Utilities (Theorem 4.4 Compliance)

This module calculates PPE protocol parameters based on the security parameter κ
to ensure the adversary's multiplicative advantage C* remains bounded.

From the paper:
- κ: security parameter (higher = more secure, typical values: 40, 80, 128)
- m: number of responders
- d: expected degree (average neighbors per node)
- p: edge probability, where d = p(m-1)
- η_E: effort threshold (max failure fraction before node exclusion)
- η_V: validity threshold (max excluded fraction before poll is invalid)
- C*: adversary advantage = (1 + η_V) / (1 - η_V)

Theorem 4.4 bounds:
- The probability of adversary success should be negligible in κ (i.e., ≤ 2^(-κ))
- C* should be minimized while maintaining practical poll completion rates

Key relationships:
1. Higher κ → stricter thresholds → smaller C* → more secure
2. Expected degree d = Ω(log m) for graph connectivity
3. η_E must allow honest nodes to pass with overwhelming probability
4. η_V determines maximum tolerable exclusion rate
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict

logger = logging.getLogger(__name__)


@dataclass
class SecurityParams:
    """Computed security parameters for a PPE poll."""
    kappa: int                    # Security parameter
    m: int                        # Number of responders
    expected_degree: float        # d = average neighbors per node
    edge_probability: float       # p = d/(m-1)
    effort_threshold: float       # η_E
    validity_threshold: float     # η_V
    adversary_advantage: float    # C* = (1 + η_V)/(1 - η_V)
    honest_failure_rate: float    # ε = assumed honest PPE failure rate
    connectivity_probability: float  # Probability graph is connected

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kappa': self.kappa,
            'm': self.m,
            'expected_degree': round(self.expected_degree, 4),
            'edge_probability': round(self.edge_probability, 6),
            'effort_threshold': round(self.effort_threshold, 4),
            'validity_threshold': round(self.validity_threshold, 4),
            'adversary_advantage': round(self.adversary_advantage, 4),
            'honest_failure_rate': round(self.honest_failure_rate, 4),
            'connectivity_probability': round(self.connectivity_probability, 6),
        }


def compute_adversary_advantage(eta_v: float) -> float:
    """
    Compute adversary's multiplicative advantage C*.

    C* = (1 + η_V) / (1 - η_V)

    This bounds how much an adversary can skew poll results.
    C* = 1.0 means no advantage; higher values favor the adversary.
    """
    if eta_v >= 1.0:
        return float('inf')
    if eta_v <= 0.0:
        return 1.0
    return (1 + eta_v) / (1 - eta_v)


def compute_validity_threshold_from_advantage(c_star: float) -> float:
    """
    Compute η_V from desired adversary advantage C*.

    Solving C* = (1 + η_V) / (1 - η_V) for η_V:
    η_V = (C* - 1) / (C* + 1)
    """
    if c_star <= 1.0:
        return 0.0
    return (c_star - 1) / (c_star + 1)


def compute_expected_degree(
    m: int,
    kappa: int,
    connectivity_factor: float = 2.0,
) -> float:
    """
    Compute expected degree d for the certification graph.

    For a random graph G(n, p), connectivity threshold is:
        p ≥ (ln(n) + c) / n  for some constant c

    Expected degree d = p(m-1), so for connectivity:
        d ≥ ln(m) + c

    We scale with κ for additional security margin:
        d = connectivity_factor * ln(m) + κ/16

    Higher d means:
    - More verification opportunities per node
    - Stronger concentration bounds for honest behavior
    - More PPE overhead (more challenges to complete)
    """
    if m <= 1:
        return 0.0

    base_degree = connectivity_factor * math.log(m)
    security_margin = kappa / 16.0

    return base_degree + security_margin


def compute_edge_probability(expected_degree: float, m: int) -> float:
    """
    Compute edge probability p from expected degree d.

    p = d / (m - 1)

    Clamped to [0, 1].
    """
    if m <= 1:
        return 0.0
    p = expected_degree / (m - 1)
    return min(1.0, max(0.0, p))


def compute_connectivity_probability(m: int, p: float) -> float:
    """
    Estimate probability that G(m, p) is connected.

    For large m with p = (ln(m) + c) / m:
    - If c → ∞, connectivity probability → 1
    - If c → -∞, connectivity probability → 0

    Approximation: P(connected) ≈ exp(-m * exp(-p*(m-1)))
    """
    if m <= 1:
        return 1.0
    if p >= 1.0:
        return 1.0
    if p <= 0.0:
        return 0.0

    expected_degree = p * (m - 1)
    if expected_degree > 2 * math.log(m):
        return 1.0 - 1e-10

    try:
        isolated_prob = (1 - p) ** (m - 1)
        expected_isolated = m * isolated_prob
        return math.exp(-expected_isolated)
    except (OverflowError, ValueError):
        return 1.0 if expected_degree > math.log(m) else 0.0


def compute_effort_threshold(
    kappa: int,
    expected_degree: float,
    honest_failure_rate: float = 0.05,
) -> float:
    """
    Compute effort threshold η_E using Chernoff-style bounds.

    An honest node with PPE failure rate ε has expected failures = ε * d.
    We want honest nodes to pass (failures ≤ η_E * d) with probability ≥ 1 - 2^(-κ).

    Using Chernoff bound for Binomial(d, ε):
        P(failures > (1 + δ)εd) ≤ exp(-δ²εd / 3)

    For this to be ≤ 2^(-κ):
        δ²εd / 3 ≥ κ * ln(2)
        δ ≥ sqrt(3κ * ln(2) / (εd))

    So η_E = ε(1 + δ) = ε + ε*sqrt(3κ*ln(2)/(εd))
                      = ε + sqrt(3κ*ln(2)*ε/d)

    We add a safety margin and clamp to reasonable bounds.
    """
    if expected_degree <= 0:
        return 0.5

    epsilon = honest_failure_rate

    chernoff_delta = math.sqrt(3 * kappa * math.log(2) * epsilon / expected_degree)

    eta_e = epsilon * (1 + chernoff_delta)

    eta_e += 0.05

    eta_e = min(0.5, max(0.1, eta_e))

    return eta_e


def compute_validity_threshold(
    kappa: int,
    m: int,
    max_adversary_advantage: float = 1.1,
) -> float:
    """
    Compute validity threshold η_V based on security requirements.

    We want to bound C* = (1 + η_V)/(1 - η_V) while allowing polls to complete.

    Approach:
    1. Start with max acceptable C* (e.g., 1.1 = 10% adversary advantage)
    2. Derive base η_V from C*
    3. Scale down with κ for stronger security
    4. Scale down with m for larger polls (more nodes = tighter tolerance)

    η_V = base_η_V / (1 + κ/64) / (1 + log(m)/16)
    """
    base_eta_v = compute_validity_threshold_from_advantage(max_adversary_advantage)

    kappa_factor = 1 + kappa / 64.0
    m_factor = 1 + math.log(max(2, m)) / 16.0

    eta_v = base_eta_v / (kappa_factor * m_factor)

    eta_v = max(0.005, min(0.1, eta_v))

    return eta_v


def compute_security_params(
    kappa: int,
    m: int,
    honest_failure_rate: float = 0.05,
    max_adversary_advantage: float = 1.1,
    connectivity_factor: float = 2.0,
) -> SecurityParams:
    """
    Compute all security parameters for a PPE poll.

    Args:
        kappa: Security parameter (typical: 40 for low, 80 for medium, 128 for high)
        m: Number of responders
        honest_failure_rate: Expected PPE failure rate for honest nodes (default 5%)
        max_adversary_advantage: Maximum acceptable C* (default 1.1 = 10% advantage)
        connectivity_factor: Multiplier for ln(m) in degree calculation

    Returns:
        SecurityParams with all computed values

    Example:
        params = compute_security_params(kappa=80, m=100)
        # Use params.edge_probability, params.effort_threshold, etc.
    """
    if kappa < 1:
        raise ValueError(f"Security parameter κ must be positive, got {kappa}")
    if m < 2:
        raise ValueError(f"Need at least 2 responders, got {m}")

    expected_degree = compute_expected_degree(m, kappa, connectivity_factor)

    edge_probability = compute_edge_probability(expected_degree, m)

    actual_degree = edge_probability * (m - 1)

    eta_e = compute_effort_threshold(kappa, actual_degree, honest_failure_rate)

    eta_v = compute_validity_threshold(kappa, m, max_adversary_advantage)

    c_star = compute_adversary_advantage(eta_v)

    connectivity_prob = compute_connectivity_probability(m, edge_probability)

    params = SecurityParams(
        kappa=kappa,
        m=m,
        expected_degree=actual_degree,
        edge_probability=edge_probability,
        effort_threshold=eta_e,
        validity_threshold=eta_v,
        adversary_advantage=c_star,
        honest_failure_rate=honest_failure_rate,
        connectivity_probability=connectivity_prob,
    )

    logger.info(
        f"Security params for κ={kappa}, m={m}: "
        f"d={actual_degree:.2f}, p={edge_probability:.4f}, "
        f"η_E={eta_e:.3f}, η_V={eta_v:.4f}, C*={c_star:.4f}"
    )

    return params


def recommend_params_for_poll(
    expected_responders: int,
    security_level: str = "medium",
) -> SecurityParams:
    """
    Get recommended parameters for a poll based on expected size and security level.

    Security levels:
    - "low": κ=40, suitable for casual polls
    - "medium": κ=80, good balance of security and usability
    - "high": κ=128, for high-stakes decisions

    Args:
        expected_responders: Estimated number of participants
        security_level: "low", "medium", or "high"

    Returns:
        SecurityParams with recommended values
    """
    kappa_map = {
        "low": 40,
        "medium": 80,
        "high": 128,
    }

    if security_level not in kappa_map:
        raise ValueError(f"Unknown security level: {security_level}")

    kappa = kappa_map[security_level]

    honest_failure_rates = {
        "low": 0.10,
        "medium": 0.05,
        "high": 0.02,
    }

    max_advantages = {
        "low": 1.2,
        "medium": 1.1,
        "high": 1.05,
    }

    return compute_security_params(
        kappa=kappa,
        m=expected_responders,
        honest_failure_rate=honest_failure_rates[security_level],
        max_adversary_advantage=max_advantages[security_level],
    )


def validate_params(
    m: int,
    edge_probability: float,
    effort_threshold: float,
    validity_threshold: float,
    kappa: int = 80,
) -> Dict[str, Any]:
    """
    Validate user-provided parameters against security requirements.

    Returns a dict with:
    - valid: bool
    - warnings: list of potential issues
    - computed: SecurityParams that would be recommended
    - adversary_advantage: actual C* for provided η_V
    """
    warnings = []
    valid = True

    if edge_probability <= 0 or edge_probability > 1:
        warnings.append(f"Edge probability {edge_probability} out of range (0, 1]")
        valid = False

    if effort_threshold <= 0 or effort_threshold >= 1:
        warnings.append(f"Effort threshold {effort_threshold} out of range (0, 1)")
        valid = False

    if validity_threshold <= 0 or validity_threshold >= 1:
        warnings.append(f"Validity threshold {validity_threshold} out of range (0, 1)")
        valid = False

    c_star = compute_adversary_advantage(validity_threshold)
    if c_star > 1.5:
        warnings.append(
            f"High adversary advantage C*={c_star:.2f} - "
            f"consider lowering η_V from {validity_threshold}"
        )

    expected_degree = edge_probability * (m - 1)
    min_degree = 2 * math.log(m) if m > 1 else 1
    if expected_degree < min_degree:
        warnings.append(
            f"Expected degree {expected_degree:.1f} may be too low for "
            f"connectivity (recommend ≥ {min_degree:.1f})"
        )

    recommended = compute_security_params(kappa, m)

    return {
        'valid': valid,
        'warnings': warnings,
        'provided': {
            'edge_probability': edge_probability,
            'effort_threshold': effort_threshold,
            'validity_threshold': validity_threshold,
            'adversary_advantage': c_star,
            'expected_degree': expected_degree,
        },
        'recommended': recommended.to_dict(),
    }
