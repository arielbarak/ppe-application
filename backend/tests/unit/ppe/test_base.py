"""Unit tests for app.ppe.base."""

import pytest

from app.ppe.base import PPEBase, derive_difficulty_from_eta_e


def test_derive_difficulty_inverse_of_eta_e():
    assert derive_difficulty_from_eta_e(0.2) == pytest.approx(0.8)
    assert derive_difficulty_from_eta_e(0.5) == pytest.approx(0.5)
    assert derive_difficulty_from_eta_e(0.0) == pytest.approx(1.0)
    assert derive_difficulty_from_eta_e(1.0) == pytest.approx(0.0)


def test_derive_difficulty_clamps_below_zero():
    assert derive_difficulty_from_eta_e(1.5) == 0.0


def test_derive_difficulty_clamps_above_one():
    assert derive_difficulty_from_eta_e(-0.5) == 1.0


def test_ppe_base_cannot_instantiate():
    with pytest.raises(TypeError):
        PPEBase()
