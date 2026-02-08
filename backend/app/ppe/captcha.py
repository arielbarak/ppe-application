"""Math CAPTCHA PPE: simple arithmetic problems (+, -, *) as proof of effort."""

import logging
import random
from typing import Any, Dict, List, Optional

from .base import PPEBase

logger = logging.getLogger(__name__)


class MathCaptchaPPE(PPEBase):
    """Random arithmetic problems with difficulty scaled from η_E."""

    def __init__(self, difficulty: float = 0.5, operators: Optional[List[str]] = None):
        super().__init__(difficulty)
        self.operators = operators or self._operators_for_difficulty()
        self.max_value = self._max_value_for_difficulty()

    def _operators_for_difficulty(self) -> List[str]:
        """Select operators based on difficulty level."""
        if self._difficulty < 0.3:
            return ['+', '-']
        if self._difficulty < 0.7:
            return ['+', '-', '*']
        return ['+', '-', '*']

    def _max_value_for_difficulty(self) -> int:
        """Scale operand range based on difficulty (10-100)."""
        return int(10 + self._difficulty * 90)

    def generate(self) -> Dict[str, Any]:
        a = random.randint(1, self.max_value)
        b = random.randint(1, self.max_value)
        op = random.choice(self.operators)

        if op == '+':
            solution = a + b
        elif op == '-':
            if a < b:
                a, b = b, a
            solution = a - b
        elif op == '*':
            mult_max = int(5 + self._difficulty * 15)
            a = random.randint(1, mult_max)
            b = random.randint(1, mult_max)
            solution = a * b
        else:
            raise ValueError(f"Unknown operator: {op}")

        question = f"{a} {op} {b} = ?"
        logger.debug(f"Generated CAPTCHA: {question} (solution: {solution}, difficulty: {self._difficulty})")

        return {
            'question': question,
            'solution': str(solution),
            'difficulty': self.get_difficulty()
        }

    def validate(self, challenge: str, solution: str) -> bool:
        """Re-parse the challenge string and check the answer."""
        try:
            # Expected format: "a op b = ?"
            parts = challenge.replace('?', '').replace('=', '').strip().split()
            if len(parts) != 3:
                logger.warning(f"Invalid challenge format: {challenge}")
                return False

            a, op, b = int(parts[0]), parts[1], int(parts[2])

            if op == '+':
                expected = a + b
            elif op == '-':
                expected = a - b
            elif op == '*':
                expected = a * b
            else:
                logger.warning(f"Unknown operator in challenge: {op}")
                return False

            correct = str(expected) == solution.strip()
            if not correct:
                logger.debug(f"CAPTCHA failed: {challenge} (expected {expected}, got {solution})")
            return correct

        except (ValueError, IndexError) as e:
            logger.error(f"CAPTCHA validation error: {e}")
            return False
