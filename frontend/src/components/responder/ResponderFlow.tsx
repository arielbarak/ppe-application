import React, { useState, useEffect, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { useCrypto } from '../../hooks/useCrypto';
import { useWebSocket } from '../../hooks/useWebSocket';
import { api } from '../../services/api';
import { CertificationView } from './CertificationView';
import { CertificationViewP2P } from './CertificationViewP2P';
import { VotingView } from './VotingView';
import { SessionList } from './SessionList';

// Feature flag for P2P mode (decentralized challenge generation)
const USE_P2P_CERTIFICATION = true;
import type { WSMessage } from '../../types';
import {
  saveSession,
  updateSessionProgress,
  updateCertificationProgress,
  touchSession,
  getSession,
  type SavedSession,
} from '../../services/storage';

interface ResponderFlowProps {
  onReset: () => void;
  onSwitchToVerifier: (sessionId: string) => void;
}

export function ResponderFlow({ onReset, onSwitchToVerifier }: ResponderFlowProps) {
  const [sessionId, setSessionId] = useState('');
  const [step, setStep] = useState<'join' | 'captcha' | 'registered' | 'certification' | 'voting'>('join');
  const [captchaChallenge, setCaptchaChallenge] = useState<any>(null);
  const [captchaSolution, setCaptchaSolution] = useState('');
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [pollStatus, setPollStatus] = useState<string>('registration');
  const [showSessionList, setShowSessionList] = useState(true);
  const [isRestoringSession, setIsRestoringSession] = useState(false);
  const [hasVoted, setHasVoted] = useState(false);
  const [isCertified, setIsCertified] = useState(false);
  const [certificationStatus, setCertificationStatus] = useState<{
    verified_edges: number;
    total_edges: number;
    message: string;
  } | null>(null);
  const [ppeType, setPpeType] = useState<string | undefined>(undefined);

  const { generateKeyPair, publicKeyBase64, hasKeys, exportKeys, restoreKeys, signMessage } = useCrypto();

  // WebSocket message handler
  const handleWSMessage = useCallback((message: WSMessage) => {
    console.log('ResponderFlow received:', message.type, message.data);

    switch (message.type) {
      case 'status.changed':
        const newStatus = message.data.new_status;
        console.log('Poll status changed to:', newStatus);

        if (newStatus === 'cancelled') {
          alert('⚠️ Poll Cancelled\n\nThe pollster has cancelled this poll because not enough participants completed the certification phase.\n\nThank you for participating!');
        }
        break;
    }
  }, []);

  // Connect to WebSocket when we have session and node info.
  // During P2P certification, CertificationViewP2P manages its own WebSocket.
  // We must NOT create a second connection to the same (session, node) or the
  // server will overwrite one with the other, causing an infinite reconnect loop.
  const skipWS = step === 'certification' && USE_P2P_CERTIFICATION;
  const { isConnected } = useWebSocket({
    sessionId: skipWS ? null : (sessionId || null),
    nodeId: nodeId || null,
    role: 'responder',
    onMessage: handleWSMessage,
  });

  const handleRestoreSession = async (savedSession: SavedSession) => {
    setIsRestoringSession(true);
    try {
      // Restore keys
      await restoreKeys(
        savedSession.privateKeyJWK,
        savedSession.publicKeyJWK,
        savedSession.publicKeyBase64
      );

      // Restore state
      setSessionId(savedSession.sessionId);
      setNodeId(savedSession.nodeId);
      setStep(savedSession.currentStep);
      setPollStatus(savedSession.pollStatus);
      setHasVoted(savedSession.hasVoted || false);

      // Update last accessed time
      touchSession(savedSession.sessionId);

      // Hide session list
      setShowSessionList(false);

      console.log('Session restored:', savedSession.sessionId);
    } catch (error) {
      console.error('Failed to restore session:', error);
      alert('Failed to restore session. Please join a new poll.');
    } finally {
      setIsRestoringSession(false);
    }
  };

  const handleStartNewSession = () => {
    setShowSessionList(false);
    setStep('join');
  };

  const joinPoll = async () => {
    if (!sessionId.trim()) {
      alert('Please enter a Session ID');
      return;
    }

    // Check if already registered for this poll
    const existingSession = getSession(sessionId.trim());
    if (existingSession) {
      const restore = window.confirm(
        'You are already registered for this poll.\n\n' +
        'Would you like to restore your existing session?\n\n' +
        'Click OK to restore, or Cancel to go back.'
      );
      if (restore) {
        await handleRestoreSession(existingSession);
      }
      return;
    }

    setIsLoading(true);
    try {
      // Generate keys
      if (!hasKeys) {
        await generateKeyPair();
      }

      // Get CAPTCHA
      const captcha = await api.getCaptcha(sessionId);
      setCaptchaChallenge(captcha);
      setStep('captcha');
    } catch (error) {
      console.error('Failed to join poll:', error);
      alert(`Failed to join poll: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  const solveCaptcha = async () => {
    if (!captchaSolution.trim() || !publicKeyBase64 || !captchaChallenge) {
      alert('Please solve the CAPTCHA');
      return;
    }

    setIsLoading(true);
    try {
      const result = await api.register(sessionId, {
        pseudonym: publicKeyBase64,
        captcha_solution: captchaSolution,
        captcha_token: captchaChallenge.token,
      });

      setNodeId(result.node_id);
      setStep('registered');
      console.log('Registered as node:', result.node_id);

      // Save session to localStorage for re-access
      const keys = await exportKeys();
      if (keys) {
        saveSession({
          sessionId,
          nodeId: result.node_id,
          publicKeyBase64,
          publicKeyJWK: keys.publicKeyJWK,
          privateKeyJWK: keys.privateKeyJWK,
          currentStep: 'registered',
          pollStatus: 'registration',
          savedAt: new Date().toISOString(),
          lastAccessedAt: new Date().toISOString(),
        });
      }
    } catch (error) {
      console.error('Registration failed:', error);
      alert(`Registration failed: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Load hasVoted status from localStorage
  useEffect(() => {
    if (sessionId) {
      const session = getSession(sessionId);
      if (session) {
        setHasVoted(session.hasVoted || false);
      }
    }
  }, [sessionId]);

  // Poll for status changes when registered
  useEffect(() => {
    if ((step === 'registered' || step === 'certification' || step === 'voting') && sessionId && nodeId) {
      const checkStatus = async () => {
        try {
          const pollInfo = await api.getPoll(sessionId);
          setPollStatus(pollInfo.status);
          if (pollInfo.parameters?.ppe_type) {
            setPpeType(pollInfo.parameters.ppe_type);
          }

          // Check certification status when voting opens
          if (pollInfo.status === 'voting' || pollInfo.status === 'certification') {
            try {
              const certStatus = await api.checkNodeCertification(sessionId, nodeId);
              setIsCertified(certStatus.is_certified);
              setCertificationStatus({
                verified_edges: certStatus.verified_edges,
                total_edges: certStatus.total_edges,
                message: certStatus.message,
              });
              // Save certification progress to localStorage for session list display
              updateCertificationProgress(sessionId, certStatus.verified_edges, certStatus.total_edges);
              console.log('Certification status:', certStatus);
            } catch (error) {
              console.error('Failed to check certification status:', error);
            }
          }

          // Update session progress in localStorage
          if (step === 'registered') {
            updateSessionProgress(sessionId, 'registered', pollInfo.status);
          } else if (step === 'certification') {
            updateSessionProgress(sessionId, 'certification', pollInfo.status);
          } else if (step === 'voting') {
            updateSessionProgress(sessionId, 'voting', pollInfo.status);
          }

          // Auto-advance to certification when poll status changes
          if (pollInfo.status === 'certification' && step === 'registered') {
            setStep('certification');
            updateSessionProgress(sessionId, 'certification', pollInfo.status);
          }

          // Auto-advance to voting
          if (pollInfo.status === 'voting' && step === 'certification') {
            setStep('voting');
            updateSessionProgress(sessionId, 'voting', pollInfo.status);
          }
        } catch (error) {
          console.error('Failed to check poll status:', error);
        }
      };

      // Check immediately
      checkStatus();

      // Poll every 3 seconds
      const interval = setInterval(checkStatus, 3000);
      return () => clearInterval(interval);
    }
  }, [step, sessionId, nodeId]);

  // Show session list if enabled
  if (showSessionList) {
    return (
      <SessionList
        onSelectSession={handleRestoreSession}
        onStartNew={handleStartNewSession}
        onBack={onReset}
      />
    );
  }

  if (step === 'join') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="Join Poll as Responder" className="max-w-md w-full">
          <Input
            label="Poll Session ID"
            placeholder="Enter session ID from pollster"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value.trim())}
          />

          <div className="flex gap-4">
            <Button onClick={joinPoll} disabled={isLoading} className="flex-1">
              {isLoading ? 'Joining...' : 'Join Poll (Protocol 2)'}
            </Button>
            <Button variant="secondary" onClick={() => setShowSessionList(true)}>
              Back
            </Button>
          </div>

          <div className="mt-4 p-3 bg-blue-50 rounded text-sm text-blue-800">
            <p><strong>Protocol 2: Registration</strong></p>
            <p className="mt-1">You'll generate a local key pair and solve a CAPTCHA to register.</p>
          </div>
        </Card>
      </div>
    );
  }

  if (step === 'certification' && nodeId) {
    // Use P2P mode for decentralized challenge generation
    if (USE_P2P_CERTIFICATION && publicKeyBase64) {
      return (
        <CertificationViewP2P
          sessionId={sessionId}
          nodeId={nodeId}
          publicKeyBase64={publicKeyBase64}
          onComplete={() => setStep('voting')}
          onBack={onReset}
          signMessage={signMessage}
          ppeType={ppeType}
        />
      );
    }

    // Legacy mode: server-generated challenges
    return (
      <CertificationView
        sessionId={sessionId}
        nodeId={nodeId}
        onComplete={() => setStep('voting')}
        onBack={onReset}
        signMessage={signMessage}
      />
    );
  }

  if (step === 'voting' && nodeId) {
    return (
      <VotingView
        sessionId={sessionId}
        nodeId={nodeId}
        signMessage={signMessage}
        onComplete={() => {
          setHasVoted(true);
          setStep('registered');
        }}
      />
    );
  }

  if (step === 'captcha') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card title="Solve CAPTCHA" className="max-w-md w-full">
          <div className="mb-6 p-4 bg-gray-100 rounded-lg text-center">
            <p className="text-2xl font-mono font-bold">{captchaChallenge?.challenge}</p>
          </div>

          <Input
            label="Your Answer"
            type="number"
            placeholder="Enter answer"
            value={captchaSolution}
            onChange={(e) => setCaptchaSolution(e.target.value)}
          />

          <div className="flex gap-4">
            <Button onClick={solveCaptcha} disabled={isLoading} className="flex-1">
              {isLoading ? 'Submitting...' : 'Submit'}
            </Button>
            <Button variant="secondary" onClick={() => setStep('join')}>
              Cancel
            </Button>
          </div>

          <div className="mt-4 p-3 bg-green-50 rounded text-sm text-green-800">
            <p>🔒 Your private key was generated locally and will never leave your browser!</p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card title="Registration Complete!" className="max-w-md w-full">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
          <p className="font-mono text-sm mb-2">
            <strong>Your Node ID:</strong>
            <br />
            {nodeId}
          </p>
          <p className="text-sm text-green-700 mt-2">
            ✅ You are now registered in the poll!
          </p>
        </div>

        <div className="space-y-4 mb-6">
          <div className={`p-4 rounded ${
            pollStatus === 'cancelled' ? 'bg-red-50 border-2 border-red-300' :
            pollStatus === 'certification' ? 'bg-green-50 border-2 border-green-300' :
            (pollStatus === 'voting' && !hasVoted && isCertified) ? 'bg-green-50 border-2 border-green-300' :
            (pollStatus === 'voting' && !hasVoted && !isCertified) ? 'bg-red-50 border-2 border-red-300' :
            (pollStatus === 'voting' && hasVoted) ? 'bg-blue-50 border-2 border-blue-300' :
            pollStatus === 'results' ? 'bg-purple-50 border-2 border-purple-300' :
            'bg-blue-50'
          }`}>
            <p className={`text-sm ${
              pollStatus === 'cancelled' ? 'text-red-800' :
              pollStatus === 'certification' || (pollStatus === 'voting' && !hasVoted && isCertified) ? 'text-green-800' :
              (pollStatus === 'voting' && !hasVoted && !isCertified) ? 'text-red-800' :
              (pollStatus === 'voting' && hasVoted) ? 'text-blue-800' :
              pollStatus === 'results' ? 'text-purple-800' :
              'text-blue-800'
            }`}>
              <strong>Poll Status: {pollStatus}</strong>
              <br />
              {pollStatus === 'cancelled' && (
                <>
                  ❌ Poll Cancelled by Pollster
                  <br />
                  This poll has been cancelled because not enough participants completed the certification phase.
                  <br />
                  <span className="font-medium">Thank you for participating!</span>
                </>
              )}
              {pollStatus === 'registration' && (
                <>
                  • Waiting for certification phase to start...
                  <br />
                  • The pollster will advance when ready
                </>
              )}
              {pollStatus === 'certification' && (
                <>
                  🎉 Certification phase has started!
                  <br />
                  Click "Continue to Certification" to begin PPE
                </>
              )}
              {pollStatus === 'voting' && !hasVoted && isCertified && (
                <>
                  🗳️ Voting phase has started!
                  <br />
                  Click "Continue to Voting" to cast your vote
                </>
              )}
              {pollStatus === 'voting' && !hasVoted && !isCertified && certificationStatus && (
                <>
                  ❌ Voting is open, but you cannot vote
                  <br />
                  You did not complete certification ({certificationStatus.verified_edges}/{certificationStatus.total_edges} edges verified)
                </>
              )}
              {pollStatus === 'voting' && hasVoted && (
                <>
                  ✅ Vote submitted successfully!
                  <br />
                  Waiting for results to be published...
                </>
              )}
              {pollStatus === 'results' && (
                <>
                  📊 Results have been published!
                  <br />
                  View the final results below
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex gap-4">
          {pollStatus === 'certification' && (
            <Button onClick={() => setStep('certification')} className="flex-1">
              Continue to Certification
            </Button>
          )}
          {pollStatus === 'voting' && !hasVoted && isCertified && (
            <Button onClick={() => setStep('voting')} className="flex-1">
              Continue to Voting
            </Button>
          )}
          {pollStatus === 'voting' && !hasVoted && !isCertified && (
            <Button disabled className="flex-1 bg-gray-400 cursor-not-allowed">
              Cannot Vote - Not Certified
            </Button>
          )}
          {pollStatus === 'voting' && hasVoted && (
            <Button disabled className="flex-1 bg-gray-400 cursor-not-allowed">
              Waiting for Pollster to Publish Results...
            </Button>
          )}
          {pollStatus === 'results' && (
            <Button onClick={() => onSwitchToVerifier(sessionId)} className="flex-1 bg-purple-600 hover:bg-purple-700">
              View Results & Verify
            </Button>
          )}
          <Button variant="secondary" onClick={onReset}>
            {pollStatus === 'results' || pollStatus === 'cancelled' ? 'Back to Menu' : 'Done'}
          </Button>
        </div>
      </Card>
    </div>
  );
}
