import { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Mail,
  Eye,
  MousePointer,
  AlertTriangle,
} from 'lucide-react';
import {
  AreaChart,
  Area,
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
import { Card, CardHeader, CardTitle, Button } from '../components/ui';
import { C1AnalyticsQuery } from '../components/c1/C1AnalyticsQuery';
import { analyticsApi } from '../api';
import type { AnalyticsOverview, DailyStat, DomainStats } from '../api/analytics';

interface EngagementData {
  [key: string]: unknown;
  name: string;
  value: number;
  color: string;
}

export function AnalyticsPage() {
  const [period, setPeriod] = useState<7 | 30 | 90>(7);
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [dailyStats, setDailyStats] = useState<DailyStat[]>([]);
  const [domainStats, setDomainStats] = useState<DomainStats[]>([]);

  useEffect(() => {
    loadAnalyticsData();
  }, []);

  useEffect(() => {
    loadDailyStats();
  }, [period]);

  const loadAnalyticsData = async () => {
    try {
      setLoading(true);
      const [overviewData, domainData] = await Promise.all([
        analyticsApi.getOverview(),
        analyticsApi.getAllDomainStats(30),
      ]);
      setOverview(overviewData);
      setDomainStats(domainData);
    } catch (error) {
      console.error('Failed to load analytics data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadDailyStats = async () => {
    try {
      const stats = await analyticsApi.getDailyStats(undefined, undefined, period);
      setDailyStats(stats);
    } catch (error) {
      console.error('Failed to load daily stats:', error);
    }
  };

  const periodLabels = {
    7: 'Last 7 Days',
    30: 'Last 30 Days',
    90: 'Last 90 Days',
  };

  // Calculate engagement breakdown from overview stats
  const engagementData: EngagementData[] = overview
    ? [
        {
          name: 'Opened',
          value: Math.round((overview.open_rate / 100) * overview.emails_sent_this_month),
          color: '#10b981',
        },
        {
          name: 'Clicked',
          value: Math.round((overview.click_rate / 100) * overview.emails_sent_this_month),
          color: '#3b82f6',
        },
        {
          name: 'Replied',
          value: Math.round((overview.reply_rate / 100) * overview.emails_sent_this_month),
          color: '#8b5cf6',
        },
        {
          name: 'Bounced',
          value: Math.round((overview.bounce_rate / 100) * overview.emails_sent_this_month),
          color: '#ef4444',
        },
      ].filter((item) => item.value > 0)
    : [];

  // Format daily stats for chart
  const chartData = dailyStats.map((stat) => ({
    date: new Date(stat.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    sent: stat.total_sent,
    opened: stat.total_opened,
    clicked: stat.total_clicked,
  }));

  if (loading) {
    return (
      <div className="h-full">
        <Header
          title="Analytics"
          subtitle="Monitor your email performance and engagement metrics"
        />
        <div className="flex items-center justify-center h-96">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="h-full">
        <Header
          title="Analytics"
          subtitle="Monitor your email performance and engagement metrics"
        />
        <div className="p-6">
          <Card className="bg-blue-50 border-blue-200">
            <div className="p-6 text-center">
              <Mail className="w-12 h-12 text-blue-600 mx-auto mb-3" />
              <h3 className="text-lg font-semibold text-gray-900 mb-2">No Analytics Data Yet</h3>
              <p className="text-gray-600">
                Start sending campaigns to see your email performance metrics here.
              </p>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full">
      <Header
        title="Analytics"
        subtitle="Monitor your email performance and engagement metrics"
        actions={
          <div className="flex gap-2">
            <Button
              variant={period === 7 ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setPeriod(7)}
            >
              7D
            </Button>
            <Button
              variant={period === 30 ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setPeriod(30)}
            >
              30D
            </Button>
            <Button
              variant={period === 90 ? 'primary' : 'outline'}
              size="sm"
              onClick={() => setPeriod(90)}
            >
              90D
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* AI Analytics Query */}
        <C1AnalyticsQuery />

        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="bg-gradient-to-br from-blue-50 to-blue-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-blue-600 font-medium">Emails Sent</p>
                  <p className="text-2xl font-bold text-blue-900">
                    {overview.emails_sent_this_month.toLocaleString()}
                  </p>
                </div>
                <div className="w-12 h-12 bg-blue-200 rounded-lg flex items-center justify-center">
                  <Mail className="w-6 h-6 text-blue-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-blue-600">
                <span>This month</span>
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-green-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-green-600 font-medium">Open Rate</p>
                  <p className="text-2xl font-bold text-green-900">{overview.open_rate.toFixed(1)}%</p>
                </div>
                <div className="w-12 h-12 bg-green-200 rounded-lg flex items-center justify-center">
                  <Eye className="w-6 h-6 text-green-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-green-600">
                {overview.open_rate >= 50 ? (
                  <>
                    <TrendingUp className="w-4 h-4" />
                    <span>Excellent performance</span>
                  </>
                ) : (
                  <span>Industry average: 21%</span>
                )}
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-purple-50 to-purple-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-purple-600 font-medium">Click Rate</p>
                  <p className="text-2xl font-bold text-purple-900">{overview.click_rate.toFixed(1)}%</p>
                </div>
                <div className="w-12 h-12 bg-purple-200 rounded-lg flex items-center justify-center">
                  <MousePointer className="w-6 h-6 text-purple-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-purple-600">
                {overview.click_rate >= 10 ? (
                  <>
                    <TrendingUp className="w-4 h-4" />
                    <span>Great engagement</span>
                  </>
                ) : (
                  <span>Industry average: 2.6%</span>
                )}
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-red-50 to-red-100">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-red-600 font-medium">Bounce Rate</p>
                  <p className="text-2xl font-bold text-red-900">{overview.bounce_rate.toFixed(1)}%</p>
                </div>
                <div className="w-12 h-12 bg-red-200 rounded-lg flex items-center justify-center">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
              </div>
              <div className="flex items-center gap-1 mt-2 text-sm text-red-600">
                {overview.bounce_rate < 5 ? (
                  <>
                    <TrendingDown className="w-4 h-4" />
                    <span>Healthy rate</span>
                  </>
                ) : (
                  <>
                    <TrendingUp className="w-4 h-4" />
                    <span>Review email list quality</span>
                  </>
                )}
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
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
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
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  No activity data for this period
                </div>
              )}
            </div>
          </Card>

          {/* Engagement Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Engagement Breakdown</CardTitle>
            </CardHeader>
            <div className="p-4 h-64">
              {engagementData.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={engagementData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {engagementData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex justify-center gap-4 mt-2">
                    {engagementData.map((item) => (
                      <div key={item.name} className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                        <span className="text-xs text-gray-600">{item.name}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  No engagement data yet
                </div>
              )}
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
              {domainStats.length > 0 ? (
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Domain
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Sent
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Open Rate
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Click Rate
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {domainStats.slice(0, 5).map((domain, idx) => (
                      <tr key={domain.domain || idx} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm font-medium text-gray-900">
                          {domain.domain || domain.domain_name || 'Unknown'}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 text-right">
                          {domain.total_sent.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 text-right">
                          <span className="text-green-600">{domain.open_rate.toFixed(1)}%</span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 text-right">
                          {domain.click_rate.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-6 text-center text-gray-500">No domain data available</div>
              )}
            </div>
          </Card>

          {/* Recent Campaigns */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Campaigns</CardTitle>
            </CardHeader>
            <div className="overflow-x-auto">
              {overview.recent_campaigns.length > 0 ? (
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Campaign
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Sent
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Open Rate
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {overview.recent_campaigns.map((campaign) => (
                      <tr key={campaign.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm font-medium text-gray-900">
                          {campaign.name}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 text-right">
                          {campaign.sent.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600 text-right">
                          {campaign.open_rate.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-6 text-center text-gray-500">No campaigns yet</div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default AnalyticsPage;
