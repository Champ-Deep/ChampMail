import { useState, useEffect } from 'react';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Mail,
  Eye,
  MousePointer,
  AlertTriangle,
  Reply,
  Calendar,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Button, Badge } from '../components/ui';

const mockDailyData = [
  { date: 'Mon', sent: 1200, opened: 890, clicked: 450 },
  { date: 'Tue', sent: 1400, opened: 1050, clicked: 520 },
  { date: 'Wed', sent: 1100, opened: 780, clicked: 380 },
  { date: 'Thu', sent: 1600, opened: 1200, clicked: 640 },
  { date: 'Fri', sent: 1300, opened: 920, clicked: 490 },
  { date: 'Sat', sent: 800, opened: 580, clicked: 290 },
  { date: 'Sun', sent: 600, opened: 420, clicked: 210 },
];

const mockEngagementData = [
  { name: 'Opened', value: 8940, color: '#10b981' },
  { name: 'Clicked', value: 2980, color: '#3b82f6' },
  { name: 'Replied', value: 850, color: '#8b5cf6' },
  { name: 'Bounced', value: 320, color: '#ef4444' },
];

const mockTopDomains = [
  { domain: 'outreach.lakeb2b.com', sent: 5420, open_rate: 72.5, click_rate: 28.3 },
  { domain: 'mail.champmail.com', sent: 3890, open_rate: 68.2, click_rate: 24.1 },
  { domain: 'email.champions.dev', sent: 2150, open_rate: 71.8, click_rate: 26.7 },
];

const mockRecentCampaigns = [
  { name: 'Product Launch', sent: 2500, open_rate: 68.5, click_rate: 22.3, status: 'active' },
  { name: 'Follow-up Series', sent: 1800, open_rate: 72.1, click_rate: 28.5, status: 'active' },
  { name: 'Newsletter #42', sent: 4200, open_rate: 45.2, click_rate: 12.8, status: 'completed' },
  { name: 'Webinar Invite', sent: 1200, open_rate: 78.5, click_rate: 35.2, status: 'completed' },
];

export function AnalyticsPage() {
  const [period, setPeriod] = useState<'7d' | '30d' | '90d'>('7d');

  const stats = {
    totalSent: 8900,
    totalOpened: 6340,
    totalClicked: 2980,
    totalReplied: 850,
    totalBounced: 320,
    openRate: 71.2,
    clickRate: 33.5,
    bounceRate: 3.6,
    replyRate: 9.5,
  };

  const periodLabels = {
    '7d': 'Last 7 Days',
    '30d': 'Last 30 Days',
    '90d': 'Last 90 Days',
  };

  return (
    <div className="h-full">
      <Header
        title="Analytics"
        subtitle="Monitor your email performance and engagement metrics"
        action={
          <div className="flex gap-2">
            <Button
              variant={period === '7d' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setPeriod('7d')}
            >
              7D
            </Button>
            <Button
              variant={period === '30d' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setPeriod('30d')}
            >
              30D
            </Button>
            <Button
              variant={period === '90d' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setPeriod('90d')}
            >
              90D
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="bg-gradient-to-br from-blue-50 to-blue-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-blue-600 font-medium">Emails Sent</p>
                  <p className="text-2xl font-bold text-blue-900">{stats.totalSent.toLocaleString()}</p>
                </div>
                <div className="w-12 h-12 bg-blue-200 rounded-lg flex items-center justify-center">
                  <Mail className="w-6 h-6 text-blue-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-blue-600">
                <TrendingUp className="w-4 h-4" />
                <span>+12.5% from last period</span>
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-green-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-green-600 font-medium">Open Rate</p>
                  <p className="text-2xl font-bold text-green-900">{stats.openRate}%</p>
                </div>
                <div className="w-12 h-12 bg-green-200 rounded-lg flex items-center justify-center">
                  <Eye className="w-6 h-6 text-green-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-green-600">
                <TrendingUp className="w-4 h-4" />
                <span>+3.2% from last period</span>
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-purple-50 to-purple-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-purple-600 font-medium">Click Rate</p>
                  <p className="text-2xl font-bold text-purple-900">{stats.clickRate}%</p>
                </div>
                <div className="w-12 h-12 bg-purple-200 rounded-lg flex items-center justify-center">
                  <MousePointer className="w-6 h-6 text-purple-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-purple-600">
                <TrendingUp className="w-4 h-4" />
                <span>+5.8% from last period</span>
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-red-50 to-red-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-red-600 font-medium">Bounce Rate</p>
                  <p className="text-2xl font-bold text-red-900">{stats.bounceRate}%</p>
                </div>
                <div className="w-12 h-12 bg-red-200 rounded-lg flex items-center justify-center">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-red-600">
                <TrendingDown className="w-4 h-4" />
                <span>-1.2% from last period</span>
              </div>
            </div>
          </Card>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Email Activity Chart */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Email Activity - {periodLabels[period]}</CardTitle>
            </CardHeader>
            <div className="p-4 h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={mockDailyData}>
                  <defs>
                    <linearGradient id="sentGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="openedGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="date" stroke="#9ca3af" />
                  <YAxis stroke="#9ca3af" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="sent"
                    stroke="#3b82f6"
                    fill="url(#sentGradient)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="opened"
                    stroke="#10b981"
                    fill="url(#openedGradient)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Engagement Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Engagement Breakdown</CardTitle>
            </CardHeader>
            <div className="p-4 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={mockEngagementData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {mockEngagementData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-4 mt-2">
                {mockEngagementData.map((item) => (
                  <div key={item.name} className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="text-xs text-gray-600">{item.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </div>

        {/* Tables Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Top Performing Domains */}
          <Card>
            <CardHeader>
              <CardTitle>Domain Performance</CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Domain</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Sent</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Open Rate</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Click Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {mockTopDomains.map((domain) => (
                    <tr key={domain.domain} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{domain.domain}</td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">{domain.sent.toLocaleString()}</td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">
                        <span className="text-green-600">{domain.open_rate}%</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">{domain.click_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Recent Campaigns */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Campaigns</CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Campaign</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Sent</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Open Rate</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {mockRecentCampaigns.map((campaign) => (
                    <tr key={campaign.name} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{campaign.name}</td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">{campaign.sent.toLocaleString()}</td>
                      <td className="px-4 py-3 text-sm text-gray-600 text-right">{campaign.open_rate}%</td>
                      <td className="px-4 py-3 text-center">
                        <Badge className={campaign.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}>
                          {campaign.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default AnalyticsPage;