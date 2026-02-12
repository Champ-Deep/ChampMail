import api from './client';

export interface EmailAccount {
  id: string;
  name: string;
  email: string;
  is_default: boolean;
  is_active: boolean;
  smtp_host: string | null;
  smtp_port: number;
  smtp_username: string | null;
  smtp_use_tls: boolean;
  smtp_verified: boolean;
  smtp_verified_at: string | null;
  smtp_has_password: boolean;
  imap_host: string | null;
  imap_port: number;
  imap_username: string | null;
  imap_use_ssl: boolean;
  imap_mailbox: string | null;
  imap_verified: boolean;
  imap_verified_at: string | null;
  imap_has_password: boolean;
  from_name: string | null;
  reply_to_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailAccountCreate {
  name: string;
  email: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_password?: string;
  smtp_use_tls?: boolean;
  imap_host?: string;
  imap_port?: number;
  imap_username?: string;
  imap_password?: string;
  imap_use_ssl?: boolean;
  imap_mailbox?: string;
  from_name?: string;
  reply_to_email?: string;
  is_default?: boolean;
}

export interface EmailAccountUpdate {
  name?: string;
  email?: string;
  smtp_host?: string;
  smtp_port?: number;
  smtp_username?: string;
  smtp_password?: string;
  smtp_use_tls?: boolean;
  imap_host?: string;
  imap_port?: number;
  imap_username?: string;
  imap_password?: string;
  imap_use_ssl?: boolean;
  imap_mailbox?: string;
  from_name?: string;
  reply_to_email?: string;
  is_default?: boolean;
  is_active?: boolean;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export const emailAccountsApi = {
  // List all email accounts
  list: async (): Promise<EmailAccount[]> => {
    const response = await api.get('/email-accounts');
    return response.data;
  },

  // Get default account
  getDefault: async (): Promise<EmailAccount | null> => {
    const response = await api.get('/email-accounts/default');
    return response.data;
  },

  // Get a specific account
  get: async (id: string): Promise<EmailAccount> => {
    const response = await api.get(`/email-accounts/${id}`);
    return response.data;
  },

  // Create a new account
  create: async (data: EmailAccountCreate): Promise<EmailAccount> => {
    const response = await api.post('/email-accounts', data);
    return response.data;
  },

  // Update an account
  update: async (id: string, data: EmailAccountUpdate): Promise<EmailAccount> => {
    const response = await api.put(`/email-accounts/${id}`, data);
    return response.data;
  },

  // Delete an account
  delete: async (id: string): Promise<void> => {
    await api.delete(`/email-accounts/${id}`);
  },

  // Test SMTP connection
  testSmtp: async (id: string): Promise<TestConnectionResponse> => {
    const response = await api.post(`/email-accounts/${id}/test-smtp`);
    return response.data;
  },

  // Test IMAP connection
  testImap: async (id: string): Promise<TestConnectionResponse> => {
    const response = await api.post(`/email-accounts/${id}/test-imap`);
    return response.data;
  },

  // Set as default
  setDefault: async (id: string): Promise<EmailAccount> => {
    const response = await api.post(`/email-accounts/${id}/set-default`);
    return response.data;
  },
};

export default emailAccountsApi;
