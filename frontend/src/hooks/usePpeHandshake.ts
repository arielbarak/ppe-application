/**
 * usePpeHandshake - Custom hook for P2P PPE state machine
 *
 * Encapsulates all handshake phase logic:
 * - IDLE -> SOLVING -> COMMITTING -> REVEALING -> VERIFYING -> COMPLETE
 * - Message buffering for out-of-order arrivals
 * - Cryptographic verification flow
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { PpePayload } from '../types';
import {
  generateBoundChallenge,
  verifyChallengeBound,
  verifySolution,
  createCommitment,
  verifyCommitment,
  type GeneratedChallenge,
} from '../services/symmetricCaptcha';

export type HandshakePhase =
  | 'idle'
  | 'awaiting_peer_challenge'
  | 'solving'
  | 'awaiting_peer_commitment'
  | 'awaiting_peer_key'
  | 'verifying_binding'
  | 'awaiting_peer_solution'
  | 'signing'
  | 'completed'
  | 'failed';

interface PpeSession {
  sessionId: string;
  peerNodeId: string;
  peerPublicKey: string;
  phase: HandshakePhase;
  myChallenge?: GeneratedChallenge;
  theirChallengeImage?: string;
  theirHmacBinding?: string;
  theirMacKey?: string;
  mySolution?: string;
  myCommitment?: { commitmentHash: string; nonce: string };
  theirCommitmentHash?: string;
  theirNonce?: string;
  theirSolution?: string;
  mySignature?: string;
  theirSignature?: string;
  solutionInput?: string;
  errorMessage?: string;
}

interface UsePpeHandshakeOptions {
  nodeId: string;
  publicKeyBase64: string;
  ppeType: string;
  difficulty: number;
  sendToPeer: (targetNode: string, payload: PpePayload) => void;
  sendMessage: (type: string, data: any) => void;
  signMessage: (message: string) => Promise<string>;
  onComplete: (peerNodeId: string, success: boolean) => void;
}

interface UsePpeHandshakeReturn {
  session: PpeSession | null;
  phase: HandshakePhase;
  isActive: boolean;

  // Actions
  initiate: (targetNode: string, targetPublicKey: string, existingSessionId?: string) => Promise<void>;
  setSolutionInput: (value: string) => void;
  submitSolution: () => Promise<void>;
  cancel: () => void;

  // Message handling
  handlePeerMessage: (fromNode: string, payload: PpePayload) => void;
  updateSessionId: (sessionId: string) => void;

  // Buffered messages for peers without active session
  getBufferedMessages: (peerId: string) => PpePayload[];
  clearBuffer: (peerId: string) => void;
}

export function usePpeHandshake(options: UsePpeHandshakeOptions): UsePpeHandshakeReturn {
  const {
    nodeId,
    publicKeyBase64,
    ppeType,
    difficulty,
    sendToPeer,
    sendMessage,
    signMessage,
    onComplete,
  } = options;

  const [session, setSession] = useState<PpeSession | null>(null);
  const [bufferedMessages, setBufferedMessages] = useState<Record<string, PpePayload[]>>({});

  // Refs to track what we've sent (prevent duplicates)
  const sentKeyReveal = useRef(false);
  const sentSolution = useRef(false);
  const sentSignature = useRef(false);
  const sentComplete = useRef(false);

  // Reset tracking when session changes
  useEffect(() => {
    if (!session) {
      sentKeyReveal.current = false;
      sentSolution.current = false;
      sentSignature.current = false;
      sentComplete.current = false;
    }
  }, [session?.sessionId]);

  // Apply a peer message to current session
  const applyMessage = useCallback((prev: PpeSession, payload: PpePayload): PpeSession => {
    const updated = { ...prev };

    switch (payload.type) {
      case 'challenge':
        updated.theirChallengeImage = payload.challengeImage as string;
        updated.theirHmacBinding = payload.hmacBinding as string;
        if (updated.myChallenge) {
          updated.phase = 'solving';
        }
        break;

      case 'commitment':
        updated.theirCommitmentHash = payload.commitmentHash as string;
        if (updated.myCommitment && updated.phase === 'awaiting_peer_commitment') {
          updated.phase = 'awaiting_peer_key';
        }
        break;

      case 'key_reveal':
        updated.theirMacKey = payload.macKey as string;
        if (updated.myCommitment && updated.theirCommitmentHash) {
          updated.phase = 'verifying_binding';
        }
        break;

      case 'solution':
        updated.theirSolution = payload.solution as string;
        updated.theirNonce = payload.nonce as string;
        break;

      case 'signature':
        updated.theirSignature = payload.signature as string;
        break;

      case 'error':
        updated.phase = 'failed';
        updated.errorMessage = payload.message as string;
        break;
    }

    return updated;
  }, []);

  // Handle incoming peer message
  const handlePeerMessage = useCallback((fromNode: string, payload: PpePayload) => {
    setSession(prev => {
      if (prev && prev.peerNodeId === fromNode) {
        return applyMessage(prev, payload);
      }
      return prev;
    });

    // Buffer if no active session for this peer
    setBufferedMessages(prev => {
      // Only buffer if we don't have an active session with this peer
      return prev;
    });

    // Use functional update to check if message was applied
    let wasApplied = false;
    setSession(prev => {
      if (prev && prev.peerNodeId === fromNode) {
        wasApplied = true;
      }
      return prev;
    });

    if (!wasApplied) {
      setBufferedMessages(prev => ({
        ...prev,
        [fromNode]: [...(prev[fromNode] || []), payload],
      }));
    }
  }, [applyMessage]);

  // Initiate PPE with a peer
  const initiate = useCallback(async (
    targetNode: string,
    targetPublicKey: string,
    existingSessionId?: string
  ) => {
    const challenge = await generateBoundChallenge(
      publicKeyBase64,
      targetPublicKey,
      ppeType,
      difficulty
    );

    let initialSession: PpeSession = {
      sessionId: existingSessionId || '',
      peerNodeId: targetNode,
      peerPublicKey: targetPublicKey,
      phase: 'awaiting_peer_challenge',
      myChallenge: challenge,
    };

    // Apply any buffered messages
    const buffered = bufferedMessages[targetNode] || [];
    if (buffered.length > 0) {
      for (const msg of buffered) {
        initialSession = applyMessage(initialSession, msg);
      }
      setBufferedMessages(prev => {
        const { [targetNode]: _, ...rest } = prev;
        return rest;
      });
    }

    setSession(initialSession);

    // Send challenge to peer
    sendToPeer(targetNode, {
      type: 'challenge',
      challengeImage: challenge.challengeImage,
      challengeType: ppeType,
      hmacBinding: challenge.hmacBinding,
    });
  }, [publicKeyBase64, ppeType, difficulty, bufferedMessages, applyMessage, sendToPeer]);

  // Update session ID (from server confirmation)
  const updateSessionId = useCallback((sessionId: string) => {
    setSession(prev => prev ? { ...prev, sessionId } : null);
  }, []);

  // Set solution input
  const setSolutionInput = useCallback((value: string) => {
    setSession(prev => prev ? { ...prev, solutionInput: value } : null);
  }, []);

  // Submit solution
  const submitSolution = useCallback(async () => {
    if (!session || !session.solutionInput) return;

    const solution = session.solutionInput.trim();
    const commitment = await createCommitment(solution);

    sendToPeer(session.peerNodeId, {
      type: 'commitment',
      commitmentHash: commitment.commitmentHash,
      nonce: '',
    });

    setSession(prev => prev ? {
      ...prev,
      mySolution: solution,
      myCommitment: commitment,
      phase: prev.theirCommitmentHash ? 'awaiting_peer_key' : 'awaiting_peer_commitment',
    } : null);
  }, [session, sendToPeer]);

  // Cancel current session
  const cancel = useCallback(() => {
    setSession(null);
  }, []);

  // State machine processing
  useEffect(() => {
    if (!session) return;

    const processPhase = async () => {
      // Both commitments -> send key reveal
      if (session.myCommitment && session.theirCommitmentHash && !sentKeyReveal.current) {
        sentKeyReveal.current = true;

        sendToPeer(session.peerNodeId, {
          type: 'key_reveal',
          macKey: session.myChallenge!.macKey,
        });

        setSession(prev => {
          if (!prev) return null;
          if (prev.phase === 'awaiting_peer_commitment' || prev.phase === 'awaiting_peer_key') {
            return {
              ...prev,
              phase: prev.theirMacKey ? 'verifying_binding' : 'awaiting_peer_key',
            };
          }
          return prev;
        });
      }

      // Have peer key but stuck -> advance
      if (session.phase === 'awaiting_peer_key' && session.theirMacKey && session.myCommitment) {
        setSession(prev => prev ? { ...prev, phase: 'verifying_binding' } : null);
        return;
      }

      // Verify binding
      if (session.phase === 'verifying_binding' && session.theirMacKey && !sentSolution.current) {
        const isValid = await verifyChallengeBound(
          session.theirHmacBinding!,
          session.theirMacKey,
          publicKeyBase64,
          session.peerPublicKey
        );

        if (!isValid) {
          setSession(prev => prev ? {
            ...prev,
            phase: 'failed',
            errorMessage: 'Challenge binding verification failed - potential proxy attack!',
          } : null);

          sendToPeer(session.peerNodeId, {
            type: 'error',
            code: 'BINDING_FAILED',
            message: 'Challenge binding verification failed',
          });
          return;
        }

        sentSolution.current = true;

        sendToPeer(session.peerNodeId, {
          type: 'solution',
          solution: session.mySolution,
          nonce: session.myCommitment!.nonce,
        });

        setSession(prev => prev ? { ...prev, phase: 'awaiting_peer_solution' } : null);
      }

      // Both solutions -> verify and sign
      if (session.mySolution && session.theirSolution && !sentSignature.current) {
        sentSignature.current = true;

        const commitmentValid = await verifyCommitment(
          session.theirCommitmentHash!,
          session.theirSolution,
          session.theirNonce!
        );

        if (!commitmentValid) {
          setSession(prev => prev ? {
            ...prev,
            phase: 'failed',
            errorMessage: 'Peer commitment verification failed',
          } : null);
          return;
        }

        const solutionCorrect = verifySolution(
          session.myChallenge!.hmacBinding,
          session.theirSolution,
          ppeType,
          difficulty
        );

        if (!solutionCorrect) {
          setSession(prev => prev ? {
            ...prev,
            phase: 'failed',
            errorMessage: 'Peer provided incorrect solution',
          } : null);

          sendMessage('ppe.complete', {
            ppe_session_id: session.sessionId,
            peer_node: session.peerNodeId,
            success: false,
          });
          return;
        }

        const edgeLabel = [nodeId, session.peerNodeId].sort().join('-');
        const signaturePayload = `PPE:${edgeLabel}:${session.peerPublicKey}`;
        const signature = await signMessage(signaturePayload);

        sendToPeer(session.peerNodeId, {
          type: 'signature',
          signature,
          edgeLabel,
        });

        setSession(prev => {
          if (!prev) return null;

          if (prev.theirSignature) {
            // Both signatures ready
            sendMessage('ppe.complete', {
              ppe_session_id: prev.sessionId,
              peer_node: prev.peerNodeId,
              success: true,
              signature: prev.theirSignature,
            });

            sentComplete.current = true;
            onComplete(prev.peerNodeId, true);

            setTimeout(() => setSession(null), 2000);
            return { ...prev, mySignature: signature, phase: 'completed' };
          }

          return { ...prev, mySignature: signature, phase: 'signing' };
        });
      }

      // Both signatures (delayed case)
      if (session.mySignature && session.theirSignature && !sentComplete.current) {
        sentComplete.current = true;

        sendMessage('ppe.complete', {
          ppe_session_id: session.sessionId,
          peer_node: session.peerNodeId,
          success: true,
          signature: session.theirSignature,
        });

        setSession(prev => prev ? { ...prev, phase: 'completed' } : null);
        onComplete(session.peerNodeId, true);

        setTimeout(() => setSession(null), 2000);
      }
    };

    processPhase();
  }, [
    session?.phase,
    session?.myCommitment,
    session?.theirCommitmentHash,
    session?.theirMacKey,
    session?.mySolution,
    session?.theirSolution,
    session?.mySignature,
    session?.theirSignature,
    nodeId,
    publicKeyBase64,
    ppeType,
    difficulty,
    sendToPeer,
    sendMessage,
    signMessage,
    onComplete,
  ]);

  return {
    session,
    phase: session?.phase || 'idle',
    isActive: session !== null && session.phase !== 'completed' && session.phase !== 'failed',

    initiate,
    setSolutionInput,
    submitSolution,
    cancel,

    handlePeerMessage,
    updateSessionId,

    getBufferedMessages: (peerId: string) => bufferedMessages[peerId] || [],
    clearBuffer: (peerId: string) => {
      setBufferedMessages(prev => {
        const { [peerId]: _, ...rest } = prev;
        return rest;
      });
    },
  };
}
