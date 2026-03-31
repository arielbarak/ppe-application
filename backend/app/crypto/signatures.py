"""Server-side ECDSA signature verification. Private keys never leave the client."""

import base64
import logging

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)


def verify_signature(
    public_key_b64: str,
    message: str,
    signature_b64: str
) -> bool:
    """Verify an ECDSA-P256 signature against a base64 public key (SPKI format)."""
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = serialization.load_der_public_key(public_key_bytes)

        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            logger.warning("Public key is not an elliptic curve key")
            return False

        sig = base64.b64decode(signature_b64)

        public_key.verify(
            sig,
            message.encode('utf-8'),
            ec.ECDSA(hashes.SHA256())
        )

        logger.debug(f"Signature verification passed for message: {message[:50]}...")
        return True

    except InvalidSignature:
        logger.warning(f"Invalid signature for message: {message[:50]}...")
        return False

    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
