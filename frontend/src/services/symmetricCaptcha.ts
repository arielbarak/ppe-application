/**
 * Core PPE protocol layer (Protocol 3).
 *
 * Handles the crypto plumbing between two peers:
 *   - ECDSA binding: sign(sorted(PubA, PubB)) — prevents proxy attacks
 *   - Commit-reveal: SHA-256(solution:nonce) — ensures fairness
 *   - Signature swap: ECDSA P-256 — certifies the edge
 *
 * The actual effort task (math, storage proof, etc.) is injected via
 * PPEProvider. This module doesn't care what the challenge is.
 */

import { hashString } from './crypto';
import { getProvider, DEFAULT_PPE_TYPE } from './ppe/registry';

// PPE message types

export type PpeMessageType =
  | 'ppe.challenge'      // Step 1: Exchange challenges
  | 'ppe.commitment'     // Step 2: Exchange commitment hashes
  | 'ppe.solution'       // Step 3: Send actual solution
  | 'ppe.signature'      // Step 4: Send signature if solution correct
  | 'ppe.complete'       // Step 5: Finalization
  | 'ppe.error';         // Error state

export interface PpeChallenge {
  type: 'ppe.challenge';
  challengeImage: string;       // Base64 encoded challenge image or text
  challengeType: string;        // PPE provider type (e.g., 'math_captcha')
  bindingSignature: string;     // ECDSA signature of sorted(myPub, peerPub) - verified immediately
}

export interface PpeCommitment {
  type: 'ppe.commitment';
  commitmentHash: string;       // SHA256(solution + nonce)
  nonce: string;                // Random nonce for commitment
}

export interface PpeSolution {
  type: 'ppe.solution';
  solution: string;             // The actual CAPTCHA answer
  nonce: string;                // The nonce from commitment
}

export interface PpeSignature {
  type: 'ppe.signature';
  signature: string;            // ECDSA signature of peer's public key
  edgeLabel: string;            // The edge identifier
}

export interface PpeComplete {
  type: 'ppe.complete';
  success: boolean;
  reason?: string;
}

export interface PpeError {
  type: 'ppe.error';
  code: string;
  message: string;
}

export type PpeMessage =
  | PpeChallenge
  | PpeCommitment
  | PpeSolution
  | PpeSignature
  | PpeComplete
  | PpeError;

// Challenge generation with cryptographic binding

export interface GeneratedChallenge {
  question: string;             // The challenge question/text
  answer: string;               // The correct answer
  bindingSignature: string;     // ECDSA signature of binding material
  bindingSeed: string;          // Hash of signature, used as deterministic seed
  challengeImage: string;       // Rendered challenge (base64 or text)
}

