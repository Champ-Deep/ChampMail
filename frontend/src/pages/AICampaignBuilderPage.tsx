import { useState, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Sparkles,
  FileText,
  Search,
  LayoutGrid,
  MessageSquare,
  Send,
  ChevronRight,
  ChevronLeft,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Users,
  Target,
  Zap,
  Eye,
  Copy,
  RefreshCw,
  XCircle,
  Lightbulb,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { C1CampaignSuggestions } from '../components/c1/C1CampaignSuggestions';
import { clsx } from 'clsx';
import {
  adminApi,
  type CampaignEssence,
  type ResearchResult,
  type SegmentationResult,
  type Segment,
  type Pitch,
  type PersonalizedEmail,
} from '../api/admin';

// ============================================================
// Constants
// ============================================================

const STEPS = [
  {
    id: 1,
    label: 'Describe Campaign',
    icon: Sparkles,
    description: 'Tell the AI about your campaign goals',
  },
  {
    id: 2,
    label: 'Select Prospects',
    icon: Users,
    description: 'Choose a prospect list to target',
  },
  {
    id: 3,
    label: 'Research',
    icon: Search,
    description: 'AI researches your prospects',
  },
  {
    id: 4,
    label: 'Segmentation',
    icon: LayoutGrid,
    description: 'Review AI-generated segments',
  },
  {
    id: 5,
    label: 'Pitches',
    icon: MessageSquare,
    description: 'AI generates targeted pitches',
  },
  {
    id: 6,
    label: 'Preview & Send',
    icon: Send,
    description: 'Review and launch your campaign',
  },
] as const;

// ============================================================
// Stepper Component
// ============================================================

interface StepperProps {
  currentStep: number;
  completedSteps: Set<number>;
}

function Stepper({ currentStep, completedSteps }: StepperProps) {
  return (
    <nav className="w-full" aria-label="Campaign builder progress">
      <ol className="flex items-center">
        {STEPS.map((step, index) => {
          const isActive = step.id === currentStep;
          const isCompleted = completedSteps.has(step.id);
          const isLast = index === STEPS.length - 1;
          const Icon = step.icon;

          return (
            <li
              key={step.id}
              className={clsx('flex items-center', !isLast && 'flex-1')}
            >
              <div className="flex flex-col items-center relative group">
                <div
                  className={clsx(
                    'h-10 w-10 rounded-full flex items-center justify-center border-2 transition-all duration-200',
                    isActive
                      ? 'border-brand-purple bg-brand-purple text-white shadow-lg shadow-brand-purple/20'
                      : isCompleted
                      ? 'border-green-500 bg-green-500 text-white'
                      : 'border-slate-300 bg-white text-slate-400'
                  )}
                >
                  {isCompleted && !isActive ? (
                    <CheckCircle2 className="h-5 w-5" />
                  ) : (
                    <Icon className="h-5 w-5" />
                  )}
                </div>
                <span
                  className={clsx(
                    'mt-2 text-xs font-medium text-center max-w-[80px] leading-tight',
                    isActive
                      ? 'text-brand-purple'
                      : isCompleted
                      ? 'text-green-600'
                      : 'text-slate-400'
                  )}
                >
                  {step.label}
                </span>
                {/* Tooltip */}
                <div className="absolute -bottom-12 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  <div className="bg-slate-800 text-white text-xs px-2.5 py-1.5 rounded-md whitespace-nowrap">
                    {step.description}
                  </div>
                </div>
              </div>
              {!isLast && (
                <div
                  className={clsx(
                    'flex-1 h-0.5 mx-2 transition-colors duration-200',
                    isCompleted ? 'bg-green-500' : 'bg-slate-200'
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ============================================================
// Step 1: Campaign Description
// ============================================================

interface Step1Props {
  description: string;
  setDescription: (val: string) => void;
  targetAudience: string;
  setTargetAudience: (val: string) => void;
  essence: CampaignEssence | null;
  onExtract: () => void;
  isExtracting: boolean;
}

function StepCampaignDescription({
  description,
  setDescription,
  targetAudience,
  setTargetAudience,
  essence,
  onExtract,
  isExtracting,
}: Step1Props) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Describe Your Campaign
        </h2>
        <p className="text-sm text-slate-500">
          Tell the AI what you are selling, your value proposition, and who you
          want to reach. Be as detailed as possible.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Campaign Description *
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            className="w-full px-4 py-3 rounded-lg border border-slate-300 bg-white text-sm outline-none transition-colors focus:border-brand-purple focus:ring-2 focus:ring-brand-purple/20 resize-none placeholder:text-slate-400"
            placeholder="Example: We sell an AI-powered email platform that helps B2B sales teams automate cold outreach. Our key differentiator is real-time prospect research and hyper-personalization. We want to target VP of Sales and Head of Growth at mid-market SaaS companies (100-1000 employees) who currently use legacy email tools..."
          />
          <p className="text-xs text-slate-400 mt-1.5">
            {description.length} / 2000 characters
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Target Audience (optional)
          </label>
          <input
            type="text"
            value={targetAudience}
            onChange={(e) => setTargetAudience(e.target.value)}
            className="w-full h-10 px-4 rounded-lg border border-slate-300 bg-white text-sm outline-none transition-colors focus:border-brand-purple focus:ring-2 focus:ring-brand-purple/20 placeholder:text-slate-400"
            placeholder="e.g., VP of Sales at mid-market SaaS companies"
          />
        </div>

        <Button
          onClick={onExtract}
          disabled={!description.trim() || isExtracting}
          isLoading={isExtracting}
          leftIcon={<Sparkles className="h-4 w-4" />}
        >
          {isExtracting ? 'Analyzing...' : 'Extract Campaign Essence'}
        </Button>
      </div>

      {/* Essence Preview */}
      {essence && (
        <Card className="border-green-200 bg-green-50/50">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            <h3 className="font-semibold text-green-800">
              Campaign Essence Extracted
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                Value Propositions
              </p>
              <ul className="space-y-1">
                {essence.value_propositions.map((vp, i) => (
                  <li
                    key={i}
                    className="text-sm text-slate-700 flex items-start gap-2"
                  >
                    <Zap className="h-3.5 w-3.5 text-green-500 mt-0.5 flex-shrink-0" />
                    {vp}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                Pain Points Addressed
              </p>
              <ul className="space-y-1">
                {essence.pain_points.map((pp, i) => (
                  <li
                    key={i}
                    className="text-sm text-slate-700 flex items-start gap-2"
                  >
                    <Target className="h-3.5 w-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
                    {pp}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                Call to Action
              </p>
              <p className="text-sm text-slate-700">{essence.call_to_action}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                Tone
              </p>
              <p className="text-sm text-slate-700">{essence.tone}</p>
            </div>
            {essence.unique_angle && (
              <div className="col-span-full">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1.5">
                  Unique Angle
                </p>
                <p className="text-sm text-slate-700">
                  {essence.unique_angle}
                </p>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* AI Campaign Suggestions (via Thesys C1) */}
      {essence && description && (
        <C1CampaignSuggestions description={description} essence={essence} />
      )}
    </div>
  );
}

// ============================================================
// Step 2: Select Prospect List
// ============================================================

interface Step2Props {
  selectedListId: string | null;
  setSelectedListId: (id: string | null) => void;
}

function StepSelectProspects({
  selectedListId,
  setSelectedListId,
}: Step2Props) {
  const { data: lists = [], isLoading } = useQuery({
    queryKey: ['admin', 'prospect-lists'],
    queryFn: () => adminApi.getProspectLists(),
  });

  const completedLists = lists.filter((l) => l.status === 'completed');

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 text-brand-purple animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Select Prospect List
        </h2>
        <p className="text-sm text-slate-500">
          Choose which prospect list to use for this campaign. Only completed
          lists are available.
        </p>
      </div>

      {completedLists.length === 0 ? (
        <Card className="py-12 text-center">
          <Users className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            No prospect lists available
          </h3>
          <p className="text-slate-500 max-w-md mx-auto">
            Upload and process a prospect list first from the Prospect Lists
            page. Only fully processed lists can be used for campaigns.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {completedLists.map((list) => (
            <button
              key={list.id}
              onClick={() => setSelectedListId(list.id)}
              className={clsx(
                'w-full text-left rounded-xl border-2 p-4 transition-all duration-150',
                selectedListId === list.id
                  ? 'border-brand-purple bg-brand-purple/5 ring-2 ring-brand-purple/20'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={clsx(
                      'h-10 w-10 rounded-lg flex items-center justify-center',
                      selectedListId === list.id
                        ? 'bg-brand-purple/10'
                        : 'bg-slate-100'
                    )}
                  >
                    <FileText
                      className={clsx(
                        'h-5 w-5',
                        selectedListId === list.id
                          ? 'text-brand-purple'
                          : 'text-slate-400'
                      )}
                    />
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">
                      {list.name || list.file_name}
                    </p>
                    <p className="text-sm text-slate-500">
                      {list.total_prospects.toLocaleString()} prospects --
                      Uploaded{' '}
                      {new Date(list.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="success" size="sm">
                    {list.total_prospects.toLocaleString()} contacts
                  </Badge>
                  {selectedListId === list.id && (
                    <CheckCircle2 className="h-5 w-5 text-brand-purple" />
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {lists.filter((l) => l.status !== 'completed').length > 0 && (
        <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-amber-700">
            {lists.filter((l) => l.status !== 'completed').length} list(s) are
            still processing and not available for selection.
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Step 3: Research Results
// ============================================================

interface Step3Props {
  researchResults: ResearchResult[];
  onStartResearch: () => void;
  isResearching: boolean;
  researchComplete: boolean;
}

function StepResearch({
  researchResults,
  onStartResearch,
  isResearching,
  researchComplete,
}: Step3Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Prospect Research
        </h2>
        <p className="text-sm text-slate-500">
          The AI will research each prospect's company, role, and recent
          activity to generate personalized outreach.
        </p>
      </div>

      {!researchComplete && researchResults.length === 0 && (
        <Card className="text-center py-10">
          <Search className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Ready to Research
          </h3>
          <p className="text-slate-500 max-w-md mx-auto mb-6">
            The AI will analyze each prospect using real-time data from the web
            -- company info, industry trends, hiring signals, and more.
          </p>
          <Button
            onClick={onStartResearch}
            disabled={isResearching}
            isLoading={isResearching}
            leftIcon={<Search className="h-4 w-4" />}
          >
            {isResearching ? 'Researching Prospects...' : 'Start Research'}
          </Button>
          {isResearching && (
            <p className="text-xs text-slate-400 mt-3">
              This may take a few minutes depending on list size...
            </p>
          )}
        </Card>
      )}

      {researchResults.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              <span className="text-sm font-medium text-slate-700">
                {researchResults.length} prospect(s) researched
              </span>
            </div>
            {researchComplete && (
              <Badge variant="success">Research Complete</Badge>
            )}
          </div>

          <div className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
            {researchResults.map((result) => {
              const hasError = !!result.research_data?.error;
              const isExpanded = expandedId === result.prospect_id;
              const companyDesc =
                result.research_data?.company_info?.description || 'N/A';

              return (
                <Card
                  key={result.prospect_id || result.prospect_email}
                  padding="none"
                  className={clsx(
                    'transition-all',
                    hasError && 'border-red-200'
                  )}
                >
                  <button
                    onClick={() =>
                      setExpandedId(isExpanded ? null : result.prospect_id)
                    }
                    className="w-full text-left p-4 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {hasError ? (
                        <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                      ) : (
                        <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 truncate">
                          {result.prospect_email}
                        </p>
                        <p className="text-xs text-slate-500 truncate">
                          {companyDesc.substring(0, 100)}
                          {companyDesc.length > 100 ? '...' : ''}
                        </p>
                      </div>
                    </div>
                    <ChevronRight
                      className={clsx(
                        'h-4 w-4 text-slate-400 transition-transform flex-shrink-0 ml-2',
                        isExpanded && 'rotate-90'
                      )}
                    />
                  </button>

                  {isExpanded && (
                    <div className="px-4 pb-4 pt-0 border-t border-slate-100 mt-0 pt-3">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                            Company
                          </p>
                          <p className="text-slate-700">{companyDesc}</p>
                          {result.research_data?.company_info?.industry && (
                            <Badge variant="default" size="sm" className="mt-1">
                              {result.research_data.company_info.industry}
                            </Badge>
                          )}
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                            Personalization Hooks
                          </p>
                          <ul className="space-y-0.5">
                            {(
                              result.research_data?.personalization_hooks || []
                            ).map((hook, i) => (
                              <li
                                key={i}
                                className="text-slate-700 flex items-start gap-1.5"
                              >
                                <Lightbulb className="h-3 w-3 text-amber-500 mt-0.5 flex-shrink-0" />
                                {hook}
                              </li>
                            ))}
                          </ul>
                        </div>
                        {result.research_data?.triggers && (
                          <div className="col-span-full">
                            <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                              Triggers
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {result.research_data.triggers.funding && (
                                <Badge variant="info" size="sm">
                                  Funding:{' '}
                                  {result.research_data.triggers.funding}
                                </Badge>
                              )}
                              {result.research_data.triggers.expansion && (
                                <Badge variant="success" size="sm">
                                  Growth:{' '}
                                  {result.research_data.triggers.expansion}
                                </Badge>
                              )}
                              {result.research_data.triggers
                                .leadership_changes && (
                                <Badge variant="warning" size="sm">
                                  Leadership Change
                                </Badge>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Step 4: Segmentation
// ============================================================

interface Step4Props {
  segmentation: SegmentationResult | null;
  onSegment: () => void;
  isSegmenting: boolean;
  onEditSegment: (segment: Segment, index: number) => void;
}

function StepSegmentation({
  segmentation,
  onSegment,
  isSegmenting,
  onEditSegment,
}: Step4Props) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editAngle, setEditAngle] = useState('');

  const startEdit = (seg: Segment, idx: number) => {
    setEditingIndex(idx);
    setEditName(seg.name);
    setEditAngle(seg.messaging_angle);
  };

  const saveEdit = (seg: Segment, idx: number) => {
    onEditSegment(
      { ...seg, name: editName, messaging_angle: editAngle },
      idx
    );
    setEditingIndex(null);
  };

  const priorityColors: Record<string, string> = {
    high: 'border-green-200 bg-green-50',
    medium: 'border-brand-purple/20 bg-brand-purple/5',
    low: 'border-slate-200 bg-slate-50',
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          AI Segmentation
        </h2>
        <p className="text-sm text-slate-500">
          The AI groups your prospects into segments based on shared traits,
          industries, and pain points. You can edit segment names and messaging
          angles.
        </p>
      </div>

      {!segmentation && (
        <Card className="text-center py-10">
          <LayoutGrid className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Ready to Segment
          </h3>
          <p className="text-slate-500 max-w-md mx-auto mb-6">
            Based on the research data, the AI will create intelligent segments
            tailored to your campaign goals.
          </p>
          <Button
            onClick={onSegment}
            disabled={isSegmenting}
            isLoading={isSegmenting}
            leftIcon={<LayoutGrid className="h-4 w-4" />}
          >
            {isSegmenting ? 'Segmenting...' : 'Run Segmentation'}
          </Button>
        </Card>
      )}

      {segmentation && (
        <div className="space-y-4">
          {/* Strategy overview */}
          <Card className="border-brand-purple/20 bg-brand-purple/5">
            <div className="flex items-start gap-3">
              <Lightbulb className="h-5 w-5 text-brand-purple mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-brand-navy mb-1">
                  Segmentation Strategy
                </p>
                <p className="text-sm text-brand-purple">{segmentation.strategy}</p>
                {segmentation.unmatched_pct > 0 && (
                  <p className="text-xs text-brand-purple mt-1">
                    ~{segmentation.unmatched_pct}% of prospects may not match
                    any segment
                  </p>
                )}
              </div>
            </div>
          </Card>

          {/* Segments */}
          <div className="grid grid-cols-1 gap-4">
            {segmentation.segments.map((seg, idx) => (
              <Card
                key={seg.id}
                className={clsx(
                  'transition-all',
                  priorityColors[seg.priority] || priorityColors.medium
                )}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {editingIndex === idx ? (
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="text-lg font-semibold text-slate-900 bg-white border border-slate-300 rounded px-2 py-0.5"
                        autoFocus
                      />
                    ) : (
                      <h4 className="text-lg font-semibold text-slate-900">
                        {seg.name}
                      </h4>
                    )}
                    <Badge
                      variant={
                        seg.priority === 'high'
                          ? 'success'
                          : seg.priority === 'medium'
                          ? 'info'
                          : 'default'
                      }
                      size="sm"
                    >
                      {seg.priority}
                    </Badge>
                    <Badge variant="default" size="sm">
                      ~{seg.size_estimate_pct}%
                    </Badge>
                  </div>
                  <div>
                    {editingIndex === idx ? (
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => saveEdit(seg, idx)}
                        >
                          Save
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingIndex(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => startEdit(seg, idx)}
                      >
                        Edit
                      </Button>
                    )}
                  </div>
                </div>

                <p className="text-sm text-slate-600 mb-3">
                  {seg.characteristics}
                </p>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                      Criteria
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {seg.criteria.industries?.map((ind) => (
                        <Badge key={ind} variant="default" size="sm">
                          {ind}
                        </Badge>
                      ))}
                      {seg.criteria.roles?.map((role) => (
                        <Badge key={role} variant="default" size="sm">
                          {role}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                      Pain Points
                    </p>
                    <ul className="space-y-0.5">
                      {seg.pain_points.slice(0, 3).map((pp, i) => (
                        <li
                          key={i}
                          className="text-xs text-slate-600 flex items-start gap-1"
                        >
                          <Target className="h-3 w-3 text-red-400 mt-0.5 flex-shrink-0" />
                          {pp}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                      Messaging Angle
                    </p>
                    {editingIndex === idx ? (
                      <textarea
                        value={editAngle}
                        onChange={(e) => setEditAngle(e.target.value)}
                        rows={3}
                        className="w-full text-xs border border-slate-300 rounded px-2 py-1 bg-white"
                      />
                    ) : (
                      <p className="text-xs text-slate-600">
                        {seg.messaging_angle}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Step 5: Pitch Generation
// ============================================================

interface Step5Props {
  segmentation: SegmentationResult | null;
  pitches: Record<string, Pitch>;
  onGeneratePitch: (segment: Segment) => void;
  isGeneratingPitch: boolean;
  generatingSegmentId: string | null;
}

function StepPitchGeneration({
  segmentation,
  pitches,
  onGeneratePitch,
  isGeneratingPitch,
  generatingSegmentId,
}: Step5Props) {
  const [activeSegment, setActiveSegment] = useState<string | null>(null);

  const segments = segmentation?.segments || [];
  const currentSegId = activeSegment || segments[0]?.id;
  const currentPitch = currentSegId ? pitches[currentSegId] : null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Pitch Generation
        </h2>
        <p className="text-sm text-slate-500">
          The AI generates a tailored pitch for each segment. Generate pitches
          individually or review and tweak as needed.
        </p>
      </div>

      {segments.length === 0 ? (
        <Card className="text-center py-10">
          <MessageSquare className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            No segments available
          </h3>
          <p className="text-slate-500">
            Complete segmentation first to generate pitches.
          </p>
        </Card>
      ) : (
        <div className="flex gap-6">
          {/* Segment Sidebar */}
          <div className="w-56 flex-shrink-0 space-y-2">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              Segments
            </p>
            {segments.map((seg) => {
              const hasPitch = !!pitches[seg.id];
              const isActive = seg.id === currentSegId;

              return (
                <button
                  key={seg.id}
                  onClick={() => setActiveSegment(seg.id)}
                  className={clsx(
                    'w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all border',
                    isActive
                      ? 'border-brand-purple/30 bg-brand-purple/5 text-brand-purple'
                      : 'border-transparent hover:bg-slate-50 text-slate-600'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate font-medium">{seg.name}</span>
                    {hasPitch && (
                      <CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0 ml-1" />
                    )}
                  </div>
                  <span className="text-xs text-slate-400">
                    ~{seg.size_estimate_pct}% -- {seg.priority}
                  </span>
                </button>
              );
            })}

            <div className="pt-2 border-t border-slate-200 mt-3">
              <p className="text-xs text-slate-400">
                {Object.keys(pitches).length} / {segments.length} pitches
                generated
              </p>
            </div>
          </div>

          {/* Pitch Content */}
          <div className="flex-1 min-w-0">
            {currentSegId && !currentPitch && (
              <Card className="text-center py-10">
                <MessageSquare className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                <h3 className="text-base font-medium text-slate-900 mb-2">
                  Generate Pitch for "
                  {segments.find((s) => s.id === currentSegId)?.name}"
                </h3>
                <p className="text-sm text-slate-500 mb-4 max-w-md mx-auto">
                  The AI will craft subject lines, email body, and follow-ups
                  tailored to this segment's pain points and messaging angle.
                </p>
                <Button
                  onClick={() => {
                    const seg = segments.find((s) => s.id === currentSegId);
                    if (seg) onGeneratePitch(seg);
                  }}
                  disabled={isGeneratingPitch}
                  isLoading={
                    isGeneratingPitch && generatingSegmentId === currentSegId
                  }
                  leftIcon={<Sparkles className="h-4 w-4" />}
                >
                  Generate Pitch
                </Button>
              </Card>
            )}

            {currentPitch && (
              <div className="space-y-4">
                {/* Pitch Angle */}
                <Card>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
                    Pitch Angle
                  </p>
                  <p className="text-sm text-slate-800 font-medium">
                    {currentPitch.pitch_angle}
                  </p>
                </Card>

                {/* Subject Lines */}
                <Card>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                    Subject Lines
                  </p>
                  <div className="space-y-2">
                    {currentPitch.subject_lines.map((subj, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2.5 bg-slate-50 rounded-lg"
                      >
                        <p className="text-sm text-slate-800">{subj}</p>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(subj);
                            toast.success('Copied to clipboard');
                          }}
                          className="p-1 hover:bg-slate-200 rounded transition-colors flex-shrink-0 ml-2"
                        >
                          <Copy className="h-3.5 w-3.5 text-slate-400" />
                        </button>
                      </div>
                    ))}
                  </div>
                </Card>

                {/* Body Template */}
                <Card>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                      Email Body
                    </p>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(
                          currentPitch.body_template
                        );
                        toast.success('Copied to clipboard');
                      }}
                      className="p-1 hover:bg-slate-100 rounded transition-colors"
                    >
                      <Copy className="h-3.5 w-3.5 text-slate-400" />
                    </button>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-4 font-mono text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                    {currentPitch.body_template}
                  </div>
                </Card>

                {/* Key Messages */}
                <Card>
                  <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                    Key Messages
                  </p>
                  <ul className="space-y-1.5">
                    {currentPitch.key_messages.map((msg, i) => (
                      <li
                        key={i}
                        className="text-sm text-slate-700 flex items-start gap-2"
                      >
                        <Zap className="h-3.5 w-3.5 text-brand-purple mt-0.5 flex-shrink-0" />
                        {msg}
                      </li>
                    ))}
                  </ul>
                </Card>

                {/* Follow-ups */}
                {currentPitch.follow_up_templates.length > 0 && (
                  <Card>
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-3">
                      Follow-up Sequence
                    </p>
                    <div className="space-y-3">
                      {currentPitch.follow_up_templates.map((fu, i) => (
                        <div
                          key={i}
                          className="pl-4 border-l-2 border-brand-purple/20"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <Badge variant="info" size="sm">
                              Day {fu.delay_days}
                            </Badge>
                            <p className="text-sm font-medium text-slate-800">
                              {fu.subject}
                            </p>
                          </div>
                          <p className="text-xs text-slate-600 whitespace-pre-wrap">
                            {fu.body}
                          </p>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {/* Regenerate */}
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const seg = segments.find(
                        (s) => s.id === currentSegId
                      );
                      if (seg) onGeneratePitch(seg);
                    }}
                    disabled={isGeneratingPitch}
                    leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
                  >
                    Regenerate
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Step 6: Preview & Send
// ============================================================

interface Step6Props {
  personalizedEmails: PersonalizedEmail[];
  onPersonalize: () => void;
  isPersonalizing: boolean;
  onGenerateHtml: (email: PersonalizedEmail) => void;
  isGeneratingHtml: boolean;
  htmlPreviews: Record<string, string>;
  onSend: () => void;
  isSending: boolean;
}

function StepPreviewSend({
  personalizedEmails,
  onPersonalize,
  isPersonalizing,
  onGenerateHtml,
  isGeneratingHtml,
  htmlPreviews,
  onSend,
  isSending,
}: Step6Props) {
  const [selectedEmailIdx, setSelectedEmailIdx] = useState(0);
  const [showHtmlPreview, setShowHtmlPreview] = useState(false);

  const currentEmail = personalizedEmails[selectedEmailIdx];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Preview & Send
        </h2>
        <p className="text-sm text-slate-500">
          Review personalized emails and preview HTML rendering before sending
          the campaign.
        </p>
      </div>

      {personalizedEmails.length === 0 && (
        <Card className="text-center py-10">
          <Send className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Ready to Personalize
          </h3>
          <p className="text-slate-500 max-w-md mx-auto mb-6">
            Generate personalized emails for each prospect based on the segment
            pitches and their individual research data.
          </p>
          <Button
            onClick={onPersonalize}
            disabled={isPersonalizing}
            isLoading={isPersonalizing}
            leftIcon={<Sparkles className="h-4 w-4" />}
          >
            {isPersonalizing
              ? 'Personalizing Emails...'
              : 'Generate Personalized Emails'}
          </Button>
        </Card>
      )}

      {personalizedEmails.length > 0 && (
        <div className="space-y-4">
          {/* Summary Bar */}
          <div className="flex items-center justify-between p-4 bg-gradient-to-r from-brand-purple/5 to-brand-lavender/10 border border-brand-purple/20 rounded-xl">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-brand-purple/10 flex items-center justify-center">
                <Send className="h-6 w-6 text-brand-purple" />
              </div>
              <div>
                <p className="text-lg font-semibold text-slate-900">
                  {personalizedEmails.length} Emails Ready
                </p>
                <p className="text-sm text-slate-500">
                  Personalized and ready to send
                </p>
              </div>
            </div>
            <Button
              onClick={onSend}
              disabled={isSending}
              isLoading={isSending}
              leftIcon={<Send className="h-4 w-4" />}
              className="bg-gradient-to-r from-brand-purple to-brand-navy hover:from-brand-purple/90 hover:to-brand-navy/90"
            >
              {isSending ? 'Sending...' : 'Send Campaign'}
            </Button>
          </div>

          <div className="flex gap-6">
            {/* Email List */}
            <div className="w-64 flex-shrink-0 space-y-1.5 max-h-[500px] overflow-y-auto pr-1">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 sticky top-0 bg-white py-1">
                Emails ({personalizedEmails.length})
              </p>
              {personalizedEmails.map((email, idx) => (
                <button
                  key={email.prospect_email || idx}
                  onClick={() => setSelectedEmailIdx(idx)}
                  className={clsx(
                    'w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all border',
                    idx === selectedEmailIdx
                      ? 'border-brand-purple/30 bg-brand-purple/5'
                      : 'border-transparent hover:bg-slate-50'
                  )}
                >
                  <p className="font-medium text-slate-800 truncate">
                    {email.prospect_email}
                  </p>
                  <p className="text-xs text-slate-500 truncate mt-0.5">
                    {email.subject}
                  </p>
                </button>
              ))}
            </div>

            {/* Email Preview */}
            {currentEmail && (
              <div className="flex-1 min-w-0 space-y-4">
                <Card>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-slate-500">To:</p>
                        <p className="text-sm font-medium text-slate-900">
                          {currentEmail.prospect_email}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            onGenerateHtml(currentEmail);
                            setShowHtmlPreview(true);
                          }}
                          disabled={isGeneratingHtml}
                          isLoading={isGeneratingHtml}
                          leftIcon={<Eye className="h-3.5 w-3.5" />}
                        >
                          HTML Preview
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            navigator.clipboard.writeText(
                              `Subject: ${currentEmail.subject}\n\n${currentEmail.body}`
                            );
                            toast.success('Copied to clipboard');
                          }}
                          leftIcon={<Copy className="h-3.5 w-3.5" />}
                        >
                          Copy
                        </Button>
                      </div>
                    </div>

                    <div className="border-t border-slate-100 pt-3">
                      <p className="text-xs text-slate-500">Subject:</p>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5">
                        {currentEmail.subject}
                      </p>
                    </div>

                    <div className="border-t border-slate-100 pt-3">
                      <p className="text-xs text-slate-500 mb-1">Body:</p>
                      <div className="bg-slate-50 rounded-lg p-4 text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                        {currentEmail.body}
                      </div>
                    </div>

                    {/* Follow-ups */}
                    {currentEmail.follow_ups &&
                      currentEmail.follow_ups.length > 0 && (
                        <div className="border-t border-slate-100 pt-3">
                          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                            Follow-up Sequence
                          </p>
                          <div className="space-y-2">
                            {currentEmail.follow_ups.map((fu, i) => (
                              <div
                                key={i}
                                className="pl-3 border-l-2 border-brand-purple/20"
                              >
                                <div className="flex items-center gap-2">
                                  <Badge variant="info" size="sm">
                                    Day {fu.delay_days}
                                  </Badge>
                                  <span className="text-xs font-medium text-slate-700">
                                    {fu.subject}
                                  </span>
                                </div>
                                <p className="text-xs text-slate-500 mt-1 whitespace-pre-wrap">
                                  {fu.body}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                    {/* Variables Used */}
                    {currentEmail.variables_used && (
                      <div className="border-t border-slate-100 pt-3">
                        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                          Personalization Variables
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(currentEmail.variables_used).map(
                            ([key, val]) => (
                              <div
                                key={key}
                                className="text-xs bg-slate-100 rounded px-2 py-1"
                              >
                                <span className="font-mono text-slate-500">
                                  {key}:
                                </span>{' '}
                                <span className="text-slate-700">{val}</span>
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </Card>
              </div>
            )}
          </div>
        </div>
      )}

      {/* HTML Preview Modal */}
      {showHtmlPreview && currentEmail && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <div>
                <h3 className="font-semibold text-slate-900">
                  HTML Email Preview
                </h3>
                <p className="text-xs text-slate-500">
                  {currentEmail.prospect_email}
                </p>
              </div>
              <button
                onClick={() => setShowHtmlPreview(false)}
                className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <XCircle className="h-5 w-5 text-slate-400" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {htmlPreviews[currentEmail.prospect_email] ? (
                <iframe
                  srcDoc={htmlPreviews[currentEmail.prospect_email]}
                  className="w-full h-full min-h-[500px] border border-slate-200 rounded-lg"
                  title="Email HTML Preview"
                  sandbox="allow-same-origin"
                />
              ) : isGeneratingHtml ? (
                <div className="flex flex-col items-center justify-center py-16">
                  <Loader2 className="h-8 w-8 text-brand-purple animate-spin mb-3" />
                  <p className="text-sm text-slate-500">
                    Generating HTML email...
                  </p>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16">
                  <Eye className="h-10 w-10 text-slate-300 mb-3" />
                  <p className="text-sm text-slate-500">
                    Click "HTML Preview" to generate
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Main Campaign Builder Page
// ============================================================

export function AICampaignBuilderPage() {
  // Step state
  const [currentStep, setCurrentStep] = useState(1);
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(
    new Set()
  );

  // Step 1 state
  const [description, setDescription] = useState('');
  const [targetAudience, setTargetAudience] = useState('');
  const [essence, setEssence] = useState<CampaignEssence | null>(null);

  // Step 2 state
  const [selectedListId, setSelectedListId] = useState<string | null>(null);

  // Step 3 state
  const [researchResults, setResearchResults] = useState<ResearchResult[]>([]);
  const [researchComplete, setResearchComplete] = useState(false);

  // Step 4 state
  const [segmentation, setSegmentation] = useState<SegmentationResult | null>(
    null
  );

  // Step 5 state
  const [pitches, setPitches] = useState<Record<string, Pitch>>({});
  const [generatingSegmentId, setGeneratingSegmentId] = useState<
    string | null
  >(null);

  // Step 6 state
  const [personalizedEmails, setPersonalizedEmails] = useState<
    PersonalizedEmail[]
  >([]);
  const [htmlPreviews, setHtmlPreviews] = useState<Record<string, string>>({});

  // ----------------------------------------------------------
  // Navigation helpers
  // ----------------------------------------------------------

  const markCompleted = (step: number) => {
    setCompletedSteps((prev) => new Set([...prev, step]));
  };

  const canProceed = useMemo(() => {
    switch (currentStep) {
      case 1:
        return !!essence;
      case 2:
        return !!selectedListId;
      case 3:
        return researchComplete && researchResults.length > 0;
      case 4:
        return !!segmentation && segmentation.segments.length > 0;
      case 5:
        return Object.keys(pitches).length > 0;
      case 6:
        return personalizedEmails.length > 0;
      default:
        return false;
    }
  }, [
    currentStep,
    essence,
    selectedListId,
    researchComplete,
    researchResults,
    segmentation,
    pitches,
    personalizedEmails,
  ]);

  const goNext = () => {
    if (currentStep < 6) {
      markCompleted(currentStep);
      setCurrentStep(currentStep + 1);
    }
  };

  const goPrev = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  // ----------------------------------------------------------
  // Mutations
  // ----------------------------------------------------------

  const extractEssenceMutation = useMutation({
    mutationFn: () =>
      adminApi.extractEssence({
        description,
        target_audience: targetAudience || undefined,
      }),
    onSuccess: (data) => {
      setEssence(data);
      toast.success('Campaign essence extracted successfully');
    },
    onError: (err: Error) => {
      toast.error(`Failed to extract essence: ${err.message}`);
    },
  });

  const researchMutation = useMutation({
    mutationFn: () =>
      adminApi.researchProspects({
        prospect_ids: [], // The backend will use the prospect list
        campaign_id: selectedListId || undefined,
      }),
    onSuccess: (data) => {
      setResearchResults(data);
      setResearchComplete(true);
      toast.success(`Research completed for ${data.length} prospects`);
    },
    onError: (err: Error) => {
      toast.error(`Research failed: ${err.message}`);
    },
  });

  const segmentMutation = useMutation({
    mutationFn: () =>
      adminApi.segmentProspects({
        research_results: researchResults,
        campaign_goals: description,
        campaign_essence: essence!,
      }),
    onSuccess: (data) => {
      setSegmentation(data);
      toast.success(`Created ${data.segments.length} segments`);
    },
    onError: (err: Error) => {
      toast.error(`Segmentation failed: ${err.message}`);
    },
  });

  const pitchMutation = useMutation({
    mutationFn: (segment: Segment) =>
      adminApi.generatePitch({
        segment,
        campaign_essence: essence!,
        sample_research: researchResults.slice(0, 5),
      }),
    onSuccess: (data, segment) => {
      setPitches((prev) => ({ ...prev, [segment.id]: data }));
      setGeneratingSegmentId(null);
      toast.success(`Pitch generated for "${segment.name}"`);
    },
    onError: (err: Error) => {
      setGeneratingSegmentId(null);
      toast.error(`Pitch generation failed: ${err.message}`);
    },
  });

  const personalizeMutation = useMutation({
    mutationFn: () => {
      // Use the first pitch available
      const firstPitchId = Object.keys(pitches)[0];
      const pitch = pitches[firstPitchId];
      return adminApi.personalizeEmails({
        pitch,
        prospects: researchResults.map((r) => ({
          id: r.prospect_id,
          email: r.prospect_email,
        })),
        research_data: researchResults,
      });
    },
    onSuccess: (data) => {
      setPersonalizedEmails(data);
      toast.success(`Personalized ${data.length} emails`);
    },
    onError: (err: Error) => {
      toast.error(`Personalization failed: ${err.message}`);
    },
  });

  const htmlMutation = useMutation({
    mutationFn: (email: PersonalizedEmail) =>
      adminApi.generateHtml({
        subject: email.subject,
        body: email.body,
        prospect: {
          email: email.prospect_email,
          ...email.variables_used,
        },
      }),
    onSuccess: (data, email) => {
      setHtmlPreviews((prev) => ({
        ...prev,
        [email.prospect_email]: data.html,
      }));
      toast.success('HTML preview generated');
    },
    onError: (err: Error) => {
      toast.error(`HTML generation failed: ${err.message}`);
    },
  });

  const sendMutation = useMutation({
    mutationFn: () =>
      adminApi.runFullPipeline({
        description,
        prospect_list_id: selectedListId!,
        target_audience: targetAudience || undefined,
      }),
    onSuccess: () => {
      toast.success('Campaign sent successfully!');
    },
    onError: (err: Error) => {
      toast.error(`Send failed: ${err.message}`);
    },
  });

  // ----------------------------------------------------------
  // Edit segment handler
  // ----------------------------------------------------------

  const handleEditSegment = (updatedSegment: Segment, index: number) => {
    if (!segmentation) return;
    const newSegments = [...segmentation.segments];
    newSegments[index] = updatedSegment;
    setSegmentation({ ...segmentation, segments: newSegments });
  };

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------

  return (
    <div className="h-full">
      <Header
        title="AI Campaign Builder"
        subtitle="Build hyper-personalized campaigns with AI"
        actions={
          <Badge variant="info" size="sm">
            <Sparkles className="h-3 w-3 mr-1" />
            AI-Powered
          </Badge>
        }
      />

      <div className="p-6 max-w-5xl mx-auto space-y-8">
        {/* Stepper */}
        <Card>
          <Stepper currentStep={currentStep} completedSteps={completedSteps} />
        </Card>

        {/* Step Content */}
        <div className="min-h-[400px]">
          {currentStep === 1 && (
            <StepCampaignDescription
              description={description}
              setDescription={setDescription}
              targetAudience={targetAudience}
              setTargetAudience={setTargetAudience}
              essence={essence}
              onExtract={() => extractEssenceMutation.mutate()}
              isExtracting={extractEssenceMutation.isPending}
            />
          )}

          {currentStep === 2 && (
            <StepSelectProspects
              selectedListId={selectedListId}
              setSelectedListId={setSelectedListId}
            />
          )}

          {currentStep === 3 && (
            <StepResearch
              researchResults={researchResults}
              onStartResearch={() => researchMutation.mutate()}
              isResearching={researchMutation.isPending}
              researchComplete={researchComplete}
            />
          )}

          {currentStep === 4 && (
            <StepSegmentation
              segmentation={segmentation}
              onSegment={() => segmentMutation.mutate()}
              isSegmenting={segmentMutation.isPending}
              onEditSegment={handleEditSegment}
            />
          )}

          {currentStep === 5 && (
            <StepPitchGeneration
              segmentation={segmentation}
              pitches={pitches}
              onGeneratePitch={(seg) => {
                setGeneratingSegmentId(seg.id);
                pitchMutation.mutate(seg);
              }}
              isGeneratingPitch={pitchMutation.isPending}
              generatingSegmentId={generatingSegmentId}
            />
          )}

          {currentStep === 6 && (
            <StepPreviewSend
              personalizedEmails={personalizedEmails}
              onPersonalize={() => personalizeMutation.mutate()}
              isPersonalizing={personalizeMutation.isPending}
              onGenerateHtml={(email) => htmlMutation.mutate(email)}
              isGeneratingHtml={htmlMutation.isPending}
              htmlPreviews={htmlPreviews}
              onSend={() => sendMutation.mutate()}
              isSending={sendMutation.isPending}
            />
          )}
        </div>

        {/* Navigation Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-slate-200">
          <Button
            variant="outline"
            onClick={goPrev}
            disabled={currentStep === 1}
            leftIcon={<ChevronLeft className="h-4 w-4" />}
          >
            Previous
          </Button>

          <div className="flex items-center gap-2 text-sm text-slate-500">
            Step {currentStep} of {STEPS.length}
          </div>

          {currentStep < 6 ? (
            <Button
              onClick={goNext}
              disabled={!canProceed}
              rightIcon={<ChevronRight className="h-4 w-4" />}
            >
              Next Step
            </Button>
          ) : (
            <div className="w-[120px]" /> // Spacer to keep layout balanced
          )}
        </div>
      </div>
    </div>
  );
}

export default AICampaignBuilderPage;
