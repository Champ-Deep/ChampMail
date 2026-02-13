import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bot,
  Send,
  Plus,
  Trash2,
  MessageSquare,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { c1Api, type ChatMessage, type ConversationSummary } from '../api/c1';
import { toast } from 'sonner';

const SUGGESTED_PROMPTS = [
  'Show my campaign performance this week',
  'List my top prospects by company',
  'Compare open rates across my campaigns',
  'What are my best performing domains?',
  'Help me plan a new campaign targeting SaaS companies',
];

export function AIAssistantPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load conversations on mount
  useEffect(() => {
    c1Api.listConversations()
      .then(setConversations)
      .catch(() => {}); // Silently fail if C1 not configured
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const loadConversation = useCallback(async (id: string) => {
    try {
      const conv = await c1Api.getConversation(id);
      setMessages(conv.messages);
      setActiveConversationId(id);
    } catch {
      toast.error('Failed to load conversation');
    }
  }, []);

  const startNewConversation = useCallback(() => {
    setMessages([]);
    setActiveConversationId(null);
    setStreamingContent('');
    setInput('');
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await c1Api.deleteConversation(id);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (activeConversationId === id) {
        startNewConversation();
      }
      toast.success('Conversation deleted');
    } catch {
      toast.error('Failed to delete conversation');
    }
  }, [activeConversationId, startNewConversation]);

  const handleSend = useCallback(async (promptOverride?: string) => {
    const text = promptOverride || input.trim();
    if (!text || isStreaming) return;

    const userMessage: ChatMessage = { role: 'user', content: text };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    setInput('');
    setIsStreaming(true);
    setStreamingContent('');

    try {
      const response = await c1Api.chatStream({
        messages: newMessages,
        context_type: 'general',
        conversation_id: activeConversationId || undefined,
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response stream');

      const decoder = new TextDecoder();
      let content = '';
      let convId = activeConversationId;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                content += data.content;
                setStreamingContent(content);
              }
              if (data.conversation_id) {
                convId = data.conversation_id;
              }
            } catch {
              // Skip
            }
          }
        }
      }

      // Finalize
      const assistantMessage: ChatMessage = { role: 'assistant', content };
      setMessages(prev => [...prev, assistantMessage]);
      setStreamingContent('');

      if (convId) {
        setActiveConversationId(convId);
        // Refresh conversation list
        c1Api.listConversations().then(setConversations).catch(() => {});
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to get response');
    } finally {
      setIsStreaming(false);
    }
  }, [input, messages, isStreaming, activeConversationId]);

  return (
    <div className="h-[calc(100vh-4rem)] flex">
      {/* Conversation Sidebar */}
      <div className="w-64 border-r border-slate-200 bg-slate-50 flex flex-col flex-shrink-0">
        <div className="p-3 border-b border-slate-200">
          <Button
            size="sm"
            className="w-full"
            onClick={startNewConversation}
          >
            <Plus className="h-4 w-4 mr-1.5" />
            New Chat
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer hover:bg-slate-100 transition-colors group ${
                activeConversationId === conv.id ? 'bg-blue-50 border-r-2 border-blue-600' : ''
              }`}
              onClick={() => loadConversation(conv.id)}
            >
              <MessageSquare className="h-4 w-4 text-slate-400 flex-shrink-0" />
              <span className="text-sm text-slate-700 truncate flex-1">{conv.title}</span>
              <button
                onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }}
                className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-all"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}

          {conversations.length === 0 && (
            <p className="text-xs text-slate-400 text-center mt-8 px-4">
              No conversations yet. Start a new chat!
            </p>
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="h-14 border-b border-slate-200 flex items-center px-6 flex-shrink-0">
          <Bot className="h-5 w-5 text-blue-600 mr-2" />
          <h1 className="text-lg font-semibold text-slate-900">AI Assistant</h1>
          <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">Powered by Thesys C1</span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-100 to-indigo-100 flex items-center justify-center mb-4">
                <Sparkles className="h-8 w-8 text-blue-600" />
              </div>
              <h2 className="text-xl font-semibold text-slate-900 mb-2">ChampMail AI Assistant</h2>
              <p className="text-sm text-slate-500 mb-6 max-w-md">
                Ask me about your campaigns, analytics, prospects, or anything related to your email outreach.
              </p>
              <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => handleSend(prompt)}
                    className="text-xs px-3 py-1.5 rounded-full bg-slate-100 text-slate-600 hover:bg-blue-100 hover:text-blue-700 transition-colors"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-900'
                }`}
              >
                <div className="prose prose-sm max-w-none whitespace-pre-wrap" style={msg.role === 'user' ? { color: 'white' } : {}}>
                  {msg.content}
                </div>
              </div>
            </div>
          ))}

          {/* Streaming response */}
          {isStreaming && (
            <div className="flex justify-start">
              <div className="max-w-[75%] rounded-2xl px-4 py-3 bg-slate-100 text-slate-900">
                {streamingContent ? (
                  <div className="prose prose-sm max-w-none whitespace-pre-wrap">
                    {streamingContent}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">Thinking...</span>
                  </div>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-200 p-4 flex-shrink-0">
          <div className="flex items-center gap-3 max-w-3xl mx-auto">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder="Ask about your campaigns, analytics, prospects..."
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
              disabled={isStreaming}
            />
            <Button
              onClick={() => handleSend()}
              disabled={isStreaming || !input.trim()}
              className="rounded-xl"
            >
              {isStreaming ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AIAssistantPage;
