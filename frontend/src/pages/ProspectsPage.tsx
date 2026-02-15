import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Search,
  Upload,
  Download,
  MoreVertical,
  Building,
  ChevronLeft,
  ChevronRight,
  X,
  Loader2,
  Users,
  Trash2,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { clsx } from 'clsx';
import { prospectsApi, type ProspectCreate } from '../api';

export function ProspectsPage() {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedProspects, setSelectedProspects] = useState<string[]>([]);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newProspect, setNewProspect] = useState<ProspectCreate>({ email: '' });

  // Fetch prospects from API
  const { data: prospects = [], isLoading, error } = useQuery({
    queryKey: ['prospects', searchQuery],
    queryFn: () => prospectsApi.list({ search: searchQuery || undefined, limit: 100 }),
  });

  // Create prospect mutation
  const createMutation = useMutation({
    mutationFn: (data: ProspectCreate) => prospectsApi.create(data),
    onSuccess: () => {
      toast.success('Prospect added successfully');
      queryClient.invalidateQueries({ queryKey: ['prospects'] });
      setShowAddModal(false);
      setNewProspect({ email: '' });
    },
    onError: (err: Error) => {
      toast.error(`Failed to add prospect: ${err.message}`);
    },
  });

  // Delete prospect mutation
  const deleteMutation = useMutation({
    mutationFn: (email: string) => prospectsApi.delete(email),
    onSuccess: () => {
      toast.success('Prospect deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['prospects'] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to delete prospect: ${err.message}`);
    },
  });

  // Bulk delete mutation
  const bulkDeleteMutation = useMutation({
    mutationFn: async (emails: string[]) => {
      await Promise.all(emails.map(email => prospectsApi.delete(email)));
    },
    onSuccess: () => {
      toast.success(`${selectedProspects.length} prospects deleted`);
      queryClient.invalidateQueries({ queryKey: ['prospects'] });
      setSelectedProspects([]);
    },
    onError: (err: Error) => {
      toast.error(`Failed to delete prospects: ${err.message}`);
    },
  });

  const filteredProspects = prospects;

  const toggleSelectAll = () => {
    if (selectedProspects.length === filteredProspects.length) {
      setSelectedProspects([]);
    } else {
      setSelectedProspects(filteredProspects.map((p) => p.email));
    }
  };

  const toggleSelect = (email: string) => {
    setSelectedProspects((prev) =>
      prev.includes(email) ? prev.filter((e) => e !== email) : [...prev, email]
    );
  };

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const handleAddProspect = () => {
    if (!newProspect.email) {
      toast.error('Email is required');
      return;
    }
    createMutation.mutate(newProspect);
  };

  const handleBulkDelete = () => {
    if (confirm(`Are you sure you want to delete ${selectedProspects.length} prospects?`)) {
      bulkDeleteMutation.mutate(selectedProspects);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="h-full">
        <Header title="Prospects" subtitle="Loading..." />
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 text-brand-purple animate-spin" />
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-full">
        <Header title="Prospects" subtitle="Error loading prospects" />
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <Users className="h-12 w-12 text-red-300 mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-1">
            Failed to load prospects
          </h3>
          <p className="text-slate-500 mb-4">{(error as Error).message}</p>
          <Button onClick={() => queryClient.invalidateQueries({ queryKey: ['prospects'] })}>
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full">
      <Header
        title="Prospects"
        subtitle={`${prospects.length} total prospects`}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              leftIcon={<Upload className="h-4 w-4" />}
              onClick={() => setShowImportModal(true)}
            >
              Import
            </Button>
            <Button
              variant="outline"
              leftIcon={<Download className="h-4 w-4" />}
              onClick={() => toast.info('Export coming soon')}
            >
              Export
            </Button>
            <Button
              leftIcon={<Plus className="h-4 w-4" />}
              onClick={() => setShowAddModal(true)}
            >
              Add Prospect
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-4">
        {/* Search and Filters */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search prospects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
            />
          </div>

          {selectedProspects.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-brand-purple/5 rounded-lg">
              <span className="text-sm text-brand-purple">
                {selectedProspects.length} selected
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => toast.info('Add to sequence coming soon')}
              >
                Add to Sequence
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-red-600 hover:text-red-700"
                onClick={handleBulkDelete}
                disabled={bulkDeleteMutation.isPending}
              >
                <Trash2 className="h-4 w-4 mr-1" />
                Delete
              </Button>
            </div>
          )}
        </div>

        {/* Prospects Table */}
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={
                        selectedProspects.length === filteredProspects.length &&
                        filteredProspects.length > 0
                      }
                      onChange={toggleSelectAll}
                      className="h-4 w-4 rounded border-slate-300 text-brand-purple focus:ring-brand-purple"
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Contact
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Company
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Industry
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Added
                  </th>
                  <th className="w-10 px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredProspects.map((prospect) => (
                  <tr
                    key={prospect.email}
                    className={clsx(
                      'hover:bg-slate-50 transition-colors',
                      selectedProspects.includes(prospect.email) && 'bg-brand-purple/5'
                    )}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedProspects.includes(prospect.email)}
                        onChange={() => toggleSelect(prospect.email)}
                        className="h-4 w-4 rounded border-slate-300 text-brand-purple focus:ring-brand-purple"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-sm font-medium text-slate-600">
                          {prospect.first_name?.charAt(0) || prospect.email.charAt(0).toUpperCase()}
                          {prospect.last_name?.charAt(0) || ''}
                        </div>
                        <div>
                          <p className="font-medium text-slate-900">
                            {prospect.first_name || prospect.last_name
                              ? `${prospect.first_name || ''} ${prospect.last_name || ''}`.trim()
                              : prospect.email.split('@')[0]}
                          </p>
                          <p className="text-sm text-slate-500">{prospect.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Building className="h-4 w-4 text-slate-400" />
                        <div>
                          <p className="text-sm text-slate-900">{prospect.company_name || '-'}</p>
                          <p className="text-xs text-slate-500">{prospect.title || '-'}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-slate-600">{prospect.industry || '-'}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            prospect.unsubscribed
                              ? 'danger'
                              : prospect.email_status === 'valid'
                              ? 'success'
                              : prospect.email_status === 'invalid'
                              ? 'danger'
                              : 'warning'
                          }
                        >
                          {prospect.unsubscribed
                            ? 'Unsubscribed'
                            : prospect.email_status === 'valid'
                            ? 'Valid'
                            : prospect.email_status === 'invalid'
                            ? 'Invalid'
                            : 'Unknown'}
                        </Badge>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-slate-500">
                        {formatDate(prospect.created_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600"
                        onClick={() => {
                          if (confirm(`Delete ${prospect.email}?`)) {
                            deleteMutation.mutate(prospect.email);
                          }
                        }}
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Empty State */}
          {filteredProspects.length === 0 && (
            <div className="py-12 text-center">
              <Users className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-1">No prospects found</h3>
              <p className="text-slate-500 mb-4">
                {searchQuery ? 'Try adjusting your search' : 'Add your first prospect to get started'}
              </p>
              {!searchQuery && (
                <Button onClick={() => setShowAddModal(true)}>Add Prospect</Button>
              )}
            </div>
          )}

          {/* Pagination */}
          {filteredProspects.length > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200">
              <p className="text-sm text-slate-500">
                Showing 1 to {filteredProspects.length} of {prospects.length} results
              </p>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button variant="outline" size="sm" disabled>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Add Prospect Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-lg">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Add Prospect</h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="p-1 hover:bg-slate-100 rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Email *
                </label>
                <input
                  type="email"
                  value={newProspect.email}
                  onChange={(e) => setNewProspect({ ...newProspect, email: e.target.value })}
                  className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                  placeholder="john@company.com"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    First Name
                  </label>
                  <input
                    type="text"
                    value={newProspect.first_name || ''}
                    onChange={(e) => setNewProspect({ ...newProspect, first_name: e.target.value })}
                    className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                    placeholder="John"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Last Name
                  </label>
                  <input
                    type="text"
                    value={newProspect.last_name || ''}
                    onChange={(e) => setNewProspect({ ...newProspect, last_name: e.target.value })}
                    className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                    placeholder="Smith"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Company
                  </label>
                  <input
                    type="text"
                    value={newProspect.company_name || ''}
                    onChange={(e) => setNewProspect({ ...newProspect, company_name: e.target.value })}
                    className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                    placeholder="Acme Corp"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Title
                  </label>
                  <input
                    type="text"
                    value={newProspect.title || ''}
                    onChange={(e) => setNewProspect({ ...newProspect, title: e.target.value })}
                    className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                    placeholder="VP of Sales"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Industry
                </label>
                <input
                  type="text"
                  value={newProspect.industry || ''}
                  onChange={(e) => setNewProspect({ ...newProspect, industry: e.target.value })}
                  className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple"
                  placeholder="Technology"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button variant="outline" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleAddProspect}
                disabled={createMutation.isPending || !newProspect.email}
              >
                {createMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : null}
                Add Prospect
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-lg">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Import Prospects</h2>
              <button
                onClick={() => setShowImportModal(false)}
                className="p-1 hover:bg-slate-100 rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="border-2 border-dashed border-slate-200 rounded-lg p-8 text-center">
              <Upload className="h-10 w-10 text-slate-400 mx-auto mb-3" />
              <p className="text-slate-600 mb-2">
                Drag and drop your CSV file here
              </p>
              <p className="text-sm text-slate-500 mb-4">or</p>
              <Button variant="outline" onClick={() => toast.info('CSV import coming soon')}>
                Browse Files
              </Button>
            </div>

            <div className="mt-4 p-3 bg-slate-50 rounded-lg">
              <p className="text-sm text-slate-600">
                <strong>Required columns:</strong> email
              </p>
              <p className="text-sm text-slate-500 mt-1">
                Optional: first_name, last_name, title, company_name, industry
              </p>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button variant="outline" onClick={() => setShowImportModal(false)}>
                Cancel
              </Button>
              <Button disabled>Upload & Import</Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

export default ProspectsPage;
