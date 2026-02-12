import api from './client';

// ============================================================================
// Types
// ============================================================================

export interface Team {
  id: string;
  name: string;
  owner_id: string;
  max_members: number;
  member_count: number;
  is_owner: boolean;
  is_admin: boolean;
}

export interface TeamMember {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_owner: boolean;
}

export interface TeamInvite {
  id: string;
  email: string;
  role: string;
  token: string;
  invited_by_email: string | null;
  expires_at: string;
  invite_url: string;
}

export interface PendingInvite {
  id: string;
  team_name: string;
  team_id: string;
  role: string;
  token: string;
  expires_at: string;
}

export interface CreateTeamData {
  name: string;
  max_members?: number;
}

export interface UpdateTeamData {
  name?: string;
  max_members?: number;
}

export interface InviteMemberData {
  email: string;
  role?: string;
}

export interface AcceptInviteResponse {
  message: string;
  team: {
    id: string;
    name: string;
    member_count: number;
  };
}

// ============================================================================
// API Client
// ============================================================================

export const teamsApi = {
  // --- Team CRUD ---

  async createTeam(data: CreateTeamData): Promise<Team> {
    const response = await api.post<Team>('/teams', data);
    return response.data;
  },

  async getMyTeam(): Promise<Team | null> {
    const response = await api.get<Team | null>('/teams/my-team');
    return response.data;
  },

  async getTeam(teamId: string): Promise<Team> {
    const response = await api.get<Team>(`/teams/${teamId}`);
    return response.data;
  },

  async updateTeam(teamId: string, data: UpdateTeamData): Promise<Team> {
    const response = await api.put<Team>(`/teams/${teamId}`, data);
    return response.data;
  },

  async deleteTeam(teamId: string): Promise<void> {
    await api.delete(`/teams/${teamId}`);
  },

  // --- Member Management ---

  async getMembers(teamId: string): Promise<TeamMember[]> {
    const response = await api.get<TeamMember[]>(`/teams/${teamId}/members`);
    return response.data;
  },

  async updateMemberRole(teamId: string, memberId: string, role: string): Promise<void> {
    await api.put(`/teams/${teamId}/members/${memberId}/role`, { role });
  },

  async removeMember(teamId: string, memberId: string): Promise<void> {
    await api.delete(`/teams/${teamId}/members/${memberId}`);
  },

  async leaveTeam(teamId: string): Promise<void> {
    await api.post(`/teams/${teamId}/leave`);
  },

  // --- Invitations ---

  async inviteMember(teamId: string, data: InviteMemberData): Promise<TeamInvite> {
    const response = await api.post<TeamInvite>(`/teams/${teamId}/invites`, data);
    return response.data;
  },

  async getPendingInvites(teamId: string): Promise<TeamInvite[]> {
    const response = await api.get<TeamInvite[]>(`/teams/${teamId}/invites`);
    return response.data;
  },

  async revokeInvite(teamId: string, inviteId: string): Promise<void> {
    await api.delete(`/teams/${teamId}/invites/${inviteId}`);
  },

  async acceptInvite(token: string): Promise<AcceptInviteResponse> {
    const response = await api.post<AcceptInviteResponse>('/teams/accept-invite', { token });
    return response.data;
  },

  async getMyInvites(): Promise<PendingInvite[]> {
    const response = await api.get<PendingInvite[]>('/teams/my-invites');
    return response.data;
  },
};

export default teamsApi;
