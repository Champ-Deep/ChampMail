import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Mail, Users, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { teamsApi } from '../api';
import { useAuthStore } from '../store/authStore';
import { Button, Card, CardHeader, CardTitle } from '../components/ui';

export function JoinTeamPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAuthStore();
  const token = searchParams.get('token');

  const [status, setStatus] = useState<'loading' | 'ready' | 'success' | 'error'>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  // Check for pending invites for the current user
  const { data: myInvites = [], isLoading: invitesLoading } = useQuery({
    queryKey: ['myInvites'],
    queryFn: () => teamsApi.getMyInvites(),
    enabled: isAuthenticated && !!token,
  });

  // Find matching invite
  const matchingInvite = myInvites.find((inv) => inv.token === token);

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setErrorMessage('No invitation token provided');
      return;
    }

    if (!isAuthenticated) {
      // Redirect to login with return URL
      navigate(`/login?returnTo=/join-team?token=${token}`);
      return;
    }

    if (!invitesLoading) {
      if (matchingInvite) {
        setStatus('ready');
      } else {
        setStatus('error');
        setErrorMessage(
          'This invitation is invalid, expired, or not associated with your email address.'
        );
      }
    }
  }, [token, isAuthenticated, invitesLoading, matchingInvite, navigate]);

  const acceptMutation = useMutation({
    mutationFn: () => teamsApi.acceptInvite(token!),
    onSuccess: (data) => {
      setStatus('success');
      toast.success(`Welcome to ${data.team.name}!`);
      // Redirect to settings/team after a moment
      setTimeout(() => navigate('/settings'), 2000);
    },
    onError: (error: any) => {
      setStatus('error');
      setErrorMessage(error.response?.data?.detail || 'Failed to accept invitation');
    },
  });

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <Mail className="h-10 w-10 text-brand-purple" />
          <span className="text-2xl font-bold text-slate-900">ChampMail</span>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-center">Team Invitation</CardTitle>
          </CardHeader>

          <div className="p-6">
            {status === 'loading' && (
              <div className="text-center py-8">
                <Loader2 className="h-12 w-12 text-brand-purple animate-spin mx-auto mb-4" />
                <p className="text-slate-600">Validating invitation...</p>
              </div>
            )}

            {status === 'ready' && matchingInvite && (
              <div className="text-center py-4">
                <div className="flex justify-center mb-6">
                  <div className="h-16 w-16 rounded-full bg-brand-purple/10 flex items-center justify-center">
                    <Users className="h-8 w-8 text-brand-purple" />
                  </div>
                </div>

                <h3 className="text-lg font-medium text-slate-900 mb-2">
                  You've been invited to join
                </h3>
                <p className="text-2xl font-bold text-brand-purple mb-2">
                  {matchingInvite.team_name}
                </p>
                <p className="text-sm text-slate-500 mb-6">
                  as a <span className="font-medium">{matchingInvite.role === 'team_admin' ? 'Team Admin' : 'Team Member'}</span>
                </p>

                <div className="bg-slate-50 rounded-lg p-4 mb-6 text-sm text-slate-600">
                  <p>
                    Logged in as: <strong>{user?.email}</strong>
                  </p>
                </div>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    onClick={() => navigate('/')}
                    className="flex-1"
                  >
                    Decline
                  </Button>
                  <Button
                    onClick={() => acceptMutation.mutate()}
                    isLoading={acceptMutation.isPending}
                    className="flex-1"
                  >
                    Accept Invitation
                  </Button>
                </div>
              </div>
            )}

            {status === 'success' && (
              <div className="text-center py-8">
                <div className="flex justify-center mb-4">
                  <div className="h-16 w-16 rounded-full bg-green-100 flex items-center justify-center">
                    <CheckCircle className="h-8 w-8 text-green-600" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-slate-900 mb-2">
                  Welcome to the team!
                </h3>
                <p className="text-slate-500">
                  Redirecting you to your dashboard...
                </p>
              </div>
            )}

            {status === 'error' && (
              <div className="text-center py-8">
                <div className="flex justify-center mb-4">
                  <div className="h-16 w-16 rounded-full bg-red-100 flex items-center justify-center">
                    <XCircle className="h-8 w-8 text-red-600" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-slate-900 mb-2">
                  Invitation Error
                </h3>
                <p className="text-slate-500 mb-6">{errorMessage}</p>
                <Button onClick={() => navigate('/')}>Go to Dashboard</Button>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

export default JoinTeamPage;
