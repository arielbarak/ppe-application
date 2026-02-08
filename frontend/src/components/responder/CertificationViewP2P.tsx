/**
 * CertificationViewP2P - Peer-to-Peer PPE Implementation
 *
 * UI component for Protocol 3 (Responder Certification).
 * State machine logic is encapsulated in usePpeHandshake hook.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { api } from '../../services/api';
import { useWebSocket } from '../../hooks/useWebSocket';
import { usePpeHandshake } from '../../hooks/usePpeHandshake';
import type { WSMessage, PpePayload } from '../../types';
import { updateCertificationProgress } from '../../services/storage';
import { extractChallengeText } from '../../services/symmetricCaptcha';
import { getProvider, DEFAULT_PPE_TYPE, deriveDifficultyFromEtaE } from '../../services/ppe';

interface CertificationViewP2PProps {
  sessionId: string;
  nodeId: string;
  publicKeyBase64: string;
  onComplete: () => void;
  onBack: () => void;
  signMessage: (message: string) => Promise<string>;
  ppeType?: string;
}

interface Neighbor {
  nodeId: string;
  publicKey?: string;
  status: 'pending' | 'in_progress' | 'verified' | 'failed';
  hasPendingRequest?: boolean;
}

export function CertificationViewP2P({
  sessionId,
  nodeId,
  publicKeyBase64,
  onComplete,
  onBack,
  signMessage,
  ppeType = DEFAULT_PPE_TYPE,
}: CertificationViewP2PProps) {
  // UI State
  const [neighbors, setNeighbors] = useState<Neighbor[]>([]);
  const [certStatus, setCertStatus] = useState<any>(null);
  const [pendingRequests, setPendingRequests] = useState<Record<string, { sessionId: string; fromNode: string }>>({});
  const [difficulty, setDifficulty] = useState<number>(0.5);
  const [neighborsError, setNeighborsError] = useState<string | null>(null);
  const [isLoadingNeighbors, setIsLoadingNeighbors] = useState(true);

  const pendingRequestsRef = useRef(pendingRequests);
  pendingRequestsRef.current = pendingRequests;

  // Data fetching
  const fetchCertificationStatus = useCallback(async () => {
    try {
      const status = await api.getCertificationStatus(sessionId, nodeId);
      setCertStatus(status);
      updateCertificationProgress(sessionId, status.verified_edges || 0, status.total_edges || 0);
    } catch (error) {
      console.error('Failed to fetch certification status:', error);
    }
  }, [sessionId, nodeId]);

  const fetchNeighbors = useCallback(async () => {
    setIsLoadingNeighbors(true);
    try {
      const result = await api.getNeighborsDetailed(sessionId, nodeId);
      setNeighborsError(null);
      setNeighbors(prev => {
        const existingStatuses = new Map(prev.map(n => [n.nodeId, n]));
        const currentPendingRequests = pendingRequestsRef.current;
        return result.neighbors.map((neighbor) => {
          const existing = existingStatuses.get(neighbor.node_id);
          if (existing && (existing.status === 'verified' || existing.status === 'failed')) {
            return { ...existing, publicKey: neighbor.public_key };
          }
          const serverStatus = neighbor.status as 'pending' | 'verified' | 'failed';
          return {
            nodeId: neighbor.node_id,
            publicKey: neighbor.public_key,
            status: serverStatus !== 'pending' ? serverStatus : (existing?.status || 'pending'),
            hasPendingRequest: existing?.hasPendingRequest || neighbor.node_id in currentPendingRequests,
          };
        });
      });
    } catch (error: any) {
      console.error('Failed to fetch neighbors:', error);
      try {
        const result = await api.getNeighbors(sessionId, nodeId);
        setNeighborsError(null);
        setNeighbors(prev => {
          const existingStatuses = new Map(prev.map(n => [n.nodeId, n]));
          const currentPendingRequests = pendingRequestsRef.current;
          return result.neighbors.map((nId: string) => {
            const existing = existingStatuses.get(nId);
            if (existing && (existing.status === 'verified' || existing.status === 'failed')) {
              return existing;
            }
            return {
              nodeId: nId,
              publicKey: '',
              status: 'pending' as const,
              hasPendingRequest: existing?.hasPendingRequest || nId in currentPendingRequests,
            };
          });
        });
      } catch (fallbackError: any) {
        const errorMsg = fallbackError?.message || error?.message || 'Unknown error';
        if (errorMsg.includes('not in certification phase') || errorMsg.includes('400')) {
          setNeighborsError('Waiting for poll to enter certification phase...');
        } else {
          setNeighborsError(`Failed to load neighbors: ${errorMsg}`);
        }
      }
    } finally {
      setIsLoadingNeighbors(false);
    }
  }, [sessionId, nodeId]);

  // P2P Message Relay
  const { isConnected, sendMessage } = useWebSocket({
    sessionId,
    nodeId,
    role: 'responder',
    onMessage: () => {}, // Will be set after hook initialization
  });

  const sendToPeer = useCallback((targetNode: string, payload: PpePayload) => {
    sendMessage('ppe.relay', { target_node: targetNode, payload });
  }, [sendMessage]);

  // PPE Handshake Hook
  const handshake = usePpeHandshake({
    nodeId,
    publicKeyBase64,
    ppeType,
    difficulty,
    sendToPeer,
    sendMessage,
    signMessage,
    onComplete: (peerNodeId, success) => {
      setNeighbors(prev =>
        prev.map(n =>
          n.nodeId === peerNodeId
            ? { ...n, status: success ? 'verified' : 'failed' }
            : n
        )
      );
      fetchCertificationStatus();
    },
  });

  // WebSocket Message Handling
  const handleWSMessage = useCallback(async (message: WSMessage) => {
    switch (message.type) {
      case 'ppe.request': {
        const { ppe_session_id, from_node } = message.data as any;

        if (handshake.isActive && handshake.session?.peerNodeId === from_node) {
          // Conflict - use node ID ordering
          if (nodeId < from_node) {
            console.log(`[P2P] Conflict: we initiate, ignoring their request`);
            break;
          }
        }

        setPendingRequests(prev => ({ ...prev, [from_node]: { sessionId: ppe_session_id, fromNode: from_node } }));
        setNeighbors(prev => prev.map(n => n.nodeId === from_node ? { ...n, hasPendingRequest: true } : n));
        break;
      }

      case 'ppe.initiated': {
        const { ppe_session_id } = message.data as any;
        handshake.updateSessionId(ppe_session_id);
        break;
      }

      case 'ppe.message': {
        const { from_node, payload } = message.data as any;
        handshake.handlePeerMessage(from_node, payload as PpePayload);
        break;
      }

      case 'status_change':
      case 'status.changed': {
        if (message.data.new_status === 'voting') {
          onComplete();
        }
        break;
      }
    }
  }, [handshake, nodeId, onComplete]);

  // Re-register message handler
  const { sendMessage: _, ...wsRest } = useWebSocket({
    sessionId,
    nodeId,
    role: 'responder',
    onMessage: handleWSMessage,
  });

  // Conflict resolution helper
  const shouldInitiate = (myId: string, peerId: string): boolean => myId < peerId;

  // PPE Actions
  const initiatePPE = async (targetNode: string, targetPublicKey: string) => {
    if (!isConnected) return;

    const pendingRequest = pendingRequests[targetNode];
    if (pendingRequest) {
      if (!shouldInitiate(nodeId, targetNode)) {
        await acceptPPERequest(targetNode, targetPublicKey);
        return;
      }
      setPendingRequests(prev => {
        const { [targetNode]: _, ...rest } = prev;
        return rest;
      });
      setNeighbors(prev => prev.map(n => n.nodeId === targetNode ? { ...n, hasPendingRequest: false } : n));
    }

    setNeighbors(prev => prev.map(n => n.nodeId === targetNode ? { ...n, status: 'in_progress' } : n));
    sendMessage('ppe.initiate', { target_node: targetNode });
    await handshake.initiate(targetNode, targetPublicKey);
  };

  const acceptPPERequest = async (fromNode: string, fromPublicKey: string) => {
    const request = pendingRequests[fromNode];
    if (!request) return;

    setPendingRequests(prev => {
      const { [fromNode]: _, ...rest } = prev;
      return rest;
    });
    setNeighbors(prev => prev.map(n =>
      n.nodeId === fromNode ? { ...n, status: 'in_progress', hasPendingRequest: false } : n
    ));

    await handshake.initiate(fromNode, fromPublicKey, request.sessionId);
  };

  // Clear stale pending requests when handshake starts
  useEffect(() => {
    if (!handshake.session) return;
    const peerNodeId = handshake.session.peerNodeId;
    if (peerNodeId in pendingRequests) {
      setPendingRequests(prev => {
        const { [peerNodeId]: _, ...rest } = prev;
        return rest;
      });
      setNeighbors(prev => prev.map(n => n.nodeId === peerNodeId ? { ...n, hasPendingRequest: false } : n));
    }
  }, [handshake.session?.peerNodeId, pendingRequests]);

  // Fetch poll info for difficulty
  useEffect(() => {
    const fetchPollInfo = async () => {
      try {
        const poll = await api.getPoll(sessionId);
        const etaE = poll.parameters.effort_threshold;
        setDifficulty(deriveDifficultyFromEtaE(etaE));
      } catch (error) {
        console.error('Failed to fetch poll info:', error);
      }
    };
    fetchPollInfo();
  }, [sessionId]);

  // Initial data fetch and polling
  useEffect(() => {
    fetchNeighbors();
    fetchCertificationStatus();

    const neighborsInterval = setInterval(() => {
      if (neighborsError || neighbors.length === 0) fetchNeighbors();
    }, 3000);

    const statusInterval = setInterval(fetchCertificationStatus, 5000);

    return () => {
      clearInterval(neighborsInterval);
      clearInterval(statusInterval);
    };
  }, [fetchNeighbors, fetchCertificationStatus, neighborsError, neighbors.length]);

  // Active PPE modal
  if (handshake.isActive && handshake.session) {
    const { session, phase } = handshake;

    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="P2P PPE Challenge" className="max-w-md w-full">
          <div className="mb-4 p-3 bg-blue-50 rounded text-sm text-blue-800">
            <p className="font-semibold">Peer-to-Peer Verification</p>
            <p>Challenges are generated client-side with cryptographic binding.</p>
          </div>

          <div className="mb-4">
            <p className="text-sm text-gray-600">PPE with:</p>
            <p className="font-mono text-sm">{session.peerNodeId}</p>
          </div>

          <div className="mb-4">
            <p className="text-sm text-gray-600">State:</p>
            <p className={`font-semibold ${phase.includes('await') ? 'text-yellow-600' : 'text-blue-600'}`}>
              {phase.replace(/_/g, ' ')}
            </p>
          </div>

          {phase === 'solving' && session.theirChallengeImage && (() => {
            const provider = getProvider(ppeType);
            return (
              <>
                <div className="mb-4 p-4 bg-gray-100 rounded-lg">
                  <p className="text-sm text-gray-600 mb-2">Solve their challenge:</p>
                  <p className="text-2xl font-mono font-bold text-center">
                    {extractChallengeText(session.theirChallengeImage, ppeType)}
                  </p>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium mb-2">Your Answer:</label>
                  <input
                    type={provider.inputType || 'text'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    value={session.solutionInput || ''}
                    onChange={(e) => handshake.setSolutionInput(e.target.value)}
                    placeholder={provider.inputPlaceholder || 'Enter your solution'}
                  />
                </div>

                <Button
                  onClick={handshake.submitSolution}
                  disabled={!session.solutionInput?.trim()}
                  className="w-full"
                >
                  Submit & Commit
                </Button>
              </>
            );
          })()}

          {phase === 'awaiting_peer_commitment' && (
            <WaitingSpinner color="blue" text="Waiting for peer's commitment..." subtext="Your solution is committed securely" />
          )}

          {phase === 'awaiting_peer_key' && (
            <WaitingSpinner color="green" text="Both committed! Exchanging keys..." subtext="Verifying challenge bindings" />
          )}

          {phase === 'verifying_binding' && (
            <WaitingSpinner color="yellow" text="Verifying challenge binding..." subtext="Checking HMAC proof" />
          )}

          {(phase === 'awaiting_peer_solution' || phase === 'signing') && (
            <WaitingSpinner color="purple" text="Exchanging solutions and signatures..." subtext="Almost done!" />
          )}

          {phase === 'awaiting_peer_challenge' && (
            <WaitingSpinner color="blue" text="Exchanging challenges..." />
          )}

          <Button variant="secondary" onClick={handshake.cancel} className="w-full mt-4">
            Cancel
          </Button>
        </Card>
      </div>
    );
  }

  // Completed/Failed state
  if (handshake.session && (handshake.phase === 'completed' || handshake.phase === 'failed')) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="PPE Result" className="max-w-md w-full">
          <div className={`text-center p-6 rounded-lg ${handshake.phase === 'completed' ? 'bg-green-50' : 'bg-red-50'}`}>
            <p className="text-4xl mb-2">{handshake.phase === 'completed' ? '✓' : '✗'}</p>
            <p className="text-lg font-semibold">
              {handshake.phase === 'completed' ? 'PPE Verified Successfully!' : 'PPE Verification Failed'}
            </p>
            {handshake.session.errorMessage && (
              <p className="text-sm text-red-600 mt-2">{handshake.session.errorMessage}</p>
            )}
          </div>
        </Card>
      </div>
    );
  }

  // Main neighbor list view
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card title="Certification Phase (P2P Protocol 3)" className="max-w-2xl w-full">
        <div className="mb-4 p-3 bg-green-50 rounded text-sm text-green-800">
          <p className="font-semibold">Decentralized PPE Mode</p>
          <p>Challenges are generated locally with HMAC binding to prevent proxy attacks.</p>
        </div>

        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="text-sm text-gray-600">Your Node ID:</p>
              <p className="font-mono text-sm">{nodeId}</p>
            </div>
            <ConnectionBadge isConnected={isConnected} />
          </div>

          {certStatus && <CertificationStats certStatus={certStatus} neighborsCount={neighbors.length} />}
        </div>

        <NeighborList
          neighbors={neighbors}
          pendingRequests={pendingRequests}
          isLoading={isLoadingNeighbors}
          error={neighborsError}
          nodeId={nodeId}
          isConnected={isConnected}
          isHandshakeActive={handshake.isActive}
          shouldInitiate={shouldInitiate}
          onInitiate={initiatePPE}
          onAccept={acceptPPERequest}
          onRetry={fetchNeighbors}
        />

        <div className="flex gap-4">
          <Button variant="secondary" onClick={fetchCertificationStatus}>Refresh</Button>
          <Button variant="secondary" onClick={onBack}>Back</Button>
        </div>
      </Card>
    </div>
  );
}

function WaitingSpinner({ color, text, subtext }: { color: string; text: string; subtext?: string }) {
  const colorClass = {
    blue: 'border-blue-500',
    green: 'border-green-500',
    yellow: 'border-yellow-500',
    purple: 'border-purple-500',
  }[color] || 'border-blue-500';

  return (
    <div className="text-center p-4">
      <div className={`animate-spin h-8 w-8 border-4 ${colorClass} border-t-transparent rounded-full mx-auto mb-4`} />
      <p className="text-gray-600">{text}</p>
      {subtext && <p className="text-xs text-gray-400 mt-2">{subtext}</p>}
    </div>
  );
}

function ConnectionBadge({ isConnected }: { isConnected: boolean }) {
  return (
    <div className={`px-3 py-1 rounded-full text-sm ${isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
      {isConnected ? 'Connected' : 'Disconnected'}
    </div>
  );
}

function CertificationStats({ certStatus, neighborsCount }: { certStatus: any; neighborsCount: number }) {
  return (
    <div className="grid grid-cols-3 gap-4 mb-4">
      <div className="p-3 bg-blue-50 rounded-lg text-center">
        <p className="text-2xl font-bold text-blue-600">{certStatus.total_neighbors || neighborsCount}</p>
        <p className="text-xs text-blue-800">Neighbors</p>
      </div>
      <div className="p-3 bg-green-50 rounded-lg text-center">
        <p className="text-2xl font-bold text-green-600">{certStatus.verified_edges || 0}</p>
        <p className="text-xs text-green-800">Verified</p>
      </div>
      <div className="p-3 bg-gray-50 rounded-lg text-center">
        <p className="text-2xl font-bold text-gray-600">
          {(certStatus.total_neighbors || neighborsCount) - (certStatus.verified_edges || 0)}
        </p>
        <p className="text-xs text-gray-800">Pending</p>
      </div>
    </div>
  );
}

interface NeighborListProps {
  neighbors: Neighbor[];
  pendingRequests: Record<string, any>;
  isLoading: boolean;
  error: string | null;
  nodeId: string;
  isConnected: boolean;
  isHandshakeActive: boolean;
  shouldInitiate: (myId: string, peerId: string) => boolean;
  onInitiate: (nodeId: string, publicKey: string) => void;
  onAccept: (nodeId: string, publicKey: string) => void;
  onRetry: () => void;
}

function NeighborList({
  neighbors, pendingRequests, isLoading, error, nodeId, isConnected,
  isHandshakeActive, shouldInitiate, onInitiate, onAccept, onRetry
}: NeighborListProps) {
  if (isLoading && neighbors.length === 0) {
    return (
      <div className="p-4 bg-gray-50 rounded text-center text-gray-600 mb-6">
        <div className="animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
        Loading neighbors...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded text-center mb-6">
        <p className="text-yellow-800">{error}</p>
        <Button variant="secondary" onClick={onRetry} className="mt-3">Retry</Button>
      </div>
    );
  }

  if (neighbors.length === 0) {
    return (
      <div className="p-4 bg-gray-50 rounded text-center text-gray-600 mb-6">
        No neighbors assigned (edge probability may be too low)
      </div>
    );
  }

  return (
    <div className="space-y-3 mb-6">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-gray-700">Your Neighbors:</h3>
        <span className="text-xs text-gray-500">Initiator: smaller node ID</span>
      </div>

      {neighbors.map((neighbor) => (
        <NeighborRow
          key={neighbor.nodeId}
          neighbor={neighbor}
          hasPendingRequest={neighbor.hasPendingRequest || neighbor.nodeId in pendingRequests}
          nodeId={nodeId}
          isConnected={isConnected}
          isHandshakeActive={isHandshakeActive}
          shouldInitiate={shouldInitiate}
          onInitiate={onInitiate}
          onAccept={onAccept}
        />
      ))}
    </div>
  );
}

interface NeighborRowProps {
  neighbor: Neighbor;
  hasPendingRequest: boolean;
  nodeId: string;
  isConnected: boolean;
  isHandshakeActive: boolean;
  shouldInitiate: (myId: string, peerId: string) => boolean;
  onInitiate: (nodeId: string, publicKey: string) => void;
  onAccept: (nodeId: string, publicKey: string) => void;
}

function NeighborRow({
  neighbor, hasPendingRequest, nodeId, isConnected, isHandshakeActive,
  shouldInitiate, onInitiate, onAccept
}: NeighborRowProps) {
  const iAmInitiator = shouldInitiate(nodeId, neighbor.nodeId);

  return (
    <div className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50">
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <p className="font-mono text-sm">{neighbor.nodeId}</p>
          {hasPendingRequest && (
            <span className="px-2 py-1 text-xs bg-orange-100 text-orange-800 rounded-full">! Request</span>
          )}
          {neighbor.status === 'pending' && !hasPendingRequest && !iAmInitiator && (
            <span className="px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">They initiate</span>
          )}
          {neighbor.status === 'pending' && !hasPendingRequest && iAmInitiator && (
            <span className="px-2 py-1 text-xs bg-blue-100 text-blue-600 rounded-full">You initiate</span>
          )}
        </div>
        <p className="text-xs text-gray-500">
          Status: <StatusLabel status={neighbor.status} />
        </p>
      </div>

      <div className="flex gap-2">
        {hasPendingRequest ? (
          <Button
            onClick={() => onAccept(neighbor.nodeId, neighbor.publicKey || '')}
            disabled={!isConnected || isHandshakeActive}
            className="bg-green-600 hover:bg-green-700"
          >
            Accept PPE
          </Button>
        ) : neighbor.status === 'pending' ? (
          iAmInitiator ? (
            <Button
              onClick={() => onInitiate(neighbor.nodeId, neighbor.publicKey || '')}
              disabled={!isConnected || isHandshakeActive}
            >
              Start PPE
            </Button>
          ) : (
            <span className="px-3 py-2 text-sm text-gray-500 bg-gray-100 rounded">Waiting for peer...</span>
          )
        ) : (
          <Button disabled>
            {neighbor.status === 'in_progress' && 'In Progress'}
            {neighbor.status === 'verified' && '✓ Done'}
            {neighbor.status === 'failed' && '✗ Failed'}
          </Button>
        )}
      </div>
    </div>
  );
}

function StatusLabel({ status }: { status: Neighbor['status'] }) {
  const config = {
    verified: { class: 'text-green-600', text: '✓ Verified' },
    in_progress: { class: 'text-blue-600', text: 'In Progress' },
    failed: { class: 'text-red-600', text: '✗ Failed' },
    pending: { class: 'text-gray-600', text: 'Pending' },
  };
  const { class: className, text } = config[status];
  return <span className={`font-semibold ${className}`}>{text}</span>;
}
