import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Search, FileText, MoreVertical, Edit, Trash2, Copy, Eye, Loader2 } from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { templatesApi, type EmailTemplate } from '../api';

export function TemplatesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeMenu, setActiveMenu] = useState<string | null>(null);

  // Fetch templates from API
  const { data, isLoading, error } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(100, 0),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => templatesApi.delete(id),
    onSuccess: () => {
      toast.success('Template deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['templates'] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to delete template: ${err.message}`);
    },
  });

  // Duplicate mutation
  const duplicateMutation = useMutation({
    mutationFn: async (template: EmailTemplate) => {
      return templatesApi.create({
        name: `${template.name} (Copy)`,
        subject: template.subject,
        mjml_content: template.mjml_content,
        compile_html: true,
      });
    },
    onSuccess: () => {
      toast.success('Template duplicated successfully');
      queryClient.invalidateQueries({ queryKey: ['templates'] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to duplicate template: ${err.message}`);
    },
  });

  const templates = data?.templates || [];
  const filteredTemplates = templates.filter(
    (template) =>
      template.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      template.subject?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const handleDelete = (e: React.MouseEvent, template: EmailTemplate) => {
    e.stopPropagation();
    setActiveMenu(null);
    if (confirm(`Are you sure you want to delete "${template.name}"?`)) {
      deleteMutation.mutate(template.id);
    }
  };

  const handleDuplicate = (e: React.MouseEvent, template: EmailTemplate) => {
    e.stopPropagation();
    setActiveMenu(null);
    duplicateMutation.mutate(template);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="h-full">
        <Header
          title="Email Templates"
          subtitle="Create and manage your email templates"
        />
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-full">
        <Header
          title="Email Templates"
          subtitle="Create and manage your email templates"
        />
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <FileText className="h-12 w-12 text-red-300 mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-1">
            Failed to load templates
          </h3>
          <p className="text-slate-500 mb-4">{(error as Error).message}</p>
          <Button onClick={() => queryClient.invalidateQueries({ queryKey: ['templates'] })}>
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full">
      <Header
        title="Email Templates"
        subtitle="Create and manage your email templates"
        actions={
          <Button
            leftIcon={<Plus className="h-4 w-4" />}
            onClick={() => navigate('/templates/new')}
          >
            New Template
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
              placeholder="Search templates..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Templates Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTemplates.map((template) => (
            <Card
              key={template.id}
              className="group hover:border-blue-200 hover:shadow-md transition-all cursor-pointer"
              onClick={() => navigate(`/templates/${template.id}/edit`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-blue-50">
                    <FileText className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-slate-900 group-hover:text-blue-600 transition-colors">
                      {template.name}
                    </h3>
                    <p className="text-sm text-slate-500 mt-0.5 line-clamp-1">
                      {template.subject || 'No subject'}
                    </p>
                  </div>
                </div>
                <div className="relative">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setActiveMenu(activeMenu === template.id ? null : template.id);
                    }}
                    className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600"
                  >
                    <MoreVertical className="h-4 w-4" />
                  </button>

                  {activeMenu === template.id && (
                    <div className="absolute right-0 top-8 w-40 bg-white rounded-lg shadow-lg border border-slate-200 py-1 z-10">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/templates/${template.id}/edit`);
                        }}
                        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                      >
                        <Edit className="h-4 w-4" />
                        Edit
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toast.info('Preview coming soon');
                          setActiveMenu(null);
                        }}
                        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                      >
                        <Eye className="h-4 w-4" />
                        Preview
                      </button>
                      <button
                        onClick={(e) => handleDuplicate(e, template)}
                        disabled={duplicateMutation.isPending}
                        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                      >
                        <Copy className="h-4 w-4" />
                        Duplicate
                      </button>
                      <hr className="my-1" />
                      <button
                        onClick={(e) => handleDelete(e, template)}
                        disabled={deleteMutation.isPending}
                        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2 flex-wrap">
                {template.variables.map((variable) => (
                  <Badge key={variable} variant="info" size="sm">
                    {`{{${variable}}}`}
                  </Badge>
                ))}
                {template.variables.length === 0 && (
                  <span className="text-xs text-slate-400">No variables</span>
                )}
              </div>

              <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500">
                <span>Created {formatDate(template.created_at)}</span>
                <span>Updated {formatDate(template.updated_at)}</span>
              </div>
            </Card>
          ))}

          {/* Empty State */}
          {filteredTemplates.length === 0 && (
            <div className="col-span-full py-12 text-center">
              <FileText className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-1">
                No templates found
              </h3>
              <p className="text-slate-500 mb-4">
                {searchQuery
                  ? 'Try adjusting your search query'
                  : 'Create your first email template to get started'}
              </p>
              {!searchQuery && (
                <Button onClick={() => navigate('/templates/new')}>
                  Create Template
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default TemplatesPage;
