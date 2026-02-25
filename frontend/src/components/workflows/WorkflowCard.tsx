import { useState } from 'react';
import { toast } from 'sonner';
import {
  Pause,
  Trash2,
  Zap,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Copy,
  Link,
  Power,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card, Button, Badge } from '../ui';
import { workflowsApi, type Workflow as WorkflowType, type WorkflowExecution } from '../../api/workflows';

const WORKFLOW_TYPE_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  auto_reply: {
    icon: <Zap className="h-5 w-5" />, // Changed from MessageSquare to Zap for variety
    color: 'bg-brand-purple/10 text-brand-purple',
    label: 'Auto Reply',
  },
  email_writer: {
    icon: <Zap className="h-5 w-5" />, // Standardizing on Zap or similar
    color: 'bg-green-100 text-green-700',
    label: 'Email Writer',
  },
  email_summary: {
    icon: <Zap className="h-5 w-5" />,
    color: 'bg-purple-100 text-purple-700',
    label: 'Email Summary',
  },
  controller: {
    icon: <Zap className="h-5 w-5" />,
    color: 'bg-orange-100 text-orange-700',
    label: 'Controller',
  },
  custom: {
    icon: <Zap className="h-5 w-5" />,
    color: 'bg-slate-100 text-slate-700',
    label: 'Custom',
  },
};

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  active: { color: 'bg-green-100 text-green-700', icon: <CheckCircle className="h-4 w-4" /> },
  inactive: { color: 'bg-slate-100 text-slate-600', icon: <Pause className="h-4 w-4" /> },
  error: { color: 'bg-red-100 text-red-700', icon: <XCircle className="h-4 w-4" /> },
};

interface WorkflowCardProps {
  workflow: WorkflowType;
  onToggle: () => void;
  onTrigger: () => void;
  onDelete: () => void;
  isToggling: boolean;
  isTriggering: boolean;
}

