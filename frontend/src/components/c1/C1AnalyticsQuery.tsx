import { useState, useCallback } from 'react';
import { Sparkles, Loader2, X } from 'lucide-react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { c1Api, type ChatMessage } from '../../api/c1';

const SUGGESTED_QUERIES = [
  'Show my campaign performance this week',
  'Compare open rates across domains',
  'Which campaigns have the highest bounce rate?',
  'Plot daily send volume for the last 30 days',
];

export function C1AnalyticsQuery() {
  const [query, setQuery] = useState('');
  const [c1Response, setC1Response] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleQuery = useCallback(async (input?: string) => {
    const q = input || query;
    if (!q.trim()) return;

    setIsLoading(true);
    setError(null);
    setC1Response(null);

    try {
      const messages: ChatMessage[] = [{ role: 'user', content: q }];
      const response = await c1Api.chatStream({
        messages,
        context_type: 'analytics',
      });

      const reader = response.body?.getReader();
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
                setC1Response(content);
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get AI response');
    } finally {
      setIsLoading(false);
    }
  }, [query]);

  return (
    <Card padding="none" className="p-4 border-brand-purple/20 bg-gradient-to-r from-brand-purple/5 to-brand-purple/10 mb-6">
      <div className="flex items-center gap-3 mb-3">
        <Sparkles className="h-5 w-5 text-brand-purple flex-shrink-0" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isLoading && handleQuery()}
          placeholder="Ask about your analytics... e.g. 'Show open rates by domain this month'"
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-brand-purple text-slate-900"
          disabled={isLoading}
        />
        <Button
          size="sm"
          onClick={() => handleQuery()}
          disabled={isLoading || !query.trim()}
        >
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Ask AI'}
        </Button>
      </div>

      {/* Suggested queries */}
      {!c1Response && !isLoading && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTED_QUERIES.map((sq) => (
            <button
              key={sq}
              onClick={() => { setQuery(sq); handleQuery(sq); }}
              className="text-xs px-2.5 py-1 rounded-full bg-brand-purple/10 text-brand-purple hover:bg-brand-purple/20 transition-colors"
            >
              {sq}
            </button>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-3 p-3 rounded-lg bg-red-50 text-red-700 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)}><X className="h-4 w-4" /></button>
        </div>
      )}

      {/* C1 Response */}
      {c1Response && (
        <div className="mt-4 border-t border-brand-purple/20 pt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-brand-purple font-medium">AI Response</span>
            <button
              onClick={() => { setC1Response(null); setQuery(''); }}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              Clear
            </button>
          </div>
          <div className="prose prose-sm max-w-none text-slate-700 whitespace-pre-wrap">
            {c1Response}
          </div>
        </div>
      )}
    </Card>
  );
}
