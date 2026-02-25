import { useState } from 'react';
import { LayoutGrid, Lightbulb, Target } from 'lucide-react';
import { Card, Button, Badge } from '../../ui';
import type { SegmentationResult, Segment } from '../../../api/admin';
import { clsx } from 'clsx';

interface Step4Props {
  segmentation: SegmentationResult | null;
  onSegment: () => void;
  isSegmenting: boolean;
  onEditSegment: (segment: Segment, index: number) => void;
}

export function StepSegmentation({
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
