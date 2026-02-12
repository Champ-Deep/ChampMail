import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { clsx } from 'clsx';

// Mock data
const mockSequences = [
  {
    id: '1',
    name: 'Cold Outreach - Tech Startups',
    description: 'Initial outreach sequence for tech startup founders',
    status: 'active',
    steps_count: 5,
    enrolled_count: 234,
    completed_count: 89,
    replied_count: 23,
    open_rate: 68.5,
    reply_rate: 9.8,
    created_at: '2024-01-10T10:30:00Z',
  },
  {
    id: '2',
    name: 'Follow-up - No Response',
    description: 'Re-engagement sequence for prospects who haven\'t replied',
    status: 'active',
    steps_count: 3,
    enrolled_count: 156,
    completed_count: 45,
    replied_count: 12,
    open_rate: 45.2,
    reply_rate: 7.7,
    created_at: '2024-01-08T14:20:00Z',
  },
  {
    id: '3',
    name: 'Enterprise Outreach',
    description: 'High-touch sequence for enterprise prospects',
    status: 'paused',
    steps_count: 7,
    enrolled_count: 45,
    completed_count: 12,
    replied_count: 8,
    open_rate: 72.1,
    reply_rate: 17.8,
    created_at: '2024-01-05T09:00:00Z',
  },
  {
    id: '4',
    name: 'Product Launch Announcement',
    description: 'Announce new product features to existing contacts',
    status: 'draft',
    steps_count: 2,
    enrolled_count: 0,
    completed_count: 0,
    replied_count: 0,
    open_rate: 0,
    reply_rate: 0,
    created_at: '2024-01-15T16:45:00Z',
  },
];

const statusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'default' | 'danger' }> = {
  active: { label: 'Active', variant: 'success' },
  paused: { label: 'Paused', variant: 'warning' },
  draft: { label: 'Draft', variant: 'default' },
  completed: { label: 'Completed', variant: 'default' },
};

export function SequencesPage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const filteredSequences = mockSequences.filter((seq) => {
    const matchesSearch =
      seq.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      seq.description?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = !statusFilter || seq.status === statusFilter;
    return matchesSearch && matchesStatus;
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
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
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
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-slate-600 hover:bg-slate-100'
                )}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Sequences List */}
        <div className="space-y-4">
          {filteredSequences.map((sequence) => (
            <Card
              key={sequence.id}
              className="hover:border-blue-200 hover:shadow-md transition-all"
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
                        className="font-semibold text-slate-900 hover:text-blue-600 cursor-pointer"
                        onClick={() => navigate(`/sequences/${sequence.id}`)}
                      >
                        {sequence.name}
                      </h3>
                      <Badge variant={statusConfig[sequence.status].variant}>
                        {statusConfig[sequence.status].label}
                      </Badge>
                    </div>
                    <p className="text-sm text-slate-500 mt-1">
                      {sequence.description}
                    </p>
                    <div className="flex items-center gap-6 mt-3 text-sm text-slate-500">
                      <div className="flex items-center gap-1.5">
                        <Mail className="h-4 w-4" />
                        <span>{sequence.steps_count} steps</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Users className="h-4 w-4" />
                        <span>{sequence.enrolled_count} enrolled</span>
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
                          {sequence.open_rate}%
                        </p>
                        <p className="text-xs text-slate-500">Open Rate</p>
                      </div>
                      <div className="text-center">
                        <p className="text-2xl font-bold text-green-600">
                          {sequence.reply_rate}%
                        </p>
                        <p className="text-xs text-slate-500">Reply Rate</p>
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {sequence.status === 'active' ? (
                      <Button variant="outline" size="sm" leftIcon={<Pause className="h-4 w-4" />}>
                        Pause
                      </Button>
                    ) : sequence.status === 'paused' ? (
                      <Button variant="outline" size="sm" leftIcon={<Play className="h-4 w-4" />}>
                        Resume
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
              {sequence.enrolled_count > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-slate-500">Progress</span>
                    <span className="text-slate-700">
                      {sequence.completed_count} of {sequence.enrolled_count} completed
                    </span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full"
                      style={{
                        width: `${(sequence.completed_count / sequence.enrolled_count) * 100}%`,
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
      </div>
    </div>
  );
}

export default SequencesPage;
