import { Sparkles, Zap, Target, CheckCircle2 } from 'lucide-react';
import { Card, Button } from '../../ui';
import { C1CampaignSuggestions } from '../../c1/C1CampaignSuggestions';
import type { CampaignEssence } from '../../../api/admin';

interface Step1Props {
  description: string;
  setDescription: (val: string) => void;
  targetAudience: string;
  setTargetAudience: (val: string) => void;
  essence: CampaignEssence | null;
  onExtract: () => void;
  isExtracting: boolean;
}

export function StepCampaignDescription({
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
