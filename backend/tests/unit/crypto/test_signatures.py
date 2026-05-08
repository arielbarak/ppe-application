"""Unit tests for app.crypto.signatures."""

import base64

import pytest

from app.crypto.signatures import verify_signature
from tests.fixtures import make_rsa_pubkey_b64


def test_sign_verify_round_trip(responder_keypairs, signed_message_factory):
    priv, _, pub_b64, _ = responder_keypairs[0]
    sig = signed_message_factory(priv, "hello world")

    assert verify_signature(pub_b64, "hello world", sig) is True


def test_verify_returns_false_on_wrong_message(responder_keypairs, signed_message_factory):
    priv, _, pub_b64, _ = responder_keypairs[0]
    sig = signed_message_factory(priv, "original message")

    assert verify_signature(pub_b64, "tampered message", sig) is False


def test_verify_returns_false_on_wrong_key(responder_keypairs, signed_message_factory):
    priv0, _, _, _ = responder_keypairs[0]
    _, _, pub_b64_other, _ = responder_keypairs[1]

    sig = signed_message_factory(priv0, "msg")

    # Signed by keypair 0, verified against keypair 1's pubkey -> forgery rejected
    assert verify_signature(pub_b64_other, "msg", sig) is False


def test_verify_returns_false_on_malformed_signature_b64(responder_keypairs):
    _, _, pub_b64, _ = responder_keypairs[0]
    assert verify_signature(pub_b64, "msg", "not-base64-!!!!") is False


def test_verify_returns_false_on_malformed_pubkey_b64(responder_keypairs, signed_message_factory):
    priv, _, _, _ = responder_keypairs[0]
    sig = signed_message_factory(priv, "msg")
    assert verify_signature("not-base64-!!!!", "msg", sig) is False


def test_verify_returns_false_on_rsa_pubkey(responder_keypairs, signed_message_factory):
    priv, _, _, _ = responder_keypairs[0]
    sig = signed_message_factory(priv, "msg")

    rsa_pub_b64 = make_rsa_pubkey_b64()
    # Guard at signatures.py:23 — non-EC keys are rejected without raising
    assert verify_signature(rsa_pub_b64, "msg", sig) is False


def test_verify_returns_false_on_truncated_signature(responder_keypairs, signed_message_factory):
    priv, _, pub_b64, _ = responder_keypairs[0]
    sig = signed_message_factory(priv, "msg")

    raw = base64.b64decode(sig)
    truncated = base64.b64encode(raw[:-5]).decode("utf-8")

    assert verify_signature(pub_b64, "msg", truncated) is False


@pytest.mark.parametrize("bad", ["", "AAAA", "Zg==", "ZGVhZGJlZWY="])
def test_verify_returns_false_on_random_invalid_pubkey(bad):
    """Smoke check: assorted nonsense pubkeys never raise; always return False."""
    assert verify_signature(bad, "msg", "AAAA") is False
