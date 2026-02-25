import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Workflow,
  Zap,
  Upload,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button } from '../components/ui';
import { WorkflowCard } from '../components/workflows/WorkflowCard';
import { workflowsApi } from '../api/workflows';

export function WorkflowsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);

  // Fetch workflows
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => workflowsApi.list(),
  });

  // Seed default workflows mutation
  const seedMutation = useMutation({
    mutationFn: workflowsApi.seedDefaults,
    onSuccess: (workflows) => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success(`Created ${workflows.length} default workflows`);
    },
    onError: () => {
      toast.error('Failed to create default workflows');
    },
  });

  // Import workflow mutation
  const importMutation = useMutation({
    mutationFn: workflowsApi.importFromFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow imported successfully');
    },
    onError: () => {
      toast.error('Failed to import workflow');
    },
  });

  // Toggle workflow
  const handleToggle = async (id: string) => {
    setTogglingId(id);
    try {
      await workflowsApi.toggle(id);
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow status updated');
    } catch {
      toast.error('Failed to toggle workflow');
    } finally {
      setTogglingId(null);
    }
  };

  // Trigger workflow
  const handleTrigger = async (id: string) => {
    setTriggeringId(id);
    try {
      const result = await workflowsApi.trigger(id);
      toast.success(result.message);
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
    } catch {
      toast.error('Failed to trigger workflow');
    } finally {
      setTriggeringId(null);
    }
  };

  // Delete workflow
  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this workflow?')) return;
    try {
      await workflowsApi.delete(id);
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow deleted');
    } catch {
      toast.error('Failed to delete workflow');
    }
  };

  // Handle file import
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      importMutation.mutate(file);
    }
  };

  const workflows = data?.workflows || [];

  return (
    <div className="h-full">
      <Header
        title="Email Automation Workflows"
        subtitle="Manage your n8n email automation workflows"
        actions={
          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".json"
              className="hidden"
            />
            <Button
              variant="outline"
              leftIcon={<Upload className="h-4 w-4" />}
              onClick={() => fileInputRef.current?.click()}
              disabled={importMutation.isPending}
            >
              Import
            </Button>
            <Button
              variant="outline"
              leftIcon={<RefreshCw className="h-4 w-4" />}
              onClick={() => seedMutation.mutate()}
              disabled={seedMutation.isPending}
            >
              {seedMutation.isPending ? 'Creating...' : 'Seed Defaults'}
            </Button>
            <Button
              leftIcon={<Plus className="h-4 w-4" />}
              disabled
              title="Create workflow dialog coming soon"
            >
              New Workflow
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Workflows Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-8 w-8 text-slate-400 animate-spin" />
          </div>
        ) : error ? (
          <Card className="text-center py-16">
            <AlertCircle className="h-16 w-16 text-red-300 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-slate-900 mb-2">
              Failed to load workflows
            </h2>
            <p className="text-slate-500 mb-4">Please check your connection and try again.</p>
            <Button variant="outline" onClick={() => refetch()}>
              Retry
            </Button>
          </Card>
        ) : workflows.length === 0 ? (
          <Card className="text-center py-16">
            <Workflow className="h-16 w-16 text-slate-300 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-slate-900 mb-2">
              No Workflows Yet
            </h2>
            <p className="text-slate-500 max-w-md mx-auto mb-6">
              Get started by seeding the default email automation workflows from your n8n instance,
              or import a workflow from a JSON file.
            </p>
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="primary"
                leftIcon={<Zap className="h-4 w-4" />}
                onClick={() => seedMutation.mutate()}
                disabled={seedMutation.isPending}
              >
                {seedMutation.isPending ? 'Creating...' : 'Create Default Workflows'}
              </Button>
              <Button
                variant="outline"
                leftIcon={<Upload className="h-4 w-4" />}
                onClick={() => fileInputRef.current?.click()}
              >
                Import from File
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {workflows.map((workflow) => (
              <WorkflowCard
                key={workflow.id}
                workflow={workflow}
                onToggle={() => handleToggle(workflow.id)}
                onTrigger={() => handleTrigger(workflow.id)}
                onDelete={() => handleDelete(workflow.id)}
                isToggling={togglingId === workflow.id}
                isTriggering={triggeringId === workflow.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default WorkflowsPage;
