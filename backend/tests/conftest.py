"""Shared pytest fixtures for the PPE polling backend test suite."""

import base64
from typing import Callable, List, Tuple

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app.crypto.graph import compute_node_id
from app.crypto.keys import export_public_key, generate_server_keypair
from app.ppe.captcha import MathCaptchaPPE
from app.ppe.coordinator import PPECoordinator
from app.storage.memory import InMemoryStorage


Keypair = Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey, str, str]


def _make_keypair() -> Keypair:
    priv, pub = generate_server_keypair()
    pub_b64 = export_public_key(pub)
    node_id = compute_node_id(pub_b64)
    return priv, pub, pub_b64, node_id


def _sign(priv: ec.EllipticCurvePrivateKey, message: str) -> str:
    sig = priv.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode("utf-8")


@pytest.fixture(scope="session")
def pollster_keypair() -> Keypair:
    """Single ECDSA P-256 keypair used as the pollster's identity across tests."""
    return _make_keypair()


@pytest.fixture(scope="session")
def responder_keypairs() -> List[Keypair]:
    """Eight reusable ECDSA keypairs. Tests slice [:n]; keys are stable per session."""
    return [_make_keypair() for _ in range(8)]


@pytest.fixture(scope="session")
def signed_message_factory() -> Callable[[ec.EllipticCurvePrivateKey, str], str]:
    """Factory returning base64 ECDSA-P256 signatures."""
    return _sign


@pytest.fixture
def storage() -> InMemoryStorage:
    """Fresh InMemoryStorage instance per test (unit-test use)."""
    return InMemoryStorage()


@pytest.fixture
def coordinator() -> PPECoordinator:
    """Fresh PPECoordinator instance per test (unit-test use)."""
    return PPECoordinator()


@pytest.fixture
def captcha_provider() -> MathCaptchaPPE:
    """Default math CAPTCHA provider at difficulty 0.5."""
    return MathCaptchaPPE(difficulty=0.5)


