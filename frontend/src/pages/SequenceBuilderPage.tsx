import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowLeft,
  Save,
  Play,
  Settings,
  Clock,
  Mail,
  GitBranch,
  GripVertical,
  X,
  Check,
  Reply,
  ArrowRight
} from 'lucide-react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button, Card, Badge } from '../components/ui';
import { clsx } from 'clsx';

interface StepConfig {
  // Email step
  subject?: string;
  templateId?: string;
  
  // Wait step
  days?: number;
  hours?: number;
  
  // Condition step
  conditionType?: 'reply' | 'open' | 'click' | 'no_reply' | 'no_open';
  ifTrueNext?: number;  // Step index to go to if condition met
  ifFalseNext?: number; // Step index to go to if condition not met
  
  // Auto-pause on reply
  autoPauseOnReply?: boolean;
}

interface Step {
  id: string;
  type: 'email' | 'wait' | 'condition';
  title: string;
  config: StepConfig;
}

interface StepConfigPanelProps {
  step: Step;
  onUpdate: (updates: Partial<Step>) => void;
  onClose: () => void;
}

function StepConfigPanel({ step, onUpdate, onClose }: StepConfigPanelProps) {
  const [config, setConfig] = useState(step.config);

  const handleSave = () => {
    onUpdate({ config });
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <h3 className="font-semibold text-slate-900">Configure {step.title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        
        <div className="p-4 space-y-4">
          {step.type === 'email' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Subject Line
                </label>
                <input
                  type="text"
                  value={config.subject || ''}
                  onChange={(e) => setConfig({ ...config, subject: e.target.value })}
                  placeholder="e.g., Quick question about {{company}}"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
                />
                <p className="text-xs text-slate-500 mt-1">Use {"{{}}"} for personalization variables</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Email Template
                </label>
                <select
                  value={config.templateId || ''}
                  onChange={(e) => setConfig({ ...config, templateId: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
                >
                  <option value="">Select a template...</option>
                  <option value="1">Follow Up Template</option>
                  <option value="2">Value Proposition</option>
                  <option value="3">Meeting Request</option>
                </select>
              </div>
            </>
          )}

          {step.type === 'wait' && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Days
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="30"
                    value={config.days || 0}
                    onChange={(e) => setConfig({ ...config, days: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Hours
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="23"
                    value={config.hours || 0}
                    onChange={(e) => setConfig({ ...config, hours: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
                  />
                </div>
              </div>
            </>
          )}

          {step.type === 'condition' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  If prospect...
                </label>
                <select
                  value={config.conditionType || 'reply'}
                  onChange={(e) => setConfig({ ...config, conditionType: e.target.value as StepConfig['conditionType'] })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-purple focus:border-transparent"
                >
                  <option value="reply">Replied to any email</option>
                  <option value="no_reply">Did NOT reply</option>
                  <option value="open">Opened any email</option>
                  <option value="no_open">Did NOT open</option>
                  <option value="click">Clicked any link</option>
                </select>
              </div>
              <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                <p className="text-sm text-blue-800">
                  <strong>Branch logic:</strong> If the condition is met, continue to the next step. 
                  If not, you can specify an alternative path or skip to the end.
                </p>
              </div>
            </>
          )}

          {/* Auto-pause on reply - available for all step types */}
          <div className="flex items-center gap-3 p-3 bg-green-50 rounded-lg border border-green-200">
            <input
              type="checkbox"
              id="autoPause"
              checked={config.autoPauseOnReply ?? true}
              onChange={(e) => setConfig({ ...config, autoPauseOnReply: e.target.checked })}
              className="h-4 w-4 rounded border-slate-300 text-brand-purple"
            />
            <label htmlFor="autoPause" className="flex-1">
              <span className="text-sm font-medium text-green-800">Auto-pause on reply</span>
              <p className="text-xs text-green-600">Automatically pause sequence if prospect replies</p>
            </label>
            <Reply className="h-5 w-5 text-green-600" />
          </div>
        </div>

        <div className="flex justify-end gap-3 p-4 border-t border-slate-200">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave}>
            <Check className="h-4 w-4 mr-2" />
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  );
}

// Sortable Item Component
function SortableStep({ 
  step, 
  index, 
  onConfigure 
}: { 
  step: Step; 
  index: number; 
  onConfigure: (step: Step) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id: step.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div ref={setNodeRef} style={style} className="mb-2">
      <div className="flex items-center gap-3">
        {/* Connection Line & Number */}
        <div className="flex flex-col items-center gap-1">
          {index > 0 && <div className="w-0.5 h-4 bg-slate-300" />}
          <div className={clsx(
            "flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold border-2 border-white shadow-sm z-10",
            step.type === 'email' && "bg-purple-100 text-purple-600",
            step.type === 'wait' && "bg-orange-100 text-orange-600",
            step.type === 'condition' && "bg-blue-100 text-blue-600"
          )}>
            {index + 1}
          </div>
          <div className="w-0.5 h-4 bg-slate-300" />
        </div>

        {/* Step Card */}
        <Card className="flex-1 hover:border-brand-purple/50 transition-colors group">
          <div className="flex items-center p-3 gap-3">
            <div 
              {...attributes} 
              {...listeners}
              className="cursor-grab text-slate-300 hover:text-slate-500 active:cursor-grabbing"
            >
              <GripVertical className="h-5 w-5" />
            </div>
            
            <div className={clsx(
              "flex items-center justify-center w-10 h-10 rounded-lg shrink-0",
              step.type === 'email' && "bg-purple-100 text-purple-600",
              step.type === 'wait' && "bg-orange-100 text-orange-600",
              step.type === 'condition' && "bg-blue-100 text-blue-600"
            )}>
              {step.type === 'email' ? <Mail className="h-5 w-5" /> : 
               step.type === 'wait' ? <Clock className="h-5 w-5" /> : 
               <GitBranch className="h-5 w-5" />}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h4 className="font-medium text-slate-900 truncate">{step.title}</h4>
                {step.config.autoPauseOnReply !== false && step.type === 'email' && (
                  <Badge variant="success" className="text-xs">Auto-pause</Badge>
                )}
              </div>
              <p className="text-sm text-slate-500 truncate">
                {step.type === 'email' && (step.config.subject || 'Send personalized email')}
                {step.type === 'wait' && `Wait ${step.config.days || 0} day(s) ${step.config.hours || 0} hour(s)`}
                {step.type === 'condition' && `If ${step.config.conditionType || 'reply'} → continue`}
              </p>
            </div>

            {step.type === 'condition' && (
              <div className="flex items-center gap-1 text-xs text-blue-600">
                <ArrowRight className="h-3 w-3" />
                Branch
              </div>
            )}

            <Button variant="ghost" size="sm" onClick={() => onConfigure(step)}>
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}

export function SequenceBuilderPage() {
  const navigate = useNavigate();
  const [steps, setSteps] = useState<Step[]>([
    { id: '1', type: 'email', title: 'Initial Outreach', config: { subject: '', autoPauseOnReply: true } },
    { id: '2', type: 'wait', title: 'Wait Period', config: { days: 3, hours: 0 } },
    { id: '3', type: 'email', title: 'Follow Up', config: { subject: '', autoPauseOnReply: true } },
    { id: '4', type: 'condition', title: 'Check Reply', config: { conditionType: 'reply', autoPauseOnReply: false } },
    { id: '5', type: 'wait', title: 'Final Wait', config: { days: 5 } },
    { id: '6', type: 'email', title: 'Last Follow Up', config: { subject: '', autoPauseOnReply: true } },
  ]);
  const [title, setTitle] = useState('New Outreach Sequence');
  const [configureStep, setConfigureStep] = useState<Step | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setSteps((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id);
        const newIndex = items.findIndex((item) => item.id === over.id);
        return arrayMove(items, oldIndex, newIndex);
      });
    }
  };

  const addStep = (type: Step['type']) => {
    const newStep: Step = {
      id: Math.random().toString(36).substring(7),
      type,
      title: type === 'email' ? 'New Email' : type === 'wait' ? 'Wait Period' : 'Condition',
      config: type === 'wait' ? { days: 1, hours: 0 } : 
             type === 'condition' ? { conditionType: 'reply', autoPauseOnReply: false } :
             { autoPauseOnReply: true }
    };
    setSteps([...steps, newStep]);
  };

  const updateStep = (id: string, updates: Partial<Step>) => {
    setSteps(steps.map(s => s.id === id ? { ...s, ...updates } : s));
  };

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Top Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200 shadow-sm z-10">
        <div className="flex items-center gap-4 flex-1">
          <button 
            onClick={() => navigate('/sequences')}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="flex-1 max-w-md">
            <input 
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="text-lg font-semibold text-slate-900 bg-transparent border-none outline-none focus:ring-0 w-full"
              placeholder="Sequence Name"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" leftIcon={<Save className="h-4 w-4" />}>
            Save Draft
          </Button>
          <Button leftIcon={<Play className="h-4 w-4" />}>
            Publish Sequence
          </Button>
        </div>
      </div>

      {/* Main Builder Area */}
      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-3xl mx-auto">
          
          {/* Sequence Flow Visualization */}
          <div className="mb-6 p-4 bg-white rounded-lg border border-slate-200">
            <h3 className="text-sm font-medium text-slate-500 mb-3">Sequence Flow</h3>
            <div className="flex items-center gap-2 flex-wrap">
              {steps.map((step, idx) => (
                <div key={step.id} className="flex items-center">
                  <div className={clsx(
                    "px-3 py-1.5 rounded-lg text-xs font-medium",
                    step.type === 'email' && "bg-purple-100 text-purple-700",
                    step.type === 'wait' && "bg-orange-100 text-orange-700",
                    step.type === 'condition' && "bg-blue-100 text-blue-700"
                  )}>
                    {idx + 1}. {step.type}
                  </div>
                  {idx < steps.length - 1 && <ArrowRight className="h-4 w-4 text-slate-300 mx-1" />}
                </div>
              ))}
            </div>
          </div>
          
          <DndContext 
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext 
              items={steps.map(s => s.id)}
              strategy={verticalListSortingStrategy}
            >
              <div className="py-2">
                {steps.map((step, index) => (
                  <SortableStep 
                    key={step.id} 
                    step={step} 
                    index={index}
                    onConfigure={(step) => setConfigureStep(step)}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>

          {/* Add Step Button */}
          <div className="flex justify-center mt-6">
            <div className="bg-white border border-slate-200 rounded-full shadow-sm p-1.5 flex items-center gap-1">
              <Button variant="ghost" size="sm" onClick={() => addStep('email')} className="rounded-full px-4">
                <Mail className="h-4 w-4 mr-2 text-purple-500" />
                Email
              </Button>
              <div className="w-px h-4 bg-slate-200 mx-1" />
              <Button variant="ghost" size="sm" onClick={() => addStep('wait')} className="rounded-full px-4">
                <Clock className="h-4 w-4 mr-2 text-orange-500" />
                Wait
              </Button>
              <div className="w-px h-4 bg-slate-200 mx-1" />
              <Button variant="ghost" size="sm" onClick={() => addStep('condition')} className="rounded-full px-4">
                <GitBranch className="h-4 w-4 mr-2 text-blue-500" />
                Branch
              </Button>
            </div>
          </div>

        </div>
      </div>

      {/* Step Configuration Panel */}
      {configureStep && (
        <StepConfigPanel
          step={configureStep}
          onUpdate={(updates) => updateStep(configureStep.id, updates)}
          onClose={() => setConfigureStep(null)}
        />
      )}
    </div>
  );
}

export default SequenceBuilderPage;