import { useState, useRef, useCallback } from 'react';
import { Code, Eye, Plus } from 'lucide-react';
import { clsx } from 'clsx';

interface TemplateEditorProps {
  initialContent?: string;
  onContentChange?: (content: string) => void;
}

const VARIABLES = [
  { label: 'First Name', value: '{{first_name}}' },
  { label: 'Last Name', value: '{{last_name}}' },
  { label: 'Full Name', value: '{{full_name}}' },
  { label: 'Email', value: '{{email}}' },
  { label: 'Company', value: '{{company_name}}' },
  { label: 'Job Title', value: '{{job_title}}' },
  { label: 'Industry', value: '{{industry}}' },
];

const DEFAULT_HTML = `<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }
    .container { max-width: 600px; margin: 0 auto; }
    h1 { color: #6D08BE; }
    .button { display: inline-block; padding: 12px 24px; background: #6D08BE; color: #fff; text-decoration: none; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Hello {{first_name}},</h1>
    <p>We wanted to reach out to you at {{company_name}} about an exciting opportunity.</p>
    <p>Would you be open to a quick chat this week?</p>
    <p><a href="#" class="button">Schedule a Call</a></p>
    <p>Best regards,<br/>The ChampMail Team</p>
  </div>
</body>
</html>`;

export const TemplateEditor: React.FC<TemplateEditorProps> = ({
  initialContent,
  onContentChange,
}) => {
  const [content, setContent] = useState(initialContent || DEFAULT_HTML);
  const [activeTab, setActiveTab] = useState<'code' | 'preview'>('code');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleContentChange = useCallback((newContent: string) => {
    setContent(newContent);
    onContentChange?.(newContent);
  }, [onContentChange]);

  const insertVariable = useCallback((variable: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const newContent = content.slice(0, start) + variable + content.slice(end);
    handleContentChange(newContent);

    requestAnimationFrame(() => {
      textarea.focus();
      textarea.selectionStart = textarea.selectionEnd = start + variable.length;
    });
  }, [content, handleContentChange]);

  return (
    <div className="flex flex-col h-full">
      {/* Variable insertion bar */}
      <div className="flex items-center gap-2 px-4 py-2 bg-slate-50 border-b border-slate-200 overflow-x-auto">
        <span className="text-xs font-medium text-slate-500 shrink-0">Insert:</span>
        {VARIABLES.map((v) => (
          <button
            key={v.value}
            onClick={() => insertVariable(v.value)}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-brand-purple bg-brand-purple/5 rounded hover:bg-brand-purple/10 transition-colors shrink-0"
          >
            <Plus className="h-3 w-3" />
            {v.label}
          </button>
        ))}
      </div>

      {/* Tab bar (mobile) / Split pane (desktop) */}
      <div className="flex items-center gap-1 px-4 py-1.5 bg-white border-b border-slate-200 md:hidden">
        <button
          onClick={() => setActiveTab('code')}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded transition-colors',
            activeTab === 'code'
              ? 'bg-brand-purple/10 text-brand-purple'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          <Code className="h-4 w-4" /> Code
        </button>
        <button
          onClick={() => setActiveTab('preview')}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded transition-colors',
            activeTab === 'preview'
              ? 'bg-brand-purple/10 text-brand-purple'
              : 'text-slate-500 hover:text-slate-700'
          )}
        >
          <Eye className="h-4 w-4" /> Preview
        </button>
      </div>

      {/* Editor + Preview */}
      <div className="flex-1 flex overflow-hidden">
        {/* Code Editor */}
        <div
          className={clsx(
            'flex-1 flex flex-col border-r border-slate-200',
            activeTab !== 'code' && 'hidden md:flex'
          )}
        >
          <div className="px-4 py-1.5 bg-slate-50 border-b border-slate-200 hidden md:flex items-center gap-1.5">
            <Code className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs font-medium text-slate-500">HTML Editor</span>
          </div>
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => handleContentChange(e.target.value)}
            spellCheck={false}
            className="flex-1 w-full p-4 font-mono text-sm text-slate-800 bg-white resize-none outline-none"
            placeholder="Enter your HTML email template here..."
          />
        </div>

        {/* Preview */}
        <div
          className={clsx(
            'flex-1 flex flex-col',
            activeTab !== 'preview' && 'hidden md:flex'
          )}
        >
          <div className="px-4 py-1.5 bg-slate-50 border-b border-slate-200 hidden md:flex items-center gap-1.5">
            <Eye className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs font-medium text-slate-500">Preview</span>
          </div>
          <div className="flex-1 bg-slate-100 p-4 overflow-auto">
            <div className="max-w-[640px] mx-auto bg-white rounded-lg shadow-sm overflow-hidden">
              <iframe
                srcDoc={content}
                title="Email Preview"
                className="w-full border-0"
                style={{ minHeight: '500px', height: '100%' }}
                sandbox="allow-same-origin"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
