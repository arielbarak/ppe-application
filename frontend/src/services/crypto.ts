// TODO: Switch to IndexedDB. Keys are extractable to survive refresh.

export async function generateKeyPair(): Promise<CryptoKeyPair> {
  const keyPair = await window.crypto.subtle.generateKey(
    {
      name: 'ECDSA',
      namedCurve: 'P-256',
    },
    true, // EXTRACTABLE - for session persistence
    ['sign', 'verify']
  );

  console.log('Generated ECDSA P-256 key pair (extractable for session persistence)');
  return keyPair;
}

/**
 * Export public key to base64-encoded SPKI format
 * This is sent to the server for registration
 */
export async function exportPublicKey(publicKey: CryptoKey): Promise<string> {
  const exported = await window.crypto.subtle.exportKey('spki', publicKey);
  const exportedAsBase64 = btoa(
    String.fromCharCode(...new Uint8Array(exported))
  );
  return exportedAsBase64;
}

/**
 * Sign a message with private key
 *
 * @param privateKey - The signing key (never leaves browser)
 * @param message - Message to sign
 * @returns Base64-encoded signature
 */
export async function signMessage(
  privateKey: CryptoKey,
  message: string
): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(message);

  const signature = await window.crypto.subtle.sign(
    {
      name: 'ECDSA',
      hash: 'SHA-256',
    },
    privateKey,
    data
  );

  const signatureAsBase64 = btoa(
    String.fromCharCode(...new Uint8Array(signature))
  );

  return signatureAsBase64;
}

/**
 * Compute SHA-256 hash of a string
 * Used for commitment phase in PPE
 */
export async function hashString(input: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(input);

  const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
  const hashArray = new Uint8Array(hashBuffer);

  const hashAsBase64 = btoa(
    String.fromCharCode(...hashArray)
  );

  return hashAsBase64;
}

/**
 * Verify a signature (client-side verification for debugging)
 * In production, server does the verification
 */
export async function verifySignature(
  publicKey: CryptoKey,
  message: string,
  signatureBase64: string
): Promise<boolean> {
  try {
    const encoder = new TextEncoder();
    const data = encoder.encode(message);

    // Decode base64 signature
    const signatureStr = atob(signatureBase64);
    const signature = new Uint8Array(signatureStr.length);
    for (let i = 0; i < signatureStr.length; i++) {
      signature[i] = signatureStr.charCodeAt(i);
    }

    const isValid = await window.crypto.subtle.verify(
      {
        name: 'ECDSA',
        hash: 'SHA-256',
      },
      publicKey,
      signature,
      data
    );

    return isValid;
  } catch (error) {
    console.error('Signature verification error:', error);
    return false;
  }
}

/**
 * Import public key from base64-encoded SPKI format
 * Used for verifying peer signatures
 */
export async function importPublicKey(publicKeyBase64: string): Promise<CryptoKey> {
  const binaryStr = atob(publicKeyBase64);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }

  const publicKey = await window.crypto.subtle.importKey(
    'spki',
    bytes,
    {
      name: 'ECDSA',
      namedCurve: 'P-256',
    },
    true,
    ['verify']
  );

  return publicKey;
}

/**
 * Export private key to JWK format for localStorage persistence
 * SECURITY WARNING: Only use for session persistence
 */
export async function exportPrivateKey(privateKey: CryptoKey): Promise<string> {
  const exported = await window.crypto.subtle.exportKey('jwk', privateKey);
  return JSON.stringify(exported);
}

export async function importPrivateKey(jwkString: string): Promise<CryptoKey> {
  const jwk = JSON.parse(jwkString);
  const privateKey = await window.crypto.subtle.importKey(
    'jwk',
    jwk,
    {
      name: 'ECDSA',
      namedCurve: 'P-256',
    },
    true, // extractable
    ['sign']
  );
  return privateKey;
}

/**
 * Export public key as JWK (for storage alongside private key)
 */
export async function exportPublicKeyAsJWK(publicKey: CryptoKey): Promise<string> {
  const exported = await window.crypto.subtle.exportKey('jwk', publicKey);
  return JSON.stringify(exported);
}

/**
 * Import public key from JWK format (for restoring full keypair)
 */
export async function importPublicKeyFromJWK(jwkString: string): Promise<CryptoKey> {
  const jwk = JSON.parse(jwkString);
  const publicKey = await window.crypto.subtle.importKey(
    'jwk',
    jwk,
    {
      name: 'ECDSA',
      namedCurve: 'P-256',
    },
    true,
    ['verify']
  );
  return publicKey;
}
