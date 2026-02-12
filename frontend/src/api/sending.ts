import api from './client';

export interface SendEmailRequest {
  to: string;
  from_name?: string;
  from_address?: string;
  subject: string;
  html_body: string;
  text_body?: string;
  reply_to?: string;
  domain_id?: string;
  track_opens?: boolean;
  track_clicks?: boolean;
}

export interface SendEmailResponse {
  message_id: string;
  status: string;
  domain_id: string;
  sent_at: string;
}

export interface BatchSendRequest {
  emails: SendEmailRequest[];
  domain_id?: string;
}

export interface BatchSendResponse {
  total: number;
  successful: number;
  failed: number;
  results: SendEmailResponse[];
}

export interface SendStats {
  domain_id: string;
  today_sent: number;
  today_limit: number;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  bounce_rate: number;
}

export const sendingApi = {
  sendEmail: async (request: SendEmailRequest): Promise<SendEmailResponse> => {
    const { data } = await api.post('/send', request);
    return data;
  },

  sendBatch: async (request: BatchSendRequest): Promise<BatchSendResponse> => {
    const { data } = await api.post('/send/batch', request);
    return data;
  },

  getStatus: async (messageId: string): Promise<{
    id: string;
    status: string;
    sent_at: string;
    opened_at?: string;
    clicked_at?: string;
  }> => {
    const { data } = await api.get(`/send/status/${messageId}`);
    return data;
  },

  getStats: async (domainId?: string): Promise<SendStats> => {
    const params = domainId ? `?domain_id=${domainId}` : '';
    const { data } = await api.get(`/send/stats${params}`);
    return data;
  },
};