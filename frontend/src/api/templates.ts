import api from './client';

export interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  mjml_content: string;
  html_content?: string | null;
  variables: string[];
  owner_id: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TemplateListResponse {
  templates: EmailTemplate[];
  total: number;
  limit: number;
  offset: number;
}

export interface TemplateCreate {
  name: string;
  subject: string;
  mjml_content: string;
  compile_html?: boolean;
}

export interface TemplateUpdate {
  name?: string;
  subject?: string;
  mjml_content?: string;
  recompile?: boolean;
}

export interface TemplatePreviewRequest {
  variables: Record<string, string>;
}

export interface TemplatePreviewResponse {
  subject: string;
  html: string;
  variables_used: string[];
}

export interface CompileResponse {
  html: string | null;
  error: string | null;
  variables: string[];
}

export const templatesApi = {
  async list(limit = 50, offset = 0, myTemplates = false): Promise<TemplateListResponse> {
    const response = await api.get<TemplateListResponse>('/templates', {
      params: { limit, offset, my_templates: myTemplates }
    });
    return response.data;
  },

  async get(id: string): Promise<EmailTemplate> {
    const response = await api.get<EmailTemplate>(`/templates/${id}`);
    return response.data;
  },

  async create(data: TemplateCreate): Promise<EmailTemplate> {
    const response = await api.post<EmailTemplate>('/templates', data);
    return response.data;
  },

  async update(id: string, data: TemplateUpdate): Promise<EmailTemplate> {
    const response = await api.put<EmailTemplate>(`/templates/${id}`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/templates/${id}`);
  },

  async preview(id: string, variables: Record<string, string>): Promise<TemplatePreviewResponse> {
    const response = await api.post<TemplatePreviewResponse>(`/templates/${id}/preview`, { variables });
    return response.data;
  },

  async compile(mjmlContent: string): Promise<CompileResponse> {
    const response = await api.post<CompileResponse>('/templates/compile', { mjml_content: mjmlContent });
    return response.data;
  },

  async validate(mjmlContent: string): Promise<{ valid: boolean; issues: string[]; variables: string[] }> {
    const response = await api.post('/templates/validate', { mjml_content: mjmlContent });
    return response.data;
  },
};

export default templatesApi;
