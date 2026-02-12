import api from './client';

export interface TeamStats {
  team_id: string;
  period: {
    start: string;
    end: string;
  };
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  total_replied: number;
  open_rate: number;
  click_rate: number;
  bounce_rate: number;
  reply_rate: number;
}

export interface CampaignStats {
  campaign_id: string;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  bounce_rate: number;
}

export interface DomainStats {
  domain_id: string;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  bounce_rate: number;
}

export interface DailyStat {
  date: string;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
}

export interface DailyStatsResponse {
  period: string;
  stats: DailyStat[];
}

export interface AnalyticsOverview {
  emails_sent_today: number;
  emails_sent_this_week: number;
  emails_sent_this_month: number;
  open_rate: number;
  click_rate: number;
  bounce_rate: number;
  reply_rate: number;
  top_performing_domain: {
    domain_name: string;
    open_rate: number;
  } | null;
  recent_campaigns: {
    id: string;
    name: string;
    sent: number;
    open_rate: number;
  }[];
}

export const analyticsApi = {
  getTeamStats: async (
    startDate?: string,
    endDate?: string
  ): Promise<TeamStats> => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const { data } = await api.get(`/analytics/team?${params.toString()}`);
    return data;
  },

  getCampaignStats: async (campaignId: string): Promise<CampaignStats> => {
    const { data } = await api.get(`/analytics/campaigns/${campaignId}`);
    return data;
  },

  getDomainStats: async (domainId: string): Promise<DomainStats> => {
    const { data } = await api.get(`/analytics/domains/${domainId}`);
    return data;
  },

  getDailyStats: async (
    domainId?: string,
    campaignId?: string,
    days: number = 7
  ): Promise<DailyStat[]> => {
    const params = new URLSearchParams();
    params.append('days', days.toString());
    if (domainId) params.append('domain_id', domainId);
    if (campaignId) params.append('campaign_id', campaignId);
    const { data } = await api.get(`/analytics/daily?${params.toString()}`);
    return data;
  },

  getOverview: async (): Promise<AnalyticsOverview> => {
    const { data } = await api.get('/analytics/overview');
    return data;
  },
};