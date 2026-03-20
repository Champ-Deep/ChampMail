/**
 * Shared Zod validation schemas for ChampMail forms.
 *
 * Used by: Settings page, Upload flow, Campaign send.
 */

import { z } from 'zod';

// ============================================================
// Primitives
// ============================================================

const emailField = z
  .string()
  .min(1, 'Email is required')
  .email('Enter a valid email address');

const portField = z.coerce
  .number()
  .int()
  .min(1, 'Port must be between 1 and 65535')
  .max(65535, 'Port must be between 1 and 65535');

const hostnameField = z
  .string()
  .min(1, 'Hostname is required')
  .regex(
    /^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$/,
    'Enter a valid hostname (e.g. smtp.example.com)',
  );

// ============================================================
// SMTP Settings
// ============================================================

export const smtpSettingsSchema = z.object({
  host: hostnameField,
  port: portField.default(587),
  username: z.string().min(1, 'Username is required'),
  password: z.string().optional(),
  use_tls: z.boolean().default(true),
});

export type SmtpSettingsForm = z.infer<typeof smtpSettingsSchema>;

// ============================================================
// IMAP Settings
// ============================================================

export const imapSettingsSchema = z.object({
  host: hostnameField,
  port: portField.default(993),
  username: z.string().min(1, 'Username is required'),
  password: z.string().optional(),
  use_ssl: z.boolean().default(true),
  mailbox: z.string().default('INBOX'),
});

export type ImapSettingsForm = z.infer<typeof imapSettingsSchema>;

// ============================================================
// Sender Identity
// ============================================================

export const senderIdentitySchema = z.object({
  from_name: z.string().optional(),
  from_email: z.union([emailField, z.literal('')]).optional(),
  reply_to_email: z.union([emailField, z.literal('')]).optional(),
});

export type SenderIdentityForm = z.infer<typeof senderIdentitySchema>;

// ============================================================
// Column Mapping (upload flow)
// ============================================================

/** The system fields a file column can be mapped to. */
export const SYSTEM_FIELDS = [
  'email',
  'first_name',
  'last_name',
  'company_name',
  'company_domain',
  'title',
  'phone',
  'linkedin_url',
  'industry',
  'company_size',
] as const;

export type SystemField = (typeof SYSTEM_FIELDS)[number];

/**
 * Validates the column_mapping dict submitted during upload-confirm.
 * At least one header must be mapped to "email".
 */
export const columnMappingSchema = z
  .record(z.string(), z.string())
  .refine(
    (mapping) => Object.values(mapping).includes('email'),
    { message: 'You must map at least one column to "email"' },
  );

export type ColumnMapping = z.infer<typeof columnMappingSchema>;

// ============================================================
// Campaign Send
// ============================================================

export const sendTestEmailSchema = z.object({
  email: emailField,
});

export type SendTestEmailForm = z.infer<typeof sendTestEmailSchema>;

// ============================================================
// Helpers
// ============================================================

/**
 * Extract the first error message for a given field path from a ZodError.
 * Returns undefined if there's no error for that path.
 */
export function zodFieldError(
  error: z.ZodError | null | undefined,
  path: string,
): string | undefined {
  if (!error) return undefined;
  const issue = error.issues.find(
    (i) => i.path.join('.') === path,
  );
  return issue?.message;
}
