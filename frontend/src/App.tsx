import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { useAuthStore } from './store/authStore';
import { MainLayout } from './components/layout';
import { OnboardingProvider } from './components/onboarding';
import { HelpChatWidget } from './components/help';
import {
  LoginPage,
  DashboardPage,
  TemplatesPage,
  TemplateEditorPage,
  ProspectsPage,
  SequencesPage,
  CampaignsPage,
  WorkflowsPage,
  SettingsPage,
  JoinTeamPage,
  DomainManagerPage,
  SendConsolePage,
  AnalyticsPage,
} from './pages';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
    },
  },
});

// Protected route wrapper
function ProtectedRoute() {
  const { isAuthenticated, isLoading, fetchUser } = useAuthStore();

  useEffect(() => {
    // Check if user is authenticated on mount
    const token = localStorage.getItem('access_token');
    if (token && !isAuthenticated) {
      fetchUser();
    }
  }, []);

  // Show nothing while checking auth
  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-50">
        <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

// Public route wrapper (redirect to dashboard if already logged in)
function PublicRoute() {
  const { isAuthenticated } = useAuthStore();

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster
        position="top-right"
        richColors
        closeButton
        toastOptions={{
          duration: 4000,
        }}
      />
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route element={<PublicRoute />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>

          {/* Protected routes with onboarding and help */}
          <Route
            element={
              <OnboardingProvider>
                <ProtectedRoute />
                <HelpChatWidget />
              </OnboardingProvider>
            }
          >
            <Route element={<MainLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/prospects" element={<ProspectsPage />} />
              <Route path="/sequences" element={<SequencesPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/campaigns" element={<CampaignsPage />} />
              <Route path="/workflows" element={<WorkflowsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/domains" element={<DomainManagerPage />} />
              <Route path="/send" element={<SendConsolePage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
            </Route>

            {/* Full-screen template editor (no sidebar) */}
            <Route path="/templates/:id/edit" element={<TemplateEditorPage />} />
            <Route path="/templates/new" element={<TemplateEditorPage />} />

            {/* Join team page (full-screen, no sidebar) */}
            <Route path="/join-team" element={<JoinTeamPage />} />
          </Route>

          {/* Catch all - redirect to dashboard */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
