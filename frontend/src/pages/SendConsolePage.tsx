import { useState, useEffect } from 'react';
import {
  Send,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Button, Input, Textarea } from '../components/ui';
import { useSendingStore } from '../store/sendingStore';
import { useDomainStore } from '../store/domainStore';
import { clsx } from 'clsx';

export function SendConsolePage() {
  const { stats, isLoading, error, fetchStats, sendEmail, clearError } = useSendingStore();
  const { domains } = useDomainStore();

  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [htmlBody, setHtmlBody] = useState('');
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [trackOpens, setTrackOpens] = useState(true);
  const [trackClicks, setTrackClicks] = useState(true);
  const [sendResult, setSendResult] = useState<{
    success: boolean;
    message_id?: string;
    status?: string;
  } | null>(null);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  useEffect(() => {
    if (domains.length > 0 && !selectedDomain) {
      const verified = domains.find((d) => d.status === 'verified');
      if (verified) setSelectedDomain(verified.id);
    }
  }, [domains, selectedDomain]);

  const handleSend = async () => {
    if (!to || !subject || !htmlBody) {
      alert('Please fill in all required fields');
      return;
    }

    clearError();
    setSendResult(null);

    try {
      const result = await sendEmail({
        to,
        subject,
        html_body: htmlBody,
        domain_id: selectedDomain || undefined,
        track_opens: trackOpens,
        track_clicks: trackClicks,
      });
      setSendResult({ success: true, message_id: result.message_id, status: result.status });
      setTo('');
      setSubject('');
      setHtmlBody('');
    } catch (err) {
      setSendResult({ success: false });
    }
  };

  const verifiedDomains = domains.filter((d) => d.status === 'verified');

  return (
    <div className="h-full">
      <Header
        title="Send Console"
        subtitle="Send individual emails or test your email configuration"
      />

      <div className="p-6 space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        {sendResult && (
          <div className={clsx(
            'border rounded-lg p-4 flex items-center gap-2',
            sendResult.success ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'
          )}>
            {sendResult.success ? (
              <CheckCircle className="w-5 h-5" />
            ) : (
              <XCircle className="w-5 h-5" />
            )}
            <span>
              {sendResult.success
                ? `Email sent successfully! Message ID: ${sendResult.message_id}`
                : 'Failed to send email'
              }
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Send Form */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>Send Email</CardTitle>
              </CardHeader>
              <div className="p-4 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    From Domain *
                  </label>
                  <select
                    value={selectedDomain}
                    onChange={(e) => setSelectedDomain(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select a domain</option>
                    {verifiedDomains.map((domain) => (
                      <option key={domain.id} value={domain.id}>
                        {domain.domain_name}
                      </option>
                    ))}
                  </select>
                  {verifiedDomains.length === 0 && (
                    <p className="text-xs text-yellow-600 mt-1">
                      No verified domains. Please verify a domain first.
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    To (Email) *
                  </label>
                  <Input
                    type="email"
                    value={to}
                    onChange={(e) => setTo(e.target.value)}
                    placeholder="recipient@example.com"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Subject *
                  </label>
                  <Input
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="Your email subject"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    HTML Body *
                  </label>
                  <Textarea
                    value={htmlBody}
                    onChange={(e) => setHtmlBody(e.target.value)}
                    placeholder="<html><body><p>Hello!</p></body></html>"
                    rows={10}
                  />
                </div>

                <div className="flex items-center gap-6">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={trackOpens}
                      onChange={(e) => setTrackOpens(e.target.checked)}
                      className="w-4 h-4 rounded"
                    />
                    <span className="text-sm">Track opens</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={trackClicks}
                      onChange={(e) => setTrackClicks(e.target.checked)}
                      className="w-4 h-4 rounded"
                    />
                    <span className="text-sm">Track clicks</span>
                  </label>
                </div>

                <Button
                  onClick={handleSend}
                  disabled={isLoading || verifiedDomains.length === 0}
                  className="w-full"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    <>
                      <Send className="w-4 h-4 mr-2" />
                      Send Email
                    </>
                  )}
                </Button>
              </div>
            </Card>
          </div>

          {/* Stats & Quick Send */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Today's Stats</CardTitle>
              </CardHeader>
              <div className="p-4 space-y-4">
                {stats ? (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="text-center p-3 bg-gray-50 rounded-lg">
                        <div className="text-2xl font-bold text-blue-600">{stats.today_sent}</div>
                        <div className="text-xs text-gray-500">Sent</div>
                      </div>
                      <div className="text-center p-3 bg-gray-50 rounded-lg">
                        <div className="text-2xl font-bold text-gray-600">{stats.today_limit}</div>
                        <div className="text-xs text-gray-500">Limit</div>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Open Rate</span>
                        <span className="font-medium">{stats.open_rate}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Click Rate</span>
                        <span className="font-medium">{stats.click_rate}%</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Bounce Rate</span>
                        <span className="font-medium">{stats.bounce_rate}%</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-gray-500">No data available</p>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Quick Tips</CardTitle>
              </CardHeader>
              <div className="p-4 space-y-3 text-sm text-gray-600">
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500 mt-0.5" />
                  <span>Use verified domains for better deliverability</span>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500 mt-0.5" />
                  <span>Keep subject lines clear and relevant</span>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500 mt-0.5" />
                  <span>Enable tracking to monitor engagement</span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SendConsolePage;