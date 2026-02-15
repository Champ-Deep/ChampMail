import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Plus,
  Workflow,
  Pause,
  Trash2,
  Settings,
  Zap,
  Mail,
  MessageSquare,
  Bot,
  Upload,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Phone,
  PhoneOff,
  Copy,
  Link,
  Power,
  Send,
  Loader2,
  X,
} from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button, Badge } from '../components/ui';
import { workflowsApi, type Workflow as WorkflowType, type WorkflowExecution, type EmailDraft } from '../api/workflows';

const WORKFLOW_TYPE_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  auto_reply: {
    icon: <MessageSquare className="h-5 w-5" />,
    color: 'bg-brand-purple/10 text-brand-purple',
    label: 'Auto Reply',
  },
  email_writer: {
    icon: <Mail className="h-5 w-5" />,
    color: 'bg-green-100 text-green-700',
    label: 'Email Writer',
  },
  email_summary: {
    icon: <Zap className="h-5 w-5" />,
    color: 'bg-purple-100 text-purple-700',
    label: 'Email Summary',
  },
  controller: {
    icon: <Bot className="h-5 w-5" />,
    color: 'bg-orange-100 text-orange-700',
    label: 'Controller',
  },
  custom: {
    icon: <Settings className="h-5 w-5" />,
    color: 'bg-slate-100 text-slate-700',
    label: 'Custom',
  },
};

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  active: { color: 'bg-green-100 text-green-700', icon: <CheckCircle className="h-4 w-4" /> },
  inactive: { color: 'bg-slate-100 text-slate-600', icon: <Pause className="h-4 w-4" /> },
  error: { color: 'bg-red-100 text-red-700', icon: <XCircle className="h-4 w-4" /> },
};

interface WorkflowCardProps {
  workflow: WorkflowType;
  onToggle: () => void;
  onTrigger: () => void;
  onDelete: () => void;
  isToggling: boolean;
  isTriggering: boolean;
}

