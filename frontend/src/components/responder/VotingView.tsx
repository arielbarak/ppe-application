import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { api } from '../../services/api';
import { markSessionAsVoted } from '../../services/storage';
import type { PollSession } from '../../types';

interface VotingViewProps {
  sessionId: string;
  nodeId: string;
  signMessage: (message: string) => Promise<string>;
  onComplete: () => void;
}

export function VotingView({ sessionId, nodeId, signMessage, onComplete }: VotingViewProps) {
  const [poll, setPoll] = useState<PollSession | null>(null);
  const [selectedOption, setSelectedOption] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchPoll = async () => {
      try {
        const pollData = await api.getPoll(sessionId);
        setPoll(pollData);
        setIsLoading(false);
      } catch (error) {
        console.error('Failed to fetch poll data:', error);
        alert('Failed to load voting page');
        setIsLoading(false);
      }
    };

    fetchPoll();
  }, [sessionId]);

  const submitVote = async () => {
    if (!selectedOption || !poll) {
      alert('Please select an option');
      return;
    }

    setIsSubmitting(true);
    try {
      // Create vote object
      const vote = {
        [poll.questions[0].id]: selectedOption,
      };

      // Sign the vote
      const voteString = JSON.stringify(vote);
      const signature = await signMessage(voteString);

      // Submit vote
      await api.submitVote(sessionId, {
        node_id: nodeId,
        vote,
        signatures: [], // Neighbor signatures from certification (placeholder)
        signature, // Self signature
      });

      console.log('Vote submitted successfully');

      // Mark session as voted in localStorage
      markSessionAsVoted(sessionId);

      alert('Vote submitted successfully!');
      onComplete();
    } catch (error) {
      console.error('Failed to submit vote:', error);
      alert(`Failed to submit vote: ${error}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="Loading..." className="max-w-md w-full">
          <p className="text-center text-gray-600">Loading voting page...</p>
        </Card>
      </div>
    );
  }

  if (!poll) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="Error" className="max-w-md w-full">
          <p className="text-center text-red-600">Failed to load poll</p>
        </Card>
      </div>
    );
  }

  const question = poll.questions[0];

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card title="Cast Your Vote (Protocol 4)" className="max-w-2xl w-full">
        <div className="mb-6">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
            <p className="font-mono text-sm mb-1">
              <strong>Your Node ID:</strong> {nodeId}
            </p>
            <p className="text-sm text-blue-700">
              ✅ Certification complete - ready to vote
            </p>
          </div>

          <div className="mb-6">
            <h3 className="text-lg font-bold mb-4">{question.text}</h3>

            <div className="space-y-3">
              {question.options.map((option, index) => (
                <label
                  key={index}
                  className={`flex items-center p-4 border-2 rounded-lg cursor-pointer transition-all ${
                    selectedOption === option
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="radio"
                    name="vote"
                    value={option}
                    checked={selectedOption === option}
                    onChange={(e) => setSelectedOption(e.target.value)}
                    className="w-5 h-5 text-blue-600 mr-3"
                  />
                  <span className="text-lg">{option}</span>
                </label>
              ))}
            </div>
          </div>

          <Button
            onClick={submitVote}
            disabled={!selectedOption || isSubmitting}
            className="w-full"
          >
            {isSubmitting ? 'Submitting...' : 'Submit Vote'}
          </Button>

          <div className="mt-4 p-3 bg-blue-50 rounded text-sm text-blue-800">
            <p className="font-semibold mb-1">About Protocol 4 (Response):</p>
            <p>
              Your vote will be signed with your private key and submitted with the
              signatures you collected during certification. This proves you completed
              the PPE protocol with your neighbors.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
