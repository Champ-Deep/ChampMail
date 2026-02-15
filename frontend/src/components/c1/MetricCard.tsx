import { Card } from '../ui/Card';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { clsx } from 'clsx';

interface MetricCardProps {
  label: string;
  value: string;
  change?: number;
  trend?: 'up' | 'down' | 'flat';
  color?: 'blue' | 'green' | 'purple' | 'red' | 'orange';
}

const colorMap = {
  blue: { bg: 'from-brand-purple/5 to-brand-purple/10', text: 'text-brand-navy', accent: 'text-brand-purple' },
  green: { bg: 'from-green-50 to-green-100', text: 'text-green-900', accent: 'text-green-600' },
  purple: { bg: 'from-purple-50 to-purple-100', text: 'text-purple-900', accent: 'text-purple-600' },
  red: { bg: 'from-red-50 to-red-100', text: 'text-red-900', accent: 'text-red-600' },
  orange: { bg: 'from-orange-50 to-orange-100', text: 'text-orange-900', accent: 'text-orange-600' },
};

const TrendIcon = ({ trend }: { trend?: string }) => {
  if (trend === 'up') return <TrendingUp className="h-4 w-4 text-green-600" />;
  if (trend === 'down') return <TrendingDown className="h-4 w-4 text-red-500" />;
  return <Minus className="h-4 w-4 text-slate-400" />;
};

export function MetricCard({ label, value, change, trend, color = 'blue' }: MetricCardProps) {
  const colors = colorMap[color] || colorMap.blue;

  return (
    <Card padding="none" className={clsx('p-4 bg-gradient-to-br', colors.bg)}>
      <p className={clsx('text-sm font-medium mb-1', colors.accent)}>{label}</p>
      <p className={clsx('text-3xl font-bold', colors.text)}>{value}</p>
      {(change !== undefined || trend) && (
        <div className="flex items-center gap-1.5 mt-2">
          <TrendIcon trend={trend} />
          {change !== undefined && (
            <span className={clsx('text-sm font-medium', change >= 0 ? 'text-green-600' : 'text-red-500')}>
              {change >= 0 ? '+' : ''}{change}%
            </span>
          )}
        </div>
      )}
    </Card>
  );
}
