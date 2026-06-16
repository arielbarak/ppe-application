"""
Security parameter utilities implementing Theorem 4.4 and Appendix C of AMR14.

This module computes PPE protocol parameters and the adversary's multiplicative
advantage C* exactly as defined in Alberini--Moran--Rosen ("Public Verification of
Private Effort", eprint 2014/983), rather than via a heuristic surrogate.

Notation (matching the paper):
- kappa : security parameter (adversary failure probability <= 2^{-kappa})
- m     : number of responders / nodes
- d     : expected degree (expected PPE executions per responder)
- p     : edge probability; here p = d/(m-1) so the realised expected degree equals d
- eta_E : effort threshold  (max fraction of PPEs a node may fail before exclusion)
- eta_V : validity threshold (max fraction of deleted nodes before the poll is invalid)
- sigma : honest PPE failure probability
- theta : upper bound on the fraction of maliciously controlled responders
- C*    : multiplicative advantage of the adversary (Theorem 4.4)

Theorem 4.4 (soundness):
    b  = sqrt( d (1/2 - eta_V) / (2 (ln m - 1)) )
    valid only when   b > (1/2 - eta_V)/(1/2 - eta_V - eta_E) > 1
    C* = b / ((b - 1)(1/2 - eta_V) - b * eta_E) + 1

Because the bound is worst-case, C* is typically *large* (the paper's own Table 4
reports C* of 200, 10, 670, 23 for its example regimes); it is not close to 1. The
degree d is the lever that drives C* down: increasing d (more PPEs per responder)
reduces the advantage.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core paper formulas (Theorem 4.4, Theorem 5.2, Appendix C.1)
# ---------------------------------------------------------------------------

def _b_param(d: float, eta_v: float, m: int) -> float:
    """b = sqrt( d (1/2 - eta_V) / (2 (ln m - 1)) ) from Theorem 4.4."""
    half_minus_v = 0.5 - eta_v
    denom = 2.0 * (math.log(m) - 1.0)
    if half_minus_v <= 0.0 or denom <= 0.0 or d <= 0.0:
        return 0.0
    return math.sqrt(d * half_minus_v / denom)


def soundness_precondition_holds(d: float, eta_v: float, eta_e: float, m: int) -> bool:
    """Theorem 4.4 precondition:  b > (1/2 - eta_V)/(1/2 - eta_V - eta_E) > 1."""
    half_minus_v = 0.5 - eta_v
    gap = half_minus_v - eta_e  # 1/2 - eta_V - eta_E
    if gap <= 0.0 or half_minus_v <= 0.0:
        return False
    b = _b_param(d, eta_v, m)
    threshold = half_minus_v / gap
    return b > threshold > 1.0


def compute_adversary_advantage(d: float, eta_v: float, eta_e: float, m: int) -> float:
    """
    Real multiplicative advantage C* from Theorem 4.4:

        C* = b / ((b - 1)(1/2 - eta_V) - b * eta_E) + 1

    Returns +inf when the soundness precondition fails (the denominator is
    non-positive), i.e. when the degree is too small to bound the adversary.
    """
    b = _b_param(d, eta_v, m)
    half_minus_v = 0.5 - eta_v
    denom = (b - 1.0) * half_minus_v - b * eta_e
    if denom <= 0.0:
        return float("inf")
    return b / denom + 1.0


def min_degree_for_soundness(eta_v: float, eta_e: float, m: int) -> float:
    """
    Appendix C.1 constraint (1): the smallest degree for which the Theorem 4.4
    precondition can hold,

        d > ((1/2 - eta_V) / (1/2 - eta_V - eta_E)^2) (2 ln m - 2).

    Returns +inf when 1/2 - eta_V - eta_E <= 0 (the bound is then unattainable).
    """
    half_minus_v = 0.5 - eta_v
    gap = half_minus_v - eta_e
    if gap <= 0.0 or m <= 1:
        return float("inf")
    return (half_minus_v / (gap * gap)) * (2.0 * math.log(m) - 2.0)


def compute_free_nodes(kappa: int, m: int, eta_v: float) -> float:
    """K = kappa + (eta_V m + 2) ln m + eta_V m  (nodes the adversary controls 'for free')."""
    return kappa + (eta_v * m + 2.0) * math.log(m) + eta_v * m


def compute_min_honest_fraction(kappa: int, m: int, eta_v: float) -> float:
    """alpha = K/m + eta_V  (minimum honest fraction required for soundness)."""
    return compute_free_nodes(kappa, m, eta_v) / m + eta_v


def eta_v_max_from_alpha(kappa: int, m: int, alpha: float) -> float:
    """Appendix C.1 eq (3): eta_V^max = (alpha - (kappa + 2 ln m)/m) / (2 + ln m)."""
    ln_m = math.log(m)
    return (alpha - (kappa + 2.0 * ln_m) / m) / (2.0 + ln_m)


def eta_v_min_completeness(
    kappa: int, m: int, d: float, sigma: float, theta: float, eta_e: float
) -> float:
    """
    Theorem 5.2 completeness lower bound on eta_V:

        eta_V^min = theta
                    + 3 max{kappa/(md), theta} / eta_E
                    + (2 sigma / eta_E) (1 + max{2, 2 kappa/(md sigma)})
    """
    if eta_e <= 0.0:
        return float("inf")
    md = m * d
    if md <= 0.0:
        return float("inf")
    effort_term = 3.0 * max(kappa / md, theta) / eta_e
    if sigma <= 0.0:
        noise_term = 0.0
    else:
        noise_term = (2.0 * sigma / eta_e) * (1.0 + max(2.0, 2.0 * kappa / (md * sigma)))
    return theta + effort_term + noise_term


def _degree_for_target_advantage(
    eta_v: float, eta_e: float, m: int, target_c_star: float, d_start: float
) -> float:
    """
    Smallest degree d >= d_start whose C* is at most target_c_star.

    C* is monotonically decreasing in d above the soundness threshold, so a
    bisection between d_start and the clique degree (m-1) suffices. If even the
    clique degree cannot reach the target, the clique degree is returned.
    """
    lo = d_start
    hi = float(m - 1)
    if hi <= lo:
        return lo
    if compute_adversary_advantage(lo, eta_v, eta_e, m) <= target_c_star:
        return lo
    if compute_adversary_advantage(hi, eta_v, eta_e, m) > target_c_star:
        return hi
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if compute_adversary_advantage(mid, eta_v, eta_e, m) <= target_c_star:
            hi = mid
        else:
            lo = mid
    return hi


def compute_connectivity_probability(m: int, p: float) -> float:
    """Estimate P(G(m, p) is connected) via the isolated-vertex first moment."""
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


# ---------------------------------------------------------------------------
# Threshold selection
# ---------------------------------------------------------------------------

def default_thresholds(sigma: float) -> Tuple[float, float]:
    """
    Default (eta_E, eta_V) for a regime, taken from the paper's Table 4:
      - error-free PPE (sigma = 0):  eta_E = 1/8,  eta_V = 0.025   (Scenarios 1-2)
      - noisy PPE     (sigma > 0):   eta_E = 0.23, eta_V = 0.028   (Scenarios 3-4)
    """
    if sigma <= 0.0:
        return 0.125, 0.025
    return 0.23, 0.028


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

@dataclass
class SecurityParams:
    """Computed security parameters for a PPE poll (Theorem 4.4 / Appendix C)."""
    kappa: int                       # security parameter
    m: int                           # number of responders
    expected_degree: float           # d
    edge_probability: float          # p = d/(m-1)
    effort_threshold: float          # eta_E
    validity_threshold: float        # eta_V
    adversary_advantage: float       # C* (Theorem 4.4)
    honest_failure_rate: float       # sigma
    connectivity_probability: float  # P(graph connected)
    b: float                         # Theorem 4.4 b parameter
    free_nodes: float                # K
    min_honest_fraction: float       # alpha
    malicious_fraction: float        # theta
    eta_v_min: float                 # Theorem 5.2 completeness lower bound on eta_V
    eta_v_max: float                 # Appendix C.1 upper bound on eta_V
    soundness_precondition_ok: bool  # Theorem 4.4 precondition holds at (d, eta_V, eta_E)
    completeness_ok: bool            # eta_V >= eta_V^min

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kappa": self.kappa,
            "m": self.m,
            "expected_degree": round(self.expected_degree, 4),
            "edge_probability": round(self.edge_probability, 6),
            "effort_threshold": round(self.effort_threshold, 4),
            "validity_threshold": round(self.validity_threshold, 4),
            "adversary_advantage": (
                None if math.isinf(self.adversary_advantage)
                else round(self.adversary_advantage, 4)
            ),
            "honest_failure_rate": round(self.honest_failure_rate, 6),
            "connectivity_probability": round(self.connectivity_probability, 6),
            "b": round(self.b, 4),
            "free_nodes": round(self.free_nodes, 2),
            "min_honest_fraction": round(self.min_honest_fraction, 4),
            "malicious_fraction": self.malicious_fraction,
            "eta_v_min": round(self.eta_v_min, 5),
            "eta_v_max": round(self.eta_v_max, 5),
            "soundness_precondition_ok": self.soundness_precondition_ok,
            "completeness_ok": self.completeness_ok,
        }


def compute_security_params(
    kappa: int,
    m: int,
    honest_failure_rate: float = 0.0,
    max_adversary_advantage: Optional[float] = None,
    connectivity_factor: float = 1.05,
    malicious_fraction: float = 1e-3,
    effort_threshold: Optional[float] = None,
    validity_threshold: Optional[float] = None,
) -> SecurityParams:
    """
    Compute all security parameters for a PPE poll using the real Theorem 4.4
    bound.

    Thresholds eta_E and eta_V default to the paper's Table 4 regime values for
    the given honest failure rate (sigma); pass them explicitly to override. The
    degree d is set to the soundness minimum (Appendix C.1 constraint 1) scaled by
    ``connectivity_factor``, then increased -- if ``max_adversary_advantage`` is
    given -- until C* meets that target (capped at the clique degree m-1).

    Args:
        kappa: security parameter.
        m: number of responders (>= 2).
        honest_failure_rate: sigma, the honest PPE failure probability.
        max_adversary_advantage: target upper bound on C* (None = minimum degree).
        connectivity_factor: multiplier (>= 1) on the soundness-minimum degree.
        malicious_fraction: theta, upper bound on the malicious responder fraction.
        effort_threshold / validity_threshold: override the regime defaults.
    """
    if kappa < 1:
        raise ValueError(f"Security parameter kappa must be positive, got {kappa}")
    if m < 2:
        raise ValueError(f"Need at least 2 responders, got {m}")

    sigma = honest_failure_rate
    theta = malicious_fraction

    eta_e, eta_v = default_thresholds(sigma)
    if effort_threshold is not None:
        eta_e = effort_threshold
    if validity_threshold is not None:
        eta_v = validity_threshold

    if 0.5 - eta_v - eta_e <= 0.0:
        raise ValueError(
            f"Infeasible thresholds: 1/2 - eta_V - eta_E must be > 0 "
            f"(eta_V={eta_v}, eta_E={eta_e})"
        )

    d_min = min_degree_for_soundness(eta_v, eta_e, m)
    # Nudge strictly above the boundary so the precondition holds (not just =).
    d = d_min * max(1.0, connectivity_factor)
    if max_adversary_advantage is not None:
        d = _degree_for_target_advantage(eta_v, eta_e, m, max_adversary_advantage, d)
    d = min(d, float(m - 1))

    edge_probability = min(1.0, max(0.0, d / (m - 1)))

    c_star = compute_adversary_advantage(d, eta_v, eta_e, m)
    free_nodes = compute_free_nodes(kappa, m, eta_v)
    alpha = compute_min_honest_fraction(kappa, m, eta_v)
    v_min = eta_v_min_completeness(kappa, m, d, sigma, theta, eta_e)
    v_max = eta_v_max_from_alpha(kappa, m, alpha)
    connectivity_prob = compute_connectivity_probability(m, edge_probability)

    params = SecurityParams(
        kappa=kappa,
        m=m,
        expected_degree=d,
        edge_probability=edge_probability,
        effort_threshold=eta_e,
        validity_threshold=eta_v,
        adversary_advantage=c_star,
        honest_failure_rate=sigma,
        connectivity_probability=connectivity_prob,
        b=_b_param(d, eta_v, m),
        free_nodes=free_nodes,
        min_honest_fraction=alpha,
        malicious_fraction=theta,
        eta_v_min=v_min,
        eta_v_max=v_max,
        soundness_precondition_ok=soundness_precondition_holds(d, eta_v, eta_e, m),
        completeness_ok=(eta_v >= v_min - 1e-12),
    )

    logger.info(
        "Security params for kappa=%s, m=%s: d=%.2f, p=%.4f, eta_E=%.3f, "
        "eta_V=%.4f, C*=%s",
        kappa, m, d, edge_probability, eta_e, eta_v,
        "inf" if math.isinf(c_star) else f"{c_star:.2f}",
    )
    return params


def recommend_params_for_poll(
    expected_responders: int,
    security_level: str = "medium",
) -> SecurityParams:
    """
    Recommend parameters for a poll given its expected size and a security level.

    Levels map to (kappa, sigma, theta, target C*):
      - "low":    kappa=40,  sigma=0,     theta=1e-3,  minimum viable degree
      - "medium": kappa=80,  sigma=0,     theta=1e-3,  target C* <= 20
      - "high":   kappa=128, sigma=1e-3,  theta=1e-4,  target C* <= 8

    Note: the Theorem 4.4 bound is worst-case, so a small poll may be unable to
    reach the target C* (the degree is capped at m-1); the returned C* is then the
    best achievable and ``soundness_precondition_ok`` indicates whether the bound
    holds at all.
    """
    presets = {
        "low": dict(kappa=40, sigma=0.0, theta=1e-3, target=None),
        "medium": dict(kappa=80, sigma=0.0, theta=1e-3, target=20.0),
        "high": dict(kappa=128, sigma=1e-3, theta=1e-4, target=8.0),
    }
    if security_level not in presets:
        raise ValueError(f"Unknown security level: {security_level}")

    cfg = presets[security_level]
    return compute_security_params(
        kappa=cfg["kappa"],
        m=expected_responders,
        honest_failure_rate=cfg["sigma"],
        max_adversary_advantage=cfg["target"],
        malicious_fraction=cfg["theta"],
    )


def validate_params(
    m: int,
    edge_probability: float,
    effort_threshold: float,
    validity_threshold: float,
    kappa: int = 80,
) -> Dict[str, Any]:
    """
    Validate user-provided parameters against the Theorem 4.4 / Appendix C bounds.

    Returns a dict with ``valid``, ``warnings``, the ``provided`` parameters (with
    their real C* and the soundness-minimum degree), and the ``recommended``
    parameters for the same (m, kappa).
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

    d = edge_probability * (m - 1)
    c_star = compute_adversary_advantage(d, validity_threshold, effort_threshold, m)

    if 0.5 - validity_threshold - effort_threshold <= 0:
        warnings.append(
            "1/2 - eta_V - eta_E <= 0: the Theorem 4.4 soundness bound cannot hold; "
            "C* is unbounded"
        )
        valid = False
    else:
        d_min = min_degree_for_soundness(validity_threshold, effort_threshold, m)
        if d < d_min:
            warnings.append(
                f"Expected degree {d:.1f} is below the soundness minimum "
                f"{d_min:.1f} (Theorem 4.4 precondition); adversary advantage is "
                f"unbounded"
            )
            valid = False

    if math.isinf(c_star):
        warnings.append("Adversary advantage C* is unbounded for these parameters")
    elif c_star > 100:
        warnings.append(
            f"Large adversary advantage C*={c_star:.1f}; increase the degree "
            f"(lower eta_V or raise p) to reduce it"
        )

    recommended = compute_security_params(kappa, m)

    return {
        "valid": valid,
        "warnings": warnings,
        "provided": {
            "edge_probability": edge_probability,
            "effort_threshold": effort_threshold,
            "validity_threshold": validity_threshold,
            "adversary_advantage": None if math.isinf(c_star) else c_star,
            "expected_degree": d,
        },
        "recommended": recommended.to_dict(),
    }
