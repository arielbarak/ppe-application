import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { api } from '../../services/api';
import { RegistrationMonitor } from './RegistrationMonitor';
import { CertificationMonitor } from './CertificationMonitor';
import { VotingMonitor } from './VotingMonitor';
import { ResultsPublisher } from './ResultsPublisher';
import type { PollSession, PollStatus } from '../../types';
import { listProviders, DEFAULT_PPE_TYPE } from '../../services/ppe';

interface PollsterFlowEnhancedProps {
  onReset: () => void;
}

const PHASES: PollStatus[] = ['registration', 'certification', 'voting', 'results'];

export function PollsterFlowEnhanced({ onReset }: PollsterFlowEnhancedProps) {
  const [session, setSession] = useState<PollSession | null>(null);
  const [currentPhase, setCurrentPhase] = useState<PollStatus>('registration');
  const [isCreating, setIsCreating] = useState(false);

  // Poll creation form
  const [questionText, setQuestionText] = useState('');
  const [options, setOptions] = useState(['', '', '']);
  const [edgeProbability, setEdgeProbability] = useState(0.5);
  const [effortThreshold, setEffortThreshold] = useState(0.5);
  const [validityThreshold, setValidityThreshold] = useState(0.025);
  const [ppeType, setPpeType] = useState(DEFAULT_PPE_TYPE);

  // Poll session status
  useEffect(() => {
    if (session) {
      const interval = setInterval(async () => {
        try {
          const updated = await api.getPoll(session.session_id);
          if (updated.status && updated.status !== currentPhase) {
            setCurrentPhase(updated.status);
          }
        } catch (error) {
          console.error('Failed to fetch poll status:', error);
        }
      }, 3000);

      return () => clearInterval(interval);
    }
  }, [session, currentPhase]);

  const createPoll = async () => {
    if (!questionText.trim() || options.some((opt) => !opt.trim())) {
      return;
    }

    // Check for duplicate options (case-insensitive)
    const filteredOptions = options.filter((opt) => opt.trim()).map((opt) => opt.trim());
    const lowerCaseOptions = filteredOptions.map((opt) => opt.toLowerCase());
    const uniqueOptions = new Set(lowerCaseOptions);
    if (uniqueOptions.size !== filteredOptions.length) {
      return;
    }

    setIsCreating(true);
    try {
      const newSession = await api.createPoll({
        questions: [
          {
            id: 'q1',
            text: questionText,
            options: filteredOptions,
          },
        ],
        edge_probability: edgeProbability,
        effort_threshold: effortThreshold,
        validity_threshold: validityThreshold,
        ppe_type: ppeType,
      });

      setSession(newSession);
      setCurrentPhase('registration');

      console.log('Poll created:', newSession);
    } catch (error) {
      console.error('Failed to create poll:', error);
    } finally {
      setIsCreating(false);
    }
  };

  const handleReset = () => {
    setSession(null);
    setCurrentPhase('registration');
    setQuestionText('');
    setOptions(['', '', '']);
  };

  const handleBackToHome = () => {
    onReset();
  };

  // Poll creation form
  if (!session) {
    return (
      <div className="min-h-screen p-4">
        <div className="max-w-3xl mx-auto">
          <Card>
            <div className="mb-6">
              <h1 className="text-3xl font-bold text-primary-600 mb-2">
                Create New Poll
              </h1>
              <p className="text-gray-600">
                Protocol 1: Announcement Phase - Set up your poll parameters
              </p>
            </div>

            <Input
              label="Question"
              placeholder="e.g., What is your favorite programming language?"
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
            />

            <div className="mb-4">
              <label className="label">Answer Options</label>
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
              <Button
                variant="secondary"
                onClick={() => setOptions([...options, ''])}
                className="w-full text-sm"
              >
                + Add Option
              </Button>
            </div>

            <div className="mb-6">
              <label className="label">
                PPE Challenge Type
              </label>
              <select
                value={ppeType}
                onChange={(e) => setPpeType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white"
              >
                {listProviders().map((p) => (
                  <option key={p.type} value={p.type}>{p.label}</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Type of proof-of-effort challenge used during peer certification
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-6 mb-6">
              <div>
                <label className="label">
                  Edge Probability (p): <strong>{edgeProbability}</strong>
                </label>
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
                  Probability of edge between two nodes in certification graph
                </p>
              </div>

              <div>
                <label className="label">
                  Effort Threshold (η_E): <strong>{effortThreshold}</strong>
                </label>
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
                  Max failed PPE fraction before node exclusion from tally
                </p>
              </div>

              <div>
                <label className="label">
                  Validity Threshold (η_V): <strong>{(validityThreshold * 100).toFixed(1)}%</strong>
                </label>
                <input
                  type="range"
                  min="0.01"
                  max="0.25"
                  step="0.005"
                  value={validityThreshold}
                  onChange={(e) => setValidityThreshold(parseFloat(e.target.value))}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Max excluded nodes before poll is invalid (Sybil protection)
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <Button onClick={createPoll} disabled={isCreating} className="flex-1">
                {isCreating ? 'Creating...' : 'Create Poll (Protocol 1)'}
              </Button>
              <Button variant="secondary" onClick={handleBackToHome}>
                Back
              </Button>
            </div>

            <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded text-sm">
              <p className="font-bold mb-2">About the Parameters:</p>
              <ul className="space-y-1 text-blue-800 text-xs">
                <li>
                  <strong>Edge Probability (p):</strong> Higher values mean more neighbors per
                  node (more PPE challenges)
                </li>
                <li>
                  <strong>Effort Threshold (η_E):</strong> Nodes failing &gt;η_E of their PPE
                  challenges are excluded from the final tally
                </li>
                <li>
                  <strong>Validity Threshold (η_V):</strong> If more than η_V of total nodes are
                  excluded, the entire poll is marked INVALID (Sybil attack protection)
                </li>
              </ul>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  // Progress stepper
  const currentPhaseIndex = PHASES.indexOf(currentPhase);

  return (
    <div className="min-h-screen p-4 bg-gray-50">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6 bg-white rounded-lg shadow-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-primary-600">Poll Dashboard</h1>
              <p className="text-sm text-gray-600">Session: {session.session_id}</p>
            </div>
            <Button variant="secondary" onClick={handleReset} className="text-sm">
              ← Back
            </Button>
          </div>

          {/* Phase Stepper */}
          <div className="flex items-center justify-between">
            {PHASES.map((phase, index) => {
              const isActive = index === currentPhaseIndex;
              const isCompleted = index < currentPhaseIndex;

              return (
                <React.Fragment key={phase}>
                  <div className="flex flex-col items-center flex-1">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center font-bold ${
                        isActive
                          ? 'bg-primary-500 text-white'
                          : isCompleted
                          ? 'bg-green-500 text-white'
                          : 'bg-gray-200 text-gray-500'
                      }`}
                    >
                      {isCompleted ? '✓' : index + 1}
                    </div>
                    <div
                      className={`mt-2 text-xs font-medium ${
                        isActive ? 'text-primary-600' : isCompleted ? 'text-green-600' : 'text-gray-500'
                      }`}
                    >
                      {phase.charAt(0).toUpperCase() + phase.slice(1)}
                    </div>
                  </div>
                  {index < PHASES.length - 1 && (
                    <div
                      className={`h-1 flex-1 ${
                        isCompleted ? 'bg-green-500' : 'bg-gray-200'
                      }`}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Phase Content */}
        {currentPhase === 'registration' && (
          <RegistrationMonitor
            sessionId={session.session_id}
            onAdvance={() => setCurrentPhase('certification')}
          />
        )}

        {currentPhase === 'certification' && (
          <CertificationMonitor
            sessionId={session.session_id}
            nodeId={`pollster-${session.session_id}`}
            onAdvance={() => setCurrentPhase('voting')}
          />
        )}

        {currentPhase === 'voting' && (
          <VotingMonitor
            sessionId={session.session_id}
            onPublish={() => setCurrentPhase('results')}
          />
        )}

        {currentPhase === 'results' && (
          <ResultsPublisher sessionId={session.session_id} onReset={handleReset} />
        )}

        {currentPhase === 'cancelled' && (
          <Card title="Poll Cancelled">
            <div className="text-center py-8">
              <div className="text-6xl mb-4">X</div>
              <h2 className="text-2xl font-bold text-red-600 mb-4">Poll Cancelled</h2>
              <p className="text-gray-700 mb-6">
                This poll has been cancelled because not enough participants completed the
                certification phase. The poll threshold was not met.
              </p>
              <div className="bg-gray-50 rounded-lg p-4 mb-6">
                <p className="text-sm text-gray-600">
                  <strong>Session ID:</strong> {session.session_id}
                </p>
              </div>
              <Button onClick={handleReset}>Create New Poll</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
