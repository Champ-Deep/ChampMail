import { useState, useCallback } from 'react';
import { Sparkles, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { Card } from '../ui/Card';
import { c1Api, type ChatMessage } from '../../api/c1';

interface C1CampaignSuggestionsProps {
  description: string;
  essence: Record<string, unknown>;
}

export function C1CampaignSuggestions({ description, essence }: C1CampaignSuggestionsProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [response, setResponse] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSuggestions = useCallback(async () => {
    if (response) {
      setIsExpanded(!isExpanded);
      return;
    }

    setIsExpanded(true);
    setIsLoading(true);
    setError(null);

    try {
      const prompt = `Given this campaign description: "${description}"

And these extracted campaign values: ${JSON.stringify(essence, null, 2)}

Please suggest:
1. Optimal send timing recommendations
2. Subject line A/B test variations (3-4 options)
3. Tone and positioning suggestions
4. Key personalization opportunities

Format your response with clear sections and actionable recommendations.`;

      const messages: ChatMessage[] = [{ role: 'user', content: prompt }];
      const streamResponse = await c1Api.chatStream({
        messages,
        context_type: 'campaign',
      });

      const reader = streamResponse.body?.getReader();
      if (!reader) throw new Error('No response stream');

      const decoder = new TextDecoder();
      let content = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                content += data.content;
                setResponse(content);
              }
            } catch {
              // Skip
            }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get suggestions');
    } finally {
      setIsLoading(false);
    }
  }, [description, essence, response, isExpanded]);

  return (
    <Card padding="none" className="border-blue-200 bg-blue-50/30 overflow-hidden mt-4">
      <button
        onClick={fetchSuggestions}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-blue-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-blue-600" />
          <span className="text-sm font-medium text-blue-900">AI Campaign Suggestions</span>
          {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />}
        </div>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-blue-500" />
        ) : (
          <ChevronDown className="h-4 w-4 text-blue-500" />
        )}
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 border-t border-blue-200">
          {error && (
            <p className="text-sm text-red-600 mt-3">{error}</p>
          )}
          {response && (
            <div className="mt-3 prose prose-sm max-w-none text-slate-700 whitespace-pre-wrap">
              {response}
            </div>
          )}
          {!response && !isLoading && !error && (
            <p className="text-sm text-blue-500 mt-3">Click to generate AI-powered campaign suggestions...</p>
          )}
        </div>
      )}
    </Card>
  );
}
