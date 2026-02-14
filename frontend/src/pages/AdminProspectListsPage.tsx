import { useState, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Upload,
  FileText,
  Trash2,
  Play,
  RefreshCw,
  Loader2,
  FolderOpen,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  ChevronDown,
  X,
  Users,
  FileSpreadsheet,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { clsx } from 'clsx';
import { useAuthStore } from '../store/authStore';
import {
  adminApi,
  type ProspectListItem,
  type ProspectListStatus,
} from '../api/admin';

// ============================================================
// Helpers
// ============================================================

function formatDate(dateString: string | undefined | null): string {
  if (!dateString) return 'N/A';
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function statusBadge(status: ProspectListStatus) {
  const map: Record<
    ProspectListStatus,
    { variant: 'default' | 'success' | 'warning' | 'danger' | 'info'; icon: React.ReactNode; label: string }
  > = {
    pending: {
      variant: 'warning',
      icon: <Clock className="h-3 w-3 mr-1" />,
      label: 'Pending',
    },
    processing: {
      variant: 'info',
      icon: <RefreshCw className="h-3 w-3 mr-1 animate-spin" />,
      label: 'Processing',
    },
    completed: {
      variant: 'success',
      icon: <CheckCircle2 className="h-3 w-3 mr-1" />,
      label: 'Completed',
    },
    failed: {
      variant: 'danger',
      icon: <XCircle className="h-3 w-3 mr-1" />,
      label: 'Failed',
    },
  };
  const cfg = map[status] || map.pending;
  return (
    <Badge variant={cfg.variant}>
      <span className="inline-flex items-center">
        {cfg.icon}
        {cfg.label}
      </span>
    </Badge>
  );
}

// ============================================================
// Drag-and-Drop Upload Component
// ============================================================

interface FileUploadZoneProps {
  onFileSelected: (file: File) => void;
  isUploading: boolean;
}

function FileUploadZone({ onFileSelected, isUploading }: FileUploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        const file = files[0];
        if (
          file.type === 'text/csv' ||
          file.name.endsWith('.csv') ||
          file.type ===
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
          file.name.endsWith('.xlsx')
        ) {
          onFileSelected(file);
        } else {
          toast.error('Please upload a CSV or XLSX file');
        }
      }
    },
    [onFileSelected]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileSelected(file);
      }
      // Reset input so same file can be selected again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    },
    [onFileSelected]
  );

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={clsx(
        'relative border-2 border-dashed rounded-xl p-10 text-center transition-all duration-200 cursor-pointer',
        isDragOver
          ? 'border-blue-400 bg-blue-50 scale-[1.01]'
          : 'border-slate-300 bg-slate-50 hover:border-slate-400 hover:bg-white'
      )}
      onClick={() => fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.xlsx"
        onChange={handleFileInput}
        className="hidden"
      />

      {isUploading ? (
        <div className="flex flex-col items-center">
          <Loader2 className="h-10 w-10 text-blue-500 animate-spin mb-3" />
          <p className="text-sm font-medium text-slate-700">
            Uploading prospect list...
          </p>
          <p className="text-xs text-slate-500 mt-1">
            This may take a moment for large files
          </p>
        </div>
      ) : (
        <div className="flex flex-col items-center">
          <div className="h-14 w-14 rounded-full bg-blue-100 flex items-center justify-center mb-4">
            <Upload className="h-6 w-6 text-blue-600" />
          </div>
          <p className="text-sm font-medium text-slate-700 mb-1">
            {isDragOver
              ? 'Drop your file here'
              : 'Drag and drop your CSV file here'}
          </p>
          <p className="text-xs text-slate-500 mb-4">or click to browse</p>
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
          >
            <FileSpreadsheet className="h-4 w-4 mr-1.5" />
            Browse Files
          </Button>
          <p className="text-xs text-slate-400 mt-4">
            Accepted: .csv, .xlsx -- Required column: email
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Main Page Component
// ============================================================

export function AdminProspectListsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [expandedListId, setExpandedListId] = useState<string | null>(null);

  // Check role-based access
  const allowedRoles = ['admin', 'data_team', 'superadmin'];
  const userRole = user?.role || '';
  const hasAccess = allowedRoles.includes(userRole);

  // ----------------------------------------------------------
  // Queries
  // ----------------------------------------------------------

  const {
    data: prospectLists = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ['admin', 'prospect-lists'],
    queryFn: () => adminApi.getProspectLists(),
    enabled: hasAccess,
    refetchInterval: (query) => {
      // Auto-refresh when any list is processing
      const lists = query.state.data as ProspectListItem[] | undefined;
      const hasProcessing = lists?.some((l) => l.status === 'processing');
      return hasProcessing ? 5000 : false;
    },
  });

  // ----------------------------------------------------------
  // Mutations
  // ----------------------------------------------------------

  const uploadMutation = useMutation({
    mutationFn: (file: File) => adminApi.uploadProspectList(file),
    onSuccess: (data) => {
      toast.success(`Uploaded "${data.file_name}" with ${data.total_rows} rows`);
      queryClient.invalidateQueries({ queryKey: ['admin', 'prospect-lists'] });
      setShowUploadModal(false);
    },
    onError: (err: Error) => {
      toast.error(`Upload failed: ${err.message}`);
    },
  });

  const processMutation = useMutation({
    mutationFn: (id: string) => adminApi.processProspectList(id),
    onSuccess: () => {
      toast.success('Processing started');
      queryClient.invalidateQueries({ queryKey: ['admin', 'prospect-lists'] });
    },
    onError: (err: Error) => {
      toast.error(`Processing failed: ${err.message}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteProspectList(id),
    onSuccess: () => {
      toast.success('Prospect list deleted');
      queryClient.invalidateQueries({ queryKey: ['admin', 'prospect-lists'] });
    },
    onError: (err: Error) => {
      toast.error(`Delete failed: ${err.message}`);
    },
  });

  // ----------------------------------------------------------
  // Access denied
  // ----------------------------------------------------------

  if (!hasAccess) {
    return (
      <div className="h-full">
        <Header title="Prospect Lists" subtitle="Admin access required" />
        <div className="flex flex-col items-center justify-center h-[calc(100vh-8rem)]">
          <div className="h-16 w-16 rounded-full bg-red-100 flex items-center justify-center mb-4">
            <AlertCircle className="h-8 w-8 text-red-500" />
          </div>
          <h2 className="text-xl font-semibold text-slate-900 mb-2">
            Access Denied
          </h2>
          <p className="text-slate-500 max-w-md text-center">
            You need admin or data team privileges to access prospect list
            management. Contact your administrator for access.
          </p>
          <p className="text-xs text-slate-400 mt-3">
            Current role: <span className="font-mono">{userRole || 'none'}</span>
          </p>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------------
  // Loading
  // ----------------------------------------------------------

  if (isLoading) {
    return (
      <div className="h-full">
        <Header title="Prospect Lists" subtitle="Loading..." />
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
        </div>
      </div>
    );
  }

  // ----------------------------------------------------------
  // Error
  // ----------------------------------------------------------

  if (error) {
    return (
      <div className="h-full">
        <Header title="Prospect Lists" subtitle="Error" />
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <AlertCircle className="h-12 w-12 text-red-300 mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-1">
            Failed to load prospect lists
          </h3>
          <p className="text-slate-500 mb-4">{(error as Error).message}</p>
          <Button
            onClick={() =>
              queryClient.invalidateQueries({
                queryKey: ['admin', 'prospect-lists'],
              })
            }
          >
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------------
  // Stats
  // ----------------------------------------------------------

  const totalProspects = prospectLists.reduce(
    (sum, l) => sum + (l.total_prospects || 0),
    0
  );
  const processingCount = prospectLists.filter(
    (l) => l.status === 'processing'
  ).length;

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------

  return (
    <div className="h-full">
      <Header
        title="Prospect Lists"
        subtitle={`${prospectLists.length} lists -- ${totalProspects.toLocaleString()} total prospects`}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              leftIcon={<RefreshCw className="h-4 w-4" />}
              onClick={() =>
                queryClient.invalidateQueries({
                  queryKey: ['admin', 'prospect-lists'],
                })
              }
            >
              Refresh
            </Button>
            <Button
              leftIcon={<Upload className="h-4 w-4" />}
              onClick={() => setShowUploadModal(true)}
            >
              Upload List
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-lg bg-blue-100 flex items-center justify-center">
              <FileText className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {prospectLists.length}
              </p>
              <p className="text-xs text-slate-500">Total Lists</p>
            </div>
          </Card>
          <Card className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-lg bg-green-100 flex items-center justify-center">
              <Users className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {totalProspects.toLocaleString()}
              </p>
              <p className="text-xs text-slate-500">Total Prospects</p>
            </div>
          </Card>
          <Card className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-lg bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {prospectLists.filter((l) => l.status === 'completed').length}
              </p>
              <p className="text-xs text-slate-500">Completed</p>
            </div>
          </Card>
          <Card className="flex items-center gap-4">
            <div className="h-10 w-10 rounded-lg bg-amber-100 flex items-center justify-center">
              <RefreshCw
                className={clsx(
                  'h-5 w-5 text-amber-600',
                  processingCount > 0 && 'animate-spin'
                )}
              />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {processingCount}
              </p>
              <p className="text-xs text-slate-500">Processing</p>
            </div>
          </Card>
        </div>

        {/* Prospect Lists Table */}
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    List Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Prospects
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Uploaded By
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {prospectLists.map((list) => (
                  <tr
                    key={list.id}
                    className="hover:bg-slate-50 transition-colors group"
                  >
                    <td className="px-4 py-3">
                      <button
                        className="flex items-center gap-3 text-left w-full"
                        onClick={() =>
                          setExpandedListId(
                            expandedListId === list.id ? null : list.id
                          )
                        }
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500 flex-shrink-0">
                          <FileText className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium text-slate-900 truncate">
                            {list.name || list.file_name}
                          </p>
                          <p className="text-xs text-slate-500 truncate">
                            {list.file_name}
                          </p>
                        </div>
                        <ChevronDown
                          className={clsx(
                            'h-4 w-4 text-slate-400 transition-transform flex-shrink-0',
                            expandedListId === list.id && 'rotate-180'
                          )}
                        />
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      {statusBadge(list.status)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div>
                        <span className="text-sm font-medium text-slate-900">
                          {list.total_prospects.toLocaleString()}
                        </span>
                        {list.status === 'processing' &&
                          list.processed_prospects > 0 && (
                            <div className="mt-1">
                              <div className="w-full bg-slate-200 rounded-full h-1.5">
                                <div
                                  className="bg-blue-600 h-1.5 rounded-full transition-all duration-500"
                                  style={{
                                    width: `${Math.min(
                                      100,
                                      (list.processed_prospects /
                                        list.total_prospects) *
                                        100
                                    )}%`,
                                  }}
                                />
                              </div>
                              <p className="text-[10px] text-slate-400 mt-0.5">
                                {list.processed_prospects} /{' '}
                                {list.total_prospects}
                              </p>
                            </div>
                          )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-slate-600">
                        {list.uploaded_by || 'System'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-slate-500">
                        {formatDate(list.created_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {(list.status === 'pending' ||
                          list.status === 'failed') && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => processMutation.mutate(list.id)}
                            disabled={processMutation.isPending}
                            title="Process list"
                          >
                            <Play className="h-4 w-4 text-green-600" />
                          </Button>
                        )}
                        {list.status === 'processing' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled
                            title="Processing..."
                          >
                            <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (
                              confirm(
                                `Delete "${list.name || list.file_name}"? This cannot be undone.`
                              )
                            ) {
                              deleteMutation.mutate(list.id);
                            }
                          }}
                          disabled={
                            deleteMutation.isPending ||
                            list.status === 'processing'
                          }
                          title="Delete list"
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Empty State */}
          {prospectLists.length === 0 && (
            <div className="py-16 text-center">
              <FolderOpen className="h-14 w-14 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">
                No prospect lists yet
              </h3>
              <p className="text-slate-500 max-w-sm mx-auto mb-6">
                Upload a CSV file to import your prospect data. Once uploaded,
                you can process the list to enrich and validate contacts.
              </p>
              <Button onClick={() => setShowUploadModal(true)}>
                <Upload className="h-4 w-4 mr-2" />
                Upload Your First List
              </Button>
            </div>
          )}
        </Card>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-lg">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  Upload Prospect List
                </h2>
                <p className="text-sm text-slate-500 mt-0.5">
                  Import contacts from a CSV or Excel file
                </p>
              </div>
              <button
                onClick={() => setShowUploadModal(false)}
                className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>

            <FileUploadZone
              onFileSelected={(file) => uploadMutation.mutate(file)}
              isUploading={uploadMutation.isPending}
            />

            <div className="mt-4 p-4 bg-slate-50 rounded-lg">
              <h4 className="text-sm font-medium text-slate-700 mb-2">
                File Requirements
              </h4>
              <ul className="space-y-1.5 text-sm text-slate-500">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
                  <span>
                    <strong>Required column:</strong> email
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-slate-300 mt-0.5 flex-shrink-0" />
                  <span>
                    <strong>Optional:</strong> first_name, last_name, title,
                    company_name, company_domain, industry, phone, linkedin_url
                  </span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-slate-300 mt-0.5 flex-shrink-0" />
                  <span>Max file size: 10 MB</span>
                </li>
              </ul>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <Button
                variant="outline"
                onClick={() => setShowUploadModal(false)}
                disabled={uploadMutation.isPending}
              >
                Cancel
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

export default AdminProspectListsPage;
