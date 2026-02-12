import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi, type User, type LoginCredentials } from '../api/auth';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (credentials: LoginCredentials) => {
        set({ isLoading: true, error: null });
        try {
          const response = await authApi.login(credentials);
          const token = response.access_token;
          localStorage.setItem('access_token', token);

          // Fetch user details after login
          const user = await authApi.getCurrentUser();
          set({
            token,
            user,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : 'Login failed';
          set({
            error: message,
            isLoading: false,
          });
          throw error;
        }
      },

      logout: () => {
        authApi.logout();
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          error: null,
        });
      },

      fetchUser: async () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
          set({ isAuthenticated: false });
          return;
        }

        try {
          set({ isLoading: true });
          const user = await authApi.getCurrentUser();
          set({
            user,
            token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch {
          // Token is invalid, clear it
          localStorage.removeItem('access_token');
          set({
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: false,
          });
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

export default useAuthStore;
