"""Unit tests for app.crypto.keys."""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.crypto.keys import export_public_key, generate_server_keypair


def test_generate_server_keypair_returns_p256():
    private_key, public_key = generate_server_keypair()
    assert isinstance(private_key, ec.EllipticCurvePrivateKey)
    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    assert isinstance(private_key.curve, ec.SECP256R1)


def test_export_public_key_round_trips_through_load_der_public_key():
    _, public_key = generate_server_keypair()
    pub_b64 = export_public_key(public_key)

    der = base64.b64decode(pub_b64)
    loaded = serialization.load_der_public_key(der)

    assert isinstance(loaded, ec.EllipticCurvePublicKey)
    assert loaded.public_numbers() == public_key.public_numbers()


def test_export_public_key_is_valid_base64():
    _, public_key = generate_server_keypair()
    pub_b64 = export_public_key(public_key)

    # Round-trip through base64 must succeed and produce non-empty bytes
    decoded = base64.b64decode(pub_b64)
    assert len(decoded) > 0
    # SPKI for P-256 keys is consistently 91 bytes
    assert len(decoded) == 91
