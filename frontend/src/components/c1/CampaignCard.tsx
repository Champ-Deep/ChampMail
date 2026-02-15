import { Card } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Mail, TrendingUp, TrendingDown, MousePointer } from 'lucide-react';

interface CampaignCardProps {
  name: string;
  status: 'active' | 'paused' | 'completed' | 'draft';
  sent: number;
  openRate: number;
  clickRate: number;
  bounceRate?: number;
}

const statusVariant: Record<string, 'success' | 'warning' | 'danger' | 'default' | 'info'> = {
  active: 'success',
  paused: 'warning',
  completed: 'info',
  draft: 'default',
};

export function CampaignCard({ name, status, sent, openRate, clickRate, bounceRate }: CampaignCardProps) {
  return (
    <Card padding="none" className="p-4 bg-gradient-to-br from-brand-purple/5 to-brand-purple/10 border-brand-purple/20">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-brand-purple" />
          <h3 className="text-sm font-semibold text-slate-900 truncate">{name}</h3>
        </div>
        <Badge variant={statusVariant[status] || 'default'} size="sm">{status}</Badge>
      </div>
      <p className="text-2xl font-bold text-brand-navy mb-3">{sent.toLocaleString()} <span className="text-sm font-normal text-slate-500">sent</span></p>
      <div className="flex gap-4 text-sm">
        <div className="flex items-center gap-1">
          <TrendingUp className="h-3.5 w-3.5 text-green-600" />
          <span className="text-slate-600">Open: <strong>{openRate}%</strong></span>
        </div>
        <div className="flex items-center gap-1">
          <MousePointer className="h-3.5 w-3.5 text-brand-purple" />
          <span className="text-slate-600">Click: <strong>{clickRate}%</strong></span>
        </div>
        {bounceRate !== undefined && (
          <div className="flex items-center gap-1">
            <TrendingDown className="h-3.5 w-3.5 text-red-500" />
            <span className="text-slate-600">Bounce: <strong>{bounceRate}%</strong></span>
          </div>
        )}
      </div>
    </Card>
  );
}
