/**
 * localStorage service for persisting responder sessions
 *
 * Allows responders to close browser and rejoin polls later
 *
 * Storage format:
 * - Key: 'ppe_sessions'
 * - Value: JSON array of SavedSession objects
 */

export interface SavedSession {
  sessionId: string;
  nodeId: string;
  publicKeyBase64: string;  // SPKI format for API
  publicKeyJWK: string;     // JWK format for import
  privateKeyJWK: string;    // JWK format for import
  currentStep: 'registered' | 'certification' | 'voting' | 'results';
  pollStatus: string;
  hasVoted?: boolean;       // Track if user has submitted their vote
  verifiedEdges?: number;   // Number of completed PPEs
  totalEdges?: number;      // Total PPEs needed
  savedAt: string;          // ISO timestamp
  lastAccessedAt: string;   // ISO timestamp
}

const STORAGE_KEY = 'ppe_sessions';
const MAX_SAVED_SESSIONS = 10;

/**
 * Save a responder session to localStorage
 */
export function saveSession(session: SavedSession): void {
  try {
    const sessions = getSavedSessions();

    // Remove existing session with same sessionId if exists
    const filtered = sessions.filter(s => s.sessionId !== session.sessionId);

    // Add new session at the beginning
    filtered.unshift({
      ...session,
      lastAccessedAt: new Date().toISOString(),
    });

    // Keep only last N sessions
    const trimmed = filtered.slice(0, MAX_SAVED_SESSIONS);

    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
    console.log('Session saved to localStorage:', session.sessionId);
  } catch (error) {
    console.error('Failed to save session:', error);
    // Handle quota exceeded
    if (error instanceof Error && error.name === 'QuotaExceededError') {
      // Try to make space by removing oldest session
      try {
        const sessions = getSavedSessions();
        if (sessions.length > 0) {
          sessions.pop();
          localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
          // Retry save
          saveSession(session);
        }
      } catch (retryError) {
        console.error('Failed to save even after cleanup:', retryError);
      }
    }
  }
}

/**
 * Get all saved sessions from localStorage
 */
export function getSavedSessions(): SavedSession[] {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return [];

    const sessions = JSON.parse(data);
    return Array.isArray(sessions) ? sessions : [];
  } catch (error) {
    console.error('Failed to load sessions:', error);
    return [];
  }
}

/**
 * Get a specific session by sessionId
 */
export function getSession(sessionId: string): SavedSession | null {
  const sessions = getSavedSessions();
  return sessions.find(s => s.sessionId === sessionId) || null;
}

/**
 * Update last accessed time for a session
 */
export function touchSession(sessionId: string): void {
  const sessions = getSavedSessions();
  const updated = sessions.map(s =>
    s.sessionId === sessionId
      ? { ...s, lastAccessedAt: new Date().toISOString() }
      : s
  );
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
}

/**
 * Remove a session from localStorage
 */
export function removeSession(sessionId: string): void {
  const sessions = getSavedSessions();
  const filtered = sessions.filter(s => s.sessionId !== sessionId);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  console.log('Session removed:', sessionId);
}

/**
 * Clear all saved sessions
 */
export function clearAllSessions(): void {
  localStorage.removeItem(STORAGE_KEY);
  console.log('All sessions cleared');
}

/**
 * Update session step/status
 */
export function updateSessionProgress(
  sessionId: string,
  step: SavedSession['currentStep'],
  pollStatus: string
): void {
  const sessions = getSavedSessions();
  const updated = sessions.map(s =>
    s.sessionId === sessionId
      ? { ...s, currentStep: step, pollStatus, lastAccessedAt: new Date().toISOString() }
      : s
  );
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
}

/**
 * Mark session as voted
 */
export function markSessionAsVoted(sessionId: string): void {
  const sessions = getSavedSessions();
  const updated = sessions.map(s =>
    s.sessionId === sessionId
      ? { ...s, hasVoted: true, lastAccessedAt: new Date().toISOString() }
      : s
  );
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  console.log('Session marked as voted:', sessionId);
}

/**
 * Update certification progress
 */
export function updateCertificationProgress(
  sessionId: string,
  verifiedEdges: number,
  totalEdges: number
): void {
  const sessions = getSavedSessions();
  const updated = sessions.map(s =>
    s.sessionId === sessionId
      ? { ...s, verifiedEdges, totalEdges, lastAccessedAt: new Date().toISOString() }
      : s
  );
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
}

/**
 * Clean up old sessions (older than 7 days)
 */
