import { useState, useMemo } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Sparkles,
  Search,
  LayoutGrid,
  MessageSquare,
  Send,
  ChevronRight,
  ChevronLeft,
  Users,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { adminApi, type CampaignEssence, type ResearchResult, type SegmentationResult, type Segment, type Pitch, type PersonalizedEmail } from '../api/admin';

// Import builder components
import { Stepper } from '../components/campaigns/builder/Stepper';
import { StepCampaignDescription } from '../components/campaigns/builder/StepCampaignDescription';
import { StepSelectProspects } from '../components/campaigns/builder/StepSelectProspects';
import { StepResearch } from '../components/campaigns/builder/StepResearch';
import { StepSegmentation } from '../components/campaigns/builder/StepSegmentation';
import { StepPitchGeneration } from '../components/campaigns/builder/StepPitchGeneration';
import { StepPreviewSend } from '../components/campaigns/builder/StepPreviewSend';

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
          <Stepper steps={STEPS} currentStep={currentStep} completedSteps={completedSteps} />
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
