import { api } from './client';

export interface GraphStats {
  prospect_count: number;
  company_count: number;
  sequence_count: number;
  email_count: number;
  intentsignal_count: number;
  relationships: Record<string, number>;
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'Prospect' | 'Company' | 'Sequence' | 'Email';
  properties: Record<string, any>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface SearchResult {
  query: string;
  results: any[];
  count: number;
}

export interface ChatMessage {
  message: string;
  context?: Record<string, any>;
}

export interface ChatResponse {
  interpretation: string;
  results: any[];
  suggestions?: string[];
}

export const graphApi = {
  getStats: async (): Promise<GraphStats> => {
    const { data } = await api.get('/graph/stats');
    return data;
  },

  search: async (query: string, entityTypes?: string[], limit?: number): Promise<SearchResult> => {
    const { data } = await api.post('/graph/search', {
      query,
      entity_types: entityTypes,
      limit: limit || 20,
    });
    return data;
  },

  chat: async (message: string, context?: Record<string, any>): Promise<ChatResponse> => {
    const { data } = await api.post('/graph/chat', {
      message,
      context: context || {},
    });
    return data;
  },

  getEntity: async (entityId: number, includeRelations?: boolean): Promise<any> => {
    const { data } = await api.get(`/graph/entities/${entityId}`, {
      params: { include_relations: includeRelations ?? true },
    });
    return data;
  },
};
