import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import {
  getSavedSessions,
  removeSession,
  clearAllSessions,
  updateSessionProgress,
  updateCertificationProgress,
  type SavedSession,
} from '../../services/storage';
import { api } from '../../services/api';

interface SessionListProps {
  onSelectSession: (session: SavedSession) => void;
  onStartNew: () => void;
  onBack: () => void;
}

// Check if a poll is finished (cancelled, results, or closed)
const isPollFinished = (status: string) =>
  ['cancelled', 'results', 'closed'].includes(status);

// Check if poll has been finished for more than 30 minutes
const isOldFinishedPoll = (session: SavedSession) => {
  if (!isPollFinished(session.pollStatus)) return false;
  const lastAccessed = new Date(session.lastAccessedAt);
  const thirtyMinutesAgo = new Date(Date.now() - 30 * 60 * 1000);
  return lastAccessed < thirtyMinutesAgo;
};

// Check if poll requires attention from user
const requiresAttention = (session: SavedSession) => {
  // PPE required in certification phase AND has incomplete PPEs
  if (session.pollStatus === 'certification') {
    // If we have progress info, check if there are pending PPEs
    if (session.verifiedEdges !== undefined && session.totalEdges !== undefined) {
      return session.verifiedEdges < session.totalEdges;
    }
    // If no progress info yet, assume attention needed
    return true;
  }
  // Vote required in voting phase (and hasn't voted)
  if (session.pollStatus === 'voting' && !session.hasVoted) {
    return true;
  }
  return false;
};

