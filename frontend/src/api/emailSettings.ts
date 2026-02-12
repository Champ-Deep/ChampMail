import api from './client';

export interface SMTPSettings {
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  use_tls?: boolean;
}

export interface IMAPSettings {
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  use_ssl?: boolean;
  mailbox?: string;
}

export interface SenderIdentity {
  from_email?: string;
  from_name?: string;
  reply_to_email?: string;
}

export interface EmailSettingsUpdate {
  smtp?: SMTPSettings;
  imap?: IMAPSettings;
  sender?: SenderIdentity;
}

export interface EmailSettingsResponse {
  smtp_host?: string;
  smtp_port: number;
  smtp_username?: string;
  smtp_has_password: boolean;
  smtp_use_tls: boolean;
  smtp_verified: boolean;
  smtp_verified_at?: string;

  imap_host?: string;
  imap_port: number;
  imap_username?: string;
  imap_has_password: boolean;
  imap_use_ssl: boolean;
  imap_mailbox: string;
  imap_verified: boolean;
  imap_verified_at?: string;

  from_email?: string;
  from_name?: string;
  reply_to_email?: string;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export const emailSettingsApi = {
  async get(): Promise<EmailSettingsResponse> {
    const response = await api.get<EmailSettingsResponse>('/settings/email');
    return response.data;
  },

  async update(data: EmailSettingsUpdate): Promise<EmailSettingsResponse> {
    const response = await api.put<EmailSettingsResponse>('/settings/email', data);
    return response.data;
  },

  async testSmtp(): Promise<TestConnectionResponse> {
    const response = await api.post<TestConnectionResponse>('/settings/email/test-smtp');
    return response.data;
  },

  async testImap(): Promise<TestConnectionResponse> {
    const response = await api.post<TestConnectionResponse>('/settings/email/test-imap');
    return response.data;
  },
};

export default emailSettingsApi;
