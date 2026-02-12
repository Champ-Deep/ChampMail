import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Eye, Send } from 'lucide-react';
import { TemplateEditor } from '../components/templates/TemplateEditor';
import { Button } from '../components/ui';

export function TemplateEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = id === 'new';

  const [templateName, setTemplateName] = useState(isNew ? '' : 'Welcome Email');
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = useCallback(async (values: any) => {
    setIsSaving(true);
    try {
      console.log('Saving template:', {
        name: templateName,
        content: values,
      });
      // TODO: Call API to save template
      // await templatesApi.create({ name: templateName, mjml_content: values.mjml, json_content: values.content });

      // Show success and navigate back
      setTimeout(() => {
        setIsSaving(false);
        navigate('/templates');
      }, 1000);
    } catch (error) {
      console.error('Failed to save template:', error);
      setIsSaving(false);
    }
  }, [templateName, navigate]);

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