export function cleanupOldSessions(): void {
  const sessions = getSavedSessions();
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  const active = sessions.filter(s => {
    const lastAccessed = new Date(s.lastAccessedAt);
    return lastAccessed > sevenDaysAgo;
  });

  if (active.length !== sessions.length) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(active));
    console.log(`Cleaned up ${sessions.length - active.length} old sessions`);
  }
}

/**
 * Initialize storage (call on app startup)
 * Performs cleanup of old sessions
 */
export function initializeStorage(): void {
  cleanupOldSessions();
  cleanupOldPollsterSessions();
  console.log('Storage initialized');
}

// Pollster Session Storage
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

const POLLSTER_STORAGE_KEY = 'ppe_pollster_sessions';
const MAX_POLLSTER_SESSIONS = 10;

/**
 * Save a pollster session to localStorage
 */
export function savePollsterSession(session: SavedPollsterSession): void {
  try {
    const sessions = getSavedPollsterSessions();

    // Remove existing session with same sessionId if exists
    const filtered = sessions.filter(s => s.sessionId !== session.sessionId);

    // Add new session at the beginning
    filtered.unshift({
      ...session,
      lastAccessedAt: new Date().toISOString(),
    });

    // Keep only last N sessions
    const trimmed = filtered.slice(0, MAX_POLLSTER_SESSIONS);

    localStorage.setItem(POLLSTER_STORAGE_KEY, JSON.stringify(trimmed));
    console.log('Pollster session saved:', session.sessionId);
  } catch (error) {
    console.error('Failed to save pollster session:', error);
  }
}

/**
 * Get all saved pollster sessions from localStorage
 */
export function getSavedPollsterSessions(): SavedPollsterSession[] {
  try {
    const data = localStorage.getItem(POLLSTER_STORAGE_KEY);
    if (!data) return [];

    const sessions = JSON.parse(data);
    return Array.isArray(sessions) ? sessions : [];
  } catch (error) {
    console.error('Failed to load pollster sessions:', error);
    return [];
  }
}

/**
 * Get a specific pollster session by sessionId
 */
export function getPollsterSession(sessionId: string): SavedPollsterSession | null {
  const sessions = getSavedPollsterSessions();
  return sessions.find(s => s.sessionId === sessionId) || null;
}

/**
 * Update pollster session phase and node count
 */
export function updatePollsterSessionProgress(
  sessionId: string,
  currentPhase: string,
  registeredNodes?: number
): void {
  const sessions = getSavedPollsterSessions();
  const updated = sessions.map(s =>
    s.sessionId === sessionId
      ? {
          ...s,
          currentPhase,
          registeredNodes: registeredNodes ?? s.registeredNodes,
          lastAccessedAt: new Date().toISOString(),
        }
      : s
  );
  localStorage.setItem(POLLSTER_STORAGE_KEY, JSON.stringify(updated));
}

/**
 * Touch pollster session (update last accessed time)
 */
export function touchPollsterSession(sessionId: string): void {
  const sessions = getSavedPollsterSessions();
  const updated = sessions.map(s =>
    s.sessionId === sessionId
      ? { ...s, lastAccessedAt: new Date().toISOString() }
      : s
  );
  localStorage.setItem(POLLSTER_STORAGE_KEY, JSON.stringify(updated));
}

/**
 * Remove a pollster session from localStorage
 */
export function removePollsterSession(sessionId: string): void {
  const sessions = getSavedPollsterSessions();
  const filtered = sessions.filter(s => s.sessionId !== sessionId);
  localStorage.setItem(POLLSTER_STORAGE_KEY, JSON.stringify(filtered));
  console.log('Pollster session removed:', sessionId);
}

/**
 * Clear all saved pollster sessions
 */
export function clearAllPollsterSessions(): void {
  localStorage.removeItem(POLLSTER_STORAGE_KEY);
  console.log('All pollster sessions cleared');
}

/**
 * Clean up old pollster sessions (older than 7 days)
 */
export function cleanupOldPollsterSessions(): void {
  const sessions = getSavedPollsterSessions();
  const now = new Date();
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  const active = sessions.filter(s => {
    const lastAccessed = new Date(s.lastAccessedAt);
    return lastAccessed > sevenDaysAgo;
  });

  if (active.length !== sessions.length) {
    localStorage.setItem(POLLSTER_STORAGE_KEY, JSON.stringify(active));
    console.log(`Cleaned up ${sessions.length - active.length} old pollster sessions`);
  }
}
