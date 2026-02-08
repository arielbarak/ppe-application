"""
Abstract PPE interface. Plug in any effort proof (math CAPTCHA, PoW, image
recognition, storage proof, etc.) by implementing generate/validate/get_difficulty.

Difficulty is derived from η_E (effort threshold): difficulty = 1 - η_E
- Low η_E (strict, few failures allowed) → high difficulty
- High η_E (lenient, more failures allowed) → low difficulty
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


def derive_difficulty_from_eta_e(eta_e: float) -> float:
    """Convert η_E threshold to difficulty level (0.0-1.0 scale)."""
    return max(0.0, min(1.0, 1.0 - eta_e))


class PPEBase(ABC):

    def __init__(self, difficulty: float = 0.5):
        """Initialize with difficulty level (0.0 = trivial, 1.0 = hard)."""
        self._difficulty = max(0.0, min(1.0, difficulty))

    @abstractmethod
    def generate(self) -> Dict[str, Any]:
        """Return {question, solution, difficulty} for a new challenge."""

    @abstractmethod
    def validate(self, challenge: str, solution: str) -> bool:
        """Check whether `solution` is correct for `challenge`."""

    def get_difficulty(self) -> float:
        """Difficulty on a 0.0 (trivial) to 1.0 (hard) scale."""
        return self._difficulty
