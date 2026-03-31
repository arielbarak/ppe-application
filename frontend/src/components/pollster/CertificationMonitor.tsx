import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { GraphVisualization } from '../ui/GraphVisualization';
import { api } from '../../services/api';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { WSMessage } from '../../types';

interface CertificationMonitorProps {
  sessionId: string;
  nodeId?: string;  // Pollster's node ID for WebSocket connection
  onAdvance: () => void;
}

interface NodeStatus {
  node_id: string;
  total_neighbors: number;
  completed_edges: number;
  verified_edges: number;
  pending_edges: number;
  completion_percentage: number;
}

interface ThresholdStatus {
  threshold_met: boolean;
  certified_nodes: string[];
  uncertified_nodes: string[];
  total_nodes: number;
  certification_rate: number;
  required_threshold: number;
  message: string;
}

export function CertificationMonitor({ sessionId, nodeId, onAdvance }: CertificationMonitorProps) {
  const [nodes, setNodes] = useState<any[]>([]);
  const [nodeStatuses, setNodeStatuses] = useState<Map<string, NodeStatus>>(new Map());
  const [thresholdStatus, setThresholdStatus] = useState<ThresholdStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [realtimeStats, setRealtimeStats] = useState<{
    totalEdges: number;
    verifiedEdges: number;
    lastUpdate: string;
  } | null>(null);
  const [showGraph, setShowGraph] = useState(false);
  const [graphEdges, setGraphEdges] = useState<Array<{ from: string; to: string; verified: boolean }>>([]);

  // Define fetchData first with useCallback so it can be used in handleWSMessage
  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await api.getRegisteredNodes(sessionId);
      setNodes(result.nodes);

      // Fetch threshold status
      try {
        const response = await fetch(`/api/poll/${sessionId}/certification/threshold`);
        if (response.ok) {
          const thresholdData = await response.json();
          setThresholdStatus(thresholdData);
        }
      } catch (error) {
        console.error('Failed to fetch threshold status:', error);
      }

      // Fetch certification graph for visualization
      try {
        const graphData = await api.getCertificationGraph(sessionId);
        setGraphEdges(graphData.edges);
      } catch (error) {
        console.error('Failed to fetch certification graph:', error);
      }

      // Fetch status for each node
      const statuses = new Map<string, NodeStatus>();
      for (const node of result.nodes) {
        try {
          const status = await api.getCertificationStatus(sessionId, node.node_id);
          statuses.set(node.node_id, status);
        } catch (error) {
          console.error(`Failed to fetch status for ${node.node_id}:`, error);
        }
      }
      setNodeStatuses(statuses);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  // Handle WebSocket messages for real-time updates
  const handleWSMessage = useCallback((message: WSMessage) => {
    console.log('[Pollster] Certification WS message:', message.type, message.data);

    if (message.type === 'connection.established') {
      console.log('[Pollster] WebSocket connection confirmed by server');
    }

    if (message.type === 'certification.edge_added') {
      const { from_node, to_node, verified, total_edges, verified_edges } = message.data as any;
      console.log(`[Pollster] Edge added: ${from_node} -> ${to_node}, verified=${verified}`);

      // Update real-time stats
      setRealtimeStats({
        totalEdges: total_edges,
        verifiedEdges: verified_edges,
        lastUpdate: new Date().toLocaleTimeString(),
      });

      // Trigger a data refresh to get updated node statuses
      fetchData();
    }
  }, [fetchData]);

  // Connect to WebSocket for real-time updates
  const { isConnected } = useWebSocket({
    sessionId: sessionId,
    nodeId: nodeId || 'pollster',
    role: 'pollster',
    onMessage: handleWSMessage,
  });

  // Log connection status changes
  useEffect(() => {
    console.log(`[Pollster] WebSocket connection status: ${isConnected ? 'CONNECTED' : 'DISCONNECTED'}`);
  }, [isConnected]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const advanceToVoting = async () => {
    try {
      await api.updatePollStatus(sessionId, 'voting');
      onAdvance();
    } catch (error) {
      console.error('Failed to advance:', error);
    }
  };

  const cancelPoll = async () => {
    if (!confirm('Are you sure you want to cancel this poll? All participants will be notified that the poll is cancelled due to insufficient certification completion.')) {
      return;
    }

    try {
      await api.updatePollStatus(sessionId, 'cancelled');
      onAdvance(); // Refresh the view
    } catch (error) {
      console.error('Failed to cancel poll:', error);
    }
  };

  const totalNodes = nodes.length;
  const totalEdges = Array.from(nodeStatuses.values()).reduce(
    (sum, status) => sum + status.total_neighbors,
    0
  );
  const completedEdges = Array.from(nodeStatuses.values()).reduce(
    (sum, status) => sum + status.completed_edges,
    0
  );
  const verifiedEdges = Array.from(nodeStatuses.values()).reduce(
    (sum, status) => sum + status.verified_edges,
    0
  );

  const overallProgress = totalEdges > 0 ? (completedEdges / totalEdges) * 100 : 0;

  return (
    <Card title="Certification Phase (Protocol 3)">
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-xl font-bold">Certification Graph Progress</h3>
            <p className="text-sm text-gray-600">
              Nodes completing symmetric PPE challenges with neighbors
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className={`px-2 py-1 rounded-full text-xs ${
              isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
            }`}>
              {isConnected ? '🟢 Live' : '🔴 Offline'}
            </div>
            <Button onClick={fetchData} disabled={isLoading} variant="secondary">
              {isLoading ? 'Refreshing...' : '🔄 Refresh'}
            </Button>
          </div>
        </div>

        {/* Real-time update indicator */}
        {realtimeStats && (
          <div className="mb-4 p-2 bg-green-50 border border-green-200 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="animate-pulse text-green-500">●</span>
              <span className="text-sm text-green-800">
                Real-time: {realtimeStats.verifiedEdges}/{realtimeStats.totalEdges} edges verified
              </span>
            </div>
            <span className="text-xs text-green-600">
              Last update: {realtimeStats.lastUpdate}
            </span>
          </div>
        )}

        {/* Overall Progress */}
        <div className="mb-6 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg">
          <div className="grid grid-cols-4 gap-4 mb-3">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">{totalNodes}</div>
              <div className="text-xs text-gray-600">Total Nodes</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">{totalEdges}</div>
              <div className="text-xs text-gray-600">Total Edges</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">{verifiedEdges}</div>
              <div className="text-xs text-gray-600">Verified</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">
                {totalEdges - completedEdges}
              </div>
              <div className="text-xs text-gray-600">Pending</div>
            </div>
          </div>

          <div className="relative h-6 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="absolute inset-0 bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-500"
              style={{ width: `${overallProgress}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white drop-shadow">
              {overallProgress.toFixed(1)}% Complete
            </div>
          </div>
        </div>

        {/* Certification Graph Visualization */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-lg">Certification Graph</h3>
            <Button
              variant="secondary"
              onClick={() => setShowGraph(!showGraph)}
              className="text-sm"
            >
              {showGraph ? 'Hide Graph' : 'Show Graph'}
            </Button>
          </div>
          {showGraph && nodes.length > 0 && (
            <GraphVisualization
              nodes={nodes.map(n => n.node_id)}
              edges={graphEdges}
              excludedNodes={[]}
              width={700}
              height={400}
            />
          )}
          {!showGraph && (
            <div className="text-sm text-gray-600 p-4 bg-gray-50 rounded border">
              <p>
                Graph contains {nodes.length} nodes and {graphEdges.length} edges
                ({graphEdges.filter(e => e.verified).length} verified).
              </p>
              <p className="mt-1 text-xs">
                Click "Show Graph" to visualize the certification network in real-time.
              </p>
            </div>
          )}
        </div>

        {/* Node-by-Node Status */}
        <div className="space-y-3 mb-6 max-h-96 overflow-y-auto">
          {nodes.map((node) => {
            const status = nodeStatuses.get(node.node_id);
            if (!status) return null;

            const progress =
              status.total_neighbors > 0
                ? (status.completed_edges / status.total_neighbors) * 100
                : 0;

            return (
              <div
                key={node.node_id}
                className="p-3 border border-gray-200 rounded-lg hover:border-primary-300 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex-1">
                    <p className="font-mono text-sm font-medium">
                      {node.node_id.substring(0, 16)}...
                    </p>
                  </div>
                  <div className="text-right text-xs text-gray-600">
                    {status.completed_edges}/{status.total_neighbors} edges
                  </div>
                </div>

                <div className="relative h-4 bg-gray-100 rounded-full overflow-hidden mb-1">
                  <div
                    className="absolute inset-0 bg-primary-500 transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-xs">
                  <div className="flex gap-3">
                    <span className="text-green-600">
                      ✓ {status.verified_edges} verified
                    </span>
                    {status.completed_edges - status.verified_edges > 0 && (
                      <span className="text-red-600">
                        ✗ {status.completed_edges - status.verified_edges} failed
                      </span>
                    )}
                    {status.pending_edges > 0 && (
                      <span className="text-orange-600">⏳ {status.pending_edges} pending</span>
                    )}
                  </div>
                  <span className="font-bold text-gray-700">{progress.toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Threshold Status */}
        {thresholdStatus && (
          <div className={`mb-4 p-4 rounded-lg border-2 ${
            thresholdStatus.threshold_met
              ? 'bg-green-50 border-green-300'
              : 'bg-orange-50 border-orange-300'
          }`}>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-bold text-lg">
                {thresholdStatus.threshold_met ? '✅' : '⚠️'} Certification Threshold
              </h4>
              <div className={`text-2xl font-bold ${
                thresholdStatus.threshold_met ? 'text-green-600' : 'text-orange-600'
              }`}>
                {thresholdStatus.certification_rate.toFixed(1)}%
              </div>
            </div>
            <p className={`text-sm mb-3 ${
              thresholdStatus.threshold_met ? 'text-green-800' : 'text-orange-800'
            }`}>
              {thresholdStatus.message}
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white bg-opacity-50 rounded p-2">
                <p className="text-xs text-gray-600 mb-1">Certified Nodes</p>
                <p className="text-lg font-bold text-green-600">
                  {thresholdStatus.certified_nodes.length}
                </p>
              </div>
              <div className="bg-white bg-opacity-50 rounded p-2">
                <p className="text-xs text-gray-600 mb-1">Uncertified Nodes</p>
                <p className="text-lg font-bold text-red-600">
                  {thresholdStatus.uncertified_nodes.length}
                </p>
              </div>
            </div>

            {!thresholdStatus.threshold_met && thresholdStatus.uncertified_nodes.length > 0 && (
              <div className="mt-3 pt-3 border-t border-orange-200">
                <p className="text-xs font-medium text-orange-800 mb-2">
                  Nodes that need to complete certification:
                </p>
                <div className="max-h-32 overflow-y-auto space-y-1">
                  {thresholdStatus.uncertified_nodes.map((nodeId) => (
                    <div key={nodeId} className="font-mono text-xs text-orange-700 bg-white bg-opacity-50 px-2 py-1 rounded">
                      {nodeId.substring(0, 16)}...
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="border-t pt-4">
          <div className="flex gap-3">
            <Button
              onClick={advanceToVoting}
              disabled={!thresholdStatus || !thresholdStatus.threshold_met}
              className="flex-1"
            >
              {!thresholdStatus
                ? 'Loading threshold status...'
                : thresholdStatus.threshold_met
                ? 'Advance to Voting'
                : `Cannot Advance: ${thresholdStatus.certification_rate.toFixed(1)}% < ${thresholdStatus.required_threshold}% required`}
            </Button>
            {thresholdStatus && !thresholdStatus.threshold_met && (
              <Button
                onClick={cancelPoll}
                variant="secondary"
                className="bg-red-100 hover:bg-red-200 text-red-700 border-red-300"
              >
                Cancel Poll
              </Button>
            )}
          </div>
          {thresholdStatus && thresholdStatus.threshold_met && (
            <p className="text-xs text-gray-500 mt-2 text-center">
              Certification threshold met ({thresholdStatus.certified_nodes.length}/{thresholdStatus.total_nodes} nodes). Ready for Protocol 4 (voting).
            </p>
          )}
          {thresholdStatus && !thresholdStatus.threshold_met && (
            <p className="text-xs text-orange-600 mt-2 text-center">
              ⚠️ Waiting for more nodes to complete certification. Need {thresholdStatus.required_threshold}% certified to advance.
              <br />
              <span className="text-red-600 font-medium">
                If enough nodes won't complete certification, you can cancel the poll using the button above.
              </span>
            </p>
          )}
        </div>
      </div>

      <div className="bg-purple-50 border border-purple-200 rounded p-3 text-sm">
        <p className="font-bold mb-1">🔐 Protocol 3 Status:</p>
        <ul className="text-purple-800 space-y-1 text-xs">
          <li>✓ Neighbors computed using H(i,j) ≤ p (deterministic graph)</li>
          <li>✓ Symmetric PPE via WebSocket (challenge exchange)</li>
          <li>✓ Commitments → Solutions → Signatures</li>
          <li>
            {overallProgress >= 100 ? '✓' : '○'} All edges verified, ready to advance
          </li>
        </ul>
      </div>
    </Card>
  );
}
