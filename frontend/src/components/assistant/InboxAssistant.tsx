import { useState, useRef, useEffect } from 'react';
import { toast } from 'sonner';
import {
  Mail,
  MessageSquare,
  Bot,
  Send,
  Loader2,
  X,
} from 'lucide-react';
import { Card, Button, Badge } from '../ui';
import { workflowsApi, type EmailDraft } from '../../api/workflows';

// Chat Message Interface
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  error?: boolean;
  draft?: EmailDraft;  // Draft email from n8n
}

// Email Assistant Chat Component
export function InboxAssistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pendingDraft, setPendingDraft] = useState<EmailDraft | null>(null);
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await workflowsApi.chat(userMessage.content, sessionId || undefined);

      if (!sessionId && response.session_id) {
        setSessionId(response.session_id);
      }

      const errorContent = response.error?.includes('line 1')
        ? 'The email assistant backend (n8n) is not configured or not running. Please set up n8n to use this feature.'
        : response.error || 'Sorry, I encountered an error processing your request.';

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.success
          ? response.response
          : errorContent,
        timestamp: new Date(),
        error: !response.success,
        draft: response.draft,
      };

      setMessages(prev => [...prev, assistantMessage]);

      // If n8n returned a draft, show the send confirmation UI
      if (response.draft) {
        setPendingDraft(response.draft);
        toast.info('Email drafted! Enter recipient and click Send.');
      }
    } catch (error: unknown) {
      const axiosMsg = (error as { response?: { data?: { error?: string; detail?: string } } })?.response?.data;
      const detail = axiosMsg?.error || axiosMsg?.detail || '';
      const friendlyMsg = detail.includes('line 1') || detail.includes('n8n')
        ? 'The email assistant backend (n8n) is not configured. Set up an n8n instance to use the chat assistant.'
        : 'Failed to connect to the email assistant. Please check if the backend is running.';

      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: friendlyMsg,
        timestamp: new Date(),
        error: true,
      };
      setMessages(prev => [...prev, errorMessage]);
      toast.error('Email assistant unavailable');
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    setMessages([]);
    setSessionId(null);
    setPendingDraft(null);
    setRecipientEmail('');
    toast.success('Chat cleared');
  };

  // Send the drafted email with the recipient
  const sendDraftEmail = async () => {
    if (!pendingDraft || !recipientEmail.trim()) {
      toast.error('Please enter a recipient email address');
      return;
    }

    setIsSending(true);
    try {
      const result = await workflowsApi.sendDraft({
        to: recipientEmail.trim(),
        subject: pendingDraft.subject,
        body: pendingDraft.body,
        html_body: pendingDraft.html_body,
      });

      if (result.success) {
        toast.success('Email sent successfully!');
        setPendingDraft(null);
        setRecipientEmail('');

        // Add confirmation message to chat
        const confirmMessage: ChatMessage = {
          id: `confirm-${Date.now()}`,
          role: 'assistant',
          content: `Email sent to ${recipientEmail}!`,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, confirmMessage]);
      } else {
        toast.error(result.error || 'Failed to send email');
      }
    } catch (error) {
      toast.error('Failed to send email');
    } finally {
      setIsSending(false);
    }
  };

  const cancelDraft = () => {
    setPendingDraft(null);
    setRecipientEmail('');
    toast.info('Draft cancelled');
  };

  return (
    <Card className="p-6 bg-gradient-to-br from-indigo-50 to-purple-50 border-indigo-200">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-indigo-600 rounded-full">
            <MessageSquare className="h-6 w-6 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900">Inbox Assistant (n8n)</h3>
            <p className="text-sm text-slate-500">Chat to manage your emails with AI</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <Badge className="bg-green-100 text-green-700">
              Session Active
            </Badge>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={clearChat}
            disabled={messages.length === 0}
          >
            Clear
          </Button>
        </div>
      </div>

      {/* Chat Messages */}
      <div className="bg-white rounded-lg border border-indigo-100 mb-4 h-80 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-400">
            <Bot className="h-12 w-12 mb-3 opacity-50" />
            <p className="text-center">
              Hi! I'm your Inbox Assistant.<br />
              Ask me to check your emails, write messages, or manage your inbox.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white'
                      : msg.error
                      ? 'bg-red-100 text-red-800 border border-red-200'
                      : 'bg-slate-100 text-slate-800'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                  <p className={`text-xs mt-1 ${
                    msg.role === 'user' ? 'text-indigo-200' : 'text-slate-400'
                  }`}>
                    {msg.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-slate-100 rounded-lg px-4 py-2">
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
                    <span className="text-slate-600">Thinking...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Draft Email Confirmation Panel */}
      {pendingDraft && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-green-800 flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Email Drafted - Ready to Send
            </h4>
            <button
              onClick={cancelDraft}
              className="text-green-600 hover:text-green-800"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="space-y-3">
            {/* Subject Preview */}
            <div className="bg-white rounded-lg p-3 border border-green-100">
              <p className="text-xs text-slate-500 mb-1">Subject:</p>
              <p className="text-slate-800 font-medium">{pendingDraft.subject}</p>
            </div>

            {/* Body Preview */}
            <div className="bg-white rounded-lg p-3 border border-green-100 max-h-32 overflow-y-auto">
              <p className="text-xs text-slate-500 mb-1">Body:</p>
              <p className="text-slate-700 text-sm whitespace-pre-wrap">{pendingDraft.body}</p>
            </div>

            {/* Recipient Input */}
            <div>
              <label className="text-xs text-slate-600 mb-1 block">Send to:</label>
              <div className="flex items-center gap-2">
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="Enter recipient email address"
                  className="flex-1 px-3 py-2 border border-green-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                />
                <Button
                  onClick={sendDraftEmail}
                  disabled={!recipientEmail.trim() || isSending}
                  className="bg-green-600 hover:bg-green-700"
                  leftIcon={isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                >
                  {isSending ? 'Sending...' : 'Send Email'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type a message... (e.g., 'Check my emails' or 'Write an email to john@example.com')"
          className="flex-1 px-4 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          disabled={isLoading || !!pendingDraft}
        />
        <Button
          onClick={sendMessage}
          disabled={!inputValue.trim() || isLoading || !!pendingDraft}
          leftIcon={isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        >
          Send
        </Button>
      </div>

      {/* Quick Actions */}
      <div className="mt-4 pt-4 border-t border-indigo-200">
        <p className="text-xs text-slate-500 mb-2"><strong>Quick actions:</strong></p>
        <div className="flex flex-wrap gap-2">
          {[
            'Check my emails',
            'Summarize my inbox',
            'Write a professional email',
            'Reply to the last email',
          ].map((action) => (
            <button
              key={action}
              onClick={() => {
                setInputValue(action);
                inputRef.current?.focus();
              }}
              className="text-xs px-3 py-1 bg-white border border-indigo-200 rounded-full hover:bg-indigo-50 text-indigo-700 transition-colors"
            >
              {action}
            </button>
          ))}
        </div>
      </div>
    </Card>
  );
}