function WorkflowCard({ workflow, onToggle, onTrigger, onDelete, isToggling, isTriggering }: WorkflowCardProps) {
  const [showExecutions, setShowExecutions] = useState(false);
  const [showWebhookInfo, setShowWebhookInfo] = useState(false);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loadingExecutions, setLoadingExecutions] = useState(false);

  const typeConfig = WORKFLOW_TYPE_CONFIG[workflow.workflow_type] || WORKFLOW_TYPE_CONFIG.custom;
  const statusConfig = STATUS_CONFIG[workflow.status] || STATUS_CONFIG.inactive;

  // Get the webhook URLs for n8n integration
  const apiBaseUrl = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL || 'http://localhost:8000';
  const webhookSendUrl = `${apiBaseUrl}/api/v1/webhook/send`;
  const webhookFetchUrl = `${apiBaseUrl}/api/v1/webhook/fetch`;

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

  const loadExecutions = async () => {
    if (showExecutions) {
      setShowExecutions(false);
      return;
    }
    setLoadingExecutions(true);
    try {
      const data = await workflowsApi.getExecutions(workflow.id, 5);
      setExecutions(data);
      setShowExecutions(true);
    } catch (error) {
      toast.error('Failed to load executions');
    } finally {
      setLoadingExecutions(false);
    }
  };

  return (
    <Card className="p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${typeConfig.color}`}>
            {typeConfig.icon}
          </div>
          <div>
            <h3 className="font-semibold text-slate-900">{workflow.name}</h3>
            <p className="text-sm text-slate-500">{typeConfig.label}</p>
          </div>
        </div>
        <Badge className={statusConfig.color}>
          <span className="flex items-center gap-1">
            {statusConfig.icon}
            {workflow.status}
          </span>
        </Badge>
      </div>

      {workflow.description && (
        <p className="text-sm text-slate-600 mb-4 line-clamp-2">{workflow.description}</p>
      )}

      <div className="flex items-center gap-4 text-sm text-slate-500 mb-4">
        <span className="flex items-center gap-1">
          <Zap className="h-4 w-4" />
          {workflow.execution_count} executions
        </span>
        {workflow.last_executed_at && (
          <span className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            Last: {new Date(workflow.last_executed_at).toLocaleDateString()}
          </span>
        )}
      </div>

      {workflow.last_error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span className="line-clamp-1">{workflow.last_error}</span>
          </p>
        </div>
      )}

      {/* Activation Toggle with Power Button */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-100">
        <div className="flex items-center gap-3">
          {/* Power Toggle */}
          <button
            onClick={onToggle}
            disabled={isToggling}
            className={`relative flex items-center justify-center w-12 h-12 rounded-full transition-all duration-300 ${
              workflow.is_active
                ? 'bg-green-500 hover:bg-green-600 shadow-lg shadow-green-500/30'
                : 'bg-slate-200 hover:bg-slate-300'
            } ${isToggling ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
            title={workflow.is_active ? 'Click to deactivate' : 'Click to activate'}
          >
            <Power className={`h-6 w-6 ${workflow.is_active ? 'text-white' : 'text-slate-500'}`} />
            {workflow.is_active && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-green-400 rounded-full animate-pulse" />
            )}
          </button>
          <div>
            <p className={`text-sm font-medium ${workflow.is_active ? 'text-green-700' : 'text-slate-600'}`}>
              {isToggling ? 'Switching...' : workflow.is_active ? 'Active' : 'Inactive'}
            </p>
            <p className="text-xs text-slate-500">
              {workflow.is_active ? 'Receiving n8n webhooks' : 'Click to enable'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowWebhookInfo(!showWebhookInfo)}
            leftIcon={<Link className="h-4 w-4" />}
          >
            Webhook
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onTrigger}
            disabled={!workflow.is_active || isTriggering}
            leftIcon={<Zap className="h-4 w-4" />}
          >
            {isTriggering ? 'Running...' : 'Test'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={loadExecutions}
            disabled={loadingExecutions}
            leftIcon={showExecutions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          >
            History
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onDelete}
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Webhook Info Section */}
      {showWebhookInfo && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
            <Link className="h-4 w-4" />
            n8n Webhook Integration
          </h4>
          <p className="text-xs text-slate-500 mb-3">
            Replace n8n SMTP/IMAP nodes with HTTP Request nodes pointing to these URLs.
            The app will use your configured email credentials.
          </p>
          <div className="space-y-3">
            {/* Send Email Webhook */}
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-600">Send Email (replaces SMTP node)</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => copyToClipboard(webhookSendUrl, 'Send URL')}
                  className="h-6 px-2"
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
              <code className="text-xs text-brand-purple bg-brand-purple/5 px-2 py-1 rounded block overflow-x-auto">
                POST {webhookSendUrl}
              </code>
              <p className="text-xs text-slate-500 mt-1">
                Body: {`{ "to": "email", "subject": "...", "body": "..." }`}
              </p>
            </div>

            {/* Fetch Emails Webhook */}
            <div className="bg-slate-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-slate-600">Fetch Emails (replaces IMAP node)</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => copyToClipboard(webhookFetchUrl, 'Fetch URL')}
                  className="h-6 px-2"
                >
                  <Copy className="h-3 w-3" />
                </Button>
              </div>
              <code className="text-xs text-brand-purple bg-brand-purple/5 px-2 py-1 rounded block overflow-x-auto">
                POST {webhookFetchUrl}
              </code>
              <p className="text-xs text-slate-500 mt-1">
                Body: {`{ "limit": 20, "unseen_only": false }`}
              </p>
            </div>

            {/* Header Info */}
            <div className="bg-orange-50 rounded-lg p-3">
              <span className="text-xs font-medium text-orange-700">Required Header</span>
              <code className="text-xs text-orange-600 block mt-1">
                X-Workflow-Id: {workflow.id}
              </code>
              <p className="text-xs text-orange-600 mt-1">
                Add this header in your n8n HTTP Request node
              </p>
            </div>
          </div>
        </div>
      )}

      {showExecutions && (
        <div className="mt-4 pt-4 border-t border-slate-100">
          <h4 className="text-sm font-medium text-slate-700 mb-3">Recent Executions</h4>
          {executions.length === 0 ? (
            <p className="text-sm text-slate-500">No executions yet</p>
          ) : (
            <div className="space-y-2">
              {executions.map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center justify-between py-2 px-3 bg-slate-50 rounded-lg text-sm"
                >
                  <div className="flex items-center gap-2">
                    {exec.status === 'success' ? (
                      <CheckCircle className="h-4 w-4 text-green-600" />
                    ) : exec.status === 'failed' ? (
                      <XCircle className="h-4 w-4 text-red-600" />
                    ) : (
                      <RefreshCw className="h-4 w-4 text-brand-purple animate-spin" />
                    )}
                    <span className="text-slate-700">{exec.trigger_type || 'manual'}</span>
                  </div>
                  <div className="flex items-center gap-4 text-slate-500">
                    {exec.duration_ms && <span>{exec.duration_ms}ms</span>}
                    <span>{new Date(exec.started_at).toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

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
function ChatAssistant() {
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

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.success
          ? response.response
          : response.error || 'Sorry, I encountered an error processing your request.',
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
    } catch (error) {
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: 'Failed to connect to the email assistant. Please check if the backend and n8n are running.',
        timestamp: new Date(),
        error: true,
      };
      setMessages(prev => [...prev, errorMessage]);
      toast.error('Failed to send message');
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
            <h3 className="font-semibold text-slate-900">Email Assistant</h3>
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
              Hi! I'm your Email Assistant.<br />
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

// ElevenLabs Voice Agent Component
function VoiceAgent() {
  const [isListening, setIsListening] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);

  const startVoiceAgent = async () => {
    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      // Initialize audio context
      audioContextRef.current = new AudioContext({ sampleRate: 16000 });

      // Connect to the head_bot workflow webhook
      const webhookUrl = (import.meta as unknown as { env: Record<string, string> }).env.VITE_N8N_WEBHOOK_URL || 'http://localhost:5678/webhook/email_agent';

      setIsListening(true);
      setIsConnected(true);
      toast.success('Voice agent connected! Speak your command...');

      // For now, we'll use the Web Speech API for recognition
      // In production, this would connect to ElevenLabs Conversational AI
      if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = async (event: any) => {
          const current = event.resultIndex;
          const result = event.results[current];

          if (result.isFinal) {
            const text = result[0].transcript;
            setTranscript(text);

            // Send to head_bot workflow
            try {
              const res = await fetch(webhookUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  userMessage: text,
                  chatId: 'voice_agent_' + Date.now(),
                  userName: 'Voice User',
                }),
              });

              if (res.ok) {
                const data = await res.json();
                setResponse(data.response || data.output || 'Command processed');

                // Use speech synthesis for response
                if ('speechSynthesis' in window) {
                  const utterance = new SpeechSynthesisUtterance(data.response || 'Command processed');
                  speechSynthesis.speak(utterance);
                }
              }
            } catch (error) {
              console.error('Failed to send to workflow:', error);
              setResponse('Failed to process command');
            }
          }
        };

        recognition.onerror = (event: any) => {
          console.error('Speech recognition error:', event.error);
          toast.error('Speech recognition error: ' + event.error);
          stopVoiceAgent();
        };

        recognition.start();
        (window as any).currentRecognition = recognition;
      } else {
        toast.error('Speech recognition not supported in this browser');
        stopVoiceAgent();
      }
    } catch (error) {
      console.error('Failed to start voice agent:', error);
      toast.error('Failed to access microphone');
      setIsListening(false);
      setIsConnected(false);
    }
  };

  const stopVoiceAgent = () => {
    // Stop speech recognition
    if ((window as any).currentRecognition) {
      (window as any).currentRecognition.stop();
      (window as any).currentRecognition = null;
    }

    // Stop media stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setIsListening(false);
    setIsConnected(false);
    setTranscript('');
    setResponse('');
    toast.info('Voice agent disconnected');
  };

  return (
    <Card className="p-6 bg-gradient-to-br from-purple-50 to-brand-purple/5 border-purple-200">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-purple-600 rounded-full">
            <Bot className="h-6 w-6 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900">Voice Email Assistant</h3>
            <p className="text-sm text-slate-500">Talk to control your email workflows</p>
          </div>
        </div>
        <Badge className={isConnected ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </Badge>
      </div>

      <div className="flex items-center gap-4 mb-4">
        <Button
          size="lg"
          variant={isListening ? 'outline' : 'primary'}
          onClick={isListening ? stopVoiceAgent : startVoiceAgent}
          leftIcon={isListening ? <PhoneOff className="h-5 w-5" /> : <Phone className="h-5 w-5" />}
          className={isListening ? 'border-red-300 text-red-600 hover:bg-red-50' : 'bg-purple-600 hover:bg-purple-700'}
        >
          {isListening ? 'End Call' : 'Start Voice Call'}
        </Button>
        {isListening && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
            <span className="text-sm text-slate-600">Listening...</span>
          </div>
        )}
      </div>

      {transcript && (
        <div className="bg-white rounded-lg p-4 mb-3">
          <p className="text-xs text-slate-500 mb-1">You said:</p>
          <p className="text-slate-800">{transcript}</p>
        </div>
      )}

      {response && (
        <div className="bg-purple-100 rounded-lg p-4">
          <p className="text-xs text-purple-600 mb-1">Assistant response:</p>
          <p className="text-purple-900">{response}</p>
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-purple-200">
        <p className="text-xs text-slate-500">
          <strong>Try saying:</strong> "Check my emails", "Write an email to john@example.com about the meeting",
          "Reply to the last email from marketing"
        </p>
      </div>
    </Card>
  );
}

export function WorkflowsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);

  // Fetch workflows
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => workflowsApi.list(),
  });

  // Seed default workflows mutation
  const seedMutation = useMutation({
    mutationFn: workflowsApi.seedDefaults,
    onSuccess: (workflows) => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success(`Created ${workflows.length} default workflows`);
    },
    onError: () => {
      toast.error('Failed to create default workflows');
    },
  });

  // Import workflow mutation
  const importMutation = useMutation({
    mutationFn: workflowsApi.importFromFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow imported successfully');
    },
    onError: () => {
      toast.error('Failed to import workflow');
    },
  });

  // Toggle workflow
  const handleToggle = async (id: string) => {
    setTogglingId(id);
    try {
      await workflowsApi.toggle(id);
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow status updated');
    } catch {
      toast.error('Failed to toggle workflow');
    } finally {
      setTogglingId(null);
    }
  };

  // Trigger workflow
  const handleTrigger = async (id: string) => {
    setTriggeringId(id);
    try {
      const result = await workflowsApi.trigger(id);
      toast.success(result.message);
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
    } catch {
      toast.error('Failed to trigger workflow');
    } finally {
      setTriggeringId(null);
    }
  };

  // Delete workflow
  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this workflow?')) return;
    try {
      await workflowsApi.delete(id);
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
      toast.success('Workflow deleted');
    } catch {
      toast.error('Failed to delete workflow');
    }
  };

  // Handle file import
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      importMutation.mutate(file);
    }
  };

  const workflows = data?.workflows || [];

  return (
    <div className="h-full">
      <Header
        title="Email Automation Workflows"
        subtitle="Manage your n8n email automation workflows"
        actions={
          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".json"
              className="hidden"
            />
            <Button
              variant="outline"
              leftIcon={<Upload className="h-4 w-4" />}
              onClick={() => fileInputRef.current?.click()}
              disabled={importMutation.isPending}
            >
              Import
            </Button>
            <Button
              variant="outline"
              leftIcon={<RefreshCw className="h-4 w-4" />}
              onClick={() => seedMutation.mutate()}
              disabled={seedMutation.isPending}
            >
              {seedMutation.isPending ? 'Creating...' : 'Seed Defaults'}
            </Button>
            <Button
              leftIcon={<Plus className="h-4 w-4" />}
              onClick={() => toast.info('Create workflow dialog coming soon')}
            >
              New Workflow
            </Button>
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {/* Chat Assistant Section */}
        <ChatAssistant />

        {/* Voice Agent Section */}
        <VoiceAgent />

        {/* Workflows Grid */}
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw className="h-8 w-8 text-slate-400 animate-spin" />
          </div>
        ) : error ? (
          <Card className="text-center py-16">
            <AlertCircle className="h-16 w-16 text-red-300 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-slate-900 mb-2">
              Failed to load workflows
            </h2>
            <p className="text-slate-500 mb-4">Please check your connection and try again.</p>
            <Button variant="outline" onClick={() => refetch()}>
              Retry
            </Button>
          </Card>
        ) : workflows.length === 0 ? (
          <Card className="text-center py-16">
            <Workflow className="h-16 w-16 text-slate-300 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-slate-900 mb-2">
              No Workflows Yet
            </h2>
            <p className="text-slate-500 max-w-md mx-auto mb-6">
              Get started by seeding the default email automation workflows from your n8n instance,
              or import a workflow from a JSON file.
            </p>
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="primary"
                leftIcon={<Zap className="h-4 w-4" />}
                onClick={() => seedMutation.mutate()}
                disabled={seedMutation.isPending}
              >
                {seedMutation.isPending ? 'Creating...' : 'Create Default Workflows'}
              </Button>
              <Button
                variant="outline"
                leftIcon={<Upload className="h-4 w-4" />}
                onClick={() => fileInputRef.current?.click()}
              >
                Import from File
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {workflows.map((workflow) => (
              <WorkflowCard
                key={workflow.id}
                workflow={workflow}
                onToggle={() => handleToggle(workflow.id)}
                onTrigger={() => handleTrigger(workflow.id)}
                onDelete={() => handleDelete(workflow.id)}
                isToggling={togglingId === workflow.id}
                isTriggering={triggeringId === workflow.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default WorkflowsPage;
