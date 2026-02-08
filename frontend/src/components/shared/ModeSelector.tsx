import React from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import type { Mode } from '../../types';

interface ModeSelectorProps {
  onSelectMode: (mode: Mode) => void;
}

export function ModeSelector({ onSelectMode }: ModeSelectorProps) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-4xl w-full">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-primary-600 mb-2">
            PPE Polling System
          </h1>
          <p className="text-gray-600">
            Public Verification of Private Effort - Sybil-resistant anonymous polling
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Pollster */}
          <div className="border-2 border-gray-200 rounded-lg p-6 hover:border-primary-500 transition-colors">
            <div className="text-center mb-4">
              <div className="text-4xl mb-2">📊</div>
              <h3 className="text-xl font-bold mb-2">Pollster</h3>
              <p className="text-sm text-gray-600 mb-4">
                Create and manage polls. Monitor registration, certification, and voting phases.
              </p>
            </div>
            <Button onClick={() => onSelectMode('pollster')} className="w-full">
              Start as Pollster
            </Button>
          </div>

          {/* Responder */}
          <div className="border-2 border-gray-200 rounded-lg p-6 hover:border-primary-500 transition-colors">
            <div className="text-center mb-4">
              <div className="text-4xl mb-2">🗳️</div>
              <h3 className="text-xl font-bold mb-2">Responder</h3>
              <p className="text-sm text-gray-600 mb-4">
                Register with CAPTCHA, complete peer verification (PPE), and submit your vote.
              </p>
            </div>
            <Button onClick={() => onSelectMode('responder')} className="w-full">
              Join as Responder
            </Button>
          </div>

          {/* Verifier */}
          <div className="border-2 border-gray-200 rounded-lg p-6 hover:border-primary-500 transition-colors">
            <div className="text-center mb-4">
              <div className="text-4xl mb-2">🔍</div>
              <h3 className="text-xl font-bold mb-2">Verifier</h3>
              <p className="text-sm text-gray-600 mb-4">
                Independently verify published poll results. Anyone can verify!
              </p>
            </div>
            <Button onClick={() => onSelectMode('verifier')} className="w-full">
              Verify Results
            </Button>
          </div>
        </div>

        <div className="mt-6 text-center text-sm text-gray-500">
          <p>
            Built with ECDSA P-256, Web Crypto API, and WebSocket for real-time PPE coordination
          </p>
        </div>
      </Card>
    </div>
  );
}
