import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  UserPlus,
  Search,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronRight,
  Users,
  CheckCircle2,
  Clock,
  XCircle,
  Zap,
  List,
  X,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { clsx } from 'clsx';
import {
  adminProspectsApi,
  type AdminProspect,
  type AdminUser,
  type CreateProspectData,
  type CreateUserData,
} from '../api/adminProspects';

// -------------------------------------------------------
// Helpers
// -------------------------------------------------------

function researchBadge(status: AdminProspect['research_status']) {
  const map = {
    pending: { variant: 'warning' as const, icon: <Clock className="h-3 w-3" />, label: 'Pending' },
    running: { variant: 'info' as const, icon: <Loader2 className="h-3 w-3 animate-spin" />, label: 'Researching' },
    completed: { variant: 'success' as const, icon: <CheckCircle2 className="h-3 w-3" />, label: 'Researched' },
    failed: { variant: 'danger' as const, icon: <XCircle className="h-3 w-3" />, label: 'Failed' },
  };
  const cfg = map[status] ?? map.pending;
  return (
    <Badge variant={cfg.variant}>
      <span className="flex items-center gap-1">{cfg.icon}{cfg.label}</span>
    </Badge>
  );
}

function formatDate(s?: string | null) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// -------------------------------------------------------
// Create Prospect Modal
// -------------------------------------------------------

function CreateProspectModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<CreateProspectData>({ email: '' });

  const mutation = useMutation({
    mutationFn: (data: CreateProspectData) => adminProspectsApi.createProspect(data),
    onSuccess: () => {
      toast.success('Prospect created. Research starting in background.');
      qc.invalidateQueries({ queryKey: ['admin-prospects'] });
      onClose();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-semibold">Create Prospect</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          {(
            [
              { key: 'email', label: 'Email *', type: 'email' },
              { key: 'first_name', label: 'First Name', type: 'text' },
              { key: 'last_name', label: 'Last Name', type: 'text' },
              { key: 'company_name', label: 'Company Name', type: 'text' },
              { key: 'company_domain', label: 'Company Domain', type: 'text' },
              { key: 'industry', label: 'Industry', type: 'text' },
              { key: 'job_title', label: 'Job Title', type: 'text' },
              { key: 'linkedin_url', label: 'LinkedIn URL', type: 'text' },
            ] as Array<{ key: keyof CreateProspectData; label: string; type: string }>
          ).map(({ key, label, type }) => (
            <div key={key}>
              <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
              <input
                type={type}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                value={form[key] ?? ''}
                onChange={e => setForm(prev => ({ ...prev, [key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-3 p-6 border-t">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mutation.mutate(form)}
            disabled={!form.email || mutation.isPending}
          >
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Create Prospect
          </Button>
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Create User Modal
// -------------------------------------------------------

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<CreateUserData>({ email: '', password: '', name: '', role: 'user' });

  const mutation = useMutation({
    mutationFn: (data: CreateUserData) => adminProspectsApi.createUser(data),
    onSuccess: () => {
      toast.success('User account created successfully.');
      qc.invalidateQueries({ queryKey: ['admin-users'] });
      onClose();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-semibold">Create User Account</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email *</label>
            <input type="email" className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={form.email} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Password *</label>
            <input type="password" className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Full Name</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
            <select className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}>
              <option value="user">User</option>
              <option value="team_admin">Team Admin</option>
              <option value="data_team">Data Team</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-3 p-6 border-t">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => mutation.mutate(form)}
            disabled={!form.email || !form.password || mutation.isPending}
          >
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Create User
          </Button>
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Assign Modal
// -------------------------------------------------------

function AssignModal({
  prospect,
  users,
  onClose,
}: {
  prospect: AdminProspect;
  users: AdminUser[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [userId, setUserId] = useState('');
  const [campaignId, setCampaignId] = useState('');

  const mutation = useMutation({
    mutationFn: () => adminProspectsApi.assignProspect(prospect.id, { user_id: userId, campaign_id: campaignId || undefined }),
    onSuccess: () => {
      toast.success('Prospect assigned successfully.');
      qc.invalidateQueries({ queryKey: ['admin-prospects'] });
      onClose();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-semibold">Assign Prospect</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-sm text-slate-600">Assigning: <strong>{prospect.email}</strong></p>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Assign to User *</label>
            <select
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={userId} onChange={e => setUserId(e.target.value)}
            >
              <option value="">— Select user —</option>
              {users.map(u => (
                <option key={u.user_id} value={u.user_id}>
                  {u.full_name || u.email} ({u.role})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Campaign ID (optional)</label>
            <input
              type="text"
              placeholder="Pre-enroll in campaign"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={campaignId} onChange={e => setCampaignId(e.target.value)}
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 p-6 border-t">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!userId || mutation.isPending}>
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Assign
          </Button>
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Enroll Modal
// -------------------------------------------------------

function EnrollModal({ prospect, onClose }: { prospect: AdminProspect; onClose: () => void }) {
  const qc = useQueryClient();
  const [campaignId, setCampaignId] = useState('');

  const mutation = useMutation({
    mutationFn: () => adminProspectsApi.enrollProspect(prospect.id, { campaign_id: campaignId || undefined }),
    onSuccess: (data) => {
      toast.success(`Enrolled! Step 1 firing now. Enrollment: ${data.enrollment_id.slice(0, 8)}…`);
      qc.invalidateQueries({ queryKey: ['admin-prospects'] });
      onClose();
    },
    onError: (e: Error) => toast.error(`Failed: ${e.message}`),
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-semibold">Enroll in 3-Point Follow-up</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-sm text-slate-600">
            Enrolling <strong>{prospect.email}</strong> in the 3-Point Follow-up sequence.
            Step 1 (initial email) fires immediately.
          </p>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Campaign ID (optional)</label>
            <input
              type="text"
              placeholder="Link to a campaign"
              className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={campaignId} onChange={e => setCampaignId(e.target.value)}
            />
          </div>
        </div>
        <div className="flex justify-end gap-3 p-6 border-t">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Start Sequence
          </Button>
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Logs Panel
// -------------------------------------------------------

function LogsPanel({ prospectId, onClose }: { prospectId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['prospect-logs', prospectId],
    queryFn: () => adminProspectsApi.getProspectLogs(prospectId),
  });

  const actionColor: Record<string, string> = {
    sent: 'text-blue-600',
    acknowledged: 'text-green-600',
    followed_up: 'text-yellow-600',
    completed: 'text-purple-600',
    skipped: 'text-slate-400',
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-lg font-semibold">Sequence Step Logs</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
          ) : !data?.logs?.length ? (
            <p className="text-center text-slate-500 py-8">No sequence logs yet for this prospect.</p>
          ) : (
            <div className="space-y-4">
              {data.logs.map((log) => (
                <div key={log.id} className="border rounded-lg p-4 bg-slate-50">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold bg-slate-200 text-slate-700 rounded-full w-6 h-6 flex items-center justify-center">
                        {log.sequence_step}
                      </span>
                      <span className={clsx('text-sm font-semibold capitalize', actionColor[log.action_taken] ?? 'text-slate-600')}>
                        {log.action_taken}
                      </span>
                      {log.reply_detected && (
                        <Badge variant="success">Reply Detected</Badge>
                      )}
                    </div>
                    <span className="text-xs text-slate-400">{formatDate(log.timestamp)}</span>
                  </div>
                  {log.email_content_summary && (
                    <p className="text-sm text-slate-600 mb-1">{log.email_content_summary}</p>
                  )}
                  {log.raw_subject && (
                    <p className="text-xs text-slate-500"><strong>Subject:</strong> {log.raw_subject}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="p-4 border-t">
          <Button variant="secondary" onClick={onClose} className="w-full">Close</Button>
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------
// Users Tab
// -------------------------------------------------------

function UsersTab() {
  const [showCreate, setShowCreate] = useState(false);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminProspectsApi.listUsers(),
  });

  const roleBadge: Record<string, 'default' | 'info' | 'warning' | 'success'> = {
    admin: 'danger' as 'default',
    team_admin: 'warning',
    data_team: 'info',
    user: 'default',
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-slate-600">{data?.users?.length ?? 0} users</p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => refetch()}><RefreshCw className="h-4 w-4" /></Button>
          <Button onClick={() => setShowCreate(true)}>
            <UserPlus className="h-4 w-4 mr-2" /> Create User
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-slate-500">
                <th className="pb-3 font-medium">Email</th>
                <th className="pb-3 font-medium">Name</th>
                <th className="pb-3 font-medium">Role</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.users?.map(u => (
                <tr key={u.user_id} className="hover:bg-slate-50">
                  <td className="py-3 font-mono text-xs">{u.email}</td>
                  <td className="py-3">{u.full_name || '—'}</td>
                  <td className="py-3">
                    <Badge variant={roleBadge[u.role] ?? 'default'}>{u.role}</Badge>
                  </td>
                  <td className="py-3">
                    <Badge variant={u.is_active ? 'success' : 'danger'}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </td>
                  <td className="py-3 text-slate-400 text-xs">{formatDate(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.users?.length && (
            <p className="text-center text-slate-400 py-8">No users found.</p>
          )}
        </div>
      )}

      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

// -------------------------------------------------------
// Main Page
// -------------------------------------------------------

export function AdminProspectsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<'prospects' | 'users'>('prospects');
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [assignTarget, setAssignTarget] = useState<AdminProspect | null>(null);
  const [enrollTarget, setEnrollTarget] = useState<AdminProspect | null>(null);
  const [logsTarget, setLogsTarget] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: prospectsData, isLoading } = useQuery({
    queryKey: ['admin-prospects'],
    queryFn: () => adminProspectsApi.listProspects(),
  });

  const { data: usersData } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminProspectsApi.listUsers(),
  });

  const prospects = prospectsData?.prospects ?? [];
  const users = usersData?.users ?? [];

  const filtered = prospects.filter(p =>
    !search ||
    p.email.toLowerCase().includes(search.toLowerCase()) ||
    p.company_name?.toLowerCase().includes(search.toLowerCase()) ||
    p.full_name?.toLowerCase().includes(search.toLowerCase())
  );

  const getUserName = (id?: string) => {
    if (!id) return null;
    const u = users.find(u => u.user_id === id);
    return u ? (u.full_name || u.email) : id.slice(0, 8) + '…';
  };

  return (
    <div className="flex flex-col h-full">
      <Header
        title="Admin — Prospects & Users"
        subtitle="Create prospects, trigger research, assign to users, and manage accounts"
      />

      <div className="flex-1 overflow-auto p-6">
        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b">
          {(['prospects', 'users'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={clsx(
                'px-4 py-2 text-sm font-medium capitalize border-b-2 -mb-px transition-colors',
                tab === t
                  ? 'border-purple-600 text-purple-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === 'users' ? (
          <Card className="p-6"><UsersTab /></Card>
        ) : (
          <Card className="p-6">
            {/* Toolbar */}
            <div className="flex items-center justify-between mb-4 gap-3">
              <div className="flex items-center gap-2 flex-1 max-w-sm border rounded-lg px-3 py-2">
                <Search className="h-4 w-4 text-slate-400" />
                <input
                  className="flex-1 text-sm bg-transparent outline-none"
                  placeholder="Search prospects…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => qc.invalidateQueries({ queryKey: ['admin-prospects'] })}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
                <Button onClick={() => setShowCreate(true)}>
                  <Plus className="h-4 w-4 mr-2" /> Add Prospect
                </Button>
              </div>
            </div>

            {isLoading ? (
              <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-slate-500">
                      <th className="pb-3 font-medium w-6"></th>
                      <th className="pb-3 font-medium">Email</th>
                      <th className="pb-3 font-medium">Name</th>
                      <th className="pb-3 font-medium">Company</th>
                      <th className="pb-3 font-medium">Research</th>
                      <th className="pb-3 font-medium">Assigned To</th>
                      <th className="pb-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filtered.map(p => (
                      <>
                        <tr key={p.id} className="hover:bg-slate-50">
                          <td className="py-3">
                            <button
                              onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                              className="text-slate-400 hover:text-slate-600"
                            >
                              {expandedId === p.id
                                ? <ChevronDown className="h-4 w-4" />
                                : <ChevronRight className="h-4 w-4" />
                              }
                            </button>
                          </td>
                          <td className="py-3 font-mono text-xs">{p.email}</td>
                          <td className="py-3">{p.full_name || `${p.first_name ?? ''} ${p.last_name ?? ''}`.trim() || '—'}</td>
                          <td className="py-3 text-slate-500">{p.company_name || '—'}</td>
                          <td className="py-3">{researchBadge(p.research_status)}</td>
                          <td className="py-3">
                            {p.assigned_to_user_id ? (
                              <span className="text-xs text-purple-700 bg-purple-50 px-2 py-1 rounded-full">
                                {getUserName(p.assigned_to_user_id)}
                              </span>
                            ) : (
                              <span className="text-xs text-slate-400">Unassigned</span>
                            )}
                          </td>
                          <td className="py-3">
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => setAssignTarget(p)}
                                className="p-1.5 text-slate-400 hover:text-purple-600 hover:bg-purple-50 rounded"
                                title="Assign to user"
                              >
                                <UserPlus className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => setEnrollTarget(p)}
                                className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded"
                                title="Enroll in 3-Point Follow-up"
                              >
                                <Zap className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => setLogsTarget(p.id)}
                                className="p-1.5 text-slate-400 hover:text-green-600 hover:bg-green-50 rounded"
                                title="View sequence logs"
                              >
                                <List className="h-4 w-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                        {expandedId === p.id && (
                          <tr key={`${p.id}-exp`} className="bg-slate-50">
                            <td colSpan={7} className="px-8 py-4">
                              <div className="grid grid-cols-2 gap-4 text-xs text-slate-600">
                                <div><span className="font-medium">Industry:</span> {p.industry || '—'}</div>
                                <div><span className="font-medium">Job Title:</span> {p.job_title || '—'}</div>
                                <div><span className="font-medium">LinkedIn:</span> {p.linkedin_url || '—'}</div>
                                <div><span className="font-medium">Status:</span> {p.status}</div>
                                <div><span className="font-medium">Created:</span> {formatDate(p.created_at)}</div>
                                {p.research_status === 'completed' && p.research_data && (
                                  <div className="col-span-2">
                                    <span className="font-medium">Research Topics:</span>{' '}
                                    {(p.research_data as { topics_discussed?: string[] }).topics_discussed?.join(', ') || 'See full data'}
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    ))}
                  </tbody>
                </table>
                {!filtered.length && (
                  <div className="text-center py-12 text-slate-400">
                    <Users className="h-8 w-8 mx-auto mb-2 opacity-40" />
                    <p>No prospects yet. Click "Add Prospect" to create one.</p>
                  </div>
                )}
              </div>
            )}
          </Card>
        )}
      </div>

      {/* Modals */}
      {showCreate && <CreateProspectModal onClose={() => setShowCreate(false)} />}
      {assignTarget && (
        <AssignModal prospect={assignTarget} users={users} onClose={() => setAssignTarget(null)} />
      )}
      {enrollTarget && <EnrollModal prospect={enrollTarget} onClose={() => setEnrollTarget(null)} />}
      {logsTarget && <LogsPanel prospectId={logsTarget} onClose={() => setLogsTarget(null)} />}
    </div>
  );
}

export default AdminProspectsPage;
