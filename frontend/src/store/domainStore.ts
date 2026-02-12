import { create } from 'zustand';
import { domainsApi, type Domain, type DomainHealth, type DNSRecord } from '../api';

interface DomainState {
  domains: Domain[];
  selectedDomain: Domain | null;
  domainHealth: Record<string, DomainHealth>;
  dnsRecords: Record<string, DNSRecord[]>;
  isLoading: boolean;
  error: string | null;

  fetchDomains: () => Promise<void>;
  selectDomain: (domain: Domain | null) => void;
  createDomain: (name: string, selector?: string) => Promise<{ domain_id: string } | null>;
  deleteDomain: (domainId: string) => Promise<boolean>;
  verifyDomain: (domainId: string) => Promise<boolean>;
  fetchDomainHealth: (domainId: string) => Promise<DomainHealth>;
  fetchDNSRecords: (domainId: string) => Promise<DNSRecord[]>;
  searchDomains: (keyword: string) => Promise<{ domain: string; available: boolean; price: number }[]>;
  purchaseDomain: (domain: string) => Promise<boolean>;
}

export const useDomainStore = create<DomainState>((set, get) => ({
  domains: [],
  selectedDomain: null,
  domainHealth: {},
  dnsRecords: {},
  isLoading: false,
  error: null,

  fetchDomains: async () => {
    set({ isLoading: true, error: null });
    try {
      const domains = await domainsApi.list();
      set({ domains, isLoading: false });
    } catch (error) {
      set({ error: 'Failed to fetch domains', isLoading: false });
    }
  },

  selectDomain: (domain) => {
    set({ selectedDomain: domain });
  },

  createDomain: async (name, selector) => {
    set({ isLoading: true, error: null });
    try {
      const result = await domainsApi.create({ domain_name: name, selector });
      await get().fetchDomains();
      return result;
    } catch (error) {
      set({ error: 'Failed to create domain', isLoading: false });
      return null;
    }
  },

  deleteDomain: async (domainId) => {
    set({ isLoading: true, error: null });
    try {
      await domainsApi.delete(domainId);
      await get().fetchDomains();
      return true;
    } catch (error) {
      set({ error: 'Failed to delete domain', isLoading: false });
      return false;
    }
  },

  verifyDomain: async (domainId) => {
    set({ isLoading: true, error: null });
    try {
      const result = await domainsApi.verify(domainId);
      await get().fetchDomains();
      return result.all_verified;
    } catch (error) {
      set({ error: 'Failed to verify domain', isLoading: false });
      return false;
    }
  },

  fetchDomainHealth: async (domainId) => {
    try {
      const health = await domainsApi.getHealth(domainId);
      set((state) => ({
        domainHealth: { ...state.domainHealth, [domainId]: health },
      }));
      return health;
    } catch (error) {
      const defaultHealth: DomainHealth = {
        domain_id: domainId,
        health_score: 100,
        status: 'healthy',
        all_verified: false,
        details: { mx: false, spf: false, dkim: false, dmarc: false },
      };
      return defaultHealth;
    }
  },

  fetchDNSRecords: async (domainId) => {
    try {
      const result = await domainsApi.getDNSRecords(domainId);
      set((state) => ({
        dnsRecords: { ...state.dnsRecords, [domainId]: result.records },
      }));
      return result.records;
    } catch (error) {
      return [];
    }
  },

  searchDomains: async (keyword) => {
    try {
      const result = await domainsApi.searchDomains(keyword);
      return result.results;
    } catch (error) {
      return [];
    }
  },

  purchaseDomain: async (domain) => {
    set({ isLoading: true, error: null });
    try {
      const result = await domainsApi.purchaseDomain(domain);
      if (result.success) {
        await get().fetchDomains();
        return true;
      }
      set({ error: result.error || 'Failed to purchase domain', isLoading: false });
      return false;
    } catch (error) {
      set({ error: 'Failed to purchase domain', isLoading: false });
      return false;
    }
  },
}));