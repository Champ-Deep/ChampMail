import api from './client';

// ============================================================
// Types
// ============================================================

export interface UTMPreset {
  id: string;
  name: string;
  is_default: boolean;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  utm_term: string | null;
  custom_params: Record<string, string> | null;
  created_at: string;
}

export interface UTMPresetCreate {
  name: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  utm_term?: string;
  custom_params?: Record<string, string>;
}

export interface CampaignUTMConfig {
  id: string;
  campaign_id: string;
  enabled: boolean;
  preset_id: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  utm_term: string | null;
  custom_params: Record<string, string> | null;
  link_overrides: Record<string, Record<string, string>> | null;
  preserve_existing_utm: boolean;
}

export interface CampaignUTMConfigUpdate {
  enabled?: boolean;
  preset_id?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  utm_term?: string;
  custom_params?: Record<string, string>;
  link_overrides?: Record<string, Record<string, string>>;
  preserve_existing_utm?: boolean;
}

export interface UTMBreakdownItem {
  group_key: string;
  group_value: string;
  total_links: number;
  total_clicks: number;
  unique_clicks: number;
  click_rate: number;
}

export interface LinkPerformanceItem {
  original_url: string;
  anchor_text: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_content: string | null;
  utm_term: string | null;
  click_count: number;
  unique_clicks: number;
  first_clicked_at: string | null;
}

export interface UTMOverview {
  total_tracked_links: number;
  total_clicks: number;
  unique_clicks: number;
  overall_click_rate: number;
  top_sources: UTMBreakdownItem[];
  top_campaigns: UTMBreakdownItem[];
}

// ============================================================
// UTM API
// ============================================================

export const utmApi = {
  // ----------------------------------------------------------
  // Presets
  // ----------------------------------------------------------

  async getPresets(): Promise<UTMPreset[]> {
    const response = await api.get<UTMPreset[]>('/utm/presets');
    return response.data;
  },

  async createPreset(preset: UTMPresetCreate): Promise<UTMPreset> {
    const response = await api.post<UTMPreset>('/utm/presets', preset);
    return response.data;
  },

  async updatePreset(id: string, preset: Partial<UTMPresetCreate>): Promise<UTMPreset> {
    const response = await api.put<UTMPreset>(`/utm/presets/${id}`, preset);
    return response.data;
  },

  async deletePreset(id: string): Promise<void> {
    await api.delete(`/utm/presets/${id}`);
  },

  async setDefaultPreset(id: string): Promise<UTMPreset> {
    const response = await api.post<UTMPreset>(`/utm/presets/${id}/default`);
    return response.data;
  },

  // ----------------------------------------------------------
  // Campaign Config
  // ----------------------------------------------------------

  async getCampaignConfig(campaignId: string): Promise<CampaignUTMConfig> {
    const response = await api.get<CampaignUTMConfig>(`/utm/campaigns/${campaignId}`);
    return response.data;
  },

  async updateCampaignConfig(
    campaignId: string,
    config: CampaignUTMConfigUpdate
  ): Promise<CampaignUTMConfig> {
    const response = await api.put<CampaignUTMConfig>(
      `/utm/campaigns/${campaignId}`,
      config
    );
    return response.data;
  },

  async deleteCampaignConfig(campaignId: string): Promise<void> {
    await api.delete(`/utm/campaigns/${campaignId}`);
  },

  async autoGenerateConfig(campaignId: string): Promise<CampaignUTMConfig> {
    const response = await api.post<CampaignUTMConfig>(
      `/utm/campaigns/${campaignId}/auto`
    );
    return response.data;
  },

  async previewLinks(campaignId: string): Promise<LinkPerformanceItem[]> {
    const response = await api.post(`/utm/campaigns/${campaignId}/preview`);
    return response.data.links || response.data;
  },

  // ----------------------------------------------------------
  // Analytics
  // ----------------------------------------------------------

  async getOverview(): Promise<UTMOverview> {
    const response = await api.get<UTMOverview>('/utm/analytics/overview');
    return response.data;
  },

  async getCampaignBreakdown(campaignId: string): Promise<UTMBreakdownItem[]> {
    const response = await api.get<UTMBreakdownItem[]>(
      `/utm/analytics/campaigns/${campaignId}`
    );
    return response.data;
  },

  async getBreakdown(
    groupBy: string,
    campaignId?: string,
    days?: number
  ): Promise<UTMBreakdownItem[]> {
    const params = new URLSearchParams({ group_by: groupBy });
    if (campaignId) params.append('campaign_id', campaignId);
    if (days) params.append('days', days.toString());
    const response = await api.get<UTMBreakdownItem[]>(
      `/utm/analytics/breakdown?${params.toString()}`
    );
    return response.data;
  },

  async getLinkPerformance(campaignId: string): Promise<LinkPerformanceItem[]> {
    const response = await api.get<LinkPerformanceItem[]>(
      `/utm/analytics/links/${campaignId}`
    );
    return response.data;
  },
};

export default utmApi;
