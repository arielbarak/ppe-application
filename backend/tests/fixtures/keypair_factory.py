"""ECDSA keypair helpers shared by tests."""

import base64
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from app.crypto.graph import compute_node_id
from app.crypto.keys import export_public_key, generate_server_keypair


Keypair = Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey, str, str]


def make_keypair() -> Keypair:
    """Generate (private, public, pub_b64, node_id)."""
    priv, pub = generate_server_keypair()
    pub_b64 = export_public_key(pub)
    return priv, pub, pub_b64, compute_node_id(pub_b64)


def sign_b64(priv: ec.EllipticCurvePrivateKey, message: str) -> str:
    """ECDSA-P256 sign and base64-encode."""
    sig = priv.sign(message.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode("utf-8")


def make_rsa_pubkey_b64(key_size: int = 2048) -> str:
    """RSA pubkey as base64 SPKI; used to test that verify_signature rejects non-EC keys."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(raw).decode("utf-8")
