import { useState, useCallback, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft, Save } from 'lucide-react';
import { TemplateEditor } from '../components/templates/TemplateEditor';
import { Button } from '../components/ui';
import { templatesApi } from '../api/templates';

export function TemplateEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id || id === 'new';

  const [templateName, setTemplateName] = useState('');
  const [subjectLine, setSubjectLine] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const contentRef = useRef('');

  // Fetch existing template when editing
  const { data: existingTemplate } = useQuery({
    queryKey: ['template', id],
    queryFn: () => templatesApi.get(id!),
    enabled: !isNew && !!id,
  });

  // Populate form when template loads
  useEffect(() => {
    if (existingTemplate) {
      setTemplateName(existingTemplate.name);
      setSubjectLine(existingTemplate.subject || '');
      contentRef.current = existingTemplate.mjml_content || existingTemplate.html_content || '';
    }
  }, [existingTemplate]);

  const handleContentChange = useCallback((content: string) => {
    contentRef.current = content;
  }, []);

  const handleSave = useCallback(async () => {
    if (!templateName.trim()) {
      toast.error('Please enter a template name');
      return;
    }

    if (!contentRef.current.trim()) {
      toast.error('Template content cannot be empty');
      return;
    }

    setIsSaving(true);
    try {
      if (isNew) {
        await templatesApi.create({
          name: templateName,
          subject: subjectLine || templateName,
          mjml_content: contentRef.current,
        });
        toast.success('Template created successfully');
      } else {
        await templatesApi.update(id!, {
          name: templateName,
          subject: subjectLine || undefined,
          mjml_content: contentRef.current,
        });
        toast.success('Template updated successfully');
      }
      navigate('/templates');
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save template');
    } finally {
      setIsSaving(false);
    }
  }, [templateName, subjectLine, isNew, id, navigate]);

  return (
    <div className="h-screen flex flex-col bg-slate-100">
      {/* Header */}
      <header className="flex items-center justify-between h-14 px-4 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/templates')}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-slate-600" />
          </button>
          <div className="h-6 w-px bg-slate-200" />
          <input
            type="text"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            placeholder="Template name..."
            className="text-lg font-medium bg-transparent border-none outline-none focus:ring-0 placeholder:text-slate-400"
          />
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2 mr-2">
            <label className="text-sm text-slate-500">Subject:</label>
            <input
              type="text"
              value={subjectLine}
              onChange={(e) => setSubjectLine(e.target.value)}
              placeholder="Email subject line..."
              className="text-sm bg-slate-50 border border-slate-200 rounded-md px-3 py-1.5 outline-none focus:border-brand-purple focus:ring-1 focus:ring-brand-purple/20 w-64"
            />
          </div>
          <Button
            size="sm"
            leftIcon={<Save className="h-4 w-4" />}
            isLoading={isSaving}
            onClick={handleSave}
          >
            Save Template
          </Button>
        </div>
      </header>

      {/* Subject line for mobile */}
      <div className="sm:hidden px-4 py-2 bg-white border-b border-slate-200">
        <input
          type="text"
          value={subjectLine}
          onChange={(e) => setSubjectLine(e.target.value)}
          placeholder="Email subject line..."
          className="w-full text-sm bg-slate-50 border border-slate-200 rounded-md px-3 py-1.5 outline-none focus:border-brand-purple"
        />
      </div>

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        <TemplateEditor
          initialContent={existingTemplate?.mjml_content || existingTemplate?.html_content || undefined}
          onContentChange={handleContentChange}
        />
      </div>
    </div>
  );
}

export default TemplateEditorPage;
