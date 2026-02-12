import api from './client';

export type StepType = 'EMAIL' | 'WAIT' | 'CONDITION';
export type SequenceStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived';
export type EnrollmentStatus = 'active' | 'paused' | 'completed' | 'replied' | 'bounced' | 'unsubscribed';

export interface SequenceStep {
  step_number: number;
  step_type: StepType;
  delay_days: number;
  delay_hours: number;
  template_id?: string;
  subject?: string;
  body?: string;
  condition?: 'opened' | 'clicked' | 'no_reply';
}

export interface Sequence {
  id: string;
  name: string;
  description?: string;
  status: SequenceStatus;
  steps: SequenceStep[];
  created_at: string;
  updated_at?: string;
  enrolled_count?: number;
  completed_count?: number;
}

export interface SequenceCreate {
  name: string;
  description?: string;
  steps?: SequenceStep[];
}

export interface SequenceUpdate {
  name?: string;
  description?: string;
  steps?: SequenceStep[];
}

export interface SequenceAnalytics {
  sequence_id: string;
  total_enrolled: number;
  active: number;
  completed: number;
  replied: number;
  bounced: number;
  unsubscribed: number;
  email_stats: {
    sent: number;
    opened: number;
    clicked: number;
    open_rate: number;
    click_rate: number;
  };
}

export interface EnrollProspectsRequest {
  prospect_emails: string[];
}

export const sequencesApi = {
  async list(status?: SequenceStatus): Promise<Sequence[]> {
    const response = await api.get<Sequence[]>('/sequences', { params: { status } });
    return response.data;
  },

  async get(id: string): Promise<Sequence> {
    const response = await api.get<Sequence>(`/sequences/${id}`);
    return response.data;
  },

  async create(data: SequenceCreate): Promise<Sequence> {
    const response = await api.post<Sequence>('/sequences', data);
    return response.data;
  },

  async update(id: string, data: SequenceUpdate): Promise<Sequence> {
    const response = await api.put<Sequence>(`/sequences/${id}`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/sequences/${id}`);
  },

  async enroll(id: string, prospectEmails: string[]): Promise<{ enrolled: number; errors: string[] }> {
    const response = await api.post<{ enrolled: number; errors: string[] }>(
      `/sequences/${id}/enroll`,
      { prospect_emails: prospectEmails }
    );
    return response.data;
  },

  async pause(id: string): Promise<Sequence> {
    const response = await api.post<Sequence>(`/sequences/${id}/pause`);
    return response.data;
  },

  async resume(id: string): Promise<Sequence> {
    const response = await api.post<Sequence>(`/sequences/${id}/resume`);
    return response.data;
  },

  async getAnalytics(id: string): Promise<SequenceAnalytics> {
    const response = await api.get<SequenceAnalytics>(`/sequences/${id}/analytics`);
    return response.data;
  },
};

export default sequencesApi;
