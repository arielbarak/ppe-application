"""ECDSA keypair helpers shared by tests."""

import base64
import hashlib
from typing import List, Tuple

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


# Order of the SECP256R1 group; private scalars must land in [1, n-1].
_P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def deterministic_keypair(index: int) -> Keypair:
    """A *real* ECDSA P-256 keypair derived from a fixed scalar.

    Real keys, so every signature a fixture stamps actually verifies; fixed, so
    node ids -- and therefore the graph shape at a given seed -- are reproducible
    across runs. Test-only: never derive a production key this way.
    """
    digest = hashlib.sha256(f"ppe-test-key-{index}".encode("utf-8")).digest()
    scalar = int.from_bytes(digest, "big") % (_P256_ORDER - 1) + 1
    priv = ec.derive_private_key(scalar, ec.SECP256R1())
    pub = priv.public_key()
    pub_b64 = export_public_key(pub)
    return priv, pub, pub_b64, compute_node_id(pub_b64)


# Eight reproducible identities shared by the fixture layer.
STABLE_KEYPAIRS: List[Keypair] = [deterministic_keypair(i) for i in range(8)]


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
