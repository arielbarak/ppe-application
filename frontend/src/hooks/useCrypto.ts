/**
 * React hook for client-side cryptography
 *
 * Manages key generation and signing operations. Keys are persisted to
 * IndexedDB (see services/keyStore.ts) so the responder's identity survives
 * a page refresh; clearKeys() removes both the in-memory state and the
 * IndexedDB entry.
 */

import { useState, useCallback, useEffect } from 'react';
import {
  generateKeyPair as generateKeyPairCrypto,
  exportPublicKey,
  signMessage as signMessageCrypto,
  hashString,
} from '../services/crypto';
import {
  loadKeyPair,
  saveKeyPair,
  clearKeyPair as clearKeyPairStore,
} from '../services/keyStore';

export function useCrypto() {
  const [keyPair, setKeyPair] = useState<CryptoKeyPair | null>(null);
  const [publicKeyBase64, setPublicKeyBase64] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  // On first mount, try to rehydrate a previously-persisted key pair.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const stored = await loadKeyPair();
      if (cancelled || !stored) return;
      try {
        const pubKeyB64 = await exportPublicKey(stored.publicKey);
        setKeyPair(stored);
        setPublicKeyBase64(pubKeyB64);
        console.log('Key pair rehydrated from IndexedDB');
      } catch (e) {
        console.warn('Failed to rehydrate stored key pair', e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Generate new key pair and persist it to IndexedDB.
   */
  const generateKeyPair = useCallback(async () => {
    try {
      setIsGenerating(true);
      const newKeyPair = await generateKeyPairCrypto();
      const pubKeyB64 = await exportPublicKey(newKeyPair.publicKey);

      setKeyPair(newKeyPair);
      setPublicKeyBase64(pubKeyB64);
      await saveKeyPair(newKeyPair);

      console.log('Key pair generated and persisted');

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
   * Clear keys from memory and the IndexedDB keystore.
   */
  const clearKeys = useCallback(async () => {
    setKeyPair(null);
    setPublicKeyBase64(null);
    await clearKeyPairStore();
    console.log('Keys cleared from memory and IndexedDB');
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
