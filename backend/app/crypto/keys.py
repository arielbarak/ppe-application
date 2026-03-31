"""ECDSA P-256 key utilities. Responder keys are generated client-side only."""

import base64
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)


def generate_server_keypair():
    """Generate an ECDSA P-256 keypair for the pollster."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


def export_public_key(public_key) -> str:
    """Serialize public key to base64 SPKI/DER."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.b64encode(raw).decode('utf-8')
