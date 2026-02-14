import { useState, useCallback, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft, Save, Eye, Send } from 'lucide-react';
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
    }
  }, [existingTemplate]);

  const handleSave = useCallback(async (values: any) => {
    if (!templateName.trim()) {
      toast.error('Please enter a template name');
      return;
    }

    setIsSaving(true);
    try {
      if (isNew) {
        await templatesApi.create({
          name: templateName,
          subject: subjectLine || templateName,
          mjml_content: values.mjml || values.content || '',
        });
        toast.success('Template created successfully');
      } else {
        await templatesApi.update(id!, {
          name: templateName,
          subject: subjectLine || undefined,
          mjml_content: values.mjml || values.content || undefined,
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
          <Button variant="outline" size="sm" leftIcon={<Eye className="h-4 w-4" />}>
            Preview
          </Button>
          <Button variant="outline" size="sm" leftIcon={<Send className="h-4 w-4" />}>
            Send Test
          </Button>
          <Button
            size="sm"
            leftIcon={<Save className="h-4 w-4" />}
            isLoading={isSaving}
            onClick={() => {
              // Trigger save from editor
              const saveButton = document.querySelector('[data-save-trigger]');
              if (saveButton) {
                (saveButton as HTMLButtonElement).click();
              }
            }}
          >
            Save Template
          </Button>
        </div>
      </header>

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        <TemplateEditor onSave={handleSave} />
      </div>
    </div>
  );
}

export default TemplateEditorPage;
