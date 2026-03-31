import React, { useState, useEffect } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { api } from '../../services/api';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { WSMessage } from '../../types';

interface RegistrationMonitorProps {
  sessionId: string;
  onAdvance: () => void;
}

export function RegistrationMonitor({ sessionId, onAdvance }: RegistrationMonitorProps) {
  const [nodes, setNodes] = useState<any[]>([]);
  const [totalRegistered, setTotalRegistered] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // WebSocket for real-time updates
  useWebSocket({
    sessionId,
    nodeId: 'pollster',
    role: 'pollster',
    onMessage: handleWebSocketMessage,
  });

  function handleWebSocketMessage(message: WSMessage) {
    if (message.type === 'registration.update') {
      setTotalRegistered(message.data.total_registered);
      fetchNodes();
    }
  }

  const fetchNodes = async () => {
    setIsLoading(true);
    try {
      const result = await api.getRegisteredNodes(sessionId);
      setNodes(result.nodes);
      setTotalRegistered(result.total_registered);
    } catch (error) {
      console.error('Failed to fetch nodes:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
    const interval = setInterval(fetchNodes, 5000);
    return () => clearInterval(interval);
  }, [sessionId]);

  const advanceToCertification = async () => {
    try {
      await api.updatePollStatus(sessionId, 'certification');
      onAdvance();
    } catch (error) {
      console.error('Failed to advance:', error);
    }
  };

  const copySessionId = async () => {
    try {
      await navigator.clipboard.writeText(sessionId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy to clipboard:', error);
    }
  };

  return (
    <Card title="Registration Phase (Protocol 2)">
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-xl font-bold">Total Registered: {totalRegistered}</h3>
            <p className="text-sm text-gray-600">
              Responders solving CAPTCHAs to join the poll
            </p>
          </div>
          <Button onClick={fetchNodes} disabled={isLoading} variant="secondary">
            {isLoading ? 'Refreshing...' : '🔄 Refresh'}
          </Button>
        </div>

        {nodes.length === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg">
            <div className="text-6xl mb-4">⏳</div>
            <p className="text-gray-600 mb-2">Waiting for responders to register...</p>
            <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
              <span>Share the Session ID:</span>
              <code className="bg-gray-200 px-2 py-1 rounded">{sessionId}</code>
              <Button
                onClick={copySessionId}
                variant="secondary"
                className="text-xs px-2 py-1"
              >
                {copied ? '✓ Copied!' : 'Copy'}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-2 mb-6">
            {nodes.map((node, idx) => (
              <div
                key={node.node_id}
                className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div className="flex-shrink-0 w-8 h-8 bg-primary-500 text-white rounded-full flex items-center justify-center font-bold">
                  {idx + 1}
                </div>
                <div className="flex-1">
                  <p className="font-mono text-sm">{node.node_id}</p>
                  <p className="text-xs text-gray-500">
                    Registered at {new Date(node.registration_time).toLocaleTimeString()}
                  </p>
                </div>
                <div className="text-green-600 font-bold">✓</div>
              </div>
            ))}
          </div>
        )}

        <div className="border-t pt-4">
          <Button
            onClick={advanceToCertification}
            disabled={totalRegistered === 0}
            className="w-full"
          >
            {totalRegistered === 0
              ? 'Waiting for Responders...'
              : `Advance to Certification (${totalRegistered} nodes)`}
          </Button>
          {totalRegistered > 0 && (
            <p className="text-xs text-gray-500 mt-2 text-center">
              This will close registration and start Protocol 3 (PPE certification)
            </p>
          )}
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
        <p className="font-bold mb-1">📋 Protocol 2 Status:</p>
        <ul className="text-blue-800 space-y-1 text-xs">
          <li>✓ Responders generate ECDSA P-256 key pairs (client-side)</li>
          <li>✓ Responders solve math CAPTCHAs (single-sided PPE)</li>
          <li>✓ Nodes added to shuffled registration list</li>
          <li>
            {totalRegistered > 0 ? '✓' : '○'} Ready to advance to certification
          </li>
        </ul>
      </div>
    </Card>
  );
}
