import api from './client';

// ============================================================
// Types
// ============================================================

export interface AdminProspect {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  company_name?: string;
  company_domain?: string;
  industry?: string;
  job_title?: string;
  linkedin_url?: string;
  status: string;
  research_status: 'pending' | 'running' | 'completed' | 'failed';
  research_data?: Record<string, unknown>;
  assigned_to_user_id?: string;
  team_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface AdminUser {
  user_id: string;
  email: string;
  full_name?: string;
  role: string;
  team_id?: string;
  is_active: boolean;
  created_at?: string;
}

export interface CreateProspectData {
  email: string;
  first_name?: string;
  last_name?: string;
  company_name?: string;
  company_domain?: string;
  industry?: string;
  job_title?: string;
  linkedin_url?: string;
}

export interface AssignProspectData {
  user_id: string;
  campaign_id?: string;
}

export interface EnrollProspectData {
  campaign_id?: string;
  sender_user_id?: string;
}

export interface CreateUserData {
  email: string;
  password: string;
  name?: string;
  role?: string;
  team_id?: string;
}

export interface SequenceStepLog {
  id: string;
  prospect_id: string;
  campaign_id?: string;
  sequence_id: string;
  enrollment_id: string;
  sequence_step: number;
  action_taken: string;
  reply_detected: boolean;
  email_content_summary?: string;
  raw_subject?: string;
  raw_body_snippet?: string;
  timestamp: string;
}

// ============================================================
// Admin Prospects API
// ============================================================

export const adminProspectsApi = {
  // Prospects
  async listProspects(limit = 100, offset = 0): Promise<{ prospects: AdminProspect[]; total: number }> {
    const response = await api.get('/admin/prospects', { params: { limit, offset } });
    return response.data;
  },

  async createProspect(data: CreateProspectData): Promise<{ prospect: AdminProspect; message: string }> {
    const response = await api.post('/admin/prospects', data);
    return response.data;
  },

  async assignProspect(
    prospectId: string,
    data: AssignProspectData
  ): Promise<{ prospect_id: string; assigned_to_user_id: string; message: string }> {
    const response = await api.post(`/admin/prospects/${prospectId}/assign`, data);
    return response.data;
  },

  async getProspectLogs(
    prospectId: string,
    limit = 50
  ): Promise<{ prospect_id: string; logs: SequenceStepLog[]; total: number }> {
    const response = await api.get(`/admin/prospects/${prospectId}/logs`, { params: { limit } });
    return response.data;
  },

  async enrollProspect(
    prospectId: string,
    data: EnrollProspectData
  ): Promise<{ enrollment_id: string; sequence_id: string; message: string }> {
    const response = await api.post(`/admin/prospects/${prospectId}/enroll`, data);
    return response.data;
  },

  // Users
  async listUsers(params?: { team_id?: string; role?: string }): Promise<{ users: AdminUser[] }> {
    const response = await api.get('/admin/users', { params });
    return response.data;
  },

  async createUser(data: CreateUserData): Promise<AdminUser & { message: string }> {
    const response = await api.post('/admin/users', data);
    return response.data;
  },
};

export default adminProspectsApi;
