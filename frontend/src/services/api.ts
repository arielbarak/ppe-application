/**
 * API client for PPE Polling System backend
 */

import type {
  PollSession,
  PollQuestion,
  CaptchaChallenge,
  PublishedResults,
  VerificationResult,
  Vote,
  Signature,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

class APIClient {
  private baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;

    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: response.statusText,
      }));
      throw new Error(error.detail || 'API request failed');
    }

    return response.json();
  }

  // Protocol 1: Announcement
  async createPoll(data: {
    questions: PollQuestion[];
    edge_probability: number;
    effort_threshold: number;
    validity_threshold?: number;
    ppe_type?: string;
  }): Promise<PollSession> {
    return this.request<PollSession>('/poll/create', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getPoll(sessionId: string): Promise<PollSession> {
    return this.request<PollSession>(`/poll/${sessionId}`);
  }

  async updatePollStatus(sessionId: string, newStatus: string): Promise<{ success: boolean; new_status: string }> {
    return this.request(`/poll/${sessionId}/status`, {
      method: 'POST',
      body: JSON.stringify({ new_status: newStatus }),
    });
  }

  async getPollStats(sessionId: string): Promise<any> {
    return this.request(`/poll/${sessionId}/stats`);
  }

  // Protocol 2: Registration
  async getCaptcha(sessionId: string): Promise<CaptchaChallenge> {
    return this.request<CaptchaChallenge>(`/poll/${sessionId}/captcha`);
  }

  async register(
    sessionId: string,
    data: {
      pseudonym: string;
      captcha_solution: string;
      captcha_token: string;
    }
  ): Promise<{ registered: boolean; node_id: string; registration_position: number }> {
    return this.request(`/poll/${sessionId}/register`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getRegisteredNodes(sessionId: string): Promise<{
    session_id: string;
    total_registered: number;
    nodes: Array<{ node_id: string; position: number; registration_time: string }>;
  }> {
    return this.request(`/poll/${sessionId}/registered`);
  }

  // Protocol 3: Certification
  async getNeighbors(
    sessionId: string,
    nodeId: string
  ): Promise<{ neighbors: string[]; graph_parameters: any }> {
    return this.request(`/poll/${sessionId}/neighbors`, {
      headers: {
        'X-Node-ID': nodeId,
      },
    });
  }

  // P2P Mode: Get neighbors with public keys for cryptographic binding
  async getNeighborsDetailed(
    sessionId: string,
    nodeId: string
  ): Promise<{
    neighbors: Array<{ node_id: string; public_key: string; status: string }>;
    my_public_key: string;
    graph_parameters: any;
  }> {
    return this.request(`/poll/${sessionId}/neighbors/detailed`, {
      headers: {
        'X-Node-ID': nodeId,
      },
    });
  }

  async getCertificationStatus(sessionId: string, nodeId: string): Promise<any> {
    return this.request(`/poll/${sessionId}/certification/status`, {
      headers: {
        'X-Node-ID': nodeId,
      },
    });
  }

  async getCertificationGraph(sessionId: string): Promise<{
    nodes: string[];
    edges: Array<{ from: string; to: string; verified: boolean }>;
    total_nodes: number;
    total_edges: number;
    verified_edges: number;
  }> {
    return this.request(`/poll/${sessionId}/certification/graph`);
  }

  async checkNodeCertification(sessionId: string, nodeId: string): Promise<{
    is_certified: boolean;
    verified_edges: number;
    total_edges: number;
    message: string;
  }> {
    return this.request(`/poll/${sessionId}/node/${nodeId}/certification`);
  }

  // Protocol 4: Response
  async submitVote(
    sessionId: string,
    data: {
      node_id: string;
      vote: Vote;
      signatures: Signature[];
      signature: string;
    }
  ): Promise<{ accepted: boolean; vote_id: string }> {
    return this.request(`/poll/${sessionId}/vote`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getVoteCount(sessionId: string): Promise<{
    session_id: string;
    total_votes: number;
    total_registered: number;
  }> {
    return this.request(`/poll/${sessionId}/votes/count`);
  }

  // Protocol 5: Results
  async publishResults(
    sessionId: string,
    pollsterKey?: string
  ): Promise<{ published: boolean; results_url: string }> {
    return this.request(`/poll/${sessionId}/publish`, {
      method: 'POST',
      headers: pollsterKey
        ? {
            'X-Pollster-Key': pollsterKey,
          }
        : {},
    });
  }

  async getResults(sessionId: string): Promise<PublishedResults> {
    return this.request<PublishedResults>(`/poll/${sessionId}/results`);
  }

  // Protocol 6: Verification
  async verify(
    sessionId: string,
    mode: 'local' | 'global',
    nodeId?: string
  ): Promise<VerificationResult> {
    return this.request<VerificationResult>(`/poll/${sessionId}/verify`, {
      method: 'POST',
      body: JSON.stringify({
        mode,
        node_id: nodeId,
      }),
    });
  }
}

export const api = new APIClient(API_BASE_URL);