export function SessionList({ onSelectSession, onStartNew, onBack }: SessionListProps) {
  const [sessions, setSessions] = useState<SavedSession[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(true);

  useEffect(() => {
    // Get sessions and auto-remove old finished polls
    const allSessions = getSavedSessions();
    const oldFinishedPolls = allSessions.filter(isOldFinishedPoll);

    // Remove old finished polls
    oldFinishedPolls.forEach(session => {
      removeSession(session.sessionId);
    });

    // Get updated list after cleanup
    const cleanedSessions = getSavedSessions();
    setSessions(cleanedSessions);

    // Fetch fresh poll statuses for all sessions
    const refreshStatuses = async () => {
      setIsRefreshing(true);
      let hasUpdates = false;

      for (const session of cleanedSessions) {
        // Skip finished polls
        if (['cancelled', 'closed', 'results'].includes(session.pollStatus)) {
          continue;
        }

        try {
          const pollInfo = await api.getPoll(session.sessionId);

          // Update poll status if changed
          if (pollInfo.status && pollInfo.status !== session.pollStatus) {
            console.log('Updating poll status:', session.sessionId.substring(0, 8), session.pollStatus, '->', pollInfo.status);
            updateSessionProgress(session.sessionId, session.currentStep, pollInfo.status);
            hasUpdates = true;
          }

          // Fetch certification status if in certification or voting phase
          if (pollInfo.status === 'certification' || pollInfo.status === 'voting') {
            try {
              const certStatus = await api.checkNodeCertification(session.sessionId, session.nodeId);
              if (
                session.verifiedEdges !== certStatus.verified_edges ||
                session.totalEdges !== certStatus.total_edges
              ) {
                updateCertificationProgress(
                  session.sessionId,
                  certStatus.verified_edges,
                  certStatus.total_edges
                );
                hasUpdates = true;
              }
            } catch (error) {
              console.debug('Could not fetch cert status:', error);
            }
          }
        } catch (error) {
          console.debug('Could not fetch poll status:', error);
        }
      }

      // Reload sessions if there were updates
      if (hasUpdates) {
        setSessions(getSavedSessions());
      }
      setIsRefreshing(false);
    };

    refreshStatuses();
  }, []);

  const handleRemove = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Remove this saved session? You will not be able to rejoin this poll without re-registering.')) {
      removeSession(sessionId);
      setSessions(getSavedSessions());
    }
  };

  const handleClearAll = () => {
    if (confirm('Clear all saved polls? This will remove all your saved sessions and you will not be able to rejoin any of them without re-registering.')) {
      clearAllSessions();
      setSessions([]);
    }
  };

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card title={isRefreshing ? "Your Saved Polls (refreshing...)" : "Your Saved Polls"} className="max-w-2xl w-full">
        {sessions.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-600 mb-6">No saved poll sessions yet.</p>
            <p className="text-sm text-gray-500 mb-6">
              After joining a poll, your session will be saved here so you can come back later.
            </p>
            <Button onClick={onStartNew}>Join a New Poll</Button>
          </div>
        ) : (
          <>
            <div className="space-y-3 mb-6">
              {sessions.map((session) => {
                const isCancelled = session.pollStatus === 'cancelled';
                const isCompleted = session.pollStatus === 'results' || session.pollStatus === 'closed';
                const needsAttention = requiresAttention(session);

                return (
                  <div
                    key={session.sessionId}
                    className={`border-2 rounded-lg p-4 transition-colors ${
                      isCancelled
                        ? 'border-red-300 bg-red-50 cursor-not-allowed opacity-75'
                        : needsAttention
                        ? 'border-yellow-400 bg-yellow-50 hover:bg-yellow-100 cursor-pointer'
                        : isCompleted
                        ? 'border-purple-300 bg-purple-50 hover:bg-purple-100 cursor-pointer'
                        : 'border-gray-200 hover:bg-gray-50 cursor-pointer'
                    }`}
                    onClick={() => {
                      if (!isCancelled) {
                        onSelectSession(session);
                      }
                    }}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-mono text-sm font-semibold">
                            {session.sessionId}
                          </p>
                          {isCancelled && (
                            <span className="text-xs text-red-700 font-bold">❌ CANCELLED</span>
                          )}
                          {needsAttention && (
                            <span className="text-xs bg-yellow-200 text-yellow-800 px-2 py-0.5 rounded font-bold">
                              ⚠️ Requires Attention
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          Node: {session.nodeId.substring(0, 20)}...
                        </p>
                      </div>
                      <button
                        onClick={(e) => handleRemove(session.sessionId, e)}
                        className="text-red-600 hover:text-red-800 text-sm px-2"
                      >
                        Remove
                      </button>
                    </div>

                    <div className="flex items-center gap-3 text-xs">
                      <span className={`px-2 py-1 rounded-full font-medium ${
                        isCancelled ? 'bg-red-200 text-red-900' :
                        session.currentStep === 'voting' ? 'bg-green-100 text-green-800' :
                        session.currentStep === 'certification' ? 'bg-blue-100 text-blue-800' :
                        session.currentStep === 'results' ? 'bg-purple-100 text-purple-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {session.currentStep}
                      </span>
                      <span className={`${isCancelled ? 'text-red-700 font-medium' : 'text-gray-500'}`}>
                        Poll: {session.pollStatus}
                      </span>
                      <span className="text-gray-400 ml-auto">
                        {formatDate(session.lastAccessedAt)}
                      </span>
                    </div>

                    {isCancelled && (
                      <p className="text-xs text-red-700 mt-2 italic">
                        This poll was cancelled by the pollster
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex gap-4">
              <Button onClick={onStartNew} className="flex-1">
                Join New Poll
              </Button>
              <Button variant="secondary" onClick={onBack}>
                Back
              </Button>
              <Button
                variant="secondary"
                onClick={handleClearAll}
                className="text-red-600 hover:text-red-800 hover:bg-red-50"
              >
                Clear All
              </Button>
            </div>
          </>
        )}

        <div className="mt-4 p-3 bg-blue-50 rounded text-sm text-blue-800">
          <p><strong>Privacy Note:</strong> Your poll sessions and cryptographic keys are stored locally in your browser.
          Don't use this on shared or public computers. Sessions older than 7 days are automatically removed.</p>
        </div>
      </Card>
    </div>
  );
}
