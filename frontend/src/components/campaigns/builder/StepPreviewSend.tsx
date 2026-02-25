import { useState } from 'react';
import { toast } from 'sonner';
import { Send, Sparkles, Eye, Copy, XCircle, Loader2 } from 'lucide-react';
import { Card, Button, Badge } from '../../ui';
import type { PersonalizedEmail } from '../../../api/admin';
import { clsx } from 'clsx';

interface Step6Props {
  personalizedEmails: PersonalizedEmail[];
  onPersonalize: () => void;
  isPersonalizing: boolean;
  onGenerateHtml: (email: PersonalizedEmail) => void;
  isGeneratingHtml: boolean;
  htmlPreviews: Record<string, string>;
  onSend: () => void;
  isSending: boolean;
}

export function StepPreviewSend({
  personalizedEmails,
  onPersonalize,
  isPersonalizing,
  onGenerateHtml,
  isGeneratingHtml,
  htmlPreviews,
  onSend,
  isSending,
}: Step6Props) {
  const [selectedEmailIdx, setSelectedEmailIdx] = useState(0);
  const [showHtmlPreview, setShowHtmlPreview] = useState(false);

  const currentEmail = personalizedEmails[selectedEmailIdx];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Preview & Send
        </h2>
        <p className="text-sm text-slate-500">
          Review personalized emails and preview HTML rendering before sending
          the campaign.
        </p>
      </div>

      {personalizedEmails.length === 0 && (
        <Card className="text-center py-10">
          <Send className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Ready to Personalize
          </h3>
          <p className="text-slate-500 max-w-md mx-auto mb-6">
            Generate personalized emails for each prospect based on the segment
            pitches and their individual research data.
          </p>
          <Button
            onClick={onPersonalize}
            disabled={isPersonalizing}
            isLoading={isPersonalizing}
            leftIcon={<Sparkles className="h-4 w-4" />}
          >
            {isPersonalizing
              ? 'Personalizing Emails...'
              : 'Generate Personalized Emails'}
          </Button>
        </Card>
      )}

      {personalizedEmails.length > 0 && (
        <div className="space-y-4">
          {/* Summary Bar */}
          <div className="flex items-center justify-between p-4 bg-gradient-to-r from-brand-purple/5 to-brand-lavender/10 border border-brand-purple/20 rounded-xl">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-brand-purple/10 flex items-center justify-center">
                <Send className="h-6 w-6 text-brand-purple" />
              </div>
              <div>
                <p className="text-lg font-semibold text-slate-900">
                  {personalizedEmails.length} Emails Ready
                </p>
                <p className="text-sm text-slate-500">
                  Personalized and ready to send
                </p>
              </div>
            </div>
            <Button
              onClick={onSend}
              disabled={isSending}
              isLoading={isSending}
              leftIcon={<Send className="h-4 w-4" />}
              className="bg-gradient-to-r from-brand-purple to-brand-navy hover:from-brand-purple/90 hover:to-brand-navy/90"
            >
              {isSending ? 'Sending...' : 'Send Campaign'}
            </Button>
          </div>

          <div className="flex gap-6">
            {/* Email List */}
            <div className="w-64 flex-shrink-0 space-y-1.5 max-h-[500px] overflow-y-auto pr-1">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2 sticky top-0 bg-white py-1">
                Emails ({personalizedEmails.length})
              </p>
              {personalizedEmails.map((email, idx) => (
                <button
                  key={email.prospect_email || idx}
                  onClick={() => setSelectedEmailIdx(idx)}
                  className={clsx(
                    'w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all border',
                    idx === selectedEmailIdx
                      ? 'border-brand-purple/30 bg-brand-purple/5'
                      : 'border-transparent hover:bg-slate-50'
                  )}
                >
                  <p className="font-medium text-slate-800 truncate">
                    {email.prospect_email}
                  </p>
                  <p className="text-xs text-slate-500 truncate mt-0.5">
                    {email.subject}
                  </p>
                </button>
              ))}
            </div>

            {/* Email Preview */}
            {currentEmail && (
              <div className="flex-1 min-w-0 space-y-4">
                <Card>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-slate-500">To:</p>
                        <p className="text-sm font-medium text-slate-900">
                          {currentEmail.prospect_email}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            onGenerateHtml(currentEmail);
                            setShowHtmlPreview(true);
                          }}
                          disabled={isGeneratingHtml}
                          isLoading={isGeneratingHtml}
                          leftIcon={<Eye className="h-3.5 w-3.5" />}
                        >
                          HTML Preview
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            navigator.clipboard.writeText(
                              `Subject: ${currentEmail.subject}

${currentEmail.body}`
                            );
                            toast.success('Copied to clipboard');
                          }}
                          leftIcon={<Copy className="h-3.5 w-3.5" />}
                        >
                          Copy
                        </Button>
                      </div>
                    </div>

                    <div className="border-t border-slate-100 pt-3">
                      <p className="text-xs text-slate-500">Subject:</p>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5">
                        {currentEmail.subject}
                      </p>
                    </div>

                    <div className="border-t border-slate-100 pt-3">
                      <p className="text-xs text-slate-500 mb-1">Body:</p>
                      <div className="bg-slate-50 rounded-lg p-4 text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                        {currentEmail.body}
                      </div>
                    </div>

                    {/* Follow-ups */}
                    {currentEmail.follow_ups &&
                      currentEmail.follow_ups.length > 0 && (
                        <div className="border-t border-slate-100 pt-3">
                          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                            Follow-up Sequence
                          </p>
                          <div className="space-y-2">
                            {currentEmail.follow_ups.map((fu, i) => (
                              <div
                                key={i}
                                className="pl-3 border-l-2 border-brand-purple/20"
                              >
                                <div className="flex items-center gap-2">
                                  <Badge variant="info" size="sm">
                                    Day {fu.delay_days}
                                  </Badge>
                                  <span className="text-xs font-medium text-slate-700">
                                    {fu.subject}
                                  </span>
                                </div>
                                <p className="text-xs text-slate-500 mt-1 whitespace-pre-wrap">
                                  {fu.body}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                    {/* Variables Used */}
                    {currentEmail.variables_used && (
                      <div className="border-t border-slate-100 pt-3">
                        <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
                          Personalization Variables
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(currentEmail.variables_used).map(
                            ([key, val]) => (
                              <div
                                key={key}
                                className="text-xs bg-slate-100 rounded px-2 py-1"
                              >
                                <span className="font-mono text-slate-500">
                                  {key}:
                                </span>{' '}
                                <span className="text-slate-700">{val}</span>
                              </div>
                            )
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </Card>
              </div>
            )}
          </div>
        </div>
      )}

      {/* HTML Preview Modal */}
      {showHtmlPreview && currentEmail && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <div>
                <h3 className="font-semibold text-slate-900">
                  HTML Email Preview
                </h3>
                <p className="text-xs text-slate-500">
                  {currentEmail.prospect_email}
                </p>
              </div>
              <button
                onClick={() => setShowHtmlPreview(false)}
                className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <XCircle className="h-5 w-5 text-slate-400" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {htmlPreviews[currentEmail.prospect_email] ? (
                <iframe
                  srcDoc={htmlPreviews[currentEmail.prospect_email]}
                  className="w-full h-full min-h-[500px] border border-slate-200 rounded-lg"
                  title="Email HTML Preview"
                  sandbox="allow-same-origin"
                />
              ) : isGeneratingHtml ? (
                <div className="flex flex-col items-center justify-center py-16">
                  <Loader2 className="h-8 w-8 text-brand-purple animate-spin mb-3" />
                  <p className="text-sm text-slate-500">
                    Generating HTML email...
                  </p>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16">
                  <Eye className="h-10 w-10 text-slate-300 mb-3" />
                  <p className="text-sm text-slate-500">
                    Click "HTML Preview" to generate
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
