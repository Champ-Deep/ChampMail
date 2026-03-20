/**
 * CampaignProgress — real-time send progress for a running campaign.
 *
 * Polls GET /campaigns/{id}/progress every 3 seconds while status is "sending".
 * Shows: progress bar, sent/failed/skipped counters, current email, and controls.
 */

import { useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Pause,
  Play,
  Square,
  Mail,
} from 'lucide-react';
import { clsx } from 'clsx';
import { campaignsApi, type CampaignProgress as ProgressData } from '../../api/campaigns';
import { Button } from '../ui';

interface CampaignProgressProps {
  campaignId: string;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  isPausing?: boolean;
  isResuming?: boolean;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  sending: {
    label: 'Sending',
    color: 'text-blue-600',
    icon: <Loader2 className="h-4 w-4 animate-spin text-blue-600" />,
  },
  paused: {
    label: 'Paused',
    color: 'text-amber-600',
    icon: <Pause className="h-4 w-4 text-amber-600" />,
  },
  cancelled: {
    label: 'Cancelled',
    color: 'text-slate-500',
    icon: <Square className="h-4 w-4 text-slate-500" />,
  },
  completed: {
    label: 'Completed',
    color: 'text-green-600',
    icon: <CheckCircle2 className="h-4 w-4 text-green-600" />,
  },
  completed_with_errors: {
    label: 'Completed with errors',
    color: 'text-amber-600',
    icon: <AlertTriangle className="h-4 w-4 text-amber-600" />,
  },
  not_started: {
    label: 'Not started',
    color: 'text-slate-400',
    icon: <Mail className="h-4 w-4 text-slate-400" />,
  },
};

export function CampaignProgress({
  campaignId,
  onPause,
  onResume,
  onCancel,
  isPausing,
  isResuming,
}: CampaignProgressProps) {
  const { data: progress } = useQuery({
    queryKey: ['campaign-progress', campaignId],
    queryFn: () => campaignsApi.getProgress(campaignId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'sending' ? 3000 : false;
    },
    enabled: !!campaignId,
  });

  if (!progress) {
    return null;
  }

  const { status, sent, failed, skipped, total } = progress;
  const processed = sent + failed + skipped;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.not_started;
  const isSending = status === 'sending';
  const isPaused = status === 'paused';
  const isDone = ['completed', 'completed_with_errors', 'cancelled'].includes(status);

  return (
    <div className="border border-slate-200 rounded-lg p-4 space-y-3 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {cfg.icon}
          <span className={clsx('text-sm font-medium', cfg.color)}>
            {cfg.label}
          </span>
        </div>
        <span className="text-sm text-slate-500 font-mono">
          {processed} / {total}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-slate-100 rounded-full h-2.5">
        <div
          className={clsx(
            'h-2.5 rounded-full transition-all duration-500',
            failed > 0 ? 'bg-amber-500' : 'bg-brand-purple',
            isSending && 'animate-pulse',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-4 text-xs">
        <span className="flex items-center gap-1 text-green-600">
          <CheckCircle2 className="h-3 w-3" />
          {sent} sent
        </span>
        {failed > 0 && (
          <span className="flex items-center gap-1 text-red-600">
            <XCircle className="h-3 w-3" />
            {failed} failed
          </span>
        )}
        {skipped > 0 && (
          <span className="flex items-center gap-1 text-slate-500">
            <AlertTriangle className="h-3 w-3" />
            {skipped} skipped
          </span>
        )}
        <span className="ml-auto text-slate-400">{pct}%</span>
      </div>

      {/* Current email being sent */}
      {isSending && progress.current_email && (
        <p className="text-xs text-slate-500 truncate">
          Sending to: <span className="font-mono">{progress.current_email}</span>
        </p>
      )}

      {/* Last error */}
      {progress.last_error && (
        <div className="flex items-start gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
          <XCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
          <span className="break-all">{progress.last_error}</span>
        </div>
      )}

      {/* Controls */}
      {(isSending || isPaused) && (
        <div className="flex items-center gap-2 pt-1">
          {isSending && onPause && (
            <Button
              variant="outline"
              size="sm"
              onClick={onPause}
              isLoading={isPausing}
            >
              <Pause className="h-3.5 w-3.5 mr-1" />
              Pause
            </Button>
          )}
          {isPaused && onResume && (
            <Button
              variant="outline"
              size="sm"
              onClick={onResume}
              isLoading={isResuming}
            >
              <Play className="h-3.5 w-3.5 mr-1" />
              Resume
            </Button>
          )}
          {!isDone && onCancel && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (confirm('Cancel this campaign? Unsent emails will not be delivered.')) {
                  onCancel();
                }
              }}
              className="text-red-600 border-red-200 hover:bg-red-50"
            >
              <Square className="h-3.5 w-3.5 mr-1" />
              Cancel
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
