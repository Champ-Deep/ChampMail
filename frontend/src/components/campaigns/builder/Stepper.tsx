import { clsx } from 'clsx';
import { CheckCircle2, type LucideIcon } from 'lucide-react';

interface Step {
  id: number;
  label: string;
  icon: LucideIcon;
  description: string;
}

interface StepperProps {
  steps: readonly Step[];
  currentStep: number;
  completedSteps: Set<number>;
}

export function Stepper({ steps, currentStep, completedSteps }: StepperProps) {
  return (
    <nav className="w-full" aria-label="Campaign builder progress">
      <ol className="flex items-center">
        {steps.map((step, index) => {
          const isActive = step.id === currentStep;
          const isCompleted = completedSteps.has(step.id);
          const isLast = index === steps.length - 1;
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
