/**
 * usePpeHandshake - Custom hook for P2P PPE state machine
 *
 * Encapsulates all handshake phase logic:
 * - IDLE -> SOLVING -> COMMITTING -> VERIFYING -> COMPLETE
 * - Message buffering for out-of-order arrivals
 * - Cryptographic verification flow (ECDSA binding, commit-reveal)
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { PpePayload } from '../types';
import {
  generateBoundChallenge,
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
  const sentSolution = useRef(false);
  const sentSignature = useRef(false);
  const sentComplete = useRef(false);

  // Reset tracking when session changes
  useEffect(() => {
    if (!session) {
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
        if (updated.myChallenge) {
          updated.phase = 'solving';
        }
        break;

      case 'commitment':
        updated.theirCommitmentHash = payload.commitmentHash as string;
        if (updated.myCommitment && updated.phase === 'awaiting_peer_commitment') {
          updated.phase = 'awaiting_peer_solution';
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
    const challenge = await generateBoundChallenge(ppeType, difficulty);

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
    });
  }, [ppeType, difficulty, bufferedMessages, applyMessage, sendToPeer, signMessage]);

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
      phase: prev.theirCommitmentHash ? 'awaiting_peer_solution' : 'awaiting_peer_commitment',
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
      // Both commitments -> go straight to sending solution
      if (session.myCommitment && session.theirCommitmentHash && !sentSolution.current) {
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
          session.myChallenge!.bindingSeed,
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
    session?.mySolution,
    session?.theirSolution,
    session?.mySignature,
    session?.theirSignature,
    nodeId,
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
