import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { GraphVisualization } from '../ui/GraphVisualization';
import { api } from '../../services/api';
import type { VerificationResult, PublishedResults } from '../../types';

interface ResultsPublisherProps {
  sessionId: string;
  onReset: () => void;
}

export function ResultsPublisher({ sessionId, onReset }: ResultsPublisherProps) {
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [publishedResults, setPublishedResults] = useState<PublishedResults | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [showGraph, setShowGraph] = useState(false);

  const verifyResults = async () => {
    setIsVerifying(true);
    try {
      const [result, results] = await Promise.all([
        api.verify(sessionId, 'global'),
        api.getResults(sessionId),
      ]);
      setVerification(result);
      setPublishedResults(results);
    } catch (error) {
      alert(`Verification failed: ${error}`);
    } finally {
      setIsVerifying(false);
    }
  };

  if (!verification) {
    return (
      <Card title="Results Published! (Protocol 5)">
        <div className="text-center py-12">
          <div className="text-6xl mb-4">🎉</div>
          <h2 className="text-2xl font-bold mb-3 text-green-600">
            Poll Results Published Successfully!
          </h2>
          <p className="text-gray-600 mb-6">
            All votes, signatures, and certification graph data have been made public.
            <br />
            Anyone can now independently verify the results.
          </p>

          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg max-w-md mx-auto">
            <p className="font-mono text-sm mb-2">
              <strong>Session ID:</strong>
            </p>
            <p className="font-mono text-xs break-all bg-white p-2 rounded">
              {sessionId}
            </p>
            <p className="text-xs text-blue-700 mt-2">
              Share this ID with verifiers to audit the poll
            </p>
          </div>

          <div className="flex gap-4 justify-center">
            <Button onClick={verifyResults} disabled={isVerifying}>
              {isVerifying ? 'Verifying...' : '🔍 Run Verification (Protocol 6)'}
            </Button>
            <Button variant="secondary" onClick={onReset}>
              Create New Poll
            </Button>
          </div>
        </div>

        <div className="mt-6 bg-purple-50 border border-purple-200 rounded p-3 text-sm">
          <p className="font-bold mb-1">📊 Protocol 5 Complete:</p>
          <ul className="text-purple-800 space-y-1 text-xs">
            <li>✓ All votes published with signatures</li>
            <li>✓ Complete certification graph published</li>
            <li>✓ Node labels and edges made public</li>
            <li>✓ Data available for public audit</li>
          </ul>
        </div>
      </Card>
    );
  }

  const isAccepted = verification.verification === 'ACCEPT';

  return (
    <Card title="Verification Results (Protocol 6)">
      <div
        className={`border-2 rounded-lg p-6 mb-6 ${
          isAccepted ? 'border-green-500 bg-green-50' : 'border-red-500 bg-red-50'
        }`}
      >
        <div className="text-center">
          <div className="text-6xl mb-2">{isAccepted ? '✅' : '❌'}</div>
          <h2
            className={`text-3xl font-bold ${
              isAccepted ? 'text-green-700' : 'text-red-700'
            }`}
          >
            {verification.verification}
          </h2>
          <p className="text-sm mt-2">{verification.details.message}</p>
        </div>
      </div>

      {/* Tally */}
      <div className="mb-6">
        <h3 className="font-bold text-lg mb-3">Final Tally</h3>
        {Object.entries(verification.tally).map(([questionId, options]) => (
          <div key={questionId} className="mb-4">
            <p className="font-medium mb-2">Question {questionId}:</p>
            <div className="space-y-2">
              {Object.entries(options).map(([option, count]) => {
                const total = Object.values(options).reduce((a, b) => a + b, 0);
                const percentage = total > 0 ? (count / total) * 100 : 0;

                return (
                  <div key={option} className="flex items-center gap-2">
                    <div className="w-32 font-medium">{option}:</div>
                    <div className="flex-1 bg-gray-200 rounded-full h-8 relative overflow-hidden">
                      <div
                        className="bg-primary-500 h-full rounded-full transition-all"
                        style={{ width: `${percentage}%` }}
                      />
                      <span className="absolute inset-0 flex items-center justify-center text-sm font-medium">
                        {count} votes ({percentage.toFixed(1)}%)
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="p-4 bg-gray-50 rounded text-center">
          <div className="text-2xl font-bold">{verification.details.total_nodes}</div>
          <div className="text-xs text-gray-600">Total Nodes</div>
        </div>
        <div className="p-4 bg-green-50 rounded text-center">
          <div className="text-2xl font-bold text-green-600">
            {verification.details.valid_nodes}
          </div>
          <div className="text-xs text-gray-600">Valid Votes</div>
        </div>
        <div className="p-4 bg-red-50 rounded text-center">
          <div className="text-2xl font-bold text-red-600">
            {verification.details.excluded_nodes_count}
          </div>
          <div className="text-xs text-gray-600">Excluded</div>
        </div>
        <div className="p-4 bg-blue-50 rounded text-center">
          <div className="text-2xl font-bold">
            {verification.details.edge_verification_passed ? '✅' : '❌'}
          </div>
          <div className="text-xs text-gray-600">Edge Check</div>
        </div>
      </div>

      {/* Excluded Nodes */}
      {verification.excluded_nodes.length > 0 && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded">
          <h4 className="font-bold mb-2 text-red-800">
            Excluded Nodes ({verification.excluded_nodes.length})
          </h4>
          <p className="text-xs text-red-700 mb-2">
            Failed &gt;50% of PPE challenges (η_E threshold)
          </p>
          <div className="font-mono text-xs space-y-1">
            {verification.excluded_nodes.map((nodeId) => (
              <div key={nodeId} className="text-red-600">
                • {nodeId}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Certification Graph */}
      {publishedResults && publishedResults.certification_graph && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-bold">Certification Graph</h4>
            <Button
              variant="secondary"
              onClick={() => setShowGraph(!showGraph)}
              className="text-sm"
            >
              {showGraph ? 'Hide Graph' : 'Show Graph'}
            </Button>
          </div>
          {showGraph && (
            <GraphVisualization
              nodes={publishedResults.certification_graph.nodes}
              edges={publishedResults.certification_graph.edges}
              excludedNodes={verification.excluded_nodes}
              width={600}
              height={400}
            />
          )}
          {!showGraph && (
            <div className="text-sm text-gray-600 p-3 bg-gray-50 rounded">
              Graph contains {publishedResults.certification_graph.nodes.length} nodes
              and {publishedResults.certification_graph.edges.length} edges.
            </div>
          )}
        </div>
      )}

      <div className="flex gap-4">
        <Button variant="secondary" onClick={onReset} className="flex-1">
          Create New Poll
        </Button>
      </div>

      <div className="mt-6 bg-green-50 border border-green-200 rounded p-3 text-sm">
        <p className="font-bold mb-1">✅ Protocol 6 Complete:</p>
        <ul className="text-green-800 space-y-1 text-xs">
          <li>✓ Tally calculated with exclusions</li>
          <li>✓ Nodes exceeding η_E threshold excluded</li>
          <li>✓ Certification graph validated</li>
          <li>✓ Public verification successful</li>
        </ul>
      </div>
    </Card>
  );
}
