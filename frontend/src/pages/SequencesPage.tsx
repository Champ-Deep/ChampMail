import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Search,
  Zap,
  Play,
  Pause,
  MoreVertical,
  Users,
  Mail,
  Clock,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { clsx } from 'clsx';
import { sequencesApi } from '../api/sequences';
import type { SequenceStatus } from '../api/sequences';

const statusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'default' | 'danger' }> = {
  active: { label: 'Active', variant: 'success' },
  paused: { label: 'Paused', variant: 'warning' },
  draft: { label: 'Draft', variant: 'default' },
  completed: { label: 'Completed', variant: 'default' },
};

export function SequencesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const { data: sequences = [], isLoading, error } = useQuery({
    queryKey: ['sequences', statusFilter],
    queryFn: () => sequencesApi.list((statusFilter as SequenceStatus) || undefined),
  });

  const pauseMutation = useMutation({
    mutationFn: (id: string) => sequencesApi.pause(id),
    onSuccess: () => {
      toast.success('Sequence paused');
      queryClient.invalidateQueries({ queryKey: ['sequences'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to pause sequence');
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (id: string) => sequencesApi.resume(id),
    onSuccess: () => {
      toast.success('Sequence resumed');
      queryClient.invalidateQueries({ queryKey: ['sequences'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to resume sequence');
    },
  });

  const filteredSequences = (sequences || []).filter((seq) => {
    if (!searchQuery) return true;
    return (
      seq.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      seq.description?.toLowerCase().includes(searchQuery.toLowerCase())
    );
  });

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="h-full">
      <Header
        title="Email Sequences"
        subtitle="Automate your outreach campaigns"
        actions={
          <Button
            leftIcon={<Plus className="h-4 w-4" />}
            onClick={() => navigate('/sequences/new')}
          >
            New Sequence
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
              placeholder="Search sequences..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
            />
          </div>

          <div className="flex items-center gap-2">
            {['all', 'active', 'paused', 'draft'].map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status === 'all' ? null : status)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                  (status === 'all' && !statusFilter) || statusFilter === status
                    ? 'bg-brand-purple/10 text-brand-purple'
                    : 'text-slate-600 hover:bg-slate-100'
                )}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="py-12 text-center">
            <Loader2 className="h-12 w-12 text-brand-purple animate-spin mx-auto mb-4" />
            <p className="text-slate-500">Loading sequences...</p>
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <div className="py-12 text-center">
            <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">
              Failed to load sequences
            </h3>
            <p className="text-slate-500 mb-4">
              {(error as any)?.response?.data?.detail || (error as Error).message || 'An unexpected error occurred'}
            </p>
            <Button
              variant="outline"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['sequences'] })}
            >
              Try Again
            </Button>
          </div>
        )}

        {/* Sequences List */}
        {!isLoading && !error && (
          <div className="space-y-4">
            {filteredSequences.map((sequence) => (
              <Card
                key={sequence.id}
                className="hover:border-brand-purple/20 hover:shadow-md transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4">
                    <div
                      className={clsx(
                        'p-3 rounded-xl',
                        sequence.status === 'active'
                          ? 'bg-green-100'
                          : sequence.status === 'paused'
                          ? 'bg-yellow-100'
                          : 'bg-slate-100'
                      )}
                    >
                      <Zap
                        className={clsx(
                          'h-6 w-6',
                          sequence.status === 'active'
                            ? 'text-green-600'
                            : sequence.status === 'paused'
                            ? 'text-yellow-600'
                            : 'text-slate-500'
                        )}
                      />
                    </div>
                    <div>
                      <div className="flex items-center gap-3">
                        <h3
                          className="font-semibold text-slate-900 hover:text-brand-purple cursor-pointer"
                          onClick={() => navigate(`/sequences/${sequence.id}`)}
                        >
                          {sequence.name}
                        </h3>
                        <Badge variant={statusConfig[sequence.status]?.variant || 'default'}>
                          {statusConfig[sequence.status]?.label || sequence.status}
                        </Badge>
                      </div>
                      <p className="text-sm text-slate-500 mt-1">
                        {sequence.description}
                      </p>
                      <div className="flex items-center gap-6 mt-3 text-sm text-slate-500">
                        <div className="flex items-center gap-1.5">
                          <Mail className="h-4 w-4" />
                          <span>{sequence.steps?.length || 0} steps</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Users className="h-4 w-4" />
                          <span>{sequence.enrolled_count || 0} enrolled</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Clock className="h-4 w-4" />
                          <span>Created {formatDate(sequence.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    {/* Stats */}
                    {sequence.status !== 'draft' && (
                      <div className="flex items-center gap-6 pr-4 border-r border-slate-200">
                        <div className="text-center">
                          <p className="text-2xl font-bold text-slate-900">
                            {sequence.enrolled_count || 0}
                          </p>
                          <p className="text-xs text-slate-500">Enrolled</p>
                        </div>
                        <div className="text-center">
                          <p className="text-2xl font-bold text-green-600">
                            {sequence.completed_count || 0}
                          </p>
                          <p className="text-xs text-slate-500">Completed</p>
                        </div>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      {sequence.status === 'active' ? (
                        <Button
                          variant="outline"
                          size="sm"
                          leftIcon={<Pause className="h-4 w-4" />}
                          onClick={() => pauseMutation.mutate(sequence.id)}
                          disabled={pauseMutation.isPending}
                        >
                          {pauseMutation.isPending ? 'Pausing...' : 'Pause'}
                        </Button>
                      ) : sequence.status === 'paused' ? (
                        <Button
                          variant="outline"
                          size="sm"
                          leftIcon={<Play className="h-4 w-4" />}
                          onClick={() => resumeMutation.mutate(sequence.id)}
                          disabled={resumeMutation.isPending}
                        >
                          {resumeMutation.isPending ? 'Resuming...' : 'Resume'}
                        </Button>
                      ) : (
                        <Button size="sm" leftIcon={<Play className="h-4 w-4" />}>
                          Launch
                        </Button>
                      )}
                      <button className="p-2 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600">
                        <MoreVertical className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Progress Bar */}
                {(sequence.enrolled_count || 0) > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-100">
                    <div className="flex items-center justify-between text-sm mb-2">
                      <span className="text-slate-500">Progress</span>
                      <span className="text-slate-700">
                        {sequence.completed_count || 0} of {sequence.enrolled_count || 0} completed
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-purple rounded-full"
                        style={{
                          width: `${((sequence.completed_count || 0) / (sequence.enrolled_count || 1)) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                )}
              </Card>
            ))}

            {/* Empty State */}
            {filteredSequences.length === 0 && (
              <div className="py-12 text-center">
                <Zap className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-1">
                  No sequences found
                </h3>
                <p className="text-slate-500 mb-4">
                  {searchQuery || statusFilter
                    ? 'Try adjusting your filters'
                    : 'Create your first email sequence to get started'}
                </p>
                {!searchQuery && !statusFilter && (
                  <Button onClick={() => navigate('/sequences/new')}>
                    Create Sequence
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default SequencesPage;
