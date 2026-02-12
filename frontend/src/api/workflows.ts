import api from './client';

export type WorkflowType = 'auto_reply' | 'email_writer' | 'email_summary' | 'controller' | 'custom';
export type WorkflowStatus = 'active' | 'inactive' | 'error';

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  workflow_type: WorkflowType;
  n8n_workflow_id: string | null;
  n8n_webhook_path: string | null;
  settings: Record<string, unknown>;
  status: WorkflowStatus;
  is_active: boolean;
  owner_id: string;
  team_id: string | null;
  execution_count: string;
  last_executed_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowListResponse {
  workflows: Workflow[];
  total: number;
  limit: number;
  offset: number;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
  workflow_type?: WorkflowType;
  n8n_workflow_id?: string;
  n8n_webhook_path?: string;
  settings?: Record<string, unknown>;
}

export interface WorkflowUpdate {
  name?: string;
  description?: string;
  settings?: Record<string, unknown>;
  is_active?: boolean;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  status: string;
  trigger_type: string | null;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: string | null;
}

export interface TriggerResponse {
  execution_id: string;
  status: string;
  message: string;
}

export interface WorkflowTypeInfo {
  value: WorkflowType;
  name: string;
  description: string;
}

// Chat API types
export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface EmailDraft {
  subject: string;
  body: string;
  html_body?: string;
}

export interface ChatResponse {
  success: boolean;
  response: string;
  session_id: string;
  error?: string;
  draft?: EmailDraft;  // Draft email from n8n (needs recipient to send)
}

export interface SendDraftRequest {
  to: string;          // Recipient (stored on frontend)
  subject: string;     // From n8n draft
  body: string;        // From n8n draft
  html_body?: string;
  from_email?: string;
  from_name?: string;
  reply_to?: string;
}

export interface SendDraftResponse {
  success: boolean;
  message: string;
  details?: Record<string, unknown>;
  error?: string;
}

export const workflowsApi = {
  async list(
    limit = 50,
    offset = 0,
    workflowType?: WorkflowType,
    myWorkflows = false
  ): Promise<WorkflowListResponse> {
    const response = await api.get<WorkflowListResponse>('/workflows', {
      params: { limit, offset, workflow_type: workflowType, my_workflows: myWorkflows }
    });
    return response.data;
  },

  async get(id: string): Promise<Workflow> {
    const response = await api.get<Workflow>(`/workflows/${id}`);
    return response.data;
  },

  async create(data: WorkflowCreate): Promise<Workflow> {
    const response = await api.post<Workflow>('/workflows', data);
    return response.data;
  },

  async update(id: string, data: WorkflowUpdate): Promise<Workflow> {
    const response = await api.put<Workflow>(`/workflows/${id}`, data);
    return response.data;
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/workflows/${id}`);
  },

  async toggle(id: string): Promise<Workflow> {
    const response = await api.post<Workflow>(`/workflows/${id}/toggle`);
    return response.data;
  },

  async trigger(id: string, inputData: Record<string, unknown> = {}): Promise<TriggerResponse> {
    const response = await api.post<TriggerResponse>(`/workflows/${id}/trigger`, { input_data: inputData });
    return response.data;
  },

  async getExecutions(id: string, limit = 20, offset = 0): Promise<WorkflowExecution[]> {
    const response = await api.get<WorkflowExecution[]>(`/workflows/${id}/executions`, {
      params: { limit, offset }
    });
    return response.data;
  },

  async seedDefaults(): Promise<Workflow[]> {
    const response = await api.post<Workflow[]>('/workflows/seed');
    return response.data;
  },

  async importFromFile(file: File): Promise<Workflow> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<Workflow>('/workflows/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async getTypes(): Promise<{ types: WorkflowTypeInfo[] }> {
    const response = await api.get<{ types: WorkflowTypeInfo[] }>('/workflows/types/available');
    return response.data;
  },

  // Chat with Email Assistant
  async chat(message: string, sessionId?: string): Promise<ChatResponse> {
    const response = await api.post<ChatResponse>('/chat', {
      message,
      session_id: sessionId,
    });
    return response.data;
  },

  // Send a drafted email (combines n8n draft with recipient from frontend)
  async sendDraft(data: SendDraftRequest): Promise<SendDraftResponse> {
    const response = await api.post<SendDraftResponse>('/send-draft', data);
    return response.data;
  },
};

export default workflowsApi;
