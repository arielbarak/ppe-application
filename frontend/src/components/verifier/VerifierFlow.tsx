import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { GraphVisualization } from '../ui/GraphVisualization';
import { api } from '../../services/api';
import type { VerificationResult, PublishedResults } from '../../types';

interface VerifierFlowProps {
  onReset: () => void;
  initialSessionId?: string;
}

export function VerifierFlow({ onReset, initialSessionId }: VerifierFlowProps) {
  const [sessionId, setSessionId] = useState(initialSessionId || '');
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [publishedResults, setPublishedResults] = useState<PublishedResults | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const [pollStatus, setPollStatus] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const checkPollStatus = useCallback(async () => {
    if (!sessionId.trim()) return;

    try {
      const pollInfo = await api.getPoll(sessionId);
      setPollStatus(pollInfo.status);
      setStatusError(null);
      return pollInfo.status;
    } catch (error: any) {
      setStatusError(error?.message || 'Failed to fetch poll status');
      return null;
    }
  }, [sessionId]);

  const verifyPoll = useCallback(async () => {
    if (!sessionId.trim()) {
      alert('Please enter a Session ID');
      return;
    }

    setIsVerifying(true);
    setStatusError(null);

    try {
      // First check poll status
      const status = await checkPollStatus();
      if (status !== 'results') {
        setIsVerifying(false);
        return; // The UI will show appropriate message based on pollStatus
      }

      // Fetch both verification and published results
      const [verification, results] = await Promise.all([
        api.verify(sessionId, 'global'),
        api.getResults(sessionId),
      ]);
      setResult(verification);
      setPublishedResults(results);
      console.log('Verification complete:', verification);
      console.log('Published results:', results);
    } catch (error: any) {
      console.error('Verification failed:', error);
      setStatusError(error?.message || 'Verification failed');
    } finally {
      setIsVerifying(false);
    }
  }, [sessionId, checkPollStatus]);

  // Auto-verify if initialSessionId is provided
  useEffect(() => {
    if (initialSessionId && initialSessionId.trim()) {
      verifyPoll();
    }
  }, [initialSessionId, verifyPoll]);

  if (!result) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="Verify Poll Results" className="max-w-md w-full">
          <Input
            label="Poll Session ID"
            placeholder="Enter session ID to verify"
            value={sessionId}
            onChange={(e) => {
              setSessionId(e.target.value);
              setPollStatus(null);
              setStatusError(null);
            }}
          />

          {/* Poll Status Display */}
          {pollStatus && pollStatus !== 'results' && (
            <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
              <p className="font-medium text-yellow-800 mb-2">
                Poll Status: <span className="font-bold">{pollStatus}</span>
              </p>
              <p className="text-sm text-yellow-700">
                {pollStatus === 'registration' && 'Poll is still in registration phase. Waiting for responders to join.'}
                {pollStatus === 'certification' && 'Poll is in certification phase. Responders are completing PPE challenges.'}
                {pollStatus === 'voting' && 'Poll is in voting phase. Waiting for votes to be cast.'}
                {pollStatus === 'cancelled' && 'This poll has been cancelled.'}
              </p>
              <p className="text-xs text-yellow-600 mt-2">
                Results will be available after the pollster publishes them.
              </p>
            </div>
          )}

          {statusError && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700">{statusError}</p>
            </div>
          )}

          <div className="flex gap-4">
            <Button
              onClick={verifyPoll}
              disabled={isVerifying || (pollStatus !== null && pollStatus !== 'results')}
              className="flex-1"
            >
              {isVerifying ? 'Checking...' : pollStatus && pollStatus !== 'results' ? 'Results Not Published Yet' : 'Verify (Protocol 6)'}
            </Button>
            <Button variant="secondary" onClick={onReset}>
              Back
            </Button>
          </div>

          <div className="mt-4 p-3 bg-blue-50 rounded text-sm text-blue-800">
            <p><strong>Protocol 6: Global Verification</strong></p>
            <p className="mt-1">
              Anyone can verify published poll results. The system will calculate the tally
              and exclude nodes that failed more than η_E of their PPE challenges.
            </p>
            <p className="mt-2">
              <strong>Validity Check (η_V):</strong> If more than η_V% of nodes are excluded,
              the entire poll is marked as INVALID (potential Sybil attack).
            </p>
          </div>
        </Card>
      </div>
    );
  }

  const isAccepted = result.verification === 'ACCEPT';
  const isInvalid = result.verification === 'INVALID';
  const isRejected = result.verification === 'REJECT';

  // Calculate exclusion percentage
  const exclusionPercentage = result.details.total_nodes > 0
    ? (result.details.excluded_nodes_count / result.details.total_nodes) * 100
    : 0;

  return (
    <div className="min-h-screen p-4">
      <div className="max-w-2xl mx-auto">
        <Card title="Verification Results">
          <div
            className={`border-2 rounded-lg p-6 mb-6 ${
              isAccepted
                ? 'border-green-500 bg-green-50'
                : isInvalid
                ? 'border-orange-500 bg-orange-50'
                : 'border-red-500 bg-red-50'
            }`}
          >
            <div className="text-center">
              <div className="text-6xl mb-2">
                {isAccepted ? '✅' : isInvalid ? '⚠️' : '❌'}
              </div>
              <h2
                className={`text-3xl font-bold ${
                  isAccepted
                    ? 'text-green-700'
                    : isInvalid
                    ? 'text-orange-700'
                    : 'text-red-700'
                }`}
              >
                {result.verification}
              </h2>
              <p className="text-sm mt-2 text-gray-700">{result.details.message}</p>
            </div>
          </div>

          {/* INVALID Poll Warning */}
          {isInvalid && (
            <div className="mb-6 p-4 bg-orange-100 border-2 border-orange-500 rounded-lg">
              <h3 className="font-bold text-orange-800 text-lg mb-2">
                Poll Results Cannot Be Trusted
              </h3>
              <p className="text-orange-700 text-sm mb-2">
                Too many participants ({result.details.excluded_nodes_count} out of{' '}
                {result.details.total_nodes}, or {exclusionPercentage.toFixed(1)}%) were excluded
                for failing PPE challenges.
              </p>
              <p className="text-orange-700 text-sm">
                This exceeds the validity threshold (η_V) of{' '}
                {result.details.eta_v !== undefined
                  ? `${(result.details.eta_v * 100).toFixed(1)}%`
                  : '2.5%'}
                , indicating a potential Sybil attack or systemic failure.
                The poll should be considered <strong>invalid</strong>.
              </p>
            </div>
          )}

          <div className="space-y-6">
            {/* Tally */}
            <div>
              <h3 className="font-bold text-lg mb-3">Vote Tally</h3>
              {Object.entries(result.tally).map(([questionId, options]) => (
                <div key={questionId} className="mb-4">
                  <p className="font-medium mb-2">Question {questionId}:</p>
                  <div className="space-y-2">
                    {Object.entries(options).map(([option, count]) => (
                      <div key={option} className="flex items-center gap-2">
                        <div className="w-24">{option}:</div>
                        <div className="flex-1 bg-gray-200 rounded-full h-6 relative overflow-hidden">
                          <div
                            className="bg-primary-500 h-full rounded-full transition-all"
                            style={{
                              width: `${
                                (count / Math.max(...Object.values(options))) * 100
                              }%`,
                            }}
                          />
                          <span className="absolute inset-0 flex items-center justify-center text-sm font-medium">
                            {count} votes
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Details */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="p-4 bg-gray-50 rounded">
                <p className="text-sm text-gray-600">Total Nodes</p>
                <p className="text-2xl font-bold">{result.details.total_nodes}</p>
              </div>
              <div className="p-4 bg-gray-50 rounded">
                <p className="text-sm text-gray-600">Valid Nodes</p>
                <p className="text-2xl font-bold text-green-600">
                  {result.details.valid_nodes}
                </p>
              </div>
              <div className="p-4 bg-gray-50 rounded">
                <p className="text-sm text-gray-600">Excluded Nodes</p>
                <p className="text-2xl font-bold text-red-600">
                  {result.details.excluded_nodes_count}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {exclusionPercentage.toFixed(1)}% of total
                </p>
              </div>
              <div className="p-4 bg-gray-50 rounded">
                <p className="text-sm text-gray-600">Edge Verification</p>
                <p className="text-2xl font-bold">
                  {result.details.edge_verification_passed ? '✅' : '❌'}
                </p>
              </div>
            </div>

            {/* Threshold Parameters */}
            {publishedResults && (
              <div className="mt-4 p-4 bg-blue-50 rounded border border-blue-200">
                <h4 className="font-medium text-blue-800 mb-2">Threshold Parameters</h4>
                <div className="grid md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-blue-700">η_E (Effort Threshold):</span>{' '}
                    <span className="font-mono">
                      {(publishedResults.parameters.effort_threshold * 100).toFixed(1)}%
                    </span>
                    <p className="text-xs text-blue-600 mt-1">
                      Nodes failing more than this % of PPEs are excluded
                    </p>
                  </div>
                  <div>
                    <span className="text-blue-700">η_V (Validity Threshold):</span>{' '}
                    <span className="font-mono">
                      {(publishedResults.parameters.validity_threshold * 100).toFixed(1)}%
                    </span>
                    <p className="text-xs text-blue-600 mt-1">
                      Poll invalid if more than this % of nodes are excluded
                    </p>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-blue-200">
                  <span className="text-blue-700">Validity Check:</span>{' '}
                  <span className={`font-bold ${result.details.validity_check_passed ? 'text-green-600' : 'text-orange-600'}`}>
                    {result.details.validity_check_passed ? 'PASSED' : 'FAILED'}
                  </span>
                  <span className="text-xs text-blue-600 ml-2">
                    ({exclusionPercentage.toFixed(1)}% excluded vs{' '}
                    {(publishedResults.parameters.validity_threshold * 100).toFixed(1)}% max allowed)
                  </span>
                </div>
              </div>
            )}

            {/* Excluded Nodes */}
            {result.excluded_nodes.length > 0 && (
              <div>
                <h3 className="font-bold text-lg mb-2">Excluded Nodes</h3>
                <div className="bg-red-50 border border-red-200 rounded p-3">
                  <p className="text-sm text-red-800 mb-2">
                    These nodes were excluded for failing more than 50% of their PPE challenges:
                  </p>
                  <div className="font-mono text-xs space-y-1">
                    {result.excluded_nodes.map((nodeId) => (
                      <div key={nodeId}>• {nodeId}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Certification Graph */}
            {publishedResults && publishedResults.certification_graph && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-bold text-lg">Certification Graph</h3>
                  <Button
                    variant="secondary"
                    onClick={() => setShowGraph(!showGraph)}
                  >
                    {showGraph ? 'Hide Graph' : 'Show Graph'}
                  </Button>
                </div>
                {showGraph && (
                  <GraphVisualization
                    nodes={publishedResults.certification_graph.nodes}
                    edges={publishedResults.certification_graph.edges}
                    excludedNodes={result.excluded_nodes}
                    width={580}
                    height={400}
                  />
                )}
                {!showGraph && (
                  <div className="text-sm text-gray-600 p-4 bg-gray-50 rounded">
                    <p>
                      Graph contains {publishedResults.certification_graph.nodes.length} nodes
                      and {publishedResults.certification_graph.edges.length} edges.
                    </p>
                    <p className="mt-1">
                      Click "Show Graph" to visualize the certification network.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex gap-4 mt-6">
            <Button variant="secondary" onClick={() => {
              setResult(null);
              setPublishedResults(null);
              setShowGraph(false);
            }}>
              Verify Another Poll
            </Button>
            <Button variant="secondary" onClick={onReset}>
              Back to Home
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
