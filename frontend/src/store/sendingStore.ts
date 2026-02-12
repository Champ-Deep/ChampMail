import { create } from 'zustand';
import { sendingApi, type SendStats } from '../api';

interface SendingState {
  stats: SendStats | null;
  recentSends: Array<{
    message_id: string;
    recipient: string;
    status: string;
    sent_at: string;
  }>;
  isLoading: boolean;
  error: string | null;

  fetchStats: (domainId?: string) => Promise<void>;
  sendEmail: (request: Parameters<typeof sendingApi.sendEmail>[0]) => Promise<ReturnType<typeof sendingApi.sendEmail>>;
  sendBatch: (request: Parameters<typeof sendingApi.sendBatch>[0]) => Promise<ReturnType<typeof sendingApi.sendBatch>>;
  clearError: () => void;
}

export const useSendingStore = create<SendingState>((set, get) => ({
  stats: null,
  recentSends: [],
  isLoading: false,
  error: null,

  fetchStats: async (domainId) => {
    set({ isLoading: true, error: null });
    try {
      const stats = await sendingApi.getStats(domainId);
      set({ stats, isLoading: false });
    } catch (error) {
      set({ error: 'Failed to fetch stats', isLoading: false });
    }
  },

  sendEmail: async (request) => {
    set({ isLoading: true, error: null });
    try {
      const result = await sendingApi.sendEmail(request);
      set((state) => ({
        recentSends: [
          {
            message_id: result.message_id,
            recipient: request.to,
            status: result.status,
            sent_at: result.sent_at,
          },
          ...state.recentSends.slice(0, 9),
        ],
        isLoading: false,
      }));
      return result;
    } catch (error) {
      set({ error: 'Failed to send email', isLoading: false });
      throw error;
    }
  },

  sendBatch: async (request) => {
    set({ isLoading: true, error: null });
    try {
      const result = await sendingApi.sendBatch(request);
      set({ isLoading: false });
      return result;
    } catch (error) {
      set({ error: 'Failed to send batch', isLoading: false });
      throw error;
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));