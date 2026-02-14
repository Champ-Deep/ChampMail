import DOMPurify from 'dompurify';
import { Card } from '../ui/Card';
import { Mail, User, Send } from 'lucide-react';

interface EmailPreviewProps {
  subject: string;
  body: string;
  from?: string;
  to?: string;
}

export function EmailPreview({ subject, body, from, to }: EmailPreviewProps) {
  return (
    <Card padding="none" className="overflow-hidden border-slate-200">
      <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 space-y-1.5">
        <div className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-slate-400" />
          <span className="text-sm font-semibold text-slate-900">{subject}</span>
        </div>
        {from && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Send className="h-3 w-3" />
            <span>From: {from}</span>
          </div>
        )}
        {to && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <User className="h-3 w-3" />
            <span>To: {to}</span>
          </div>
        )}
      </div>
      <div
        className="p-4 prose prose-sm max-w-none text-slate-700"
        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(body) }}
      />
    </Card>
  );
}
