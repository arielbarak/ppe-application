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


def verify_multiple_signatures(
    signatures: list,
    expected_message_fn=None
) -> dict:
    """Batch-verify a list of {public_key, message, signature} dicts."""
    results = {
        'total': len(signatures),
        'valid': 0,
        'invalid': 0,
        'details': []
    }

    for idx, sig_data in enumerate(signatures):
        try:
            public_key = sig_data.get('public_key')
            message = sig_data.get('message')
            signature = sig_data.get('signature')

            if not all([public_key, message, signature]):
                results['invalid'] += 1
                results['details'].append({
                    'index': idx,
                    'valid': False,
                    'error': 'Missing required fields'
                })
                continue

            if expected_message_fn and not expected_message_fn(message):
                results['invalid'] += 1
                results['details'].append({
                    'index': idx,
                    'valid': False,
                    'error': 'Message validation failed'
                })
                continue

            is_valid = verify_signature(public_key, message, signature)

            if is_valid:
                results['valid'] += 1
            else:
                results['invalid'] += 1

            results['details'].append({
                'index': idx,
                'valid': is_valid
            })

        except Exception as e:
            logger.error(f"Error verifying signature {idx}: {e}")
            results['invalid'] += 1
            results['details'].append({
                'index': idx,
                'valid': False,
                'error': str(e)
            })

    return results
