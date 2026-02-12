// Re-export all types from API modules
export type {
  User,
  LoginCredentials,
  RegisterData,
  AuthResponse,
} from '../api/auth';

export type {
  EmailTemplate,
  TemplateCreate,
  TemplateUpdate,
  TemplatePreviewRequest,
  TemplatePreviewResponse,
} from '../api/templates';

export type {
  Prospect,
  ProspectCreate,
  ProspectUpdate,
  ProspectListParams,
  ProspectTimeline,
} from '../api/prospects';

export type {
  Sequence,
  SequenceCreate,
  SequenceUpdate,
  SequenceStep,
  SequenceAnalytics,
  StepType,
  SequenceStatus,
  EnrollmentStatus,
} from '../api/sequences';

// UI Types
export interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
}

export interface StatCard {
  label: string;
  value: number | string;
  change?: number;
  changeLabel?: string;
  icon: React.ComponentType<{ className?: string }>;
}
