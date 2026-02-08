/**
 * PPE Provider Registry
 *
 * Central registry for all available PPE task modules.
 * New providers are registered here and resolved by type string.
 *
 * Usage:
 *   import { getProvider } from '../services/ppe';
 *   const provider = getProvider('math_captcha');
 */

import type { PPEProvider } from './PPEProvider';
import { deriveDifficultyFromEtaE } from './PPEProvider';
import { MathCaptchaProvider } from './MathCaptchaProvider';

export { deriveDifficultyFromEtaE };

const providers = new Map<string, PPEProvider>();

/**
 * Register a PPE provider. Call this at module load time.
 */
export function registerProvider(provider: PPEProvider): void {
  if (providers.has(provider.type)) {
    console.warn(`PPE provider '${provider.type}' is already registered, overwriting`);
  }
  providers.set(provider.type, provider);
}

/**
 * Get a registered provider by type.
 * Throws if not found.
 */
export function getProvider(type: string): PPEProvider {
  const provider = providers.get(type);
  if (!provider) {
    throw new Error(
      `Unknown PPE provider type '${type}'. ` +
      `Available: [${Array.from(providers.keys()).join(', ')}]`
    );
  }
  return provider;
}

/**
 * List all registered provider types (for UI dropdowns, etc.)
 */
export function listProviders(): { type: string; label: string }[] {
  return Array.from(providers.values()).map(p => ({
    type: p.type,
    label: p.label,
  }));
}

/** Default PPE type used when none is specified */
export const DEFAULT_PPE_TYPE = 'math_captcha';

// Register built-in providers
registerProvider(MathCaptchaProvider);
