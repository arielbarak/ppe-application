/**
 * TypeScript type definitions for PPE Polling System
 */

export type Mode = 'pollster' | 'responder' | 'verifier';

export type PollStatus = 'registration' | 'certification' | 'voting' | 'results' | 'closed' | 'cancelled';

export interface PollQuestion {
  id: string;
  text: string;
  options: string[];
}

export interface PollSession {
  session_id: string;
  public_key: string;
  questions: PollQuestion[];
  parameters: {
    edge_probability: number;
    effort_threshold: number;
    validity_threshold: number;
    ppe_type?: string;
  };
  status?: PollStatus;
  registered_nodes_count?: number;
  created_at?: string;
}

export interface CaptchaChallenge {
  token: string;
  challenge: string;
  expires_at: string;
}

export interface RegisteredNode {
  node_id: string;
  position: number;
  registration_time: string;
}

export interface Signature {
  from_node: string;
  signature: string;
  edge_label: string;
}

export interface Vote {
  [questionId: string]: string; // question_id -> selected_option
}

export interface PublishedResults {
  session_id: string;
  public_key: string;
  questions: PollQuestion[];
  parameters: {
    edge_probability: number;
    effort_threshold: number;
    validity_threshold: number;
    ppe_type?: string;
  };
  responses: Array<{
    node_id: string;
    vote: Vote;
    signatures: Signature[];
    self_signature: string;
    timestamp: string;
  }>;
  certification_graph: {
    nodes: string[];
    edges: Array<{
      from: string;
      to: string;
      verified: boolean;
      signature?: string;
      timestamp?: string;
    }>;
  };
  published_at: string;
}

export interface VerificationResult {
  verification: 'ACCEPT' | 'REJECT' | 'INVALID';
  tally: {
    [questionId: string]: {
      [option: string]: number;
    };
  };
  excluded_nodes: string[];
  details: {
    total_nodes: number;
    valid_nodes: number;
    excluded_nodes_count: number;
    edge_verification_passed: boolean;
    validity_check_passed?: boolean;
    eta_v?: number;
    max_allowed_exclusions?: number;
    message?: string;
  };
}

// WebSocket message types
export type WSMessageType =
  | 'connection.established'
  | 'poll.status_change'
  | 'status_change'
  | 'status.changed'
  | 'registration.update'
  // Legacy PPE messages (server-generated challenges)
  | 'certification.challenge_received'
  | 'certification.initiated'
  | 'certification.ready_to_reveal'
  | 'certification.complete'
  // New P2P PPE messages (client-generated challenges)
  | 'ppe.request'        // Server notifies: someone wants to start PPE with you
  | 'ppe.initiated'      // Server confirms: PPE session created
  | 'ppe.message'        // Server relays: opaque P2P message from peer
  | 'ppe.complete'       // Client reports: PPE finished
  // Certification monitoring (for pollster)
  | 'certification.edge_added'  // Server notifies: new edge in certification graph
  | 'results.published'
  | 'pong';

export interface WSMessage {
  type: WSMessageType;
  data: Record<string, unknown>;
}

// P2P PPE Protocol Types
/**
 * PPE Message types for peer-to-peer communication
 * These are relayed blindly through the server
 */
export type PpePayloadType =
  | 'challenge'      // Exchange challenges (includes ECDSA binding signature)
  | 'commitment'     // Exchange commitment hashes
  | 'solution'       // Send actual CAPTCHA solution
  | 'signature'      // Send signature if solution correct
  | 'complete'       // Finalization
  | 'error';         // Error state

export interface PpePayload {
  type: PpePayloadType;
  [key: string]: unknown;
}

export interface PpeRelayMessage {
  target_node: string;
  payload: PpePayload;
}
