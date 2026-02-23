import { useQuery } from '@tanstack/react-query';
import {
  Mail,
  Zap,
  BarChart3,
  MousePointerClick,
  Reply,
  TrendingUp,
  Loader2,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Badge } from '../components/ui';
import { analyticsApi } from '../api/analytics';
import { clsx } from 'clsx';
import { format, parseISO } from 'date-fns';

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

export function DashboardPage() {
  const {
    data: overview,
    isLoading: overviewLoading,
    isError: overviewError,
  } = useQuery({
    queryKey: ['analytics', 'overview'],
    queryFn: () => analyticsApi.getOverview(),
    refetchInterval: 60_000,
  });

  const {
    data: dailyStats,
    isLoading: chartLoading,
  } = useQuery({
    queryKey: ['analytics', 'daily', 7],
    queryFn: () => analyticsApi.getDailyStats(undefined, undefined, 7),
    refetchInterval: 60_000,
  });

  const chartData = (dailyStats ?? []).map((d) => ({
    date: (() => {
      try { return format(parseISO(d.date), 'EEE'); } catch { return d.date; }
    })(),
    sent: d.total_sent,
    opened: d.total_opened,
    clicked: d.total_clicked,
  }));

  const statsCards = overview
    ? [
        {
          label: 'Emails Sent Today',
          value: formatNumber(overview.emails_sent_today),
          icon: Mail,
          color: 'green' as const,
        },
        {
          label: 'Sent This Week',
          value: formatNumber(overview.emails_sent_this_week),
          icon: Zap,
          color: 'purple' as const,
        },
        {
          label: 'Sent This Month',
          value: formatNumber(overview.emails_sent_this_month),
          icon: TrendingUp,
          color: 'blue' as const,
        },
        {
          label: 'Open Rate',
          value: `${overview.open_rate.toFixed(1)}%`,
          icon: BarChart3,
          color: 'orange' as const,
        },
      ]
    : [];

  const colorClasses: Record<string, { text: string; iconBg: string }> = {
    blue: { text: 'text-brand-purple', iconBg: 'bg-brand-purple/10' },
    purple: { text: 'text-purple-600', iconBg: 'bg-purple-100' },
    green: { text: 'text-green-600', iconBg: 'bg-green-100' },
    orange: { text: 'text-orange-600', iconBg: 'bg-orange-100' },
  };

  return (
    <div className="h-full">
      <Header
        title="Dashboard"
        subtitle="Overview of your email marketing performance"
      />

      <div className="p-6 space-y-6">
        {/* Loading State */}
        {overviewLoading && (
          <div className="py-16 text-center">
            <Loader2 className="h-10 w-10 text-brand-purple mx-auto mb-4 animate-spin" />
            <p className="text-slate-500">Loading dashboard…</p>
          </div>
        )}

        {/* Error State */}
        {overviewError && !overviewLoading && (
          <div className="py-16 text-center">
            <Mail className="h-12 w-12 text-red-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-slate-900 mb-1">
              Failed to load analytics
            </h3>
            <p className="text-slate-500">
              Please try refreshing the page.
            </p>
          </div>
        )}

        {/* Main content */}
        {!overviewLoading && !overviewError && overview && (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {statsCards.map((stat) => {
                const colors = colorClasses[stat.color];
                return (
                  <Card key={stat.label} className="relative overflow-hidden">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm text-slate-500">{stat.label}</p>
                        <p className="text-2xl font-bold text-slate-900 mt-1">
                          {stat.value}
                        </p>
                      </div>
                      <div className={clsx('p-3 rounded-xl', colors.iconBg)}>
                        <stat.icon className={clsx('h-6 w-6', colors.text)} />
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Email Performance Chart */}
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle>Email Performance (Last 7 Days)</CardTitle>
                  <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-brand-purple" />
                      <span className="text-slate-600">Sent</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-green-500" />
                      <span className="text-slate-600">Opened</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-purple-500" />
                      <span className="text-slate-600">Clicked</span>
                    </div>
                  </div>
                </CardHeader>
                {chartLoading ? (
                  <div className="h-72 flex items-center justify-center">
                    <Loader2 className="h-8 w-8 text-slate-300 animate-spin" />
                  </div>
                ) : chartData.length === 0 ? (
                  <div className="h-72 flex items-center justify-center text-slate-400 text-sm">
                    No email data yet. Send your first campaign to see metrics here.
                  </div>
                ) : (
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData}>
                        <defs>
                          <linearGradient id="colorSent" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#6D08BE" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#6D08BE" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="colorOpened" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#22C55E" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#22C55E" stopOpacity={0} />
                          </linearGradient>
                          <linearGradient id="colorClicked" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                        <XAxis dataKey="date" stroke="#94A3B8" fontSize={12} />
                        <YAxis stroke="#94A3B8" fontSize={12} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#fff',
                            border: '1px solid #E2E8F0',
                            borderRadius: '8px',
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="sent"
                          stroke="#6D08BE"
                          fill="url(#colorSent)"
                          strokeWidth={2}
                        />
                        <Area
                          type="monotone"
                          dataKey="opened"
                          stroke="#22C55E"
                          fill="url(#colorOpened)"
                          strokeWidth={2}
                        />
                        <Area
                          type="monotone"
                          dataKey="clicked"
                          stroke="#8B5CF6"
                          fill="url(#colorClicked)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </Card>

              {/* Engagement Metrics */}
              <Card>
                <CardHeader>
                  <CardTitle>Engagement Rates</CardTitle>
                </CardHeader>
                <div className="space-y-6">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <BarChart3 className="h-4 w-4 text-green-500" />
                        <span className="text-sm text-slate-600">Open Rate</span>
                      </div>
                      <span className="text-lg font-semibold text-slate-900">
                        {overview.open_rate.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-green-500 rounded-full"
                        style={{ width: `${Math.min(overview.open_rate, 100)}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <MousePointerClick className="h-4 w-4 text-brand-purple" />
                        <span className="text-sm text-slate-600">Click Rate</span>
                      </div>
                      <span className="text-lg font-semibold text-slate-900">
                        {overview.click_rate.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-brand-purple rounded-full"
                        style={{ width: `${Math.min(overview.click_rate, 100)}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Reply className="h-4 w-4 text-purple-500" />
                        <span className="text-sm text-slate-600">Reply Rate</span>
                      </div>
                      <span className="text-lg font-semibold text-slate-900">
                        {overview.reply_rate.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-purple-500 rounded-full"
                        style={{ width: `${Math.min(overview.reply_rate * 5, 100)}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Mail className="h-4 w-4 text-red-500" />
                        <span className="text-sm text-slate-600">Bounce Rate</span>
                      </div>
                      <span className="text-lg font-semibold text-slate-900">
                        {overview.bounce_rate.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-red-400 rounded-full"
                        style={{ width: `${Math.min(overview.bounce_rate * 5, 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              </Card>
            </div>

            {/* Recent Campaigns */}
            {overview.recent_campaigns.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Recent Campaigns</CardTitle>
                </CardHeader>
                <div className="divide-y divide-slate-100">
                  {overview.recent_campaigns.map((campaign) => (
                    <div key={campaign.id} className="flex items-center gap-4 py-3">
                      <div className="p-2 rounded-lg bg-brand-purple/10">
                        <Mail className="h-4 w-4 text-brand-purple" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900">
                          {campaign.name}
                        </p>
                        <p className="text-sm text-slate-500">
                          {campaign.sent.toLocaleString()} emails sent
                        </p>
                      </div>
                      <Badge variant={campaign.open_rate > 30 ? 'success' : 'default'}>
                        {campaign.open_rate.toFixed(1)}% open rate
                      </Badge>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Empty state when no data at all */}
            {overview.emails_sent_this_month === 0 &&
              overview.recent_campaigns.length === 0 && (
                <Card>
                  <div className="py-12 text-center">
                    <Mail className="h-12 w-12 text-slate-300 mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-slate-900 mb-1">
                      No email data yet
                    </h3>
                    <p className="text-slate-500">
                      Create a campaign and send your first emails to see analytics here.
                    </p>
                  </div>
                </Card>
              )}
          </>
        )}
      </div>
    </div>
  );
}

export default DashboardPage;
