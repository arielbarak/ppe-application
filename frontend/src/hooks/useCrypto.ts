/**
 * React hook for client-side cryptography
 *
 * Manages key generation and signing operations.
 * Keys are ephemeral and exist only in memory for the current session.
 */

import { useState, useCallback } from 'react';
import {
  generateKeyPair as generateKeyPairCrypto,
  exportPublicKey,
  signMessage as signMessageCrypto,
  hashString,
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

  return {
    keyPair,
    publicKeyBase64,
    isGenerating,
    generateKeyPair,
    signMessage,
    createCommitment,
    clearKeys,
    hasKeys: keyPair !== null,
  };
}
