import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Search,
  Mail,
  Play,
  Pause,
  Users,
  Send,
  BarChart3,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { campaignsApi, type Campaign, type CampaignStatus } from '../api/campaigns';
import { CreateCampaignModal } from '../components/campaigns/CreateCampaignModal';
import { clsx } from 'clsx';

const statusConfig: Record<
  CampaignStatus,
  { label: string; variant: 'default' | 'success' | 'warning' | 'danger' }
> = {
  draft: { label: 'Draft', variant: 'default' },
  scheduled: { label: 'Scheduled', variant: 'default' },
  running: { label: 'Running', variant: 'success' },
  paused: { label: 'Paused', variant: 'warning' },
  completed: { label: 'Completed', variant: 'default' },
  failed: { label: 'Failed', variant: 'danger' },
};

const filterTabs: { label: string; value: CampaignStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Draft', value: 'draft' },
  { label: 'Running', value: 'running' },
  { label: 'Paused', value: 'paused' },
  { label: 'Completed', value: 'completed' },
];

function computeRate(numerator: number, denominator: number): string {
  if (denominator === 0) return '0.0';
  return ((numerator / denominator) * 100).toFixed(1);
}

export function CampaignsPage() {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<CampaignStatus | 'all'>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);

  // ---- Queries ----
  const {
    data,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['campaigns', statusFilter],
    queryFn: () =>
      campaignsApi.list(
        100,
        0,
        statusFilter === 'all' ? undefined : statusFilter
      ),
  });

  const campaigns: Campaign[] = data?.campaigns ?? [];

  // ---- Mutations ----
  const sendMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.send(id),
    onSuccess: () => {
      toast.success('Campaign sent successfully');
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
    onError: () => {
      toast.error('Failed to send campaign');
    },
  });

  const pauseMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.pause(id),
    onSuccess: () => {
      toast.success('Campaign paused');
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
    onError: () => {
      toast.error('Failed to pause campaign');
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (id: string) => campaignsApi.resume(id),
    onSuccess: () => {
      toast.success('Campaign resumed');
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
    },
    onError: () => {
      toast.error('Failed to resume campaign');
    },
  });

  // ---- Client-side search filter ----
  const filteredCampaigns = campaigns.filter((c) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      (c.description && c.description.toLowerCase().includes(q))
    );
  });

  // ---- Render ----
  return (
    <div className="h-full">
      <Header
        title="Campaigns"
        subtitle="Manage your email campaigns"
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => setShowCreateModal(true)}>
            New Campaign
          </Button>
        }
      />

      <div className="p-6 space-y-6">
        {/* Search and Filters */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search campaigns..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
            />
          </div>

          <div className="flex items-center gap-2">
            {filterTabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setStatusFilter(tab.value)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                  statusFilter === tab.value
                    ? 'bg-brand-purple/10 text-brand-purple'
                    : 'text-slate-600 hover:bg-slate-100'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="py-16 text-center">
            <Mail className="h-12 w-12 text-slate-300 mx-auto mb-4 animate-pulse" />
            <p className="text-slate-500">Loading campaigns...</p>
          </div>
        )}

        {/* Error State */}
        {isError && (
          <div className="py-16 text-center">
            <Mail className="h-12 w-12 text-red-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">
              Failed to load campaigns
            </h3>
            <p className="text-slate-500">
              Please try refreshing the page.
            </p>
          </div>
        )}

        {/* Campaigns List */}
        {!isLoading && !isError && (
          <div className="space-y-4">
            {filteredCampaigns.map((campaign) => {
              const openRate = computeRate(campaign.opened_count, campaign.sent_count);
              const replyRate = computeRate(campaign.replied_count, campaign.sent_count);
              const cfg = statusConfig[campaign.status];

              return (
                <Card
                  key={campaign.id}
                  className="hover:border-brand-purple/20 hover:shadow-md transition-all"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4">
                      <div
                        className={clsx(
                          'p-3 rounded-xl',
                          campaign.status === 'running'
                            ? 'bg-green-100'
                            : campaign.status === 'paused'
                            ? 'bg-yellow-100'
                            : campaign.status === 'failed'
                            ? 'bg-red-100'
                            : 'bg-slate-100'
                        )}
                      >
                        <Mail
                          className={clsx(
                            'h-6 w-6',
                            campaign.status === 'running'
                              ? 'text-green-600'
                              : campaign.status === 'paused'
                              ? 'text-yellow-600'
                              : campaign.status === 'failed'
                              ? 'text-red-600'
                              : 'text-slate-500'
                          )}
                        />
                      </div>
                      <div>
                        <div className="flex items-center gap-3">
                          <h3 className="font-semibold text-slate-900">
                            {campaign.name}
                          </h3>
                          <Badge variant={cfg.variant}>{cfg.label}</Badge>
                        </div>
                        {campaign.description && (
                          <p className="text-sm text-slate-500 mt-1">
                            {campaign.description}
                          </p>
                        )}
                        <div className="flex items-center gap-6 mt-3 text-sm text-slate-500">
                          <div className="flex items-center gap-1.5">
                            <Send className="h-4 w-4" />
                            <span>{campaign.sent_count} sent</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <BarChart3 className="h-4 w-4" />
                            <span>{campaign.opened_count} opened</span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <Users className="h-4 w-4" />
                            <span>{campaign.replied_count} replied</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      {/* Rates */}
                      {campaign.sent_count > 0 && (
                        <div className="flex items-center gap-6 pr-4 border-r border-slate-200">
                          <div className="text-center">
                            <p className="text-2xl font-bold text-slate-900">
                              {openRate}%
                            </p>
                            <p className="text-xs text-slate-500">Open Rate</p>
                          </div>
                          <div className="text-center">
                            <p className="text-2xl font-bold text-green-600">
                              {replyRate}%
                            </p>
                            <p className="text-xs text-slate-500">Reply Rate</p>
                          </div>
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex items-center gap-2">
                        {campaign.status === 'draft' && (
                          <Button
                            size="sm"
                            leftIcon={<Send className="h-4 w-4" />}
                            isLoading={sendMutation.isPending && sendMutation.variables === campaign.id}
                            onClick={() => sendMutation.mutate(campaign.id)}
                          >
                            Send
                          </Button>
                        )}
                        {campaign.status === 'running' && (
                          <Button
                            variant="outline"
                            size="sm"
                            leftIcon={<Pause className="h-4 w-4" />}
                            isLoading={pauseMutation.isPending && pauseMutation.variables === campaign.id}
                            onClick={() => pauseMutation.mutate(campaign.id)}
                          >
                            Pause
                          </Button>
                        )}
                        {campaign.status === 'paused' && (
                          <Button
                            variant="outline"
                            size="sm"
                            leftIcon={<Play className="h-4 w-4" />}
                            isLoading={resumeMutation.isPending && resumeMutation.variables === campaign.id}
                            onClick={() => resumeMutation.mutate(campaign.id)}
                          >
                            Resume
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Progress Bar */}
                  {campaign.total_prospects > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-100">
                      <div className="flex items-center justify-between text-sm mb-2">
                        <span className="text-slate-500">Progress</span>
                        <span className="text-slate-700">
                          {campaign.sent_count} of {campaign.total_prospects} sent
                        </span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-brand-purple rounded-full"
                          style={{
                            width: `${(campaign.sent_count / campaign.total_prospects) * 100}%`,
                          }}
                        />
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}

            {/* Empty State */}
            {filteredCampaigns.length === 0 && (
              <div className="py-12 text-center">
                <Mail className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-1">
                  No campaigns found
                </h3>
                <p className="text-slate-500 mb-4">
                  {searchQuery || statusFilter !== 'all'
                    ? 'Try adjusting your search or filters'
                    : 'Create your first campaign to get started'}
                </p>
                {!searchQuery && statusFilter === 'all' && (
                  <Button leftIcon={<Plus className="h-4 w-4" />}>
                    New Campaign
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <CreateCampaignModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
      />
    </div>
  );
}

export default CampaignsPage;
