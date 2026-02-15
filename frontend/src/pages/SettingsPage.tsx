import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  User,
  Mail,
  Server,
  Shield,
  Bell,
  Save,
  Key,
  Users,
  UserPlus,
  Crown,
  Trash2,
  Copy,
  LogOut,
  CheckCircle,
  XCircle,
  Loader2,
  Plus,
  Star,
  Edit2,
  MailPlus,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Button, Input, Badge } from '../components/ui';
import { useAuthStore } from '../store/authStore';
import { teamsApi, emailSettingsApi, emailAccountsApi, authApi } from '../api';
import type { EmailAccount, EmailAccountCreate, EmailAccountUpdate } from '../api';
import type { ProfileUpdate } from '../api/auth';
import { clsx } from 'clsx';

const tabs = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'team', label: 'Team', icon: Users },
  { id: 'accounts', label: 'Email Accounts', icon: MailPlus },
  { id: 'email', label: 'Email Settings', icon: Mail },
  { id: 'smtp', label: 'SMTP / IMAP', icon: Server },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'notifications', label: 'Notifications', icon: Bell },
];

// ============================================================================
// Team Settings Component
// ============================================================================

function TeamSettings() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const [showCreateTeam, setShowCreateTeam] = useState(false);
  const [teamName, setTeamName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('user');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Fetch team data
  const { data: team, isLoading: teamLoading } = useQuery({
    queryKey: ['myTeam'],
    queryFn: () => teamsApi.getMyTeam(),
  });

  const { data: members = [], isLoading: membersLoading } = useQuery({
    queryKey: ['teamMembers', team?.id],
    queryFn: () => teamsApi.getMembers(team!.id),
    enabled: !!team?.id,
  });

  const { data: invites = [] } = useQuery({
    queryKey: ['teamInvites', team?.id],
    queryFn: () => teamsApi.getPendingInvites(team!.id),
    enabled: !!team?.id && team.is_admin,
  });

  // Mutations
  const createTeamMutation = useMutation({
    mutationFn: (name: string) => teamsApi.createTeam({ name }),
    onSuccess: () => {
      toast.success('Team created successfully');
      queryClient.invalidateQueries({ queryKey: ['myTeam'] });
      setShowCreateTeam(false);
      setTeamName('');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create team');
    },
  });

  const inviteMemberMutation = useMutation({
    mutationFn: (data: { email: string; role: string }) =>
      teamsApi.inviteMember(team!.id, data),
    onSuccess: (data) => {
      toast.success(`Invitation sent to ${data.email}`);
      queryClient.invalidateQueries({ queryKey: ['teamInvites'] });
      setInviteEmail('');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to send invitation');
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: string) => teamsApi.removeMember(team!.id, memberId),
    onSuccess: () => {
      toast.success('Member removed from team');
      queryClient.invalidateQueries({ queryKey: ['teamMembers'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to remove member');
    },
  });

  const revokeInviteMutation = useMutation({
    mutationFn: (inviteId: string) => teamsApi.revokeInvite(team!.id, inviteId),
    onSuccess: () => {
      toast.success('Invitation revoked');
      queryClient.invalidateQueries({ queryKey: ['teamInvites'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to revoke invitation');
    },
  });

  const leaveTeamMutation = useMutation({
    mutationFn: () => teamsApi.leaveTeam(team!.id),
    onSuccess: () => {
      toast.success('You have left the team');
      queryClient.invalidateQueries({ queryKey: ['myTeam'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to leave team');
    },
  });

  const deleteTeamMutation = useMutation({
    mutationFn: () => teamsApi.deleteTeam(team!.id),
    onSuccess: () => {
      toast.success('Team deleted');
      queryClient.invalidateQueries({ queryKey: ['myTeam'] });
      setShowDeleteConfirm(false);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete team');
    },
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: string }) =>
      teamsApi.updateMemberRole(team!.id, memberId, role),
    onSuccess: () => {
      toast.success('Role updated');
      queryClient.invalidateQueries({ queryKey: ['teamMembers'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update role');
    },
  });

  const copyInviteLink = (token: string) => {
    const url = `${window.location.origin}/join-team?token=${token}`;
    navigator.clipboard.writeText(url);
    toast.success('Invite link copied to clipboard');
  };

  if (teamLoading) {
    return (
      <Card>
        <div className="p-8 text-center text-slate-500">
          Loading team information...
        </div>
      </Card>
    );
  }

  // No team - show create team UI
  if (!team) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Team Management</CardTitle>
        </CardHeader>
        <div className="space-y-6">
          <div className="text-center py-8">
            <Users className="h-12 w-12 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">
              You're not part of a team yet
            </h3>
            <p className="text-sm text-slate-500 mb-6">
              Create a team to collaborate with your colleagues or wait for an invitation.
            </p>

            {showCreateTeam ? (
              <div className="max-w-sm mx-auto space-y-4">
                <Input
                  label="Team Name"
                  placeholder="e.g. Sales Team"
                  value={teamName}
                  onChange={(e) => setTeamName(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setShowCreateTeam(false)}
                    className="flex-1"
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={() => createTeamMutation.mutate(teamName)}
                    isLoading={createTeamMutation.isPending}
                    disabled={!teamName.trim()}
                    className="flex-1"
                  >
                    Create Team
                  </Button>
                </div>
              </div>
            ) : (
              <Button onClick={() => setShowCreateTeam(true)}>
                <UserPlus className="h-4 w-4 mr-2" />
                Create a Team
              </Button>
            )}
          </div>
        </div>
      </Card>
    );
  }

  // Has team - show team management UI
  return (
    <div className="space-y-6">
      {/* Team Info */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{team.name}</CardTitle>
            <p className="text-sm text-slate-500 mt-1">
              {team.member_count} of {team.max_members} members
            </p>
          </div>
          {team.is_owner && (
            <Badge variant="default">
              <Crown className="h-3 w-3 mr-1" />
              Owner
            </Badge>
          )}
        </CardHeader>
      </Card>

      {/* Members List */}
      <Card>
        <CardHeader>
          <CardTitle>Team Members</CardTitle>
        </CardHeader>
        <div className="divide-y divide-slate-100">
          {membersLoading ? (
            <div className="p-4 text-center text-slate-500">Loading members...</div>
          ) : (
            members.map((member) => (
              <div key={member.id} className="flex items-center justify-between p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-purple/10 text-brand-purple font-medium">
                    {member.email.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">
                      {member.full_name || member.email}
                      {member.is_owner && (
                        <Crown className="h-4 w-4 text-amber-500 inline ml-2" />
                      )}
                    </p>
                    <p className="text-sm text-slate-500">{member.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {team.is_admin && !member.is_owner && (
                    <>
                      <select
                        value={member.role}
                        onChange={(e) =>
                          updateRoleMutation.mutate({
                            memberId: member.id,
                            role: e.target.value,
                          })
                        }
                        className="text-sm border border-slate-300 rounded-lg px-2 py-1"
                      >
                        <option value="user">Member</option>
                        <option value="team_admin">Admin</option>
                      </select>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeMemberMutation.mutate(member.id)}
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </>
                  )}
                  {!team.is_admin && member.email === user?.email && (
                    <Badge variant="default">{member.role}</Badge>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* Invite Members (Admin only) */}
      {team.is_admin && (
        <Card>
          <CardHeader>
            <CardTitle>Invite New Members</CardTitle>
          </CardHeader>
          <div className="space-y-4">
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  placeholder="Email address"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                />
              </div>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="user">Member</option>
                <option value="team_admin">Admin</option>
              </select>
              <Button
                onClick={() =>
                  inviteMemberMutation.mutate({ email: inviteEmail, role: inviteRole })
                }
                isLoading={inviteMemberMutation.isPending}
                disabled={!inviteEmail.trim()}
              >
                <UserPlus className="h-4 w-4 mr-2" />
                Send Invite
              </Button>
            </div>

            {/* Pending Invites */}
            {invites.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-slate-700 mb-2">
                  Pending Invitations
                </h4>
                <div className="space-y-2">
                  {invites.map((invite) => (
                    <div
                      key={invite.id}
                      className="flex items-center justify-between p-3 bg-slate-50 rounded-lg"
                    >
                      <div>
                        <p className="text-sm font-medium text-slate-900">
                          {invite.email}
                        </p>
                        <p className="text-xs text-slate-500">
                          Expires:{' '}
                          {new Date(invite.expires_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => copyInviteLink(invite.token)}
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => revokeInviteMutation.mutate(invite.id)}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Danger Zone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-red-600">Danger Zone</CardTitle>
        </CardHeader>
        <div className="space-y-4">
          {!team.is_owner && (
            <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
              <div>
                <p className="font-medium text-slate-900">Leave Team</p>
                <p className="text-sm text-slate-500">
                  Remove yourself from {team.name}
                </p>
              </div>
              <Button
                variant="outline"
                onClick={() => leaveTeamMutation.mutate()}
                isLoading={leaveTeamMutation.isPending}
              >
                <LogOut className="h-4 w-4 mr-2" />
                Leave Team
              </Button>
            </div>
          )}

          {team.is_owner && (
            <div className="flex items-center justify-between p-4 border border-red-200 bg-red-50 rounded-lg">
              <div>
                <p className="font-medium text-red-900">Delete Team</p>
                <p className="text-sm text-red-600">
                  Permanently delete this team and remove all members
                </p>
              </div>
              {showDeleteConfirm ? (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowDeleteConfirm(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => deleteTeamMutation.mutate()}
                    isLoading={deleteTeamMutation.isPending}
                  >
                    Confirm Delete
                  </Button>
                </div>
              ) : (
                <Button
                  variant="danger"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Team
                </Button>
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

// ============================================================================
// Email Accounts Component (Multiple Accounts)
// ============================================================================

function EmailAccountsSettings() {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingAccount, setEditingAccount] = useState<EmailAccount | null>(null);

  // Form state
  const [formData, setFormData] = useState<EmailAccountCreate>({
    name: '',
    email: '',
    smtp_host: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    smtp_use_tls: true,
    imap_host: '',
    imap_port: 993,
    imap_username: '',
    imap_password: '',
    imap_use_ssl: true,
    imap_mailbox: 'INBOX',
    from_name: '',
    is_default: false,
  });

  // Fetch accounts
  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['emailAccounts'],
    queryFn: () => emailAccountsApi.list(),
  });

  // Reset form
  const resetForm = () => {
    setFormData({
      name: '',
      email: '',
      smtp_host: '',
      smtp_port: 587,
      smtp_username: '',
      smtp_password: '',
      smtp_use_tls: true,
      imap_host: '',
      imap_port: 993,
      imap_username: '',
      imap_password: '',
      imap_use_ssl: true,
      imap_mailbox: 'INBOX',
      from_name: '',
      is_default: false,
    });
    setShowAddForm(false);
    setEditingAccount(null);
  };

  // Populate form for editing
  const startEdit = (account: EmailAccount) => {
    setEditingAccount(account);
    setFormData({
      name: account.name,
      email: account.email,
      smtp_host: account.smtp_host || '',
      smtp_port: account.smtp_port,
      smtp_username: account.smtp_username || '',
      smtp_password: '',
      smtp_use_tls: account.smtp_use_tls,
      imap_host: account.imap_host || '',
      imap_port: account.imap_port,
      imap_username: account.imap_username || '',
      imap_password: '',
      imap_use_ssl: account.imap_use_ssl,
      imap_mailbox: account.imap_mailbox || 'INBOX',
      from_name: account.from_name || '',
      is_default: account.is_default,
    });
    setShowAddForm(true);
  };

  // Create account mutation
  const createMutation = useMutation({
    mutationFn: (data: EmailAccountCreate) => emailAccountsApi.create(data),
    onSuccess: () => {
      toast.success('Email account added successfully');
      queryClient.invalidateQueries({ queryKey: ['emailAccounts'] });
      resetForm();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add account');
    },
  });

  // Update account mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: EmailAccountUpdate }) =>
      emailAccountsApi.update(id, data),
    onSuccess: () => {
      toast.success('Email account updated successfully');
      queryClient.invalidateQueries({ queryKey: ['emailAccounts'] });
      resetForm();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update account');
    },
  });

  // Delete account mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => emailAccountsApi.delete(id),
    onSuccess: () => {
      toast.success('Email account deleted');
      queryClient.invalidateQueries({ queryKey: ['emailAccounts'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete account');
    },
  });

  // Set default mutation
  const setDefaultMutation = useMutation({
    mutationFn: (id: string) => emailAccountsApi.setDefault(id),
    onSuccess: () => {
      toast.success('Default account updated');
      queryClient.invalidateQueries({ queryKey: ['emailAccounts'] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to set default');
    },
  });

  // Test SMTP mutation
  const testSmtpMutation = useMutation({
    mutationFn: (id: string) => emailAccountsApi.testSmtp(id),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(data.message);
        queryClient.invalidateQueries({ queryKey: ['emailAccounts'] });
      } else {
        toast.error(data.message);
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'SMTP test failed');
    },
  });

  // Test IMAP mutation
  const testImapMutation = useMutation({
    mutationFn: (id: string) => emailAccountsApi.testImap(id),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(data.message);
        queryClient.invalidateQueries({ queryKey: ['emailAccounts'] });
      } else {
        toast.error(data.message);
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'IMAP test failed');
    },
  });

  const handleSubmit = () => {
    if (editingAccount) {
      updateMutation.mutate({ id: editingAccount.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <div className="p-8 text-center text-slate-500">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
          Loading email accounts...
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Add Button */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Email Accounts</CardTitle>
            <p className="text-sm text-slate-500 mt-1">
              Manage multiple email accounts for sending and receiving emails
            </p>
          </div>
          <Button onClick={() => { resetForm(); setShowAddForm(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Add Account
          </Button>
        </CardHeader>
      </Card>

      {/* Account List */}
      {accounts.length === 0 && !showAddForm ? (
        <Card>
          <div className="p-8 text-center">
            <MailPlus className="h-12 w-12 text-slate-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-2">
              No email accounts configured
            </h3>
            <p className="text-sm text-slate-500 mb-6">
              Add your first email account to start sending and receiving emails.
            </p>
            <Button onClick={() => setShowAddForm(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Add Your First Account
            </Button>
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {accounts.map((account) => (
            <Card key={account.id}>
              <div className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-purple/10 text-brand-purple font-medium">
                      {account.email.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-slate-900">{account.name}</p>
                        {account.is_default && (
                          <Badge variant="default" className="flex items-center gap-1">
                            <Star className="h-3 w-3" />
                            Default
                          </Badge>
                        )}
                        {!account.is_active && (
                          <Badge variant="warning">Disabled</Badge>
                        )}
                      </div>
                      <p className="text-sm text-slate-500">{account.email}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {!account.is_default && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDefaultMutation.mutate(account.id)}
                        title="Set as default"
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => startEdit(account)}
                      title="Edit"
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteMutation.mutate(account.id)}
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                </div>

                {/* Connection Status */}
                <div className="mt-4 flex items-center gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500">SMTP:</span>
                    {account.smtp_verified ? (
                      <Badge variant="success" className="flex items-center gap-1">
                        <CheckCircle className="h-3 w-3" />
                        Verified
                      </Badge>
                    ) : (
                      <Badge variant="warning" className="flex items-center gap-1">
                        <XCircle className="h-3 w-3" />
                        Not Verified
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => testSmtpMutation.mutate(account.id)}
                      disabled={testSmtpMutation.isPending}
                      className="text-xs"
                    >
                      {testSmtpMutation.isPending ? 'Testing...' : 'Test'}
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500">IMAP:</span>
                    {account.imap_verified ? (
                      <Badge variant="success" className="flex items-center gap-1">
                        <CheckCircle className="h-3 w-3" />
                        Verified
                      </Badge>
                    ) : (
                      <Badge variant="warning" className="flex items-center gap-1">
                        <XCircle className="h-3 w-3" />
                        Not Verified
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => testImapMutation.mutate(account.id)}
                      disabled={testImapMutation.isPending}
                      className="text-xs"
                    >
                      {testImapMutation.isPending ? 'Testing...' : 'Test'}
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Add/Edit Form */}
      {showAddForm && (
        <Card>
          <CardHeader>
            <CardTitle>{editingAccount ? 'Edit Account' : 'Add New Account'}</CardTitle>
          </CardHeader>
          <div className="space-y-6">
            {/* Basic Info */}
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Account Name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g. Work Gmail"
              />
              <Input
                label="Email Address"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="you@example.com"
              />
            </div>

            <Input
              label="From Name"
              value={formData.from_name || ''}
              onChange={(e) => setFormData({ ...formData, from_name: e.target.value })}
              placeholder="Your Name"
              helperText="Name recipients will see"
            />

            {/* SMTP Settings */}
            <div className="border-t pt-4">
              <h4 className="font-medium text-slate-900 mb-4">SMTP Settings (Outbound)</h4>
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="SMTP Host"
                  value={formData.smtp_host || ''}
                  onChange={(e) => setFormData({ ...formData, smtp_host: e.target.value })}
                  placeholder="smtp.gmail.com"
                />
                <Input
                  label="SMTP Port"
                  type="number"
                  value={formData.smtp_port?.toString() || '587'}
                  onChange={(e) => setFormData({ ...formData, smtp_port: parseInt(e.target.value) || 587 })}
                  placeholder="587"
                />
              </div>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <Input
                  label="SMTP Username"
                  value={formData.smtp_username || ''}
                  onChange={(e) => setFormData({ ...formData, smtp_username: e.target.value })}
                  placeholder="you@example.com"
                />
                <Input
                  label="SMTP Password"
                  type="password"
                  value={formData.smtp_password || ''}
                  onChange={(e) => setFormData({ ...formData, smtp_password: e.target.value })}
                  placeholder={editingAccount?.smtp_has_password ? '••••••••' : 'App password'}
                  helperText={editingAccount?.smtp_has_password ? 'Leave blank to keep existing' : ''}
                />
              </div>
              <div className="flex items-center gap-2 mt-4">
                <input
                  type="checkbox"
                  id="smtp-tls"
                  checked={formData.smtp_use_tls}
                  onChange={(e) => setFormData({ ...formData, smtp_use_tls: e.target.checked })}
                  className="h-4 w-4 rounded border-slate-300 text-brand-purple"
                />
                <label htmlFor="smtp-tls" className="text-sm text-slate-700">
                  Use STARTTLS (recommended for port 587)
                </label>
              </div>
            </div>

            {/* IMAP Settings */}
            <div className="border-t pt-4">
              <h4 className="font-medium text-slate-900 mb-4">IMAP Settings (Inbound)</h4>
              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="IMAP Host"
                  value={formData.imap_host || ''}
                  onChange={(e) => setFormData({ ...formData, imap_host: e.target.value })}
                  placeholder="imap.gmail.com"
                />
                <Input
                  label="IMAP Port"
                  type="number"
                  value={formData.imap_port?.toString() || '993'}
                  onChange={(e) => setFormData({ ...formData, imap_port: parseInt(e.target.value) || 993 })}
                  placeholder="993"
                />
              </div>
              <div className="grid grid-cols-2 gap-4 mt-4">
                <Input
                  label="IMAP Username"
                  value={formData.imap_username || ''}
                  onChange={(e) => setFormData({ ...formData, imap_username: e.target.value })}
                  placeholder="you@example.com"
                />
                <Input
                  label="IMAP Password"
                  type="password"
                  value={formData.imap_password || ''}
                  onChange={(e) => setFormData({ ...formData, imap_password: e.target.value })}
                  placeholder={editingAccount?.imap_has_password ? '••••••••' : 'App password'}
                  helperText={editingAccount?.imap_has_password ? 'Leave blank to keep existing' : ''}
                />
              </div>
              <div className="flex items-center gap-2 mt-4">
                <input
                  type="checkbox"
                  id="imap-ssl"
                  checked={formData.imap_use_ssl}
                  onChange={(e) => setFormData({ ...formData, imap_use_ssl: e.target.checked })}
                  className="h-4 w-4 rounded border-slate-300 text-brand-purple"
                />
                <label htmlFor="imap-ssl" className="text-sm text-slate-700">
                  Use SSL/TLS (recommended for port 993)
                </label>
              </div>
            </div>

            {/* Default checkbox */}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is-default"
                checked={formData.is_default}
                onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                className="h-4 w-4 rounded border-slate-300 text-brand-purple"
              />
              <label htmlFor="is-default" className="text-sm text-slate-700">
                Set as default sending account
              </label>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t">
              <Button variant="outline" onClick={resetForm}>
                Cancel
              </Button>
              <Button
                onClick={handleSubmit}
                isLoading={createMutation.isPending || updateMutation.isPending}
                disabled={!formData.name || !formData.email}
              >
                <Save className="h-4 w-4 mr-2" />
                {editingAccount ? 'Update Account' : 'Add Account'}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// SMTP/IMAP Settings Component
// ============================================================================

function SmtpImapSettings() {
  const queryClient = useQueryClient();

  // Ethereal email defaults for testing
  const ETHEREAL_DEFAULTS = {
    host: 'smtp.ethereal.email',
    imapHost: 'imap.ethereal.email',
    username: 'trent.davis25@ethereal.email',
    password: 'HNJ7R9H9bf231XvnSQ',
  };

  // Form state - prepopulated with Ethereal defaults
  const [smtpHost, setSmtpHost] = useState(ETHEREAL_DEFAULTS.host);
  const [smtpPort, setSmtpPort] = useState('587');
  const [smtpUsername, setSmtpUsername] = useState(ETHEREAL_DEFAULTS.username);
  const [smtpPassword, setSmtpPassword] = useState(ETHEREAL_DEFAULTS.password);
  const [smtpUseTls, setSmtpUseTls] = useState(true);

  const [imapHost, setImapHost] = useState(ETHEREAL_DEFAULTS.imapHost);
  const [imapPort, setImapPort] = useState('993');
  const [imapUsername, setImapUsername] = useState(ETHEREAL_DEFAULTS.username);
  const [imapPassword, setImapPassword] = useState(ETHEREAL_DEFAULTS.password);
  const [imapUseSsl, setImapUseSsl] = useState(true);
  const [imapMailbox, setImapMailbox] = useState('INBOX');

  const [fromEmail, setFromEmail] = useState(ETHEREAL_DEFAULTS.username);
  const [fromName, setFromName] = useState('Trent Davis');
  const [replyToEmail, setReplyToEmail] = useState('');

  // Fetch current settings
  const { data: settings, isLoading } = useQuery({
    queryKey: ['emailSettings'],
    queryFn: () => emailSettingsApi.get(),
  });

  // Populate form when settings load
  useEffect(() => {
    if (settings) {
      setSmtpHost(settings.smtp_host || '');
      setSmtpPort(String(settings.smtp_port || 587));
      setSmtpUsername(settings.smtp_username || '');
      setSmtpUseTls(settings.smtp_use_tls ?? true);

      setImapHost(settings.imap_host || '');
      setImapPort(String(settings.imap_port || 993));
      setImapUsername(settings.imap_username || '');
      setImapUseSsl(settings.imap_use_ssl ?? true);
      setImapMailbox(settings.imap_mailbox || 'INBOX');

      setFromEmail(settings.from_email || '');
      setFromName(settings.from_name || '');
      setReplyToEmail(settings.reply_to_email || '');
    }
  }, [settings]);

  // Save settings mutation
  const saveMutation = useMutation({
    mutationFn: () => emailSettingsApi.update({
      smtp: {
        host: smtpHost || undefined,
        port: parseInt(smtpPort) || 587,
        username: smtpUsername || undefined,
        password: smtpPassword || undefined,
        use_tls: smtpUseTls,
      },
      imap: {
        host: imapHost || undefined,
        port: parseInt(imapPort) || 993,
        username: imapUsername || undefined,
        password: imapPassword || undefined,
        use_ssl: imapUseSsl,
        mailbox: imapMailbox || 'INBOX',
      },
      sender: {
        from_email: fromEmail || undefined,
        from_name: fromName || undefined,
        reply_to_email: replyToEmail || undefined,
      },
    }),
    onSuccess: () => {
      toast.success('Email settings saved successfully');
      queryClient.invalidateQueries({ queryKey: ['emailSettings'] });
      // Clear password fields after save
      setSmtpPassword('');
      setImapPassword('');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to save settings');
    },
  });

  // Test SMTP mutation
  const testSmtpMutation = useMutation({
    mutationFn: () => emailSettingsApi.testSmtp(),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(data.message);
        queryClient.invalidateQueries({ queryKey: ['emailSettings'] });
      } else {
        toast.error(data.message);
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'SMTP test failed');
    },
  });

  // Test IMAP mutation
  const testImapMutation = useMutation({
    mutationFn: () => emailSettingsApi.testImap(),
    onSuccess: (data) => {
      if (data.success) {
        toast.success(data.message);
        queryClient.invalidateQueries({ queryKey: ['emailSettings'] });
      } else {
        toast.error(data.message);
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'IMAP test failed');
    },
  });

  if (isLoading) {
    return (
      <Card>
        <div className="p-8 text-center text-slate-500">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
          Loading email settings...
        </div>
      </Card>
    );
  }

  const smtpVerified = settings?.smtp_verified || false;
  const imapVerified = settings?.imap_verified || false;

  return (
    <div className="space-y-6">
      {/* Sender Identity */}
      <Card>
        <CardHeader>
          <CardTitle>Sender Identity</CardTitle>
        </CardHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="From Name"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder="ChampMail"
              helperText="Name recipients will see"
            />
            <Input
              label="From Email"
              type="email"
              value={fromEmail}
              onChange={(e) => setFromEmail(e.target.value)}
              placeholder="noreply@yourdomain.com"
            />
          </div>
          <Input
            label="Reply-To Email"
            type="email"
            value={replyToEmail}
            onChange={(e) => setReplyToEmail(e.target.value)}
            placeholder="replies@yourdomain.com"
            helperText="Where replies will be sent"
          />
        </div>
      </Card>

      {/* SMTP Settings */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>SMTP Settings (Outbound)</CardTitle>
            <p className="text-sm text-slate-500 mt-1">
              Configure your mail server for sending emails
            </p>
          </div>
          {smtpVerified ? (
            <Badge variant="success" className="flex items-center gap-1">
              <CheckCircle className="h-3 w-3" />
              Verified
            </Badge>
          ) : (
            <Badge variant="warning" className="flex items-center gap-1">
              <XCircle className="h-3 w-3" />
              Not Verified
            </Badge>
          )}
        </CardHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="SMTP Host"
              value={smtpHost}
              onChange={(e) => setSmtpHost(e.target.value)}
              placeholder="smtp.yourdomain.com"
            />
            <Input
              label="SMTP Port"
              value={smtpPort}
              onChange={(e) => setSmtpPort(e.target.value)}
              placeholder="587"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Username"
              value={smtpUsername}
              onChange={(e) => setSmtpUsername(e.target.value)}
              placeholder="user@yourdomain.com"
            />
            <Input
              label="Password"
              type="password"
              value={smtpPassword}
              onChange={(e) => setSmtpPassword(e.target.value)}
              placeholder={settings?.smtp_has_password ? '••••••••' : 'Enter password'}
              helperText={settings?.smtp_has_password ? 'Leave blank to keep existing password' : ''}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="smtp-tls"
              checked={smtpUseTls}
              onChange={(e) => setSmtpUseTls(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-brand-purple"
            />
            <label htmlFor="smtp-tls" className="text-sm text-slate-700">
              Use STARTTLS encryption (recommended for port 587)
            </label>
          </div>

          <div className="pt-2">
            <Button
              variant="outline"
              onClick={() => testSmtpMutation.mutate()}
              isLoading={testSmtpMutation.isPending}
              disabled={!smtpHost || !smtpUsername}
            >
              {testSmtpMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Testing...
                </>
              ) : (
                'Test SMTP Connection'
              )}
            </Button>
            {settings?.smtp_verified_at && (
              <p className="text-xs text-slate-500 mt-2">
                Last verified: {new Date(settings.smtp_verified_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* IMAP Settings */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>IMAP Settings (Inbound)</CardTitle>
            <p className="text-sm text-slate-500 mt-1">
              Configure IMAP for reply detection
            </p>
          </div>
          {imapVerified ? (
            <Badge variant="success" className="flex items-center gap-1">
              <CheckCircle className="h-3 w-3" />
              Verified
            </Badge>
          ) : (
            <Badge variant="warning" className="flex items-center gap-1">
              <XCircle className="h-3 w-3" />
              Not Verified
            </Badge>
          )}
        </CardHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="IMAP Host"
              value={imapHost}
              onChange={(e) => setImapHost(e.target.value)}
              placeholder="imap.yourdomain.com"
            />
            <Input
              label="IMAP Port"
              value={imapPort}
              onChange={(e) => setImapPort(e.target.value)}
              placeholder="993"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Username"
              value={imapUsername}
              onChange={(e) => setImapUsername(e.target.value)}
              placeholder="user@yourdomain.com"
            />
            <Input
              label="Password"
              type="password"
              value={imapPassword}
              onChange={(e) => setImapPassword(e.target.value)}
              placeholder={settings?.imap_has_password ? '••••••••' : 'Enter password'}
              helperText={settings?.imap_has_password ? 'Leave blank to keep existing password' : ''}
            />
          </div>

          <Input
            label="Mailbox"
            value={imapMailbox}
            onChange={(e) => setImapMailbox(e.target.value)}
            placeholder="INBOX"
            helperText="Mailbox to monitor for replies"
          />

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="imap-ssl"
              checked={imapUseSsl}
              onChange={(e) => setImapUseSsl(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-brand-purple"
            />
            <label htmlFor="imap-ssl" className="text-sm text-slate-700">
              Use SSL/TLS encryption (recommended for port 993)
            </label>
          </div>

          <div className="pt-2">
            <Button
              variant="outline"
              onClick={() => testImapMutation.mutate()}
              isLoading={testImapMutation.isPending}
              disabled={!imapHost || !imapUsername}
            >
              {testImapMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Testing...
                </>
              ) : (
                'Test IMAP Connection'
              )}
            </Button>
            {settings?.imap_verified_at && (
              <p className="text-xs text-slate-500 mt-2">
                Last verified: {new Date(settings.imap_verified_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button
          onClick={() => saveMutation.mutate()}
          isLoading={saveMutation.isPending}
        >
          <Save className="h-4 w-4 mr-2" />
          Save All Settings
        </Button>
      </div>
    </div>
  );
}

// ============================================================================
// Main Settings Page Component
// ============================================================================

export function SettingsPage() {
  const { user, fetchUser } = useAuthStore();
  const [activeTab, setActiveTab] = useState('profile');

  // Profile form state
  const [profileName, setProfileName] = useState(user?.full_name || '');
  const [profileTitle, setProfileTitle] = useState(user?.job_title || '');

  // Sync form when user data changes
  useEffect(() => {
    if (user) {
      setProfileName(user.full_name || '');
      setProfileTitle(user.job_title || '');
    }
  }, [user]);

  // Stub save for other tabs (security, email, notifications)
  const [isSaving, setIsSaving] = useState(false);
  const handleSave = async () => {
    setIsSaving(true);
    setTimeout(() => setIsSaving(false), 1000);
  };

  const profileMutation = useMutation({
    mutationFn: (data: ProfileUpdate) => authApi.updateProfile(data),
    onSuccess: () => {
      toast.success('Profile updated successfully');
      fetchUser(); // Refresh user in auth store
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update profile');
    },
  });

  const handleProfileSave = () => {
    profileMutation.mutate({
      full_name: profileName,
      job_title: profileTitle,
    });
  };

  return (
    <div className="h-full">
      <Header
        title="Settings"
        subtitle="Manage your account and preferences"
      />

      <div className="p-6">
        <div className="flex gap-6">
          {/* Sidebar */}
          <div className="w-56 shrink-0">
            <nav className="space-y-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                    activeTab === tab.id
                      ? 'bg-brand-purple/5 text-brand-purple'
                      : 'text-slate-600 hover:bg-slate-100'
                  )}
                >
                  <tab.icon className="h-5 w-5" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 max-w-2xl">
            {activeTab === 'profile' && (
              <Card>
                <CardHeader>
                  <CardTitle>Profile Settings</CardTitle>
                </CardHeader>

                <div className="space-y-6">
                  <div className="flex items-center gap-4">
                    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-purple text-xl font-bold text-white">
                      {user?.email?.charAt(0).toUpperCase() || 'U'}
                    </div>
                    <div>
                      <Button variant="outline" size="sm">
                        Change Avatar
                      </Button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label="Full Name"
                      value={profileName}
                      onChange={(e) => setProfileName(e.target.value)}
                      placeholder="Your name"
                    />
                    <Input
                      label="Email"
                      type="email"
                      defaultValue={user?.email || ''}
                      disabled
                      helperText="Contact support to change email"
                    />
                  </div>

                  <Input
                    label="Job Title"
                    value={profileTitle}
                    onChange={(e) => setProfileTitle(e.target.value)}
                    placeholder="e.g. Sales Manager"
                  />

                  <div className="pt-4 border-t flex justify-end">
                    <Button onClick={handleProfileSave} isLoading={profileMutation.isPending}>
                      <Save className="h-4 w-4 mr-2" />
                      Save Changes
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'team' && (
              <TeamSettings />
            )}

            {activeTab === 'accounts' && (
              <EmailAccountsSettings />
            )}

            {activeTab === 'email' && (
              <Card>
                <CardHeader>
                  <CardTitle>Email Settings</CardTitle>
                </CardHeader>

                <div className="space-y-6">
                  <Input
                    label="From Name"
                    defaultValue="ChampMail"
                    helperText="Name recipients will see in their inbox"
                  />

                  <Input
                    label="From Email"
                    type="email"
                    defaultValue="noreply@yourdomain.com"
                    helperText="Must be verified in your mail server"
                  />

                  <Input
                    label="Reply-To Email"
                    type="email"
                    defaultValue="replies@yourdomain.com"
                    helperText="Where replies will be sent"
                  />

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Email Signature
                    </label>
                    <textarea
                      className="w-full h-24 px-3 py-2 rounded-lg border border-slate-300 text-sm resize-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                      placeholder="Your email signature..."
                    />
                  </div>

                  <div className="pt-4 border-t flex justify-end">
                    <Button onClick={handleSave} isLoading={isSaving}>
                      <Save className="h-4 w-4 mr-2" />
                      Save Changes
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'smtp' && (
              <SmtpImapSettings />
            )}

            {activeTab === 'security' && (
              <Card>
                <CardHeader>
                  <CardTitle>Security Settings</CardTitle>
                </CardHeader>

                <div className="space-y-6">
                  <div>
                    <h4 className="font-medium text-slate-900 mb-3">Change Password</h4>
                    <div className="space-y-4">
                      <Input
                        label="Current Password"
                        type="password"
                      />
                      <Input
                        label="New Password"
                        type="password"
                      />
                      <Input
                        label="Confirm New Password"
                        type="password"
                      />
                    </div>
                  </div>

                  <hr />

                  <div>
                    <h4 className="font-medium text-slate-900 mb-3">API Keys</h4>
                    <p className="text-sm text-slate-500 mb-4">
                      Manage API keys for external integrations
                    </p>
                    <Button variant="outline" leftIcon={<Key className="h-4 w-4" />}>
                      Generate New API Key
                    </Button>
                  </div>

                  <div className="pt-4 border-t flex justify-end">
                    <Button onClick={handleSave} isLoading={isSaving}>
                      <Save className="h-4 w-4 mr-2" />
                      Save Changes
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {activeTab === 'notifications' && (
              <Card>
                <CardHeader>
                  <CardTitle>Notification Preferences</CardTitle>
                </CardHeader>

                <div className="space-y-4">
                  {[
                    { id: 'replies', label: 'Email Replies', description: 'Get notified when prospects reply' },
                    { id: 'bounces', label: 'Bounces', description: 'Alert when emails bounce' },
                    { id: 'sequence', label: 'Sequence Complete', description: 'When a prospect completes a sequence' },
                    { id: 'daily', label: 'Daily Summary', description: 'Daily digest of campaign performance' },
                  ].map((item) => (
                    <div key={item.id} className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
                      <div>
                        <p className="font-medium text-slate-900">{item.label}</p>
                        <p className="text-sm text-slate-500">{item.description}</p>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" className="sr-only peer" defaultChecked />
                        <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-brand-purple/30 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand-purple"></div>
                      </label>
                    </div>
                  ))}

                  <div className="pt-4 flex justify-end">
                    <Button onClick={handleSave} isLoading={isSaving}>
                      <Save className="h-4 w-4 mr-2" />
                      Save Preferences
                    </Button>
                  </div>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsPage;
