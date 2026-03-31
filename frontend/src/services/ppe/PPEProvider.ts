/**
 * PPEProvider Interface - Modular Proof of Private Effort
 *
 * Defines the contract that any PPE task module must implement.
 * The core protocol layer (ECDSA binding, commit-reveal, signatures)
 * is agnostic to the specific task type. Only the "effort task" itself
 * (challenge generation, rendering, solution validation) is pluggable.
 *
 * Difficulty is derived from η_E (effort threshold): difficulty = 1 - η_E
 * - Low η_E (strict, few failures allowed) → high difficulty
 * - High η_E (lenient, more failures allowed) → low difficulty
 *
 * To add a new PPE type:
 *   1. Create a file implementing PPEProvider (e.g., StorageProofProvider.ts)
 *   2. Register it in registry.ts via registerProvider()
 *   3. Set ppe_type when creating a poll (Protocol 1: Announcement)
 *
 * The ECDSA binding and commit-reveal state machine remain in the core
 * layer (symmetricCaptcha.ts) and are NOT part of this interface.
 */

/**
 * Convert η_E threshold to difficulty level (0.0-1.0 scale).
 */
export function deriveDifficultyFromEtaE(etaE: number): number {
  return Math.max(0.0, Math.min(1.0, 1.0 - etaE));
}

/**
 * A generated challenge produced by a PPEProvider.
 *
 * The core layer wraps this with ECDSA signature binding
 * to prevent proxy attacks.
 */
export interface PPEChallenge {
  /** The challenge presented to the solver (text, base64 image, etc.) */
  challengeImage: string;
  /** The correct answer (kept secret by the generator) */
  answer: string;
}

/**
 * The pluggable PPE task interface.
 *
 * Each implementation provides a specific type of human/computational
 * effort proof (math CAPTCHA, storage proof, image recognition, etc.).
 */
export interface PPEProvider {
  /** Unique identifier for this provider (e.g., 'math_captcha', 'storage_proof') */
  readonly type: string;

  /** Human-readable label for UI display */
  readonly label: string;

  /**
   * Generate a challenge deterministically from a seed.
   *
   * The seed is the ECDSA binding computed by the core protocol layer:
   *   seed = SHA-256(ECDSA_sign(sorted(PubA, PubB)))
   *
   * The challenge MUST be deterministic given the same seed so that
   * the verifier can independently reproduce it from the binding signature.
   *
   * @param seed - Hex string from the ECDSA binding
   * @param difficulty - Difficulty level (0.0 = trivial, 1.0 = hard), derived from η_E
   * @returns The challenge image/text and correct answer
   */
  generateChallenge(seed: string, difficulty?: number): PPEChallenge;

  /**
   * Validate a solution against a challenge seed.
   *
   * Regenerates the challenge from the seed and checks the answer.
   *
   * @param seed - The ECDSA binding seed
   * @param solution - The submitted solution
   * @param difficulty - Difficulty level used when generating the challenge
   * @returns true if correct
   */
  validateSolution(seed: string, solution: string, difficulty?: number): boolean;

  /**
   * Extract a display-friendly string from the challenge image.
   *
   * Used by the UI to render the challenge to the user.
   * For simple text challenges this strips any prefix.
   * For image-based challenges this could return alt-text or a data URL.
   *
   * @param challengeImage - The raw challengeImage from generateChallenge
   * @returns A string suitable for rendering in the UI
   */
  extractDisplay(challengeImage: string): string;

  /**
   * Optional: hint text shown in the solution input field.
   */
  readonly inputPlaceholder?: string;

  /**
   * Optional: input type for the solution field (e.g., 'number', 'text').
   * Defaults to 'text'.
   */
  readonly inputType?: string;
}
