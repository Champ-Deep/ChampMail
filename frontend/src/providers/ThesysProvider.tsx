import { ThemeProvider } from '@thesysai/genui-sdk';
import type { ReactNode } from 'react';

const champMailTheme = {
  interactiveAccent: '#2563eb',
  interactiveAccentHover: '#1d4ed8',
  interactiveAccentPressed: '#1e40af',
  backgroundFills: '#f8fafc',
  containerFills: '#ffffff',
  primaryText: '#0f172a',
  secondaryText: '#64748b',
  successFills: '#ecfdf5',
  successText: '#10b981',
  dangerFills: '#fef2f2',
  dangerText: '#ef4444',
  alertFills: '#fffbeb',
  chatContainerBg: '#f8fafc',
  chatAssistantResponseBg: '#f1f5f9',
  chatAssistantResponseText: '#0f172a',
  chatUserResponseBg: '#2563eb',
  chatUserResponseText: '#ffffff',
};

export function ChampMailThesysProvider({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider mode="light" theme={champMailTheme}>
      {children}
    </ThemeProvider>
  );
}
