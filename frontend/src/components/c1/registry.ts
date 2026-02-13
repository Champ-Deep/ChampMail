/**
 * Custom C1 component registry.
 * Defines Zod schemas for domain-specific components that C1 can generate.
 */

import { z } from 'zod';

// Schema definitions for C1 custom components
export const CampaignCardSchema = z.object({
  name: z.string().describe('Campaign name'),
  status: z.enum(['active', 'paused', 'completed', 'draft']).describe('Campaign status'),
  sent: z.number().describe('Number of emails sent'),
  openRate: z.number().describe('Open rate percentage'),
  clickRate: z.number().describe('Click rate percentage'),
  bounceRate: z.number().optional().describe('Bounce rate percentage'),
}).describe('Displays a campaign summary card with key metrics');

export const MetricCardSchema = z.object({
  label: z.string().describe('Metric label'),
  value: z.string().describe('Metric value (formatted)'),
  change: z.number().optional().describe('Percentage change from previous period'),
  trend: z.enum(['up', 'down', 'flat']).optional().describe('Trend direction'),
  color: z.enum(['blue', 'green', 'purple', 'red', 'orange']).optional().describe('Card accent color'),
}).describe('Displays a single KPI metric with optional trend indicator');

export const ProspectTableSchema = z.object({
  prospects: z.array(z.object({
    email: z.string(),
    name: z.string().optional(),
    company: z.string().optional(),
    title: z.string().optional(),
    industry: z.string().optional(),
  })).describe('List of prospect data'),
}).describe('Displays a table of prospects with their details');

export const EmailPreviewSchema = z.object({
  subject: z.string().describe('Email subject line'),
  body: z.string().describe('Email body content (HTML or text)'),
  from: z.string().optional().describe('Sender address'),
  to: z.string().optional().describe('Recipient address'),
}).describe('Previews an email with subject and body');

// Component name to schema mapping for C1 API
export const customComponentSchemas = {
  CampaignCard: CampaignCardSchema,
  MetricCard: MetricCardSchema,
  ProspectTable: ProspectTableSchema,
  EmailPreview: EmailPreviewSchema,
};

// Re-export component implementations (imported by pages that use C1)
export { CampaignCard } from './CampaignCard';
export { MetricCard } from './MetricCard';
export { ProspectTable } from './ProspectTable';
export { EmailPreview } from './EmailPreview';

// Component map for C1Component customComponents prop
export const customComponents = {
  CampaignCard: () => import('./CampaignCard').then(m => m.CampaignCard),
  MetricCard: () => import('./MetricCard').then(m => m.MetricCard),
  ProspectTable: () => import('./ProspectTable').then(m => m.ProspectTable),
  EmailPreview: () => import('./EmailPreview').then(m => m.EmailPreview),
};
