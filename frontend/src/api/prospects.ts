import api from './client';

export interface Prospect {
  id?: string;
  email: string;
  first_name?: string;
  last_name?: string;
  title?: string;
  phone?: string;
  linkedin_url?: string;
  company_name?: string;
  company_domain?: string;
  industry?: string;
  email_status?: 'valid' | 'invalid' | 'unknown';
  unsubscribed?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ProspectCreate {
  email: string;
  first_name?: string;
  last_name?: string;
  title?: string;
  phone?: string;
  linkedin_url?: string;
  company_name?: string;
  company_domain?: string;
  industry?: string;
}

export interface ProspectUpdate {
  first_name?: string;
  last_name?: string;
  title?: string;
  phone?: string;
  linkedin_url?: string;
  company_name?: string;
  company_domain?: string;
  industry?: string;
}

export interface ProspectListParams {
  search?: string;
  industry?: string;
  limit?: number;
  offset?: number;
}

export interface ProspectTimeline {
  email: string;
  events: Array<{
    type: string;
    timestamp: string;
    details?: Record<string, any>;
  }>;
}

export const prospectsApi = {
  async list(params?: ProspectListParams): Promise<Prospect[]> {
    const response = await api.get<Prospect[]>('/prospects', { params });
    return response.data;
  },

  async get(email: string): Promise<Prospect> {
    const response = await api.get<Prospect>(`/prospects/${encodeURIComponent(email)}`);
    return response.data;
  },

  async create(data: ProspectCreate): Promise<Prospect> {
    const response = await api.post<Prospect>('/prospects', data);
    return response.data;
  },

  async update(email: string, data: ProspectUpdate): Promise<Prospect> {
    const response = await api.put<Prospect>(`/prospects/${encodeURIComponent(email)}`, data);
    return response.data;
  },

  async delete(email: string): Promise<void> {
    await api.delete(`/prospects/${encodeURIComponent(email)}`);
  },

  async bulkCreate(prospects: ProspectCreate[]): Promise<{ created: number; errors: string[] }> {
    const response = await api.post<{ created: number; errors: string[] }>('/prospects/bulk', { prospects });
    return response.data;
  },

  async getTimeline(email: string): Promise<ProspectTimeline> {
    const response = await api.get<ProspectTimeline>(`/prospects/${encodeURIComponent(email)}/timeline`);
    return response.data;
  },
};

export default prospectsApi;
