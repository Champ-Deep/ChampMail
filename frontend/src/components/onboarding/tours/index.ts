import type { Step } from 'react-joyride';

// Tour IDs
export const TOUR_IDS = {
  WELCOME: 'welcome',
  DASHBOARD: 'dashboard',
  TEMPLATES: 'templates',
  PROSPECTS: 'prospects',
  CAMPAIGNS: 'campaigns',
  SETTINGS: 'settings',
  EMAIL_SETUP: 'email-setup',
} as const;

// Welcome tour - shown on first login
export const welcomeTour: Step[] = [
  {
    target: 'body',
    content: 'Welcome to ChampMail! This quick tour will help you get started with your email marketing platform.',
    placement: 'center',
    disableBeacon: true,
    title: 'Welcome to ChampMail',
  },
  {
    target: '[data-tour="sidebar"]',
    content: 'Use the sidebar to navigate between different sections of the app. You can manage prospects, create templates, run campaigns, and more.',
    placement: 'right',
    title: 'Navigation',
  },
  {
    target: '[data-tour="nav-dashboard"]',
    content: 'The Dashboard gives you an overview of your email marketing performance, including sent emails, open rates, and recent activity.',
    placement: 'right',
    title: 'Dashboard',
  },
  {
    target: '[data-tour="nav-templates"]',
    content: 'Create and manage email templates here. Our visual editor makes it easy to design professional emails.',
    placement: 'right',
    title: 'Email Templates',
  },
  {
    target: '[data-tour="nav-prospects"]',
    content: 'Manage your leads and contacts. Import prospects from CSV or add them manually.',
    placement: 'right',
    title: 'Prospects',
  },
  {
    target: '[data-tour="nav-campaigns"]',
    content: 'Create and send email campaigns to your prospects. Track opens, clicks, and replies.',
    placement: 'right',
    title: 'Campaigns',
  },
  {
    target: '[data-tour="nav-settings"]',
    content: 'Configure your email settings here. You\'ll need to set up SMTP/IMAP credentials to send emails.',
    placement: 'right',
    title: 'Settings',
  },
  {
    target: 'body',
    content: 'You\'re all set! Head to Settings to configure your email credentials, then start creating templates and campaigns.',
    placement: 'center',
    title: 'Ready to Go!',
  },
];

// Templates tour
export const templatesTour: Step[] = [
  {
    target: '[data-tour="new-template-btn"]',
    content: 'Click here to create a new email template. Our visual editor supports MJML for beautiful responsive emails.',
    placement: 'bottom',
    title: 'Create Template',
    disableBeacon: true,
  },
  {
    target: '[data-tour="template-search"]',
    content: 'Search through your templates by name or subject line.',
    placement: 'bottom',
    title: 'Search Templates',
  },
  {
    target: '[data-tour="template-card"]',
    content: 'Click on any template to edit it. You can also duplicate, preview, or delete templates from the menu.',
    placement: 'right',
    title: 'Template Actions',
  },
];

// Prospects tour
export const prospectsTour: Step[] = [
  {
    target: '[data-tour="add-prospect-btn"]',
    content: 'Add prospects one at a time or import them in bulk from a CSV file.',
    placement: 'bottom',
    title: 'Add Prospects',
    disableBeacon: true,
  },
  {
    target: '[data-tour="import-btn"]',
    content: 'Import prospects from a CSV file. Required column: email. Optional: first_name, last_name, company, title.',
    placement: 'bottom',
    title: 'Import CSV',
  },
  {
    target: '[data-tour="prospect-table"]',
    content: 'View and manage all your prospects here. Select multiple prospects to add them to a campaign or delete them.',
    placement: 'top',
    title: 'Prospect List',
  },
];

// Email setup tour
export const emailSetupTour: Step[] = [
  {
    target: '[data-tour="smtp-settings"]',
    content: 'Enter your SMTP server details to send emails. Common providers: Gmail (smtp.gmail.com:587), Outlook (smtp.office365.com:587).',
    placement: 'top',
    title: 'SMTP Settings',
    disableBeacon: true,
  },
  {
    target: '[data-tour="smtp-host"]',
    content: 'Enter your SMTP server hostname. For Gmail, use smtp.gmail.com',
    placement: 'right',
    title: 'SMTP Host',
  },
  {
    target: '[data-tour="smtp-port"]',
    content: 'Use port 587 for TLS (recommended) or 465 for SSL.',
    placement: 'right',
    title: 'SMTP Port',
  },
  {
    target: '[data-tour="test-smtp-btn"]',
    content: 'Always test your connection before sending campaigns. This verifies your credentials are correct.',
    placement: 'left',
    title: 'Test Connection',
  },
  {
    target: '[data-tour="imap-settings"]',
    content: 'IMAP settings are used to detect replies to your campaigns. This is optional but recommended for tracking engagement.',
    placement: 'top',
    title: 'IMAP Settings (Optional)',
  },
];

// Get tour by ID
export const getTourById = (tourId: string): Step[] => {
  switch (tourId) {
    case TOUR_IDS.WELCOME:
      return welcomeTour;
    case TOUR_IDS.TEMPLATES:
      return templatesTour;
    case TOUR_IDS.PROSPECTS:
      return prospectsTour;
    case TOUR_IDS.EMAIL_SETUP:
      return emailSetupTour;
    default:
      return [];
  }
};
