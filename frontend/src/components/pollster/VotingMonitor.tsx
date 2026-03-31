import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { api } from '../../services/api';

interface VotingMonitorProps {
  sessionId: string;
  onPublish: () => void;
}

export function VotingMonitor({ sessionId, onPublish }: VotingMonitorProps) {
  const [voteCount, setVoteCount] = useState(0);
  const [totalRegistered, setTotalRegistered] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const fetchVoteCount = async () => {
    setIsLoading(true);
    try {
      const result = await api.getVoteCount(sessionId);
      setVoteCount(result.total_votes);
      setTotalRegistered(result.total_registered);
    } catch (error) {
      console.error('Failed to fetch vote count:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchVoteCount();
    const interval = setInterval(fetchVoteCount, 3000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const publishResults = async () => {
    try {
      await api.publishResults(sessionId);
      onPublish();
    } catch (error) {
      console.error('Failed to publish results:', error);
    }
  };

  const votingProgress = totalRegistered > 0 ? (voteCount / totalRegistered) * 100 : 0;

  return (
    <Card title="Voting Phase (Protocol 4)">
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-xl font-bold">Vote Collection</h3>
            <p className="text-sm text-gray-600">
              Responders submitting votes with collected signatures
            </p>
          </div>
          <Button onClick={fetchVoteCount} disabled={isLoading} variant="secondary">
            {isLoading ? 'Refreshing...' : '🔄 Refresh'}
          </Button>
        </div>

        {/* Vote Progress */}
        <div className="mb-6 p-6 bg-gradient-to-br from-green-50 to-blue-50 rounded-lg">
          <div className="text-center mb-4">
            <div className="text-6xl font-bold text-green-600 mb-2">
              {voteCount}
              <span className="text-3xl text-gray-400">/{totalRegistered}</span>
            </div>
            <div className="text-sm text-gray-600">Votes Submitted</div>
          </div>

          <div className="relative h-8 bg-gray-200 rounded-full overflow-hidden mb-2">
            <div
              className="absolute inset-0 bg-gradient-to-r from-green-500 to-blue-500 transition-all duration-500"
              style={{ width: `${votingProgress}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-center text-sm font-bold text-white drop-shadow">
              {votingProgress.toFixed(1)}% Complete
            </div>
          </div>

          <div className="text-center text-xs text-gray-600">
            {totalRegistered - voteCount} nodes still need to vote
          </div>
        </div>

        {voteCount === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg mb-6">
            <div className="text-6xl mb-4">🗳️</div>
            <p className="text-gray-600 mb-2">Waiting for votes...</p>
            <p className="text-sm text-gray-500">
              Responders are submitting their votes along with PPE signatures
            </p>
          </div>
        ) : (
          <div className="mb-6 p-4 bg-white border border-gray-200 rounded-lg">
            <h4 className="font-bold mb-3 text-sm">Vote Submission Timeline</h4>
            <div className="space-y-2">
              {Array.from({ length: Math.min(voteCount, 5) }).map((_, idx) => (
                <div key={idx} className="flex items-center gap-3 text-sm">
                  <div className="w-6 h-6 bg-green-500 text-white rounded-full flex items-center justify-center text-xs font-bold">
                    ✓
                  </div>
                  <div className="flex-1 text-gray-600">
                    Vote #{voteCount - idx} received
                  </div>
                  <div className="text-xs text-gray-400">Just now</div>
                </div>
              ))}
              {voteCount > 5 && (
                <div className="text-center text-xs text-gray-500 pt-2">
                  ...and {voteCount - 5} more
                </div>
              )}
            </div>
          </div>
        )}

        <div className="border-t pt-4">
          <Button
            onClick={publishResults}
            disabled={voteCount === 0}
            className="w-full"
          >
            {voteCount === 0
              ? 'Waiting for Votes...'
              : `Publish Results (${voteCount} votes collected)`}
          </Button>
          {voteCount > 0 && (
            <p className="text-xs text-gray-500 mt-2 text-center">
              This will publish all votes and certification data for public verification
              (Protocol 5)
            </p>
          )}
        </div>
      </div>

      <div className="bg-green-50 border border-green-200 rounded p-3 text-sm">
        <p className="font-bold mb-1">🗳️ Protocol 4 Status:</p>
        <ul className="text-green-800 space-y-1 text-xs">
          <li>✓ Responders create vote answers</li>
          <li>✓ Attach collected PPE signatures (Good_i)</li>
          <li>✓ Sign vote with private key (self-signature)</li>
          <li>{voteCount > 0 ? '✓' : '○'} Votes stored on bulletin board (server)</li>
        </ul>
      </div>
    </Card>
  );
}
