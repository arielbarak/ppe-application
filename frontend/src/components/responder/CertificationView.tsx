import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { api } from '../../services/api';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { WSMessage } from '../../types';
import { updateCertificationProgress } from '../../services/storage';

interface CertificationViewProps {
  sessionId: string;
  nodeId: string;
  onComplete: () => void;
  onBack: () => void;
  signMessage: (message: string) => Promise<string>;
}

interface PPESession {
  ppe_session_id: string;
  target_node: string;
  status: 'initiated' | 'waiting_commitment' | 'committed' | 'ready_to_reveal' | 'completed' | 'failed';
  my_challenge?: string;
  their_challenge?: string;
  my_solution?: string;
}

interface PPERequest {
  ppe_session_id: string;
  from_node: string;
  challenge_i_to_j: string;
  challenge_j_to_i: string;
  received_at: Date;
}

interface Neighbor {
  nodeId: string;
  status: 'pending' | 'in_progress' | 'verified' | 'failed';
  hasPendingRequest?: boolean;
  pendingRequest?: PPERequest;
}

export function CertificationView({ sessionId, nodeId, onComplete, onBack, signMessage }: CertificationViewProps) {
  const [neighbors, setNeighbors] = useState<Neighbor[]>([]);
  const [certStatus, setCertStatus] = useState<any>(null);
  const [activePPE, setActivePPE] = useState<PPESession | null>(null);
  const [solution, setSolution] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [pollStatus, setPollStatus] = useState<string>('certification');
  const [pendingRequests, setPendingRequests] = useState<Map<string, PPERequest>>(new Map());
  const cancelledAlertShown = useRef(false);

  const fetchCertificationStatus = useCallback(async () => {
    try {
      const status = await api.getCertificationStatus(sessionId, nodeId);
      setCertStatus(status);

      // Save certification progress to localStorage for session list display
      const verifiedEdges = status.verified_edges || 0;
      const totalEdges = status.total_edges || status.total_neighbors || 0;
      updateCertificationProgress(sessionId, verifiedEdges, totalEdges);

      // Update neighbor statuses based on backend certification status
      if (status.neighbor_statuses) {
        setNeighbors((prev) =>
          prev.map((n) => {
            const backendStatus = status.neighbor_statuses[n.nodeId];
            if (backendStatus === 'verified' || backendStatus === 'failed') {
              return { ...n, status: backendStatus };
            }
            return n;
          })
        );
      }
    } catch (error) {
      console.error('Failed to fetch certification status:', error);
    }
  }, [sessionId, nodeId]);

  const handleWSMessage = useCallback((message: WSMessage) => {
    console.log('Certification received:', message.type, message.data);

    switch (message.type) {
      case 'certification.challenge_received':
        // Someone initiated PPE with us - store as pending request
        const { ppe_session_id, challenge_i_to_j, challenge_j_to_i } = message.data;
        const from_node = message.data.from_node || 'unknown';

        console.log('Storing pending request from:', from_node, 'Current neighbors:', neighbors.length);

        // Store as pending request
        const request: PPERequest = {
          ppe_session_id,
          from_node,
          challenge_i_to_j,
          challenge_j_to_i,
          received_at: new Date(),
        };

        setPendingRequests(prev => {
          const updated = new Map(prev);
          updated.set(from_node, request);
          console.log('Total pending requests:', updated.size);
          return updated;
        });

        // Update neighbor to show badge - only if neighbor exists
        setNeighbors(prev => {
          const neighborExists = prev.some(n => n.nodeId === from_node);
          if (!neighborExists) {
            console.log('Neighbor not yet loaded, request will sync when neighbors load');
            return prev;
          }
          return prev.map(n =>
            n.nodeId === from_node
              ? { ...n, hasPendingRequest: true, pendingRequest: request }
              : n
          );
        });
        break;

      case 'certification.initiated':
        // We initiated PPE and received our challenge
        // As the initiator (i), we solve challenge_j_to_i (the challenge FROM responder TO us)
        const { ppe_session_id: initiated_session_id, target_node, challenge } = message.data;
        console.log('PPE initiated successfully, received challenge');
        console.log('I am the INITIATOR, my challenge:', challenge);
        setActivePPE({
          ppe_session_id: initiated_session_id,
          target_node: target_node,
          status: 'waiting_commitment',
          my_challenge: challenge,  // Initiator solves responder's challenge (challenge_j_to_i)
        });
        break;

      case 'certification.ready_to_reveal':
        // Both committed, now reveal
        setActivePPE((prev) => prev ? { ...prev, status: 'ready_to_reveal' } : null);
        break;

      case 'certification.complete':
        // PPE finished
        const { success } = message.data;
        setActivePPE((prev) => {
          if (prev) {
            // Update neighbor status immediately
            setNeighbors(prevNeighbors =>
              prevNeighbors.map(n =>
                n.nodeId === prev.target_node
                  ? { ...n, status: success ? 'verified' : 'failed' }
                  : n
              )
            );
          }
          return prev ? { ...prev, status: success ? 'completed' : 'failed' } : null;
        });
        // Refresh status
        setTimeout(() => {
          fetchCertificationStatus();
          setActivePPE(null);
          setSolution('');
        }, 2000);
        break;

      case 'status_change':
      case 'status.changed':
        // Poll status changed
        setPollStatus(message.data.new_status);
        if (message.data.new_status === 'voting') {
          onComplete();
        }
        break;
    }
  }, [fetchCertificationStatus, onComplete]);

  const { isConnected, sendMessage } = useWebSocket({
    sessionId,
    nodeId,
    role: 'responder',
    onMessage: handleWSMessage,
  });

  const fetchNeighbors = useCallback(async () => {
    try {
      const result = await api.getNeighbors(sessionId, nodeId);
      setNeighbors((prevNeighbors) => {
        // Create a map of existing statuses to preserve verified/failed states
        const existingStatuses = new Map(
          prevNeighbors.map((n) => [n.nodeId, n])
        );

        return result.neighbors.map((nId: string) => {
          const existing = existingStatuses.get(nId);
          // Preserve verified/failed status, otherwise use pending
          if (existing && (existing.status === 'verified' || existing.status === 'failed')) {
            return existing;
          }
          return {
            nodeId: nId,
            status: 'pending' as const,
            hasPendingRequest: existing?.hasPendingRequest,
            pendingRequest: existing?.pendingRequest,
          };
        });
      });
    } catch (error) {
      console.error('Failed to fetch neighbors:', error);
    }
  }, [sessionId, nodeId]);

  const fetchPollInfo = useCallback(async () => {
    try {
      const pollInfo = await api.getPoll(sessionId);
      setPollStatus(pollInfo.status);
      if (pollInfo.status === 'voting') {
        onComplete();
      }
    } catch (error) {
      console.error('Failed to fetch poll info:', error);
    }
  }, [sessionId, onComplete]);

  // Show alert when poll is cancelled
  useEffect(() => {
    if (pollStatus === 'cancelled' && !cancelledAlertShown.current) {
      cancelledAlertShown.current = true;
      alert('⚠️ Poll Cancelled\n\nThe pollster has cancelled this poll because not enough participants completed the certification phase.\n\nThank you for participating!');
    }
  }, [pollStatus]);

  useEffect(() => {
    fetchNeighbors();
    fetchCertificationStatus();
    fetchPollInfo();

    // Poll for status changes every 5 seconds
    const interval = setInterval(() => {
      fetchPollInfo();
      fetchCertificationStatus();
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchNeighbors, fetchCertificationStatus, fetchPollInfo]);

  useEffect(() => {
    // Clean up expired requests (60 seconds)
    const interval = setInterval(() => {
      const now = new Date();
      setPendingRequests(prev => {
        const updated = new Map(prev);
        let hasChanges = false;

        updated.forEach((request, fromNode) => {
          const age = now.getTime() - request.received_at.getTime();
          if (age > 60000) {
            updated.delete(fromNode);
            hasChanges = true;
          }
        });

        if (hasChanges) {
          setNeighbors(prevNeighbors =>
            prevNeighbors.map(n =>
              updated.has(n.nodeId)
                ? n
                : { ...n, hasPendingRequest: false, pendingRequest: undefined }
            )
          );
        }

        return hasChanges ? updated : prev;
      });
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  // Sync pending requests with neighbors when neighbors load or change
  useEffect(() => {
    if (neighbors.length > 0 && pendingRequests.size > 0) {
      console.log('Syncing', pendingRequests.size, 'pending requests with', neighbors.length, 'neighbors');
      setNeighbors(prev =>
        prev.map(n => {
          const request = pendingRequests.get(n.nodeId);
          if (request && !n.hasPendingRequest) {
            console.log('Synced pending request for:', n.nodeId);
            return { ...n, hasPendingRequest: true, pendingRequest: request };
          }
          return n;
        })
      );
    }
  }, [neighbors.length, pendingRequests.size]);

  const initiatePPE = async (targetNode: string) => {
    console.log('Initiating PPE with:', targetNode);
    console.log('WebSocket connected:', isConnected);
    console.log('My node ID:', nodeId);
    console.log('Session ID:', sessionId);

    if (!isConnected) {
      alert('WebSocket not connected. Please wait...');
      return;
    }

    // Check if we have a pending request from this neighbor
    const incomingRequest = pendingRequests.get(targetNode);
    if (incomingRequest) {
      console.log('Auto-accepting their incoming request');
      // Auto-accept their request instead of creating new session
      acceptPPERequest(targetNode);
      return;
    }

    setIsLoading(true);
    console.log('Sending certification.initiate to:', targetNode);
    const success = sendMessage('certification.initiate', { target_node: targetNode });
    console.log('Send result:', success);

    if (success) {
      console.log('PPE initiation sent successfully');
      setActivePPE({
        ppe_session_id: '', // Will be set when we receive challenge
        target_node: targetNode,
        status: 'initiated',
      });

      // Update neighbor status
      setNeighbors((prev) =>
        prev.map((n) =>
          n.nodeId === targetNode ? { ...n, status: 'in_progress' } : n
        )
      );
    } else {
      console.error('Failed to send PPE initiation');
      alert('Failed to send PPE initiation');
    }
    setIsLoading(false);
  };

  const commitSolution = async () => {
    if (!solution.trim() || !activePPE) {
      alert('Please enter a solution');
      return;
    }

    // Store the solution
    setActivePPE({
      ...activePPE,
      my_solution: solution,
      status: 'committed',
    });

    // Send commitment (using solution as commitment for now)
    sendMessage('certification.commit', {
      ppe_session_id: activePPE.ppe_session_id,
      commitment: solution,
    });
  };

  const revealSolution = async () => {
    if (!activePPE || !activePPE.my_solution) {
      alert('No solution to reveal');
      return;
    }

    try {
      // Sign the solution
      const signature = await signMessage(activePPE.my_solution);

      sendMessage('certification.reveal', {
        ppe_session_id: activePPE.ppe_session_id,
        solution: activePPE.my_solution,
        signature,
      });

      setActivePPE({ ...activePPE, status: 'completed' });
    } catch (error) {
      console.error('Failed to reveal solution:', error);
      alert('Failed to sign solution');
    }
  };

  const acceptPPERequest = (fromNode: string) => {
    const request = pendingRequests.get(fromNode);
    if (!request) {
      console.error('No pending request found for:', fromNode);
      return;
    }

    console.log('Accepting PPE request from:', fromNode);
    console.log('I am the RESPONDER, my challenge:', request.challenge_i_to_j);
    console.log('Their challenge (initiator will solve):', request.challenge_j_to_i);

    // Remove from pending
    setPendingRequests(prev => {
      const updated = new Map(prev);
      updated.delete(fromNode);
      return updated;
    });

    // Update neighbor status
    setNeighbors(prev =>
      prev.map(n =>
        n.nodeId === fromNode
          ? { ...n, status: 'in_progress', hasPendingRequest: false }
          : n
      )
    );

    // Show challenge modal
    // As the responder (j), we solve challenge_i_to_j (the challenge FROM initiator TO us)
    setActivePPE({
      ppe_session_id: request.ppe_session_id,
      target_node: fromNode,
      status: 'waiting_commitment',
      my_challenge: request.challenge_i_to_j,  // Responder solves initiator's challenge
      their_challenge: request.challenge_j_to_i,  // Initiator will solve our challenge
    });
  };

  const rejectPPERequest = (fromNode: string) => {
    // Remove from pending
    setPendingRequests(prev => {
      const updated = new Map(prev);
      updated.delete(fromNode);
      return updated;
    });

    // Update neighbor
    setNeighbors(prev =>
      prev.map(n =>
        n.nodeId === fromNode
          ? { ...n, hasPendingRequest: false, pendingRequest: undefined }
          : n
      )
    );
  };

  // Show PPE challenge modal if there's an active session
  if (activePPE && activePPE.status !== 'completed' && activePPE.status !== 'failed') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="PPE Challenge" className="max-w-md w-full">
          {activePPE.status === 'initiated' && (
            <div className="text-center p-4">
              <p className="text-lg">Initiating PPE with {activePPE.target_node}...</p>
              <p className="text-sm text-gray-600 mt-2">Waiting for response...</p>
            </div>
          )}

          {activePPE.status === 'waiting_commitment' && (
            <>
              <div className="mb-6">
                <div className="p-4 bg-gray-100 rounded-lg mb-4">
                  <p className="text-sm text-gray-600 mb-2">Your challenge to solve:</p>
                  <p className="text-2xl font-mono font-bold text-center">
                    {activePPE.my_challenge}
                  </p>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium mb-2">Your Answer:</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    value={solution}
                    onChange={(e) => setSolution(e.target.value)}
                    placeholder="Enter your solution"
                  />
                </div>
              </div>

              <div className="flex gap-4">
                <Button onClick={commitSolution} disabled={!solution.trim()} className="flex-1">
                  Commit Solution
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setActivePPE(null);
                    setSolution('');
                  }}
                >
                  Cancel
                </Button>
              </div>

              <div className="mt-4 p-3 bg-blue-50 rounded text-sm text-blue-800">
                <p>
                  📝 Your solution will be committed without revealing it yet. Both you and your
                  peer must commit before revealing.
                </p>
              </div>
            </>
          )}

          {activePPE.status === 'committed' && (
            <div className="text-center p-4">
              <p className="text-lg">✓ Solution committed</p>
              <p className="text-sm text-gray-600 mt-2">Waiting for peer to commit...</p>
            </div>
          )}

          {activePPE.status === 'ready_to_reveal' && (
            <>
              <div className="text-center p-4 mb-4">
                <p className="text-lg mb-2">Both solutions committed!</p>
                <p className="text-sm text-gray-600">Ready to reveal and verify</p>
              </div>

              <Button onClick={revealSolution} className="w-full">
                Reveal Solution & Sign
              </Button>
            </>
          )}
        </Card>
      </div>
    );
  }

  // Show completed/failed message briefly
  if (activePPE && (activePPE.status === 'completed' || activePPE.status === 'failed')) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="PPE Result" className="max-w-md w-full">
          <div className={`text-center p-6 rounded-lg ${
            activePPE.status === 'completed' ? 'bg-green-50' : 'bg-red-50'
          }`}>
            <p className="text-2xl mb-2">
              {activePPE.status === 'completed' ? '✓' : '✗'}
            </p>
            <p className="text-lg font-semibold">
              {activePPE.status === 'completed'
                ? 'PPE Verified Successfully!'
                : 'PPE Verification Failed'}
            </p>
            <p className="text-sm text-gray-600 mt-2">
              Returning to certification view...
            </p>
          </div>
        </Card>
      </div>
    );
  }

  // Main certification view
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card title="Certification Phase (Protocol 3)" className="max-w-2xl w-full">
        {pollStatus === 'cancelled' && (
          <div className="mb-6 p-4 bg-red-50 border-2 border-red-300 rounded-lg">
            <p className="text-red-800 font-semibold">❌ Poll Cancelled</p>
            <p className="text-red-700 text-sm mt-1">
              The pollster has cancelled this poll because not enough participants completed the certification phase.
            </p>
            <p className="text-red-700 text-sm mt-2 font-medium">Thank you for participating!</p>
          </div>
        )}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm text-gray-600">Your Node ID:</p>
              <p className="font-mono text-sm">{nodeId}</p>
            </div>
            <div className={`px-3 py-1 rounded-full text-sm ${
              isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
            }`}>
              {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
            </div>
          </div>

          {certStatus && (
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="p-3 bg-blue-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-blue-600">
                  {certStatus.total_neighbors || neighbors.length}
                </p>
                <p className="text-xs text-blue-800">Total Neighbors</p>
              </div>
              <div className="p-3 bg-green-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-green-600">
                  {certStatus.verified_edges || 0}
                </p>
                <p className="text-xs text-green-800">Verified</p>
              </div>
              <div className="p-3 bg-gray-50 rounded-lg text-center">
                <p className="text-2xl font-bold text-gray-600">
                  {certStatus.pending_edges || neighbors.length}
                </p>
                <p className="text-xs text-gray-800">Pending</p>
              </div>
            </div>
          )}

          {certStatus && certStatus.completion_percentage !== undefined && (
            <div className="mb-4">
              <div className="flex justify-between text-sm mb-1">
                <span>Progress</span>
                <span>{Math.round(certStatus.completion_percentage)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all"
                  style={{ width: `${certStatus.completion_percentage}%` }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3 mb-6">
          <h3 className="font-semibold text-sm text-gray-700">Your Neighbors:</h3>

          {neighbors.length === 0 ? (
            <div className="p-4 bg-gray-50 rounded text-center text-gray-600">
              Loading neighbors...
            </div>
          ) : (
            neighbors.map((neighbor) => (
              <div
                key={neighbor.nodeId}
                className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-mono text-sm">{neighbor.nodeId}</p>
                    {(neighbor.hasPendingRequest || pendingRequests.has(neighbor.nodeId)) && (
                      <span className="px-2 py-1 text-xs bg-orange-100 text-orange-800 rounded-full">
                        ! Request
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500">
                    Status: <span className={`font-semibold ${
                      neighbor.status === 'verified' ? 'text-green-600' :
                      neighbor.status === 'in_progress' ? 'text-blue-600' :
                      neighbor.status === 'failed' ? 'text-red-600' :
                      'text-gray-600'
                    }`}>
                      {neighbor.status === 'verified' && '✓ Verified'}
                      {neighbor.status === 'in_progress' && '⏳ In Progress'}
                      {neighbor.status === 'failed' && '✗ Failed'}
                      {neighbor.status === 'pending' && '○ Pending'}
                    </span>
                  </p>
                </div>

                <div className="flex gap-2">
                  {(neighbor.hasPendingRequest || pendingRequests.has(neighbor.nodeId)) ? (
                    <>
                      <Button
                        onClick={() => acceptPPERequest(neighbor.nodeId)}
                        disabled={!isConnected || activePPE !== null || pollStatus === 'cancelled'}
                        className="bg-green-600 hover:bg-green-700"
                      >
                        Accept PPE
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => rejectPPERequest(neighbor.nodeId)}
                        disabled={!isConnected || activePPE !== null || pollStatus === 'cancelled'}
                      >
                        Reject
                      </Button>
                    </>
                  ) : (
                    <Button
                      onClick={() => initiatePPE(neighbor.nodeId)}
                      disabled={
                        neighbor.status !== 'pending' ||
                        isLoading ||
                        !isConnected ||
                        activePPE !== null ||
                        pollStatus === 'cancelled'
                      }
                    >
                      {neighbor.status === 'pending' && 'Start PPE'}
                      {neighbor.status === 'in_progress' && 'In Progress...'}
                      {neighbor.status === 'verified' && '✓ Verified'}
                      {neighbor.status === 'failed' && '✗ Failed'}
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="p-4 bg-blue-50 rounded-lg text-sm text-blue-800">
          <p className="font-semibold mb-1">About PPE (Proof of Private Effort):</p>
          <p>
            Click "Start PPE" to begin certification with a neighbor. You'll both solve simple
            challenges and exchange cryptographic signatures to verify your identities.
          </p>
        </div>

        <div className="mt-4 flex gap-4">
          <Button variant="secondary" onClick={() => fetchCertificationStatus()}>
            Refresh Status
          </Button>
          <Button variant="secondary" onClick={onBack}>
            Back to Home
          </Button>
        </div>
      </Card>
    </div>
  );
}
