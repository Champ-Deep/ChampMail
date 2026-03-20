/**
 * CampaignDetailPage — tracking dashboard for a single campaign.
 *
 * Shows: stat cards (delivered, opened, clicked, bounced, replied, unsubscribed),
 * CampaignProgress widget (if running/paused), and recipient table.
 */

import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  ArrowLeft,
  Send,
  Eye,
  MousePointerClick,
  AlertTriangle,
  MessageSquare,
  UserX,
  Mail,
  Play,
  Pause,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { campaignsApi, type CampaignTracking, type CampaignRecipient } from '../api/campaigns';
import { CampaignProgress } from '../components/campaigns/CampaignProgress';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function fmtPct(num: number, den: number): string {
  if (den === 0) return '0.0%';
  return `${((num / den) * 100).toFixed(1)}%`;
}

const recipientStatusConfig: Record<string, { label: string; variant: 'default' | 'success' | 'warning' | 'danger' }> = {
  pending: { label: 'Pending', variant: 'default' },
  sent: { label: 'Sent', variant: 'success' },
  delivered: { label: 'Delivered', variant: 'success' },
  opened: { label: 'Opened', variant: 'success' },
  clicked: { label: 'Clicked', variant: 'success' },
  replied: { label: 'Replied', variant: 'success' },
  bounced: { label: 'Bounced', variant: 'danger' },
  failed: { label: 'Failed', variant: 'danger' },
  skipped: { label: 'Skipped', variant: 'warning' },
  unsubscribed: { label: 'Unsubscribed', variant: 'warning' },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // ---- Queries ----
  const { data: campaign, isLoading: campaignLoading } = useQuery({
    queryKey: ['campaign', id],
    queryFn: () => campaignsApi.get(id!),
    enabled: !!id,
  });

  const { data: tracking, isLoading: trackingLoading } = useQuery({
    queryKey: ['campaign-tracking', id],
    queryFn: () => campaignsApi.getTracking(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.campaign_status;
      return status === 'running' || status === 'sending' ? 10_000 : false;
    },
  });

  const { data: recipients } = useQuery({
    queryKey: ['campaign-recipients', id],
    queryFn: () => campaignsApi.getRecipients(id!),
    enabled: !!id,
  });

  // ---- Mutations ----
  const sendMutation = useMutation({
    mutationFn: () => campaignsApi.send(id!),
    onSuccess: () => {
      toast.success('Campaign sending started');
      queryClient.invalidateQueries({ queryKey: ['campaign', id] });
    },
    onError: () => toast.error('Failed to start sending'),
  });

  const pauseMutation = useMutation({
    mutationFn: () => campaignsApi.pause(id!),
    onSuccess: () => {
      toast.success('Campaign paused');
      queryClient.invalidateQueries({ queryKey: ['campaign', id] });
    },
    onError: () => toast.error('Failed to pause campaign'),
  });

  const resumeMutation = useMutation({
    mutationFn: () => campaignsApi.resume(id!),
    onSuccess: () => {
      toast.success('Campaign resumed');
      queryClient.invalidateQueries({ queryKey: ['campaign', id] });
    },
    onError: () => toast.error('Failed to resume campaign'),
  });

  // ---- Loading ----
  if (campaignLoading || trackingLoading) {
    return (
      <div className="h-full">
        <Header title="Campaign Details" />
        <div className="p-6 flex items-center justify-center py-24">
          <Mail className="h-10 w-10 text-slate-300 animate-pulse" />
        </div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="h-full">
        <Header title="Campaign not found" />
        <div className="p-6 text-center py-24">
          <p className="text-slate-500 mb-4">This campaign doesn't exist or you don't have access.</p>
          <Button variant="outline" onClick={() => navigate('/campaigns')}>
            Back to Campaigns
          </Button>
        </div>
      </div>
    );
  }

  const isRunning = campaign.status === 'running';
  const isPaused = campaign.status === 'paused';
  const isDraft = campaign.status === 'draft';

  // Build stat cards from tracking data
  const stats = tracking
    ? [
        {
          label: 'Sent',
          value: tracking.sent,
          icon: <Send className="h-5 w-5" />,
          color: 'text-blue-600',
          bg: 'bg-blue-50',
        },
        {
          label: 'Delivered',
          value: tracking.delivered,
          sub: fmtPct(tracking.delivered, tracking.sent),
          icon: <CheckCircle2 className="h-5 w-5" />,
          color: 'text-green-600',
          bg: 'bg-green-50',
        },
        {
          label: 'Opened',
          value: tracking.opens.unique,
          sub: fmtRate(tracking.opens.rate),
          icon: <Eye className="h-5 w-5" />,
          color: 'text-indigo-600',
          bg: 'bg-indigo-50',
        },
        {
          label: 'Clicked',
          value: tracking.clicks.unique,
          sub: fmtRate(tracking.clicks.rate),
          icon: <MousePointerClick className="h-5 w-5" />,
          color: 'text-purple-600',
          bg: 'bg-purple-50',
        },
        {
          label: 'Bounced',
          value: tracking.bounces.total,
          sub: fmtRate(tracking.bounces.rate),
          icon: <AlertTriangle className="h-5 w-5" />,
          color: 'text-amber-600',
          bg: 'bg-amber-50',
        },
        {
          label: 'Replied',
          value: tracking.replies.total,
          sub: fmtRate(tracking.replies.rate),
          icon: <MessageSquare className="h-5 w-5" />,
          color: 'text-green-600',
          bg: 'bg-green-50',
        },
        {
          label: 'Unsubscribed',
          value: tracking.unsubscribes,
          sub: fmtPct(tracking.unsubscribes, tracking.sent),
          icon: <UserX className="h-5 w-5" />,
          color: 'text-red-600',
          bg: 'bg-red-50',
        },
      ]
    : [];

  const recipientList: CampaignRecipient[] = recipients ?? [];

  return (
    <div className="h-full">
      <Header
        title={campaign.name}
        subtitle={campaign.description || undefined}
        actions={
          <div className="flex items-center gap-2">
            {isDraft && (
              <Button
                leftIcon={<Send className="h-4 w-4" />}
                isLoading={sendMutation.isPending}
                onClick={() => sendMutation.mutate()}
              >
                Send Campaign
              </Button>
            )}
            {isRunning && (
              <Button
                variant="outline"
                leftIcon={<Pause className="h-4 w-4" />}
                isLoading={pauseMutation.isPending}
                onClick={() => pauseMutation.mutate()}
              >
                Pause
              </Button>
            )}
            {isPaused && (
              <Button
                variant="outline"
                leftIcon={<Play className="h-4 w-4" />}
                isLoading={resumeMutation.isPending}
                onClick={() => resumeMutation.mutate()}
              >
                Resume
              </Button>
            )}
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Back link */}
        <Link
          to="/campaigns"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Campaigns
        </Link>

        {/* Campaign Progress (shown when running or paused) */}
        {(isRunning || isPaused) && id && (
          <CampaignProgress
            campaignId={id}
            onPause={() => pauseMutation.mutate()}
            onResume={() => resumeMutation.mutate()}
            isPausing={pauseMutation.isPending}
            isResuming={resumeMutation.isPending}
          />
        )}

        {/* Stat cards grid */}
        {stats.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-4">
            {stats.map((s) => (
              <Card key={s.label} className="p-4">
                <div className="flex items-center gap-3">
                  <div className={clsx('p-2 rounded-lg', s.bg)}>
                    <span className={s.color}>{s.icon}</span>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-slate-900">{s.value}</p>
                    <p className="text-xs text-slate-500">{s.label}</p>
                  </div>
                </div>
                {s.sub && (
                  <p className={clsx('text-xs font-medium mt-2', s.color)}>{s.sub}</p>
                )}
              </Card>
            ))}
          </div>
        )}

        {/* Delivery rate banner */}
        {tracking && tracking.sent > 0 && (
          <div className="flex items-center gap-4 px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg text-sm">
            <span className="text-slate-600">
              Delivery Rate: <strong className="text-slate-900">{fmtRate(tracking.delivery_rate)}</strong>
            </span>
            {tracking.clicks.click_to_open_rate > 0 && (
              <span className="text-slate-600">
                Click-to-Open: <strong className="text-slate-900">{fmtRate(tracking.clicks.click_to_open_rate)}</strong>
              </span>
            )}
            <span className="text-slate-600">
              Total Prospects: <strong className="text-slate-900">{tracking.total_prospects}</strong>
            </span>
          </div>
        )}

        {/* Recipient table */}
        {recipientList.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-slate-700 mb-3">
              Recipients ({recipientList.length})
            </h3>
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Email</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Name</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Company</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Status</th>
                    <th className="px-4 py-2.5 text-left font-medium text-slate-600">Sent At</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {recipientList.map((r) => {
                    const cfg = recipientStatusConfig[r.status] || recipientStatusConfig.pending;
                    return (
                      <tr key={r.prospect_id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-2.5 font-mono text-slate-800">{r.email}</td>
                        <td className="px-4 py-2.5 text-slate-700">
                          {[r.first_name, r.last_name].filter(Boolean).join(' ') || '-'}
                        </td>
                        <td className="px-4 py-2.5 text-slate-700">{r.company || '-'}</td>
                        <td className="px-4 py-2.5">
                          <Badge variant={cfg.variant}>{cfg.label}</Badge>
                        </td>
                        <td className="px-4 py-2.5 text-slate-500 text-xs">
                          {r.sent_at
                            ? new Date(r.sent_at).toLocaleString()
                            : '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty state when no tracking data yet */}
        {!tracking && !trackingLoading && (
          <Card className="p-8 text-center">
            <Mail className="h-10 w-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">No tracking data yet. Send the campaign to see stats here.</p>
          </Card>
        )}
      </div>
    </div>
  );
}

export default CampaignDetailPage;
