/**
 * React hook for WebSocket communication
 *
 * Manages real-time PPE coordination via WebSocket
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { WSMessage, Mode } from '../types';

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

interface UseWebSocketOptions {
  sessionId: string | null;
  nodeId: string | null;
  role: Mode | null;
  onMessage?: (message: WSMessage) => void;
}

export function useWebSocket({ sessionId, nodeId, role, onMessage }: UseWebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  const isConnectingRef = useRef(false);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const shouldReconnectRef = useRef(true);
  const connectRef = useRef<(() => void) | null>(null);

  // Keep the ref updated with the latest onMessage callback
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  /**
   * Send a message via WebSocket
   */
  const sendMessage = useCallback((type: string, data: any) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not connected, cannot send message');
      return false;
    }

    const message = { type, data };
    wsRef.current.send(JSON.stringify(message));
    console.log('WS sent:', type, data);
    return true;
  }, []);

  /**
   * Connect to WebSocket
   */
  const connect = useCallback(() => {
    if (!sessionId || !nodeId || !role) {
      console.log('Not connecting: missing sessionId, nodeId, or role');
      return;
    }

    // Prevent multiple connection attempts
    if (isConnectingRef.current) {
      console.log('Already connecting, skipping...');
      return;
    }

    // Clear any pending reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Disable reconnect BEFORE closing old WebSocket to prevent its onclose
    // from scheduling a reconnect (which would interfere with our new connection)
    shouldReconnectRef.current = false;

    // Close existing connection if any
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    // Enable auto-reconnect for this NEW connection
    shouldReconnectRef.current = true;
    isConnectingRef.current = true;

    const wsUrl = `${WS_BASE_URL}/ws/${sessionId}?node_id=${nodeId}&role=${role}`;
    console.log('Connecting to WebSocket:', wsUrl);

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      isConnectingRef.current = false;
      setIsConnected(true);

      // Clear any stale reconnect timeouts (belt and suspenders)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      // Send heartbeat every 30 seconds
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping', data: {} }));
        }
      }, 30000);

      ws.pingInterval = pingInterval;
    };

    ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);
        console.log('WS received:', message.type, message.data);

        setLastMessage(message);
        if (onMessageRef.current) {
          onMessageRef.current(message);
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      isConnectingRef.current = false;
    };

    ws.onclose = (event) => {
      console.log('WebSocket disconnected, code:', event.code, 'reason:', event.reason);
      isConnectingRef.current = false;
      setIsConnected(false);

      // Clear ping interval
      if (ws.pingInterval) {
        clearInterval(ws.pingInterval);
      }

      // Auto-reconnect if unexpected disconnect (not manual)
      if (shouldReconnectRef.current) {
        console.log('Will attempt reconnection in 2 seconds...');
        reconnectTimeoutRef.current = window.setTimeout(() => {
          if (shouldReconnectRef.current && connectRef.current) {
            console.log('Attempting reconnection...');
            connectRef.current();
          }
        }, 2000);
      }
    };

    wsRef.current = ws;
  }, [sessionId, nodeId, role]);

  // Keep the ref updated with the latest connect function
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  /**
   * Disconnect from WebSocket
   */
  const disconnect = useCallback(() => {
    // Stop reconnection attempts
    shouldReconnectRef.current = false;
    isConnectingRef.current = false;

    // Clear any pending reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      if (wsRef.current.pingInterval) {
        clearInterval(wsRef.current.pingInterval);
      }
      // Only close if the connection is open or connecting
      if (wsRef.current.readyState === WebSocket.OPEN ||
          wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }

    setIsConnected(false);
    console.log('WebSocket manually disconnected');
  }, []);

  // Auto-connect when parameters are available
  useEffect(() => {
    if (sessionId && nodeId && role) {
      connect();
    }

    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, nodeId, role]);

  return {
    isConnected,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
  };
}

// Extend WebSocket type to include custom properties
declare global {
  interface WebSocket {
    pingInterval?: number;
  }
}
