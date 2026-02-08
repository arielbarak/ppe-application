import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import {
  getSavedPollsterSessions,
  removePollsterSession,
  clearAllPollsterSessions,
  type SavedPollsterSession,
} from '../../services/storage';

interface PollsterSessionListProps {
  onSelectSession: (session: SavedPollsterSession) => void;
  onStartNew: () => void;
  onBack: () => void;
}

// Check if a poll is finished
const isPollFinished = (phase: string) =>
  ['results', 'closed', 'cancelled'].includes(phase);

// Check if poll has been finished for more than 30 minutes
const isOldFinishedPoll = (session: SavedPollsterSession) => {
  if (!isPollFinished(session.currentPhase)) return false;
  const lastAccessed = new Date(session.lastAccessedAt);
  const thirtyMinutesAgo = new Date(Date.now() - 30 * 60 * 1000);
  return lastAccessed < thirtyMinutesAgo;
};

export function PollsterSessionList({ onSelectSession, onStartNew, onBack }: PollsterSessionListProps) {
  const [sessions, setSessions] = useState<SavedPollsterSession[]>([]);

  useEffect(() => {
    // Get sessions and auto-remove old finished polls
    const allSessions = getSavedPollsterSessions();
    const oldFinishedPolls = allSessions.filter(isOldFinishedPoll);

    // Remove old finished polls
    oldFinishedPolls.forEach(session => {
      removePollsterSession(session.sessionId);
    });

    // Get updated list after cleanup
    setSessions(getSavedPollsterSessions());
  }, []);

  const handleRemove = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Remove this poll? You will lose access to manage it.')) {
      removePollsterSession(sessionId);
      setSessions(getSavedPollsterSessions());
    }
  };

  const handleClearAll = () => {
    if (confirm('Clear all saved polls? You will lose access to manage all of them.')) {
      clearAllPollsterSessions();
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

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case 'registration':
        return 'bg-blue-100 text-blue-800';
      case 'certification':
        return 'bg-yellow-100 text-yellow-800';
      case 'voting':
        return 'bg-green-100 text-green-800';
      case 'results':
        return 'bg-purple-100 text-purple-800';
      case 'cancelled':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card title="Your Polls" className="max-w-2xl w-full">
        {sessions.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-600 mb-6">No saved polls yet.</p>
            <p className="text-sm text-gray-500 mb-6">
              After creating a poll, it will be saved here so you can manage it later.
            </p>
            <div className="flex gap-4 justify-center">
              <Button onClick={onStartNew}>Create New Poll</Button>
              <Button variant="secondary" onClick={onBack}>
                Back
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="space-y-3 mb-6">
              {sessions.map((session) => {
                const isCancelled = session.currentPhase === 'cancelled';
                const isCompleted = session.currentPhase === 'results';

                return (
                  <div
                    key={session.sessionId}
                    className={`border-2 rounded-lg p-4 transition-colors ${
                      isCancelled
                        ? 'border-red-300 bg-red-50 hover:bg-red-100 cursor-pointer'
                        : isCompleted
                        ? 'border-purple-300 bg-purple-50 hover:bg-purple-100 cursor-pointer'
                        : 'border-gray-200 hover:bg-gray-50 cursor-pointer'
                    }`}
                    onClick={() => onSelectSession(session)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <p className="font-medium text-gray-900 mb-1">
                          {session.question.length > 60
                            ? session.question.substring(0, 60) + '...'
                            : session.question}
                        </p>
                        <p className="font-mono text-xs text-gray-500">
                          ID: {session.sessionId}
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
                      <span className={`px-2 py-1 rounded-full font-medium ${getPhaseColor(session.currentPhase)}`}>
                        {session.currentPhase}
                      </span>
                      <span className="text-gray-500">
                        {session.registeredNodes} participants
                      </span>
                      <span className="text-gray-400 ml-auto">
                        {formatDate(session.lastAccessedAt)}
                      </span>
                    </div>

                    {isCancelled && (
                      <p className="text-xs text-red-700 mt-2 italic">
                        This poll was cancelled
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex gap-4">
              <Button onClick={onStartNew} className="flex-1">
                Create New Poll
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
          <p>
            <strong>Note:</strong> Your poll sessions are stored locally in your browser.
            Polls older than 7 days are automatically removed.
          </p>
        </div>
      </Card>
    </div>
  );
}
