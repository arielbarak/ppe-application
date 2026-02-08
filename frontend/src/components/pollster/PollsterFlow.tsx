import React, { useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { api } from '../../services/api';
import type { PollSession, PollQuestion } from '../../types';

interface PollsterFlowProps {
  onReset: () => void;
}

export function PollsterFlow({ onReset }: PollsterFlowProps) {
  const [session, setSession] = useState<PollSession | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  const [questionText, setQuestionText] = useState('');
  const [options, setOptions] = useState(['', '', '']);
  const [edgeProbability, setEdgeProbability] = useState(0.5);
  const [effortThreshold, setEffortThreshold] = useState(0.5);

  const createPoll = async () => {
    if (!questionText.trim() || options.some((opt) => !opt.trim())) {
      alert('Please fill in all question and option fields');
      return;
    }

    // Check for duplicate options (case-insensitive)
    const filteredOptions = options.filter((opt) => opt.trim()).map((opt) => opt.trim());
    const lowerCaseOptions = filteredOptions.map((opt) => opt.toLowerCase());
    const uniqueOptions = new Set(lowerCaseOptions);
    if (uniqueOptions.size !== filteredOptions.length) {
      alert('Each answer option must be unique. Please remove duplicate options.');
      return;
    }

    setIsCreating(true);
    try {
      const questions: PollQuestion[] = [
        {
          id: 'q1',
          text: questionText,
          options: filteredOptions,
        },
      ];

      const newSession = await api.createPoll({
        questions,
        edge_probability: edgeProbability,
        effort_threshold: effortThreshold,
      });

      setSession(newSession);
      console.log('Poll created:', newSession);
    } catch (error) {
      console.error('Failed to create poll:', error);
      alert(`Failed to create poll: ${error}`);
    } finally {
      setIsCreating(false);
    }
  };

  const copySessionId = async () => {
    if (session?.session_id) {
      try {
        await navigator.clipboard.writeText(session.session_id);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (error) {
        console.error('Failed to copy:', error);
        alert('Failed to copy to clipboard');
      }
    }
  };

  if (!session) {
    return (
      <div className="min-h-screen p-4">
        <div className="max-w-2xl mx-auto">
          <Card title="Create New Poll">
            <Input
              label="Question"
              placeholder="e.g., What is your favorite color?"
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
            />

            <div className="mb-4">
              <label className="label">Options</label>
              {options.map((option, index) => (
                <Input
                  key={index}
                  placeholder={`Option ${index + 1}`}
                  value={option}
                  onChange={(e) => {
                    const newOptions = [...options];
                    newOptions[index] = e.target.value;
                    setOptions(newOptions);
                  }}
                  className="mb-2"
                />
              ))}
            </div>

            <div className="grid md:grid-cols-2 gap-4 mb-6">
              <div>
                <label className="label">Edge Probability (p): {edgeProbability}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={edgeProbability}
                  onChange={(e) => setEdgeProbability(parseFloat(e.target.value))}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Probability of edge between two nodes
                </p>
              </div>

              <div>
                <label className="label">Effort Threshold (η_E): {effortThreshold}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={effortThreshold}
                  onChange={(e) => setEffortThreshold(parseFloat(e.target.value))}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Max failed PPE fraction before exclusion
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <Button onClick={createPoll} disabled={isCreating} className="flex-1">
                {isCreating ? 'Creating...' : 'Create Poll (Protocol 1)'}
              </Button>
              <Button variant="secondary" onClick={onReset}>
                Back
              </Button>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-4xl mx-auto">
        <Card title="Poll Created!">
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
            <div className="flex items-start justify-between gap-4 mb-2">
              <div className="flex-1">
                <p className="font-mono text-sm">
                  <strong>Session ID:</strong> {session.session_id}
                </p>
              </div>
              <Button
                onClick={copySessionId}
                variant="secondary"
                className="text-xs px-3 py-1"
              >
                {copied ? '✓ Copied!' : 'Copy'}
              </Button>
            </div>
            <p className="text-sm text-green-700">
              Share this Session ID with responders so they can join!
            </p>
          </div>

          <div className="space-y-4">
            <div>
              <h3 className="font-bold mb-2">Question:</h3>
              <p>{session.questions[0].text}</p>
            </div>

            <div>
              <h3 className="font-bold mb-2">Options:</h3>
              <ul className="list-disc list-inside">
                {session.questions[0].options.map((opt, idx) => (
                  <li key={idx}>{opt}</li>
                ))}
              </ul>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-gray-600">Edge Probability (p)</p>
                <p className="font-mono">{session.parameters.edge_probability}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Effort Threshold (η_E)</p>
                <p className="font-mono">{session.parameters.effort_threshold}</p>
              </div>
            </div>
          </div>

          <div className="mt-6 p-4 bg-blue-50 rounded-lg">
            <p className="text-sm text-blue-800">
              <strong>Next Steps:</strong>
              <br />
              1. Share the Session ID with responders
              <br />
              2. Wait for responders to register (Protocol 2)
              <br />
              3. Advance to certification phase when ready
              <br />
              4. Monitor voting and publish results (Protocols 4-5)
            </p>
          </div>

          <div className="flex gap-4 mt-6">
            <Button variant="secondary" onClick={onReset}>
              Create Another Poll
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
