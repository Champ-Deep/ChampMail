import api from './client';

// ============================================================
// Types
// ============================================================

export type ProspectListStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed';

export interface ProspectListItem {
  id: string;
  name: string;
  file_name: string;
  status: ProspectListStatus;
  total_prospects: number;
  processed_prospects: number;
  failed_prospects: number;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface ProspectListDetail extends ProspectListItem {
  prospects: Array<{
    id: string;
    email: string;
    first_name?: string;
    last_name?: string;
    company_name?: string;
    title?: string;
    status: string;
  }>;
}

export interface UploadProspectListResponse {
  id: string;
  name: string;
  file_name: string;
  total_rows: number;
  status: ProspectListStatus;
  message: string;
}

// AI Campaign Pipeline Types

export interface CampaignEssence {
  value_propositions: string[];
  pain_points: string[];
  call_to_action: string;
  tone: string;
  unique_angle: string;
  target_persona: string;
}

export interface ResearchResult {
  prospect_id: string;
  prospect_email: string;
  research_data: {
    company_info: {
      description: string;
      industry?: string;
      size?: string;
      revenue?: string;
      products?: string[];
      tech_stack?: string[];
      recent_news?: string[];
    };
    industry_insights: {
      trends?: string[];
      pain_points?: string[];
      regulatory?: string[];
    };
    persona_details: {
      responsibilities?: string[];
      challenges?: string[];
      priorities?: string[];
      decision_authority?: string;
    };
    triggers: {
      funding?: string | null;
      acquisitions?: string | null;
      leadership_changes?: string | null;
      hiring?: string[];
      expansion?: string;
    };
    personalization_hooks: string[];
    _metadata?: {
      researched_at: string;
      model: string;
      prospect_id: string;
    };
    error?: string;
  };
}

export interface Segment {
  id: string;
  name: string;
  criteria: {
    industries?: string[];
    roles?: string[];
    company_size?: string[];
    key_indicators?: string[];
  };
  size_estimate_pct: number;
  characteristics: string;
  pain_points: string[];
  messaging_angle: string;
  priority: 'high' | 'medium' | 'low';
}

export interface SegmentationResult {
  segments: Segment[];
  strategy: string;
  unmatched_pct: number;
}

export interface Pitch {
  pitch_angle: string;
  key_messages: string[];
  subject_lines: string[];
  body_template: string;
  follow_up_templates: Array<{
    delay_days: number;
    subject: string;
    body: string;
  }>;
  personalization_variables: string[];
}

export interface PersonalizedEmail {
  prospect_id: string;
  prospect_email: string;
  subject: string;
  body: string;
  follow_ups: Array<{
    delay_days: number;
    subject: string;
    body: string;
  }>;
  variables_used: Record<string, string>;
}

export interface PipelineResult {
  campaign_id: string;
  status: string;
  essence: CampaignEssence;
  research_count: number;
  segments: Segment[];
  pitches: Record<string, Pitch>;
  personalized_emails: PersonalizedEmail[];
  message: string;
}

export interface CampaignStyle {
  primary_color?: string;
  company_name?: string;
}

// ============================================================
// Admin API
// ============================================================

export const adminApi = {
  // ----------------------------------------------------------
  // Prospect Lists
  // ----------------------------------------------------------

  async uploadProspectList(file: File): Promise<UploadProspectListResponse> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<UploadProspectListResponse>(
      '/admin/prospect-lists/upload',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  },

  async getProspectLists(): Promise<ProspectListItem[]> {
    const response = await api.get<ProspectListItem[]>('/admin/prospect-lists');
    return response.data;
  },

  async getProspectList(id: string): Promise<ProspectListDetail> {
    const response = await api.get<ProspectListDetail>(
      `/admin/prospect-lists/${id}`
    );
    return response.data;
  },

  async processProspectList(
    id: string
  ): Promise<{ message: string; status: string }> {
    const response = await api.post<{ message: string; status: string }>(
      `/admin/prospect-lists/${id}/process`
    );
    return response.data;
  },

  async deleteProspectList(id: string): Promise<void> {
    await api.delete(`/admin/prospect-lists/${id}`);
  },

  // ----------------------------------------------------------
  // AI Campaign Pipeline
  // ----------------------------------------------------------

  async extractEssence(data: {
    description: string;
    target_audience?: string;
  }): Promise<CampaignEssence> {
    const response = await api.post<CampaignEssence>(
      '/admin/ai-campaigns/essence',
      data
    );
    return response.data;
  },

  async researchProspects(data: {
    prospect_ids: string[];
    campaign_id?: string;
  }): Promise<ResearchResult[]> {
    const response = await api.post<ResearchResult[]>(
      '/admin/ai-campaigns/research',
      data
    );
    return response.data;
  },

  async segmentProspects(data: {
    research_results: ResearchResult[];
    campaign_goals: string;
    campaign_essence: CampaignEssence;
  }): Promise<SegmentationResult> {
    const response = await api.post<SegmentationResult>(
      '/admin/ai-campaigns/segment',
      data
    );
    return response.data;
  },

  async generatePitch(data: {
    segment: Segment;
    campaign_essence: CampaignEssence;
    sample_research: ResearchResult[];
  }): Promise<Pitch> {
    const response = await api.post<Pitch>(
      '/admin/ai-campaigns/pitch',
      data
    );
    return response.data;
  },

  async personalizeEmails(data: {
    pitch: Pitch;
    prospects: Array<Record<string, unknown>>;
    research_data: ResearchResult[];
  }): Promise<PersonalizedEmail[]> {
    const response = await api.post<PersonalizedEmail[]>(
      '/admin/ai-campaigns/personalize',
      data
    );
    return response.data;
  },

  async generateHtml(data: {
    subject: string;
    body: string;
    prospect: Record<string, unknown>;
    style?: CampaignStyle;
  }): Promise<{ html: string }> {
    const response = await api.post<{ html: string }>(
      '/admin/ai-campaigns/html',
      data
    );
    return response.data;
  },

  async runFullPipeline(data: {
    description: string;
    prospect_list_id: string;
    target_audience?: string;
    style?: CampaignStyle;
  }): Promise<PipelineResult> {
    const response = await api.post<PipelineResult>(
      '/admin/ai-campaigns/full-pipeline',
      data
    );
    return response.data;
  },
};

export default adminApi;
