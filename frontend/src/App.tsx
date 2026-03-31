import React, { useState } from 'react';
import { ModeSelector } from './components/shared/ModeSelector';
import { PollsterFlowEnhanced } from './components/pollster/PollsterFlowEnhanced';
import { ResponderFlow } from './components/responder/ResponderFlow';
import { VerifierFlow } from './components/verifier/VerifierFlow';
import type { Mode } from './types';

function App() {
  const [mode, setMode] = useState<Mode | null>(null);
  const [verifierSessionId, setVerifierSessionId] = useState<string>('');

  const handleReset = () => {
    setMode(null);
    setVerifierSessionId('');
  };

  const handleSwitchToVerifier = (sessionId: string) => {
    setVerifierSessionId(sessionId);
    setMode('verifier');
  };

  if (!mode) {
    return <ModeSelector onSelectMode={setMode} />;
  }

  return (
    <>
      {mode === 'pollster' && <PollsterFlowEnhanced onReset={handleReset} />}
      {mode === 'responder' && <ResponderFlow onReset={handleReset} onSwitchToVerifier={handleSwitchToVerifier} />}
      {mode === 'verifier' && <VerifierFlow onReset={handleReset} initialSessionId={verifierSessionId} />}
    </>
  );
}

export default App;
