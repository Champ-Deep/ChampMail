import api from './client';

export interface Domain {
  id: string;
  domain_name: string;
  status: 'pending' | 'verifying' | 'verified' | 'failed';
  mx_verified: boolean;
  spf_verified: boolean;
  dkim_verified: boolean;
  dmarc_verified: boolean;
  dkim_selector: string | null;
  daily_send_limit: number;
  sent_today: number;
  warmup_enabled: boolean;
  warmup_day: number;
  health_score: number;
  bounce_rate: number;
  cloudflare_zone_id: string | null;
  team_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface DNSRecord {
  type: string;
  name: string;
  value: string;
  priority: number | null;
  ttl: number;
}

export interface DomainHealth {
  domain_id: string;
  health_score: number;
  status: 'healthy' | 'degraded' | 'critical';
  all_verified: boolean;
  details: {
    mx: boolean;
    spf: boolean;
    dkim: boolean;
    dmarc: boolean;
  };
}

export interface DomainSearchResult {
  domain: string;
  available: boolean;
  price: number;
  currency: string;
}

export interface CreateDomainRequest {
  domain_name: string;
  selector?: string;
}

export interface DNSRecordsResponse {
  domain_id: string;
  domain_name: string;
  records: DNSRecord[];
}

export const domainsApi = {
  list: async (): Promise<Domain[]> => {
    const { data } = await api.get('/domains');
    return data;
  },

  get: async (domainId: string): Promise<Domain> => {
    const { data } = await api.get(`/domains/${domainId}`);
    return data;
  },

  create: async (request: CreateDomainRequest): Promise<{ domain_id: string; domain_name: string; records: DNSRecord[] }> => {
    const { data } = await api.post('/domains', request);
    return data;
  },

  delete: async (domainId: string): Promise<void> => {
    await api.delete(`/domains/${domainId}`);
  },

  verify: async (domainId: string): Promise<{
    domain: string;
    mx_verified: boolean;
    spf_valid: boolean;
    dkim_valid: boolean;
    dmarc_valid: boolean;
    all_verified: boolean;
  }> => {
    const { data } = await api.post(`/domains/${domainId}/verify`);
    return data;
  },

  getDNSRecords: async (domainId: string): Promise<DNSRecordsResponse> => {
    const { data } = await api.get(`/domains/${domainId}/dns-records`);
    return data;
  },

  getHealth: async (domainId: string): Promise<DomainHealth> => {
    const { data } = await api.get(`/domains/${domainId}/health`);
    return data;
  },

  searchDomains: async (keyword: string, tlds?: string[]): Promise<{ results: DomainSearchResult[] }> => {
    const { data } = await api.post('/domains/search', { keyword, tlds });
    return data;
  },

  purchaseDomain: async (domain: string, years?: number, nameservers?: string[]): Promise<{
    success: boolean;
    order_id: string;
    transaction_id: string;
    domain: string;
    error?: string;
  }> => {
    const { data } = await api.post('/domains/purchase', { domain, years, nameservers });
    return data;
  },
};