export function WorkflowCard({ workflow, onToggle, onTrigger, onDelete, isToggling, isTriggering }: WorkflowCardProps) {
  const [showExecutions, setShowExecutions] = useState(false);
  const [showWebhookInfo, setShowWebhookInfo] = useState(false);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loadingExecutions, setLoadingExecutions] = useState(false);

  const typeConfig = WORKFLOW_TYPE_CONFIG[workflow.workflow_type] || WORKFLOW_TYPE_CONFIG.custom;
  const statusConfig = STATUS_CONFIG[workflow.status] || STATUS_CONFIG.inactive;

  // Get the webhook URLs for n8n integration
  const apiBaseUrl = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL || 'http://localhost:8000';
  const webhookSendUrl = `${apiBaseUrl}/api/v1/webhook/send`;
  const webhookFetchUrl = `${apiBaseUrl}/api/v1/webhook/fetch`;

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

  const loadExecutions = async () => {
    if (showExecutions) {
      setShowExecutions(false);
      return;
    }
    setLoadingExecutions(true);
    try {
      const data = await workflowsApi.getExecutions(workflow.id, 5);
      setExecutions(data);
      setShowExecutions(true);
    } catch (error) {
      toast.error('Failed to load executions');
    } finally {
      setLoadingExecutions(false);
    }
  };

  return (
    <Card className="p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${typeConfig.color}`}>
            {typeConfig.icon}
          </div>
          <div>
            <h3 className="font-semibold text-slate-900">{workflow.name}</h3>
            <p className="text-sm text-slate-500">{typeConfig.label}</p>
          </div>
        </div>
        <Badge className={statusConfig.color}>
          <span className="flex items-center gap-1">
            {statusConfig.icon}
            {workflow.status}
          </span>
        </Badge>
      </div>

      {workflow.description && (
        <p className="text-sm text-slate-600 mb-4 line-clamp-2">{workflow.description}</p>
      )}

      <div className="flex items-center gap-4 text-sm text-slate-500 mb-4">
        <span className="flex items-center gap-1">
          <Zap className="h-4 w-4" />
          {workflow.execution_count} executions
        </span>
        {workflow.last_executed_at && (
          <span className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            Last: {new Date(workflow.last_executed_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {workflow.last_error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span className="line-clamp-1">{workflow.last_error}</span>
          </p>
        </div>
      )}

      {/* Activation Toggle with Power Button */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-100">
        <div className="flex items-center gap-3">
          {/* Power Toggle */}
          <button
            onClick={onToggle}
            disabled={isToggling}
            className={`relative flex items-center justify-center w-12 h-12 rounded-full transition-all duration-300 ${
              workflow.is_active
                ? 'bg-green-500 hover:bg-green-600 shadow-lg shadow-green-500/30'
                : 'bg-slate-200 hover:bg-slate-300'
            } ${isToggling ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
            title={workflow.is_active ? 'Click to deactivate' : 'Click to activate'}
          >
            <Power className={`h-6 w-6 ${workflow.is_active ? 'text-white' : 'text-slate-500'}`} />
            {workflow.is_active && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-green-400 rounded-full animate-pulse" />
            )}
          </button>
          <div>
            <p className={`text-sm font-medium ${workflow.is_active ? 'text-green-700' : 'text-slate-600'}`}>
              {isToggling ? 'Switching...' : workflow.is_active ? 'Active' : 'Inactive'}
            </p>
            <p className="text-xs text-slate-500">
              {workflow.is_active ? 'Receiving n8n webhooks' : 'Click to enable'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowWebhookInfo(!showWebhookInfo)}
            leftIcon={<Link className="h-4 w-4" />}
          >
            Webhook
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onTrigger}
            disabled={!workflow.is_active || isTriggering}
            leftIcon={<Zap className="h-4 w-4" />}
          >
            {isTriggering ? 'Running...' : 'Test'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={loadExecutions}
            disabled={loadingExecutions}
            leftIcon={showExecutions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          >
            History
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onDelete}
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Webhook Info Section */}
      {showWebhookInfo && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
            <Link className="h-4 w-4" />
            n8n Webhook Integration
          </h4>
          <p className="text-xs text-slate-500 mb-3">
            Replace n8n SMTP/IMAP nodes with HTTP Request nodes pointing to these URLs.
            The app will use your configured email credentials.
          </p>
          <div className="space-y-3">
            {/* Send Email Webhook */}
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-600">Send Email (replaces SMTP node)</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => copyToClipboard(webhookSendUrl, 'Send URL')}
                  className="h-6 px-2"
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
              <code className="text-xs text-brand-purple bg-brand-purple/5 px-2 py-1 rounded block overflow-x-auto">
                POST {webhookSendUrl}
              </code>
              <p className="text-xs text-slate-500 mt-1">
                Body: {`{ "to": "email", "subject": "...", "body": "..." }`}
              </p>
            </div>

            {/* Fetch Emails Webhook */}
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-600">Fetch Emails (replaces IMAP node)</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => copyToClipboard(webhookFetchUrl, 'Fetch URL')}
                  className="h-6 px-2"
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
              <code className="text-xs text-brand-purple bg-brand-purple/5 px-2 py-1 rounded block overflow-x-auto">
                POST {webhookFetchUrl}
              </code>
              <p className="text-xs text-slate-500 mt-1">
                Body: {`{ "limit": 20, "unseen_only": false }`}
              </p>
            </div>

            {/* Header Info */}
            <div className="bg-orange-50 rounded-lg p-3">
              <span className="text-xs font-medium text-orange-700">Required Header</span>
              <code className="text-xs text-orange-600 block mt-1">
                X-Workflow-Id: {workflow.id}
              </code>
              <p className="text-xs text-orange-600 mt-1">
                Add this header in your n8n HTTP Request node
              </p>
            </div>
          </div>
        </div>
      )}

      {showExecutions && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <h4 className="text-sm font-medium text-slate-700 mb-3">Recent Executions</h4>
          {executions.length === 0 ? (
            <p className="text-sm text-slate-500">No executions yet</p>
          ) : (
            <div className="space-y-2">
              {executions.map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center justify-between py-2 px-3 bg-slate-50 rounded-lg text-sm"
                >
                  <div className="flex items-center gap-2">
                    {exec.status === 'success' ? (
                      <CheckCircle className="h-4 w-4 text-green-600" />
                    ) : exec.status === 'failed' ? (
                      <XCircle className="h-4 w-4 text-red-600" />
                    ) : (
                      <Zap className="h-4 w-4 text-brand-purple animate-spin" />
                    )}
                    <span className="text-slate-700">{exec.trigger_type || 'manual'}</span>
                  </div>
                  <div className="flex items-center gap-4 text-slate-500">
                    {exec.duration_ms && <span>{exec.duration_ms}ms</span>}
                    <span>{new Date(exec.started_at).toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
