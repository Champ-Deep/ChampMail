import { useState } from 'react';
import {
  Users,
  Mail,
  Zap,
  FileText,
  TrendingUp,
  TrendingDown,
  BarChart3,
  MousePointerClick,
  Reply,
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
import { Card, CardHeader, CardTitle, Badge, Button } from '../components/ui';
import { clsx } from 'clsx';

// Mock data - will be replaced with API calls
const statsData = [
  {
    label: 'Total Prospects',
    value: '12,458',
    change: 12.5,
    icon: Users,
    color: 'blue',
  },
  {
    label: 'Active Sequences',
    value: '8',
    change: 2,
    icon: Zap,
    color: 'purple',
  },
  {
    label: 'Emails Sent (30d)',
    value: '45,231',
    change: 18.2,
    icon: Mail,
    color: 'green',
  },
  {
    label: 'Templates',
    value: '24',
    change: 4,
    icon: FileText,
    color: 'orange',
  },
];

const chartData = [
  { date: 'Mon', sent: 1200, opened: 890, clicked: 450 },
  { date: 'Tue', sent: 1400, opened: 1050, clicked: 520 },
  { date: 'Wed', sent: 1100, opened: 780, clicked: 380 },
  { date: 'Thu', sent: 1600, opened: 1200, clicked: 640 },
  { date: 'Fri', sent: 1300, opened: 920, clicked: 490 },
  { date: 'Sat', sent: 800, opened: 580, clicked: 290 },
  { date: 'Sun', sent: 600, opened: 420, clicked: 210 },
];

const recentActivity = [
  { type: 'reply', prospect: 'john@acme.com', time: '2 min ago', detail: 'Interested in demo' },
  { type: 'open', prospect: 'sarah@techcorp.io', time: '5 min ago', detail: 'Opened "Welcome" email' },
  { type: 'click', prospect: 'mike@startup.co', time: '12 min ago', detail: 'Clicked pricing link' },
  { type: 'bounce', prospect: 'invalid@test.com', time: '25 min ago', detail: 'Hard bounce' },
  { type: 'reply', prospect: 'lisa@bigco.com', time: '1 hour ago', detail: 'Scheduled meeting' },
];

const colorClasses: Record<string, { bg: string; text: string; iconBg: string }> = {
  blue: { bg: 'bg-blue-50', text: 'text-blue-600', iconBg: 'bg-blue-100' },
  purple: { bg: 'bg-purple-50', text: 'text-purple-600', iconBg: 'bg-purple-100' },
  green: { bg: 'bg-green-50', text: 'text-green-600', iconBg: 'bg-green-100' },
  orange: { bg: 'bg-orange-50', text: 'text-orange-600', iconBg: 'bg-orange-100' },
};

export function DashboardPage() {
  const [metrics] = useState({
    openRate: 68.5,
    clickRate: 24.2,
    replyRate: 8.4,
  });

  return (
    <div className="h-full">
      <Header
        title="Dashboard"
        subtitle="Overview of your email marketing performance"
      />

      <div className="p-6 space-y-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {statsData.map((stat) => {
            const colors = colorClasses[stat.color];
            const isPositive = stat.change > 0;

            return (
              <Card key={stat.label} className="relative overflow-hidden">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-slate-500">{stat.label}</p>
                    <p className="text-2xl font-bold text-slate-900 mt-1">
                      {stat.value}
                    </p>
                    <div className="flex items-center gap-1 mt-2">
                      {isPositive ? (
                        <TrendingUp className="h-4 w-4 text-green-500" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-500" />
                      )}
                      <span
                        className={clsx(
                          'text-sm font-medium',
                          isPositive ? 'text-green-600' : 'text-red-600'
                        )}
                      >
                        {isPositive ? '+' : ''}
                        {stat.change}%
                      </span>
                      <span className="text-sm text-slate-400">vs last month</span>
                    </div>
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
                  <div className="w-3 h-3 rounded-full bg-blue-500" />
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
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorSent" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
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
                    stroke="#3B82F6"
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
                    {metrics.openRate}%
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full"
                    style={{ width: `${metrics.openRate}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <MousePointerClick className="h-4 w-4 text-blue-500" />
                    <span className="text-sm text-slate-600">Click Rate</span>
                  </div>
                  <span className="text-lg font-semibold text-slate-900">
                    {metrics.clickRate}%
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full"
                    style={{ width: `${metrics.clickRate}%` }}
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
                    {metrics.replyRate}%
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-purple-500 rounded-full"
                    style={{ width: `${metrics.replyRate * 5}%` }}
                  />
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Recent Activity */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <Button variant="outline" size="sm">
              View All
            </Button>
          </CardHeader>
          <div className="divide-y divide-slate-100">
            {recentActivity.map((activity, idx) => (
              <div key={idx} className="flex items-center gap-4 py-3">
                <div
                  className={clsx(
                    'p-2 rounded-lg',
                    activity.type === 'reply' && 'bg-purple-100',
                    activity.type === 'open' && 'bg-green-100',
                    activity.type === 'click' && 'bg-blue-100',
                    activity.type === 'bounce' && 'bg-red-100'
                  )}
                >
                  {activity.type === 'reply' && <Reply className="h-4 w-4 text-purple-600" />}
                  {activity.type === 'open' && <Mail className="h-4 w-4 text-green-600" />}
                  {activity.type === 'click' && <MousePointerClick className="h-4 w-4 text-blue-600" />}
                  {activity.type === 'bounce' && <Mail className="h-4 w-4 text-red-600" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-900">
                    {activity.prospect}
                  </p>
                  <p className="text-sm text-slate-500 truncate">
                    {activity.detail}
                  </p>
                </div>
                <Badge
                  variant={
                    activity.type === 'reply'
                      ? 'success'
                      : activity.type === 'bounce'
                      ? 'danger'
                      : 'default'
                  }
                >
                  {activity.type}
                </Badge>
                <span className="text-sm text-slate-400">{activity.time}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

export default DashboardPage;
