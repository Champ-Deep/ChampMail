import { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Send, Loader2, HelpCircle, BookOpen, Settings, Mail } from 'lucide-react';
import { clsx } from 'clsx';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

// Documentation content for the assistant
const DOCUMENTATION = {
  templates: `
**Email Templates**
- Create templates using our visual MJML editor
- Use variables like {{first_name}}, {{company}}, {{title}} for personalization
- Templates support responsive design for all devices
- Click "New Template" to start creating
- Edit existing templates by clicking on them in the grid
`,
  prospects: `
**Managing Prospects**
- Add prospects manually or import from CSV
- Required field: email address
- Optional fields: first_name, last_name, company, title, industry
- Select multiple prospects to add them to campaigns
- Search and filter prospects by any field
`,
  campaigns: `
**Running Campaigns**
- Create a campaign by selecting a template
- Add prospects as recipients
- Click "Send" to start the campaign
- Track opens, clicks, and replies in real-time
- Pause and resume campaigns as needed
`,
  smtp: `
**SMTP Setup**
- Go to Settings > SMTP/IMAP Configuration
- Common SMTP servers:
  - Gmail: smtp.gmail.com, Port 587
  - Outlook: smtp.office365.com, Port 587
  - Custom: Use your mail server settings
- Always use TLS for security (port 587)
- Test your connection before sending campaigns
`,
  imap: `
**IMAP Setup (Optional)**
- IMAP is used to detect replies
- Common IMAP servers:
  - Gmail: imap.gmail.com, Port 993
  - Outlook: outlook.office365.com, Port 993
- Use SSL (port 993) for security
- Monitor your INBOX or a specific folder
`,
  sequences: `
**Email Sequences**
- Create multi-step email sequences
- Set delays between emails (days, hours)
- Sequences stop when a prospect replies
- Track engagement at each step
`,
  variables: `
**Template Variables**
Available variables for personalization:
- {{first_name}} - Prospect's first name
- {{last_name}} - Prospect's last name
- {{company}} - Company name
- {{title}} - Job title
- {{email}} - Email address
- {{industry}} - Industry

Use fallbacks: {{first_name|there}}
`,
};

// Suggested questions based on context
const SUGGESTED_QUESTIONS = [
  { icon: Mail, text: 'How do I set up SMTP?', topic: 'smtp' },
  { icon: BookOpen, text: 'How do template variables work?', topic: 'variables' },
  { icon: Settings, text: 'How do I configure IMAP?', topic: 'imap' },
];

function findAnswer(question: string): string {
  const q = question.toLowerCase();

  if (q.includes('smtp') || q.includes('send email') || q.includes('mail server')) {
    return DOCUMENTATION.smtp;
  }
  if (q.includes('imap') || q.includes('reply') || q.includes('detect')) {
    return DOCUMENTATION.imap;
  }
  if (q.includes('template') || q.includes('mjml') || q.includes('email design')) {
    return DOCUMENTATION.templates;
  }
  if (q.includes('variable') || q.includes('personali') || q.includes('{{')) {
    return DOCUMENTATION.variables;
  }
  if (q.includes('prospect') || q.includes('import') || q.includes('csv') || q.includes('lead')) {
    return DOCUMENTATION.prospects;
  }
  if (q.includes('campaign') || q.includes('send') || q.includes('track')) {
    return DOCUMENTATION.campaigns;
  }
  if (q.includes('sequence') || q.includes('multi-step') || q.includes('follow-up')) {
    return DOCUMENTATION.sequences;
  }

  return `I can help you with:
- **Templates**: Creating and editing email templates
- **Prospects**: Managing your leads and contacts
- **Campaigns**: Sending and tracking emails
- **SMTP/IMAP**: Configuring email settings
- **Variables**: Personalizing your emails

What would you like to know more about?`;
}

export function HelpChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hi! I'm your ChampMail assistant. I can help you with templates, campaigns, SMTP setup, and more. What would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Simulate AI response delay
    await new Promise((resolve) => setTimeout(resolve, 500));

    const answer = findAnswer(userMessage.content);
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: answer,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, assistantMessage]);
    setIsLoading(false);
  };

  const handleSuggestedQuestion = (question: string) => {
    setInput(question);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(true)}
        className={clsx(
          'fixed bottom-6 right-6 z-50 flex items-center justify-center',
          'h-14 w-14 rounded-full bg-blue-600 text-white shadow-lg',
          'hover:bg-blue-700 hover:scale-105 transition-all duration-200',
          isOpen && 'hidden'
        )}
        title="Help & Documentation"
      >
        <HelpCircle className="h-6 w-6" />
      </button>

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 w-96 h-[500px] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-slate-200">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-blue-600 text-white">
            <div className="flex items-center gap-2">
              <MessageCircle className="h-5 w-5" />
              <span className="font-semibold">ChampMail Help</span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 hover:bg-blue-700 rounded-lg transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">
            {messages.map((message) => (
              <div
                key={message.id}
                className={clsx(
                  'flex',
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                )}
              >
                <div
                  className={clsx(
                    'max-w-[85%] rounded-2xl px-4 py-2.5 text-sm',
                    message.role === 'user'
                      ? 'bg-blue-600 text-white rounded-br-md'
                      : 'bg-white text-slate-700 shadow-sm border border-slate-100 rounded-bl-md'
                  )}
                >
                  <div className="whitespace-pre-wrap prose prose-sm max-w-none">
                    {message.content.split('\n').map((line, i) => {
                      // Handle bold text
                      const parts = line.split(/\*\*([^*]+)\*\*/g);
                      return (
                        <p key={i} className="mb-1 last:mb-0">
                          {parts.map((part, j) =>
                            j % 2 === 1 ? (
                              <strong key={j}>{part}</strong>
                            ) : (
                              part
                            )
                          )}
                        </p>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white rounded-2xl rounded-bl-md px-4 py-3 shadow-sm border border-slate-100">
                  <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Suggested Questions (show when few messages) */}
          {messages.length <= 2 && (
            <div className="px-4 py-2 bg-white border-t border-slate-100">
              <p className="text-xs text-slate-500 mb-2">Suggested questions:</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q.text}
                    onClick={() => handleSuggestedQuestion(q.text)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full transition-colors"
                  >
                    <q.icon className="h-3 w-3" />
                    {q.text}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="p-3 bg-white border-t border-slate-200">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask a question..."
                className="flex-1 px-4 py-2.5 text-sm border border-slate-200 rounded-full outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                className={clsx(
                  'p-2.5 rounded-full transition-colors',
                  input.trim() && !isLoading
                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                    : 'bg-slate-100 text-slate-400'
                )}
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default HelpChatWidget;
