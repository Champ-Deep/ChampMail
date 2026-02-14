import api from './client';

export type CampaignStatus = 'draft' | 'scheduled' | 'running' | 'paused' | 'completed' | 'failed';

export interface Campaign {
  id: string;
  name: string;
  description?: string | null;
  status: CampaignStatus;
  owner_id: string;
  from_name?: string | null;
  from_address?: string | null;
  prospect_list_id?: string | null;
  daily_limit: number;
  total_prospects: number;
  sent_count: number;
  opened_count: number;
  clicked_count: number;
  replied_count: number;
  bounced_count: number;
  unsubscribed_count: number;
  activated_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CampaignListResponse {
  campaigns: Campaign[];
  total: number;
  limit: number;
  offset: number;
}

export interface CampaignCreate {
  name: string;
  description?: string;
  prospect_list_id?: string;
  from_name?: string;
  from_address?: string;
  daily_limit?: number;
  template_id?: string;
  sequence_id?: string;
}

export interface CampaignStats {
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  replied: number;
  bounced: number;
  open_rate: number;
  click_rate: number;
  reply_rate: number;
}

export interface CampaignRecipient {
  prospect_id: string;
  email: string;
  first_name: string;
  last_name: string;
  company: string;
  title: string;
  status: string;
  sent_at?: string | null;
  message_id?: string | null;
}

export interface PipelineStatus {
  status: string;
  current_step?: string;
  step_index?: number;
  total_steps?: number;
  progress?: number;
  error?: string;
  run_id?: string;
  started_at?: string;
  completed_at?: string;
  total_emails?: number;
}

export interface CampaignTracking {
  campaign_id: string;
  campaign_name: string;
  campaign_status: string;
  total_prospects: number;
  sent: number;
  delivered: number;
  opens: { total: number; unique: number; rate: number };
  clicks: { total: number; unique: number; rate: number; click_to_open_rate: number };
  bounces: { total: number; rate: number; breakdown: Record<string, number> };
  replies: { total: number; rate: number };
  unsubscribes: number;
  delivery_rate: number;
}

export const campaignsApi = {
  async list(
    limit = 50,
    offset = 0,
    status?: CampaignStatus,
    myCampaigns = false
  ): Promise<CampaignListResponse> {
    const response = await api.get<CampaignListResponse>('/campaigns', {
      params: { limit, offset, status, my_campaigns: myCampaigns }
    });
    return response.data;
  },

  async get(id: string): Promise<Campaign> {
    const response = await api.get<Campaign>(`/campaigns/${id}`);
    return response.data;
  },

  async create(data: CampaignCreate): Promise<Campaign> {
    const response = await api.post<Campaign>('/campaigns', data);
    return response.data;
  },

  async getStats(id: string): Promise<CampaignStats> {
    const response = await api.get<CampaignStats>(`/campaigns/${id}/stats`);
    return response.data;
  },

  async addRecipients(id: string, prospectIds: string[]): Promise<{ added: number; total_requested: number }> {
    const response = await api.post(`/campaigns/${id}/recipients`, { prospect_ids: prospectIds });
    return response.data;
  },

  async getRecipients(id: string, status?: string, limit = 100): Promise<CampaignRecipient[]> {
    const response = await api.get<CampaignRecipient[]>(`/campaigns/${id}/recipients`, {
      params: { status, limit }
    });
    return response.data;
  },

  async send(id: string): Promise<{ message: string; campaign_id: string }> {
    const response = await api.post(`/campaigns/${id}/send`);
    return response.data;
  },

  async pause(id: string): Promise<{ message: string; campaign_id: string }> {
    const response = await api.post(`/campaigns/${id}/pause`);
    return response.data;
  },

  async resume(id: string): Promise<{ message: string; campaign_id: string }> {
    const response = await api.post(`/campaigns/${id}/resume`);
    return response.data;
  },

  async getPipelineStatus(id: string): Promise<PipelineStatus> {
    const response = await api.get<PipelineStatus>(`/campaigns/${id}/pipeline-status`);
    return response.data;
  },

  async getPipelineResults(id: string): Promise<any> {
    const response = await api.get(`/campaigns/${id}/pipeline-results`);
    return response.data;
  },

  async scheduleSends(id: string): Promise<{ total_scheduled: number; first_send: string | null; last_send: string | null }> {
    const response = await api.post(`/campaigns/${id}/schedule`);
    return response.data;
  },

  async getSchedule(id: string): Promise<any> {
    const response = await api.get(`/campaigns/${id}/schedule`);
    return response.data;
  },

  async getTracking(id: string): Promise<CampaignTracking> {
    const response = await api.get<CampaignTracking>(`/campaigns/${id}/tracking`);
    return response.data;
  },
};

export default campaignsApi;
