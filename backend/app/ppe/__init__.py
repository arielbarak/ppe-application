"""PPE (Proof of Private Effort) module with challenge providers and coordination."""

from typing import Dict, Type

from .base import PPEBase
from .captcha import MathCaptchaPPE
from .coordinator import PPECoordinator, PPESession

coordinator = PPECoordinator()

# PPE provider registry

_registry: Dict[str, Type[PPEBase]] = {}


def register_ppe(ppe_type: str, cls: Type[PPEBase]) -> None:
    _registry[ppe_type] = cls


def get_ppe_provider(ppe_type: str = "math_captcha", **kwargs) -> PPEBase:
    """Instantiate a registered PPE provider by type string."""
    cls = _registry.get(ppe_type)
    if cls is None:
        available = ", ".join(_registry.keys()) or "(none)"
        raise ValueError(f"Unknown PPE type '{ppe_type}'. Available: [{available}]")
    return cls(**kwargs)


def list_ppe_types() -> list:
    return list(_registry.keys())


register_ppe("math_captcha", MathCaptchaPPE)

__all__ = [
    "PPEBase", "MathCaptchaPPE", "PPECoordinator", "PPESession", "coordinator",
    "register_ppe", "get_ppe_provider", "list_ppe_types",
]
