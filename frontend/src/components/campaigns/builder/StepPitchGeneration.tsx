import { useState } from 'react';
import { toast } from 'sonner';
import { MessageSquare, Sparkles, CheckCircle2, Copy, Zap, RefreshCw } from 'lucide-react';
import { Card, Button, Badge } from '../../ui';
import type { SegmentationResult, Segment, Pitch } from '../../../api/admin';
import { clsx } from 'clsx';

interface Step5Props {
  segmentation: SegmentationResult | null;
  pitches: Record<string, Pitch>;
  onGeneratePitch: (segment: Segment) => void;
  isGeneratingPitch: boolean;
  generatingSegmentId: string | null;
}

export function StepPitchGeneration({
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
