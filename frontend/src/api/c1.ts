/**
 * Thesys C1 Generative UI API client.
 * Uses raw fetch for SSE streaming (Axios doesn't support streaming bodies).
 */

import api from './client';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface C1ChatRequest {
  messages: ChatMessage[];
  context_type: 'general' | 'analytics' | 'campaign';
  conversation_id?: string;
}

export interface C1ChatSyncResponse {
  content: string;
  conversation_id?: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  message_count: number;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

const getApiBaseUrl = () => {
  // The Axios client already appends /api/v1, but for raw fetch we need the full URL.
  // VITE_API_URL may or may not include /api/v1 - the Axios client uses it as baseURL directly.
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
  return base;
};

const getToken = () => localStorage.getItem('access_token') || '';

export const c1Api = {
  /** Stream a C1 chat response via SSE. Returns raw Response for ReadableStream access. */
  async chatStream(request: C1ChatRequest): Promise<Response> {
    const response = await fetch(`${getApiBaseUrl()}/c1/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Chat request failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response;
  },

  /** Non-streaming chat for simple queries. */
  async chat(request: C1ChatRequest): Promise<C1ChatSyncResponse> {
    const { data } = await api.post<C1ChatSyncResponse>('/c1/chat/sync', request);
    return data;
  },

  /** List saved conversations. */
  async listConversations(): Promise<ConversationSummary[]> {
    const { data } = await api.get<ConversationSummary[]>('/c1/conversations');
    return data;
  },

  /** Get full conversation with messages. */
  async getConversation(id: string): Promise<ConversationDetail> {
    const { data } = await api.get<ConversationDetail>(`/c1/conversations/${id}`);
    return data;
  },

  /** Delete a conversation. */
  async deleteConversation(id: string): Promise<void> {
    await api.delete(`/c1/conversations/${id}`);
  },
};

export default c1Api;
