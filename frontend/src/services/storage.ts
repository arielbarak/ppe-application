/**
 * Storage service - NO-OP implementation
 *
 * All session data is server-side only. No browser caching.
 */

export interface SavedSession {
  sessionId: string;
  nodeId: string;
  publicKeyBase64: string;
  publicKeyJWK: string;
  privateKeyJWK: string;
  currentStep: 'registered' | 'certification' | 'voting' | 'results';
  pollStatus: string;
  hasVoted?: boolean;
  verifiedEdges?: number;
  totalEdges?: number;
  savedAt: string;
  lastAccessedAt: string;
}

export interface SavedPollsterSession {
  sessionId: string;
  question: string;
  options: string[];
  edgeProbability: number;
  effortThreshold: number;
  validityThreshold?: number;
  currentPhase: string;
  registeredNodes: number;
  savedAt: string;
  lastAccessedAt: string;
}

// All functions are no-ops - no browser caching

export function saveSession(_session: SavedSession): void {}
export function getSavedSessions(): SavedSession[] { return []; }
export function getSession(_sessionId: string): SavedSession | null { return null; }
export function touchSession(_sessionId: string): void {}
export function removeSession(_sessionId: string): void {}
export function clearAllSessions(): void {}
export function updateSessionProgress(_sessionId: string, _step: SavedSession['currentStep'], _pollStatus: string): void {}
export function markSessionAsVoted(_sessionId: string): void {}
export function updateCertificationProgress(_sessionId: string, _verifiedEdges: number, _totalEdges: number): void {}
export function cleanupOldSessions(): void {}
export function initializeStorage(): void {}

export function savePollsterSession(_session: SavedPollsterSession): void {}
export function getSavedPollsterSessions(): SavedPollsterSession[] { return []; }
export function getPollsterSession(_sessionId: string): SavedPollsterSession | null { return null; }
export function updatePollsterSessionProgress(_sessionId: string, _currentPhase: string, _registeredNodes?: number): void {}
export function touchPollsterSession(_sessionId: string): void {}
export function removePollsterSession(_sessionId: string): void {}
export function clearAllPollsterSessions(): void {}
export function cleanupOldPollsterSessions(): void {}