/** Random hex string of `bytes` length. */
function generateRandomHex(bytes: number): string {
  const array = new Uint8Array(bytes);
  crypto.getRandomValues(array);
  return Array.from(array)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Generate a challenge cryptographically bound to both peers.
 * The actual task (math, storage, etc.) is delegated to the PPEProvider;
 * this function only handles the ECDSA binding layer.
 *
 * @param myPublicKey - My public key (base64)
 * @param peerPublicKey - Peer's public key (base64)
 * @param signMessage - Callback to sign with private key (already threaded through system)
 * @param ppeType - PPE provider type
 * @param difficulty - Difficulty level (0.0-1.0), derived from η_E as (1 - η_E)
 */
export async function generateBoundChallenge(
  myPublicKey: string,
  peerPublicKey: string,
  signMessage: (msg: string) => Promise<string>,
  ppeType: string = DEFAULT_PPE_TYPE,
  difficulty: number = 0.5
): Promise<GeneratedChallenge> {
  const provider = getProvider(ppeType);

  // sorted so both peers derive the same binding material
  const sortedKeys = [myPublicKey, peerPublicKey].sort();
  const bindingMaterial = `PPE-BIND:${sortedKeys.join(':')}`;

  const bindingSignature = await signMessage(bindingMaterial);

  // Hash the signature to produce a deterministic seed for the provider
  const bindingSeed = await hashString(bindingSignature);
  const { challengeImage, answer } = provider.generateChallenge(bindingSeed, difficulty);

  return {
    question: provider.extractDisplay(challengeImage),
    answer,
    bindingSignature,
    bindingSeed,
    challengeImage,
  };
}

/** Regenerate expected answer from seed via the provider and compare. */
export function verifySolution(
  bindingSeed: string,
  providedSolution: string,
  ppeType: string = DEFAULT_PPE_TYPE,
  difficulty: number = 0.5
): boolean {
  const provider = getProvider(ppeType);
  return provider.validateSolution(bindingSeed, providedSolution, difficulty);
}

// Commit-reveal scheme

/** SHA-256(solution:nonce) — the hiding phase of commit-reveal. */
export async function createCommitment(solution: string): Promise<{
  commitmentHash: string;
  nonce: string;
}> {
  const nonce = generateRandomHex(16);
  const preimage = `${solution}:${nonce}`;
  const commitmentHash = await hashString(preimage);

  return { commitmentHash, nonce };
}

/** Verify a commitment opening matches the hash. */
export async function verifyCommitment(
  commitmentHash: string,
  solution: string,
  nonce: string
): Promise<boolean> {
  const preimage = `${solution}:${nonce}`;
  const computedHash = await hashString(preimage);
  return computedHash === commitmentHash;
}

// Client-side PPE state machine

export type PpeState =
  | 'idle'
  | 'awaiting_challenge'       // Sent our challenge, waiting for theirs
  | 'challenges_exchanged'     // Both challenges received
  | 'awaiting_commitment'      // Sent commitment, waiting for theirs
  | 'commitments_exchanged'    // Both commitments received
  | 'awaiting_solution'        // Sent solution, waiting for theirs
  | 'solutions_exchanged'      // Both solutions received
  | 'awaiting_signature'       // Sent signature, waiting for theirs
  | 'completed'                // Success!
  | 'failed';                  // Failure

export interface PpeSessionState {
  state: PpeState;
  sessionId: string;
  myNodeId: string;
  peerNodeId: string;
  myPublicKey: string;
  peerPublicKey: string;

  // My challenge (I generated, they solve)
  myChallenge?: GeneratedChallenge;

  // Their challenge (they generated, I solve)
  theirChallengeImage?: string;
  theirBindingSignature?: string;
  mySolution?: string;         // My solution to their challenge

  // Commitment phase
  myCommitment?: { commitmentHash: string; nonce: string };
  theirCommitmentHash?: string;
  theirNonce?: string;         // Revealed with solution

  // Solution verification
  theirSolution?: string;

  // Signatures
  mySignature?: string;
  theirSignature?: string;

  // Error tracking
  errorMessage?: string;
}

/** Initialize a fresh PPE session between two peers. */
export function createPpeSession(
  sessionId: string,
  myNodeId: string,
  peerNodeId: string,
  myPublicKey: string,
  peerPublicKey: string
): PpeSessionState {
  return {
    state: 'idle',
    sessionId,
    myNodeId,
    peerNodeId,
    myPublicKey,
    peerPublicKey,
  };
}

/** Drive the PPE state machine forward based on a received message. */
export async function processMessage(
  currentState: PpeSessionState,
  message: PpeMessage,
  signMessage: (msg: string) => Promise<string>,
  ppeType: string = DEFAULT_PPE_TYPE,
  difficulty: number = 0.5
): Promise<{
  newState: PpeSessionState;
  response?: PpeMessage;
}> {
  const state = { ...currentState };

  switch (message.type) {
    case 'ppe.challenge': {
      state.theirChallengeImage = message.challengeImage;
      state.theirBindingSignature = message.bindingSignature;

      if (state.myChallenge) {
        state.state = 'challenges_exchanged';
      } else {
        state.state = 'awaiting_challenge';
      }
      return { newState: state };
    }

    case 'ppe.commitment': {
      state.theirCommitmentHash = message.commitmentHash;

      if (state.myCommitment) {
        state.state = 'commitments_exchanged';
      } else {
        state.state = 'awaiting_commitment';
      }
      return { newState: state };
    }

    case 'ppe.solution': {
      const commitmentValid = await verifyCommitment(
        state.theirCommitmentHash!,
        message.solution,
        message.nonce
      );

      if (!commitmentValid) {
        state.state = 'failed';
        state.errorMessage = 'Commitment verification failed - solution changed';
        return {
          newState: state,
          response: {
            type: 'ppe.error',
            code: 'COMMITMENT_MISMATCH',
            message: state.errorMessage,
          },
        };
      }

      state.theirSolution = message.solution;
      state.theirNonce = message.nonce;

      const isCorrect = verifySolution(state.myChallenge!.bindingSeed, message.solution, ppeType, difficulty);

      if (!isCorrect) {
        state.state = 'failed';
        state.errorMessage = 'Peer provided incorrect solution';
        return {
          newState: state,
          response: {
            type: 'ppe.complete',
            success: false,
            reason: 'Incorrect solution',
          },
        };
      }

      const edgeLabel = [state.myNodeId, state.peerNodeId].sort().join('-');
      const signaturePayload = `PPE:${edgeLabel}:${state.peerPublicKey}`;
      const signature = await signMessage(signaturePayload);

      state.mySignature = signature;

      if (state.theirSignature) {
        state.state = 'completed';
      } else {
        state.state = 'awaiting_signature';
      }

      return {
        newState: state,
        response: {
          type: 'ppe.signature',
          signature,
          edgeLabel,
        },
      };
    }

    case 'ppe.signature': {
      state.theirSignature = message.signature;

      if (state.mySignature) {
        state.state = 'completed';
      } else {
        state.state = 'awaiting_signature';
      }
      return { newState: state };
    }

    case 'ppe.complete': {
      if (message.success) {
        state.state = 'completed';
      } else {
        state.state = 'failed';
        state.errorMessage = message.reason || 'PPE failed';
      }
      return { newState: state };
    }

    case 'ppe.error': {
      state.state = 'failed';
      state.errorMessage = message.message;
      return { newState: state };
    }

    default:
      return { newState: state };
  }
}

/** Extract display text from a challenge image via the provider. */
export function extractChallengeText(
  challengeImage: string,
  ppeType: string = DEFAULT_PPE_TYPE
): string {
  const provider = getProvider(ppeType);
  return provider.extractDisplay(challengeImage);
}
