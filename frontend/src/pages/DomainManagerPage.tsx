import { useEffect, useState } from 'react';
import {
  Globe,
  Plus,
  Trash2,
  RefreshCw,
  Check,
  AlertTriangle,
  Clock,
  ExternalLink,
  Search,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Button, Badge } from '../components/ui';
import { useDomainStore } from '../store/domainStore';
import { clsx } from 'clsx';

const statusColors: Record<string, { bg: string; text: string }> = {
  pending: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  verifying: { bg: 'bg-brand-purple/10', text: 'text-brand-purple' },
  verified: { bg: 'bg-green-100', text: 'text-green-800' },
  failed: { bg: 'bg-red-100', text: 'text-red-800' },
};

export function DomainManagerPage() {
  const {
    domains,
    isLoading,
    error,
    fetchDomains,
    createDomain,
    deleteDomain,
    verifyDomain,
    fetchDomainHealth,
    fetchDNSRecords,
    domainHealth,
    dnsRecords,
  } = useDomainStore();

  const [showAddModal, setShowAddModal] = useState(false);
  const [newDomainName, setNewDomainName] = useState('');
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [showDNSRecords, setShowDNSRecords] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetchDomains();
  }, [fetchDomains]);

  const handleAddDomain = async () => {
    if (!newDomainName.trim()) return;
    await createDomain(newDomainName.trim());
    setNewDomainName('');
    setShowAddModal(false);
  };

  const handleVerify = async (domainId: string) => {
    await verifyDomain(domainId);
  };

  const handleDelete = async (domainId: string) => {
    if (confirm('Are you sure you want to delete this domain?')) {
      await deleteDomain(domainId);
    }
  };

  const handleSelectDomain = async (domainId: string) => {
    setSelectedDomain(domainId);
    await fetchDomainHealth(domainId);
    await fetchDNSRecords(domainId);
  };

  const filteredDomains = domains.filter((d) =>
    d.domain_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const selectedDomainData = domains.find((d) => d.id === selectedDomain);
  const selectedHealth = domainHealth[selectedDomain || ''];
  const selectedDNS = dnsRecords[selectedDomain || ''] || [];

  return (
    <div className="h-full">
      <Header
        title="Domain Manager"
        subtitle="Manage your sending domains and DNS configuration"
        actions={
          <Button onClick={() => setShowAddModal(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Add Domain
          </Button>
        }
      />

      <div className="p-6 space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        <div className="flex gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search domains..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
            />
          </div>
          <Button variant="outline" onClick={() => fetchDomains()}>
            <RefreshCw className={clsx('w-4 h-4 mr-2', isLoading && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Domain List */}
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Your Domains</CardTitle>
              </CardHeader>
              <div className="divide-y">
                {filteredDomains.length === 0 ? (
                  <div className="p-8 text-center text-gray-500">
                    <Globe className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                    <p>No domains yet</p>
                    <p className="text-sm">Add your first sending domain to get started</p>
                  </div>
                ) : (
                  filteredDomains.map((domain) => (
                    <div
                      key={domain.id}
                      className={clsx(
                        'p-4 cursor-pointer transition-colors hover:bg-gray-50',
                        selectedDomain === domain.id && 'bg-brand-purple/5'
                      )}
                      onClick={() => handleSelectDomain(domain.id)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
                            <Globe className="w-5 h-5 text-gray-600" />
                          </div>
                          <div>
                            <div className="font-medium">{domain.domain_name}</div>
                            <div className="text-sm text-gray-500">
                              {domain.sent_today}/{domain.daily_send_limit} sent today
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge className={statusColors[domain.status]?.bg + ' ' + statusColors[domain.status]?.text}>
                            {domain.status}
                          </Badge>
                          <div className="text-right">
                            <div className="text-sm font-medium">{domain.health_score}%</div>
                            <div className="text-xs text-gray-500">health</div>
                          </div>
                        </div>
                      </div>

                      {/* DNS Status */}
                      <div className="mt-3 flex gap-4 text-xs">
                        <span className={clsx('flex items-center gap-1', domain.mx_verified ? 'text-green-600' : 'text-gray-400')}>
                          MX {domain.mx_verified ? '✓' : '○'}
                        </span>
                        <span className={clsx('flex items-center gap-1', domain.spf_verified ? 'text-green-600' : 'text-gray-400')}>
                          SPF {domain.spf_verified ? '✓' : '○'}
                        </span>
                        <span className={clsx('flex items-center gap-1', domain.dkim_verified ? 'text-green-600' : 'text-gray-400')}>
                          DKIM {domain.dkim_verified ? '✓' : '○'}
                        </span>
                        <span className={clsx('flex items-center gap-1', domain.dmarc_verified ? 'text-green-600' : 'text-gray-400')}>
                          DMARC {domain.dmarc_verified ? '✓' : '○'}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>

          {/* Domain Details */}
          <div className="space-y-4">
            {selectedDomainData ? (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle>{selectedDomainData.domain_name}</CardTitle>
                  </CardHeader>
                  <div className="p-4 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-sm text-gray-500">Status</div>
                        <Badge className={statusColors[selectedDomainData.status]?.bg + ' ' + statusColors[selectedDomainData.status]?.text}>
                          {selectedDomainData.status}
                        </Badge>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Health Score</div>
                        <div className={clsx(
                          'text-lg font-bold',
                          (selectedHealth?.health_score || 100) >= 80 ? 'text-green-600' :
                          (selectedHealth?.health_score || 100) >= 50 ? 'text-yellow-600' : 'text-red-600'
                        )}>
                          {selectedHealth?.health_score || selectedDomainData.health_score}%
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Sent Today</div>
                        <div className="text-lg font-bold">{selectedDomainData.sent_today}</div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-500">Daily Limit</div>
                        <div className="text-lg font-bold">{selectedDomainData.daily_send_limit}</div>
                      </div>
                    </div>

                    {selectedDomainData.warmup_enabled && (
                      <div className="bg-brand-purple/5 rounded-lg p-3">
                        <div className="flex items-center gap-2 text-brand-purple">
                          <Clock className="w-4 h-4" />
                          <span className="text-sm font-medium">Warmup in progress</span>
                        </div>
                        <div className="text-sm text-brand-purple mt-1">
                          Day {selectedDomainData.warmup_day}/30
                        </div>
                      </div>
                    )}

                    <div className="flex gap-2">
                      {selectedDomainData.status !== 'verified' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleVerify(selectedDomainData.id)}
                          disabled={isLoading}
                        >
                          <Check className="w-4 h-4 mr-1" />
                          Verify DNS
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowDNSRecords(showDNSRecords === selectedDomainData.id ? null : selectedDomainData.id)}
                      >
                        <ExternalLink className="w-4 h-4 mr-1" />
                        DNS Records
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDelete(selectedDomainData.id)}
                        className="text-red-600 hover:bg-red-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </Card>

                {/* DNS Records */}
                {showDNSRecords === selectedDomainData.id && (
                  <Card>
                    <CardHeader>
                      <CardTitle>DNS Records</CardTitle>
                    </CardHeader>
                    <div className="p-4 space-y-2">
                      {selectedDNS.length === 0 ? (
                        <p className="text-sm text-gray-500">No DNS records configured</p>
                      ) : (
                        selectedDNS.map((record, index) => (
                          <div key={index} className="bg-gray-50 rounded p-2 text-sm">
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{record.type}</span>
                              <span className="text-xs text-gray-500">TTL: {record.ttl}</span>
                            </div>
                            <div className="text-xs text-gray-600 break-all">{record.name}</div>
                            <div className="text-xs text-gray-800 mt-1 break-all">{record.value}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </Card>
                )}
              </>
            ) : (
              <Card>
                <div className="p-8 text-center text-gray-500">
                  <Globe className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                  <p>Select a domain to view details</p>
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>

      {/* Add Domain Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-semibold mb-4">Add New Domain</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Domain Name
                </label>
                <input
                  type="text"
                  value={newDomainName}
                  onChange={(e) => setNewDomainName(e.target.value)}
                  placeholder="e.g., outreach.yourcompany.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
                />
              </div>
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-700">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <p>You'll need to configure DNS records after adding the domain.</p>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <Button variant="outline" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button onClick={handleAddDomain} disabled={!newDomainName.trim()}>
                Add Domain
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DomainManagerPage;