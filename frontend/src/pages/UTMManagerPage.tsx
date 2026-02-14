import { useState, useEffect, useCallback } from 'react';
import {
  Link2,
  Plus,
  Trash2,
  Pencil,
  Star,
  Save,
  X,
  Eye,
  Zap,
  MousePointer,
  BarChart3,
  ExternalLink,
  Settings2,
  Tag,
  Activity,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Header } from '../components/layout';
import { Card, CardHeader, CardTitle, Button, Badge, Input } from '../components/ui';
import { utmApi } from '../api/utm';
import { campaignsApi } from '../api/campaigns';
import type {
  UTMPreset,
  UTMPresetCreate,
  CampaignUTMConfig,
  UTMOverview,
  UTMBreakdownItem,
  LinkPerformanceItem,
} from '../api/utm';
import type { Campaign } from '../api/campaigns';

// ============================================================
// Constants
// ============================================================

const TABS = [
  { id: 'presets', label: 'Presets', icon: Tag },
  { id: 'config', label: 'Campaign Config', icon: Settings2 },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'links', label: 'Link Performance', icon: Activity },
] as const;

type TabId = (typeof TABS)[number]['id'];

const CHART_COLORS = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
];

const TEMPLATE_VARIABLES = [
  '{{campaign_name_slug}}',
  '{{segment}}',
  '{{prospect_company}}',
  '{{date}}',
];

const EMPTY_PRESET_FORM: UTMPresetCreate = {
  name: '',
  utm_source: 'champmail',
  utm_medium: 'email',
  utm_campaign: '',
  utm_content: '',
  utm_term: '',
};

// ============================================================
// Sub-components
// ============================================================

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
    </div>
  );
}

function EmptyState({ icon: Icon, title, description }: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <Card className="bg-blue-50 border-blue-200">
      <div className="p-6 text-center">
        <Icon className="w-12 h-12 text-blue-600 mx-auto mb-3" />
        <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
        <p className="text-gray-600">{description}</p>
      </div>
    </Card>
  );
}

function CampaignSelector({
  campaigns,
  selectedId,
  onSelect,
  loading,
}: {
  campaigns: Campaign[];
  selectedId: string;
  onSelect: (id: string) => void;
  loading: boolean;
}) {
  return (
    <div className="w-full max-w-md">
      <label className="block text-sm font-medium text-slate-700 mb-1.5">
        Select Campaign
      </label>
      <select
        value={selectedId}
        onChange={(e) => onSelect(e.target.value)}
        disabled={loading}
        className="w-full h-10 px-3 rounded-lg border border-slate-300 bg-white text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-200 disabled:bg-slate-50 disabled:cursor-not-allowed"
      >
        <option value="">-- Choose a campaign --</option>
        {campaigns.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.status})
          </option>
        ))}
      </select>
    </div>
  );
}

// ============================================================
// Tab 1: Presets
// ============================================================

