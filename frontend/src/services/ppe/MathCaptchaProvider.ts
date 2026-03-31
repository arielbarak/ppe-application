/**
 * Math CAPTCHA PPE Provider
 *
 * Generates deterministic arithmetic problems seeded from the binding signature.
 * Difficulty is derived from η_E: difficulty = 1 - η_E
 * - Low η_E (strict) → high difficulty (larger numbers, multiplication)
 * - High η_E (lenient) → low difficulty (smaller numbers, add/subtract only)
 */

import type { PPEProvider, PPEChallenge } from './PPEProvider';

function seedToNumber(seed: string): number {
  // Derive a stable integer from any string (hex, base64, etc.)
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function generateMathChallenge(seed: string, difficulty: number = 0.5): { question: string; answer: string } {
  const seedNum = seedToNumber(seed);

  // Scale operators based on difficulty (exclude multiplication for easy)
  const operators = difficulty < 0.3 ? ['+', '-'] : ['+', '-', '*'];
  const op = operators[seedNum % operators.length];

  // Scale operand ranges based on difficulty (10-100)
  const maxValue = Math.floor(10 + difficulty * 90);
  let a = ((seedNum >> 3) % maxValue) + 1;
  let b = ((seedNum >> 11) % Math.floor(maxValue * 0.6)) + 1;

  let answer: number;
  switch (op) {
    case '+':
      answer = a + b;
      break;
    case '-':
      // Ensure non-negative result
      if (a < b) [a, b] = [b, a];
      answer = a - b;
      break;
    case '*':
      // Scale multiplication operands based on difficulty (5-20)
      const multMax = Math.floor(5 + difficulty * 15);
      a = ((seedNum >> 3) % multMax) + 1;
      b = ((seedNum >> 11) % multMax) + 1;
      answer = a * b;
      break;
    default:
      answer = a + b;
  }

  return {
    question: `${a} ${op} ${b} = ?`,
    answer: answer.toString(),
  };
}

export const MathCaptchaProvider: PPEProvider = {
  type: 'math_captcha',
  label: 'Math CAPTCHA',
  inputPlaceholder: 'Enter answer',
  inputType: 'text',

  generateChallenge(seed: string, difficulty: number = 0.5): PPEChallenge {
    const { question, answer } = generateMathChallenge(seed, difficulty);
    return {
      challengeImage: `[CAPTCHA] ${question}`,
      answer,
    };
  },

  validateSolution(seed: string, solution: string, difficulty: number = 0.5): boolean {
    const { answer } = generateMathChallenge(seed, difficulty);
    return answer.trim() === solution.trim();
  },

  extractDisplay(challengeImage: string): string {
    if (challengeImage.startsWith('[CAPTCHA] ')) {
      return challengeImage.substring(10);
    }
    return challengeImage;
  },
};
