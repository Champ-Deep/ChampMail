import { useAuthStore } from '../store/authStore';

export function usePermissions() {
  const { user } = useAuthStore();
  const role = user?.role;

  const isDataTeam = role === 'data_team';
  const isAdmin = role === 'admin' || role === 'superadmin';

  // Data Team members have read-only access
  const canEdit = !isDataTeam;
  const canCreate = !isDataTeam;
  const canDelete = isAdmin;

  return {
    canEdit,
    canCreate,
    canDelete,
    isDataTeam,
    isAdmin,
  };
}