function PresetsTab() {
  const [presets, setPresets] = useState<UTMPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<UTMPresetCreate>({ ...EMPTY_PRESET_FORM });
  const [saving, setSaving] = useState(false);

  const loadPresets = useCallback(async () => {
    try {
      setLoading(true);
      const data = await utmApi.getPresets();
      setPresets(data);
    } catch (error) {
      console.error('Failed to load UTM presets:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPresets();
  }, [loadPresets]);

  const handleSave = async () => {
    if (!form.name.trim()) return;
    try {
      setSaving(true);
      if (editingId) {
        await utmApi.updatePreset(editingId, form);
      } else {
        await utmApi.createPreset(form);
      }
      setShowForm(false);
      setEditingId(null);
      setForm({ ...EMPTY_PRESET_FORM });
      await loadPresets();
    } catch (error) {
      console.error('Failed to save preset:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (preset: UTMPreset) => {
    setEditingId(preset.id);
    setForm({
      name: preset.name,
      utm_source: preset.utm_source || '',
      utm_medium: preset.utm_medium || '',
      utm_campaign: preset.utm_campaign || '',
      utm_content: preset.utm_content || '',
      utm_term: preset.utm_term || '',
    });
    setShowForm(true);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this preset?')) return;
    try {
      await utmApi.deletePreset(id);
      await loadPresets();
    } catch (error) {
      console.error('Failed to delete preset:', error);
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await utmApi.setDefaultPreset(id);
      await loadPresets();
    } catch (error) {
      console.error('Failed to set default preset:', error);
    }
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingId(null);
    setForm({ ...EMPTY_PRESET_FORM });
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      {/* Header with Create button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">UTM Presets</h2>
          <p className="text-sm text-slate-500">
            Manage reusable UTM parameter templates for your campaigns.
          </p>
        </div>
        {!showForm && (
          <Button
            onClick={() => {
              setForm({ ...EMPTY_PRESET_FORM });
              setEditingId(null);
              setShowForm(true);
            }}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Create Preset
          </Button>
        )}
      </div>

      {/* Create / Edit form */}
      {showForm && (
        <Card padding="lg">
          <CardHeader>
            <CardTitle>{editingId ? 'Edit Preset' : 'Create New Preset'}</CardTitle>
          </CardHeader>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <Input
              label="Preset Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Default Email Campaign"
            />
            <Input
              label="UTM Source"
              value={form.utm_source || ''}
              onChange={(e) => setForm({ ...form, utm_source: e.target.value })}
              placeholder="champmail"
            />
            <Input
              label="UTM Medium"
              value={form.utm_medium || ''}
              onChange={(e) => setForm({ ...form, utm_medium: e.target.value })}
              placeholder="email"
            />
            <Input
              label="UTM Campaign"
              value={form.utm_campaign || ''}
              onChange={(e) => setForm({ ...form, utm_campaign: e.target.value })}
              placeholder="{{campaign_name_slug}}"
            />
            <Input
              label="UTM Content"
              value={form.utm_content || ''}
              onChange={(e) => setForm({ ...form, utm_content: e.target.value })}
              placeholder="Optional"
            />
            <Input
              label="UTM Term"
              value={form.utm_term || ''}
              onChange={(e) => setForm({ ...form, utm_term: e.target.value })}
              placeholder="Optional"
            />
          </div>
          <div className="mt-3">
            <p className="text-xs text-slate-500">
              Available variables:{' '}
              {TEMPLATE_VARIABLES.map((v, i) => (
                <span key={v}>
                  <code className="bg-slate-100 px-1 py-0.5 rounded text-blue-600">
                    {v}
                  </code>
                  {i < TEMPLATE_VARIABLES.length - 1 && ', '}
                </span>
              ))}
            </p>
          </div>
          <div className="flex items-center gap-3 mt-5">
            <Button onClick={handleSave} isLoading={saving} leftIcon={<Save className="h-4 w-4" />}>
              {editingId ? 'Update Preset' : 'Save Preset'}
            </Button>
            <Button variant="outline" onClick={handleCancel} leftIcon={<X className="h-4 w-4" />}>
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {/* Presets Table */}
      {presets.length === 0 ? (
        <EmptyState
          icon={Tag}
          title="No Presets Yet"
          description="Create your first UTM preset to standardize tracking across campaigns."
        />
      ) : (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Medium
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Campaign
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Content
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Term
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                    Default
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {presets.map((preset) => (
                  <tr key={preset.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">
                      {preset.name}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {preset.utm_source || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {preset.utm_medium || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 font-mono text-xs">
                      {preset.utm_campaign || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {preset.utm_content || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {preset.utm_term || '--'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {preset.is_default ? (
                        <Badge variant="success">Default</Badge>
                      ) : (
                        <button
                          onClick={() => handleSetDefault(preset.id)}
                          className="text-slate-400 hover:text-yellow-500 transition-colors"
                          title="Set as default"
                        >
                          <Star className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleEdit(preset)}
                          className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(preset.id)}
                          className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

// ============================================================
// Tab 2: Campaign Config
// ============================================================

function CampaignConfigTab() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [presets, setPresets] = useState<UTMPreset[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState('');
  const [, setConfig] = useState<CampaignUTMConfig | null>(null);
  const [previewLinks, setPreviewLinks] = useState<LinkPerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [configLoading, setConfigLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Local override fields
  const [overrideSource, setOverrideSource] = useState('');
  const [overrideMedium, setOverrideMedium] = useState('');
  const [overrideCampaign, setOverrideCampaign] = useState('');
  const [overrideContent, setOverrideContent] = useState('');
  const [overrideTerm, setOverrideTerm] = useState('');
  const [preserveExisting, setPreserveExisting] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [selectedPresetId, setSelectedPresetId] = useState('');

  useEffect(() => {
    const loadInitial = async () => {
      try {
        setLoading(true);
        const [campaignData, presetData] = await Promise.all([
          campaignsApi.list(200),
          utmApi.getPresets(),
        ]);
        setCampaigns(campaignData.campaigns);
        setPresets(presetData);
      } catch (error) {
        console.error('Failed to load campaigns/presets:', error);
      } finally {
        setLoading(false);
      }
    };
    loadInitial();
  }, []);

  const loadConfig = useCallback(async (campaignId: string) => {
    if (!campaignId) {
      setConfig(null);
      return;
    }
    try {
      setConfigLoading(true);
      const data = await utmApi.getCampaignConfig(campaignId);
      setConfig(data);
      setEnabled(data.enabled);
      setSelectedPresetId(data.preset_id || '');
      setOverrideSource(data.utm_source || '');
      setOverrideMedium(data.utm_medium || '');
      setOverrideCampaign(data.utm_campaign || '');
      setOverrideContent(data.utm_content || '');
      setOverrideTerm(data.utm_term || '');
      setPreserveExisting(data.preserve_existing_utm);
    } catch {
      // No config exists yet - reset to defaults
      setConfig(null);
      setEnabled(false);
      setSelectedPresetId('');
      setOverrideSource('');
      setOverrideMedium('');
      setOverrideCampaign('');
      setOverrideContent('');
      setOverrideTerm('');
      setPreserveExisting(true);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedCampaignId) {
      loadConfig(selectedCampaignId);
      setShowPreview(false);
      setPreviewLinks([]);
    }
  }, [selectedCampaignId, loadConfig]);

  const handleSaveConfig = async () => {
    if (!selectedCampaignId) return;
    try {
      setSaving(true);
      await utmApi.updateCampaignConfig(selectedCampaignId, {
        enabled,
        preset_id: selectedPresetId || undefined,
        utm_source: overrideSource || undefined,
        utm_medium: overrideMedium || undefined,
        utm_campaign: overrideCampaign || undefined,
        utm_content: overrideContent || undefined,
        utm_term: overrideTerm || undefined,
        preserve_existing_utm: preserveExisting,
      });
      await loadConfig(selectedCampaignId);
    } catch (error) {
      console.error('Failed to save UTM config:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleAutoGenerate = async () => {
    if (!selectedCampaignId) return;
    try {
      setConfigLoading(true);
      await utmApi.autoGenerateConfig(selectedCampaignId);
      await loadConfig(selectedCampaignId);
    } catch (error) {
      console.error('Failed to auto-generate config:', error);
    } finally {
      setConfigLoading(false);
    }
  };

  const handlePreview = async () => {
    if (!selectedCampaignId) return;
    try {
      setPreviewLoading(true);
      const links = await utmApi.previewLinks(selectedCampaignId);
      setPreviewLinks(links);
      setShowPreview(true);
    } catch (error) {
      console.error('Failed to preview links:', error);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Find the selected preset to show placeholder values
  const activePreset = presets.find((p) => p.id === selectedPresetId);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Campaign UTM Configuration</h2>
        <p className="text-sm text-slate-500">
          Configure UTM tracking parameters for individual campaigns.
        </p>
      </div>

      <CampaignSelector
        campaigns={campaigns}
        selectedId={selectedCampaignId}
        onSelect={setSelectedCampaignId}
        loading={false}
      />

      {!selectedCampaignId && (
        <EmptyState
          icon={Settings2}
          title="Select a Campaign"
          description="Choose a campaign from the dropdown above to configure its UTM parameters."
        />
      )}

      {selectedCampaignId && configLoading && <LoadingSpinner />}

      {selectedCampaignId && !configLoading && (
        <Card padding="lg">
          <div className="space-y-6">
            {/* Enable toggle */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-900">Enable UTM Tracking</p>
                <p className="text-xs text-slate-500">
                  Automatically append UTM parameters to all links in this campaign.
                </p>
              </div>
              <button
                onClick={() => setEnabled(!enabled)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  enabled ? 'bg-blue-600' : 'bg-slate-300'
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    enabled ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            {enabled && (
              <>
                {/* Preset selector */}
                <div className="w-full max-w-md">
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">
                    Apply Preset
                  </label>
                  <select
                    value={selectedPresetId}
                    onChange={(e) => setSelectedPresetId(e.target.value)}
                    className="w-full h-10 px-3 rounded-lg border border-slate-300 bg-white text-sm outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                  >
                    <option value="">-- No preset (manual) --</option>
                    {presets.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} {p.is_default ? '(default)' : ''}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Override fields */}
                <div>
                  <p className="text-sm font-medium text-slate-700 mb-3">
                    Override Parameters{' '}
                    <span className="font-normal text-slate-400">
                      (leave blank to use preset values)
                    </span>
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <Input
                      label="Source"
                      value={overrideSource}
                      onChange={(e) => setOverrideSource(e.target.value)}
                      placeholder={activePreset?.utm_source || 'champmail'}
                    />
                    <Input
                      label="Medium"
                      value={overrideMedium}
                      onChange={(e) => setOverrideMedium(e.target.value)}
                      placeholder={activePreset?.utm_medium || 'email'}
                    />
                    <Input
                      label="Campaign"
                      value={overrideCampaign}
                      onChange={(e) => setOverrideCampaign(e.target.value)}
                      placeholder={activePreset?.utm_campaign || '{{campaign_name_slug}}'}
                    />
                    <Input
                      label="Content"
                      value={overrideContent}
                      onChange={(e) => setOverrideContent(e.target.value)}
                      placeholder={activePreset?.utm_content || 'optional'}
                    />
                    <Input
                      label="Term"
                      value={overrideTerm}
                      onChange={(e) => setOverrideTerm(e.target.value)}
                      placeholder={activePreset?.utm_term || 'optional'}
                    />
                  </div>
                </div>

                {/* Preserve existing */}
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={preserveExisting}
                    onChange={(e) => setPreserveExisting(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      Preserve existing UTM parameters
                    </p>
                    <p className="text-xs text-slate-500">
                      If a link already has UTM params, keep them instead of overwriting.
                    </p>
                  </div>
                </label>
              </>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-3 pt-2 border-t border-slate-200">
              <Button
                onClick={handleSaveConfig}
                isLoading={saving}
                leftIcon={<Save className="h-4 w-4" />}
              >
                Save Config
              </Button>
              <Button
                variant="outline"
                onClick={handleAutoGenerate}
                leftIcon={<Zap className="h-4 w-4" />}
              >
                Auto-Generate
              </Button>
              <Button
                variant="outline"
                onClick={handlePreview}
                isLoading={previewLoading}
                leftIcon={<Eye className="h-4 w-4" />}
              >
                Preview Links
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Preview Links Table */}
      {showPreview && previewLinks.length > 0 && (
        <Card padding="none">
          <div className="px-4 py-3 border-b border-slate-200">
            <h3 className="text-sm font-semibold text-slate-900">
              Link Preview ({previewLinks.length} links)
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    URL
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Medium
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Campaign
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {previewLinks.map((link, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-blue-600 font-mono text-xs max-w-xs truncate">
                      {link.original_url.length > 60
                        ? link.original_url.slice(0, 60) + '...'
                        : link.original_url}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.utm_source || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.utm_medium || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.utm_campaign || '--'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {showPreview && previewLinks.length === 0 && (
        <EmptyState
          icon={Link2}
          title="No Links Found"
          description="This campaign's template does not contain any trackable links."
        />
      )}
    </div>
  );
}

// ============================================================
// Tab 3: Analytics
// ============================================================

function AnalyticsTab() {
  const [overview, setOverview] = useState<UTMOverview | null>(null);
  const [sourceBreakdown, setSourceBreakdown] = useState<UTMBreakdownItem[]>([]);
  const [campaignBreakdown, setCampaignBreakdown] = useState<UTMBreakdownItem[]>([]);
  const [period, setPeriod] = useState<7 | 30 | 90>(30);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [overviewData, sources, campaigns] = await Promise.all([
        utmApi.getOverview(),
        utmApi.getBreakdown('source', undefined, period),
        utmApi.getBreakdown('campaign', undefined, period),
      ]);
      setOverview(overviewData);
      setSourceBreakdown(sources);
      setCampaignBreakdown(campaigns);
    } catch (error) {
      console.error('Failed to load UTM analytics:', error);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <LoadingSpinner />;

  if (!overview) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No Analytics Data Yet"
        description="Enable UTM tracking on your campaigns to start collecting analytics."
      />
    );
  }

  const sourceChartData = sourceBreakdown.slice(0, 7).map((item) => ({
    name: item.group_value || 'Unknown',
    clicks: item.total_clicks,
    unique: item.unique_clicks,
  }));

  const campaignChartData = campaignBreakdown.slice(0, 7).map((item) => ({
    name:
      item.group_value.length > 20
        ? item.group_value.slice(0, 20) + '...'
        : item.group_value || 'Unknown',
    clicks: item.total_clicks,
    unique: item.unique_clicks,
  }));

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">UTM Analytics</h2>
          <p className="text-sm text-slate-500">
            Track UTM parameter performance across campaigns.
          </p>
        </div>
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
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100">
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-600 font-medium">Tracked Links</p>
                <p className="text-2xl font-bold text-blue-900">
                  {overview.total_tracked_links.toLocaleString()}
                </p>
              </div>
              <div className="w-12 h-12 bg-blue-200 rounded-lg flex items-center justify-center">
                <Link2 className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-green-50 to-green-100">
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-green-600 font-medium">Total Clicks</p>
                <p className="text-2xl font-bold text-green-900">
                  {overview.total_clicks.toLocaleString()}
                </p>
              </div>
              <div className="w-12 h-12 bg-green-200 rounded-lg flex items-center justify-center">
                <MousePointer className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-purple-50 to-purple-100">
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-purple-600 font-medium">Unique Clicks</p>
                <p className="text-2xl font-bold text-purple-900">
                  {overview.unique_clicks.toLocaleString()}
                </p>
              </div>
              <div className="w-12 h-12 bg-purple-200 rounded-lg flex items-center justify-center">
                <ExternalLink className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </div>
        </Card>

        <Card className="bg-gradient-to-br from-amber-50 to-amber-100">
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-amber-600 font-medium">Click Rate</p>
                <p className="text-2xl font-bold text-amber-900">
                  {overview.overall_click_rate.toFixed(1)}%
                </p>
              </div>
              <div className="w-12 h-12 bg-amber-200 rounded-lg flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-amber-600" />
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Sources */}
        <Card>
          <CardHeader>
            <CardTitle>Top UTM Sources</CardTitle>
          </CardHeader>
          <div className="p-4 h-80">
            {sourceChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sourceChartData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" stroke="#9ca3af" />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="#9ca3af"
                    width={100}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="clicks" fill={CHART_COLORS[0]} radius={[0, 4, 4, 0]} name="Total Clicks" />
                  <Bar dataKey="unique" fill={CHART_COLORS[1]} radius={[0, 4, 4, 0]} name="Unique Clicks" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                No source data for this period
              </div>
            )}
          </div>
        </Card>

        {/* Top Campaigns */}
        <Card>
          <CardHeader>
            <CardTitle>Top UTM Campaigns</CardTitle>
          </CardHeader>
          <div className="p-4 h-80">
            {campaignChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={campaignChartData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" stroke="#9ca3af" />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="#9ca3af"
                    width={140}
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="clicks" fill={CHART_COLORS[4]} radius={[0, 4, 4, 0]} name="Total Clicks" />
                  <Bar dataKey="unique" fill={CHART_COLORS[5]} radius={[0, 4, 4, 0]} name="Unique Clicks" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                No campaign data for this period
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ============================================================
// Tab 4: Link Performance
// ============================================================

function LinkPerformanceTab() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState('');
  const [links, setLinks] = useState<LinkPerformanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [linksLoading, setLinksLoading] = useState(false);

  useEffect(() => {
    const loadCampaigns = async () => {
      try {
        setLoading(true);
        const data = await campaignsApi.list(200);
        setCampaigns(data.campaigns);
      } catch (error) {
        console.error('Failed to load campaigns:', error);
      } finally {
        setLoading(false);
      }
    };
    loadCampaigns();
  }, []);

  useEffect(() => {
    if (!selectedCampaignId) {
      setLinks([]);
      return;
    }
    const loadLinks = async () => {
      try {
        setLinksLoading(true);
        const data = await utmApi.getLinkPerformance(selectedCampaignId);
        // Sort by click_count descending
        data.sort((a, b) => b.click_count - a.click_count);
        setLinks(data);
      } catch (error) {
        console.error('Failed to load link performance:', error);
        setLinks([]);
      } finally {
        setLinksLoading(false);
      }
    };
    loadLinks();
  }, [selectedCampaignId]);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Link Performance</h2>
        <p className="text-sm text-slate-500">
          Analyze click performance for individual links within a campaign.
        </p>
      </div>

      <CampaignSelector
        campaigns={campaigns}
        selectedId={selectedCampaignId}
        onSelect={setSelectedCampaignId}
        loading={false}
      />

      {!selectedCampaignId && (
        <EmptyState
          icon={Activity}
          title="Select a Campaign"
          description="Choose a campaign to view link-level performance data."
        />
      )}

      {selectedCampaignId && linksLoading && <LoadingSpinner />}

      {selectedCampaignId && !linksLoading && links.length === 0 && (
        <EmptyState
          icon={Link2}
          title="No Link Data"
          description="No tracked links found for this campaign. Enable UTM tracking and send the campaign to collect data."
        />
      )}

      {selectedCampaignId && !linksLoading && links.length > 0 && (
        <Card padding="none">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    URL
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Anchor Text
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Medium
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Campaign
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    Clicks
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                    Unique
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    First Clicked
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {links.map((link, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm font-mono text-xs text-blue-600 max-w-xs">
                      <span title={link.original_url}>
                        {link.original_url.length > 60
                          ? link.original_url.slice(0, 60) + '...'
                          : link.original_url}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.anchor_text || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.utm_source || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.utm_medium || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {link.utm_campaign || '--'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 font-semibold text-right">
                      {link.click_count.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 text-right">
                      {link.unique_clicks.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {link.first_clicked_at
                        ? new Date(link.first_clicked_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })
                        : '--'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

// ============================================================
// Main Page Component
// ============================================================

export function UTMManagerPage() {
  const [activeTab, setActiveTab] = useState<TabId>('presets');

  return (
    <div className="h-full">
      <Header
        title="UTM Manager"
        subtitle="Manage UTM tracking parameters, presets, and link analytics"
      />

      <div className="p-6 space-y-6">
        {/* Tab Navigation */}
        <div className="border-b border-slate-200">
          <nav className="flex gap-6" aria-label="UTM Manager tabs">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 pb-3 text-sm font-medium transition-colors border-b-2 ${
                    isActive
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Tab Content */}
        {activeTab === 'presets' && <PresetsTab />}
        {activeTab === 'config' && <CampaignConfigTab />}
        {activeTab === 'analytics' && <AnalyticsTab />}
        {activeTab === 'links' && <LinkPerformanceTab />}
      </div>
    </div>
  );
}

export default UTMManagerPage;
