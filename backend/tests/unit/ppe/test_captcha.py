"""Unit tests for app.ppe.captcha (MathCaptchaPPE)."""

import random

import pytest

from app.ppe.captcha import MathCaptchaPPE


# generate


def test_generate_returns_required_keys(captcha_provider):
    challenge = captcha_provider.generate()
    assert set(challenge.keys()) == {"question", "solution", "difficulty"}
    assert challenge["question"].endswith("= ?")
    assert isinstance(challenge["solution"], str)


def test_generate_solution_validates_against_own_question(captcha_provider):
    challenge = captcha_provider.generate()
    assert captcha_provider.validate(challenge["question"], challenge["solution"]) is True


def test_difficulty_low_uses_only_addition_subtraction():
    provider = MathCaptchaPPE(difficulty=0.1)
    assert provider.operators == ["+", "-"]


def test_difficulty_medium_includes_multiplication():
    provider = MathCaptchaPPE(difficulty=0.5)
    assert "*" in provider.operators


def test_difficulty_high_increases_max_value():
    low = MathCaptchaPPE(difficulty=0.1)
    high = MathCaptchaPPE(difficulty=1.0)
    assert high.max_value > low.max_value


def test_difficulty_clamped_above_one():
    provider = MathCaptchaPPE(difficulty=5.0)
    assert provider.get_difficulty() == 1.0


def test_difficulty_clamped_below_zero():
    provider = MathCaptchaPPE(difficulty=-1.0)
    assert provider.get_difficulty() == 0.0


# validate


@pytest.mark.parametrize(
    "question, solution, expected",
    [
        ("3 + 4 = ?", "7", True),
        ("10 - 4 = ?", "6", True),
        ("3 * 4 = ?", "12", True),
        ("3 + 4 = ?", "8", False),
        ("3 + 4 = ?", " 7 ", True),  # whitespace-tolerant
    ],
)
def test_validate_correct_and_wrong_answers(captcha_provider, question, solution, expected):
    assert captcha_provider.validate(question, solution) is expected


def test_validate_returns_false_on_malformed_challenge(captcha_provider):
    """Malformed challenge string returns False without raising."""
    assert captcha_provider.validate("not a math problem", "7") is False


def test_validate_returns_false_on_unknown_operator(captcha_provider):
    """Operators outside {+, -, *} return False without raising."""
    assert captcha_provider.validate("3 / 7 = ?", "0") is False


def test_validate_returns_false_on_non_integer_operand(captcha_provider):
    assert captcha_provider.validate("hello + 4 = ?", "any") is False


def test_generate_is_random_across_calls(captcha_provider):
    """Across many calls, multiple distinct questions appear."""
    random.seed(None)  # ensure no leftover deterministic seed
    questions = {captcha_provider.generate()["question"] for _ in range(20)}
    assert len(questions) > 1
