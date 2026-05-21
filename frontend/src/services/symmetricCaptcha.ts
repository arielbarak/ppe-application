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

export interface GeneratedChallenge {
  question: string;
  answer: string;
  bindingSeed: string;
  challengeImage: string;
}

/** Random hex string of `bytes` length. */
function generateRandomHex(bytes: number): string {
  const array = new Uint8Array(bytes);
  crypto.getRandomValues(array);
  return Array.from(array)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

export async function generateBoundChallenge(
  ppeType: string = DEFAULT_PPE_TYPE,
  difficulty: number = 0.5
): Promise<GeneratedChallenge> {
  const provider = getProvider(ppeType);
  const bindingSeed = generateRandomHex(32);
  const { challengeImage, answer } = provider.generateChallenge(bindingSeed, difficulty);

  return {
    question: provider.extractDisplay(challengeImage),
    answer,
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

/** Extract display text from a challenge image via the provider. */
export function extractChallengeText(
  challengeImage: string,
  ppeType: string = DEFAULT_PPE_TYPE
): string {
  const provider = getProvider(ppeType);
  return provider.extractDisplay(challengeImage);
}
