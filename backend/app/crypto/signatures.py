"""Server-side ECDSA signature verification. Private keys never leave the client."""

import base64
import logging

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

logger = logging.getLogger(__name__)

# A raw ECDSA-P256 signature in IEEE P1363 format is exactly r||s, each a
# 32-byte big-endian integer.
_P256_RAW_SIG_LEN = 64


def _p1363_to_der(sig: bytes) -> bytes | None:
    """Convert a raw P1363 (r||s) P-256 signature to ASN.1 DER, or None if not raw.

    The browser's Web Crypto ``subtle.sign`` emits signatures in the raw P1363
    format, whereas ``cryptography``'s ``verify`` expects ASN.1 DER. Without this
    conversion every genuine client-produced signature would be rejected.
    """
    if len(sig) != _P256_RAW_SIG_LEN:
        return None
    r = int.from_bytes(sig[:32], byteorder="big")
    s = int.from_bytes(sig[32:], byteorder="big")
    return encode_dss_signature(r, s)


def verify_signature(
    public_key_b64: str,
    message: str,
    signature_b64: str
) -> bool:
    """Verify an ECDSA-P256 signature against a base64 public key (SPKI format).

    Accepts both ASN.1 DER signatures (as produced by ``cryptography``) and raw
    P1363 ``r||s`` signatures (as produced by the browser's Web Crypto API).
    """
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = serialization.load_der_public_key(public_key_bytes)

        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            logger.warning("Public key is not an elliptic curve key")
            return False

        sig = base64.b64decode(signature_b64)
        message_bytes = message.encode('utf-8')

        # First try the raw P1363 form used by the browser clients; fall back to
        # the DER form used server-side. Whichever decodes and verifies wins.
        der_from_raw = _p1363_to_der(sig)
        candidates = [c for c in (der_from_raw, sig) if c is not None]

        for candidate in candidates:
            try:
                public_key.verify(
                    candidate,
                    message_bytes,
                    ec.ECDSA(hashes.SHA256())
                )
                logger.debug(f"Signature verification passed for message: {message[:50]}...")
                return True
            except InvalidSignature:
                continue

        logger.warning(f"Invalid signature for message: {message[:50]}...")
        return False

    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
