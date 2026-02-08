/**
 * React hook for client-side cryptography
 *
 * Manages key generation and signing operations
 * SECURITY NOTE: Keys can be exported for session persistence
 */

import { useState, useCallback } from 'react';
import {
  generateKeyPair as generateKeyPairCrypto,
  exportPublicKey,
  signMessage as signMessageCrypto,
  hashString,
  exportPrivateKey,
  importPrivateKey,
  exportPublicKeyAsJWK,
  importPublicKeyFromJWK,
} from '../services/crypto';

export function useCrypto() {
  const [keyPair, setKeyPair] = useState<CryptoKeyPair | null>(null);
  const [publicKeyBase64, setPublicKeyBase64] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  /**
   * Generate new key pair
   */
  const generateKeyPair = useCallback(async () => {
    try {
      setIsGenerating(true);
      const newKeyPair = await generateKeyPairCrypto();
      const pubKeyB64 = await exportPublicKey(newKeyPair.publicKey);

      setKeyPair(newKeyPair);
      setPublicKeyBase64(pubKeyB64);

      console.log('Key pair generated successfully');

      return { keyPair: newKeyPair, publicKey: pubKeyB64 };
    } catch (error) {
      console.error('Key generation failed:', error);
      throw error;
    } finally {
      setIsGenerating(false);
    }
  }, []);

  /**
   * Sign a message with the private key
   */
  const signMessage = useCallback(
    async (message: string): Promise<string> => {
      if (!keyPair) {
        throw new Error('No key pair available. Generate keys first.');
      }

      try {
        const signature = await signMessageCrypto(keyPair.privateKey, message);
        console.log('Message signed:', message.substring(0, 50) + '...');
        return signature;
      } catch (error) {
        console.error('Signing failed:', error);
        throw error;
      }
    },
    [keyPair]
  );

  /**
   * Create commitment hash for PPE
   */
  const createCommitment = useCallback(async (solution: string): Promise<string> => {
    try {
      const commitment = await hashString(solution);
      console.log('Commitment created for solution');
      return commitment;
    } catch (error) {
      console.error('Commitment creation failed:', error);
      throw error;
    }
  }, []);

  /**
   * Clear keys (e.g., when switching modes)
   */
  const clearKeys = useCallback(() => {
    setKeyPair(null);
    setPublicKeyBase64(null);
    console.log('Keys cleared from memory');
  }, []);

  /**
   * Export keys for localStorage storage
   * Returns JWK strings for both private and public keys
   */
  const exportKeys = useCallback(async (): Promise<{
    privateKeyJWK: string;
    publicKeyJWK: string;
  } | null> => {
    if (!keyPair) {
      console.warn('No keys to export');
      return null;
    }

    try {
      const privateKeyJWK = await exportPrivateKey(keyPair.privateKey);
      const publicKeyJWK = await exportPublicKeyAsJWK(keyPair.publicKey);

      console.log('Keys exported for storage');
      return { privateKeyJWK, publicKeyJWK };
    } catch (error) {
      console.error('Failed to export keys:', error);
      throw error;
    }
  }, [keyPair]);

  /**
   * Restore keys from JWK strings (for session recovery)
   */
  const restoreKeys = useCallback(async (
    privateKeyJWK: string,
    publicKeyJWK: string,
    publicKeyBase64Input: string
  ): Promise<void> => {
    try {
      const privateKey = await importPrivateKey(privateKeyJWK);
      const publicKey = await importPublicKeyFromJWK(publicKeyJWK);

      const restoredKeyPair: CryptoKeyPair = {
        privateKey,
        publicKey,
      };

      setKeyPair(restoredKeyPair);
      setPublicKeyBase64(publicKeyBase64Input);

      console.log('Keys restored from storage');
      console.log('Public key (base64):', publicKeyBase64Input.substring(0, 50) + '...');
    } catch (error) {
      console.error('Failed to restore keys:', error);
      throw error;
    }
  }, []);

  return {
    keyPair,
    publicKeyBase64,
    isGenerating,
    generateKeyPair,
    signMessage,
    createCommitment,
    clearKeys,
    hasKeys: keyPair !== null,
    exportKeys,
    restoreKeys,
  };
}
