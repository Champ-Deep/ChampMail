import { Header } from '../components/layout';

export function TemplatesPage() {
  return (
    <div className="h-full flex flex-col">
      <Header
        title="Email Templates"
        subtitle="Browse professional templates from CampaignTemplate.com"
      />
      <div className="flex-1 w-full p-6">
        <div className="w-full h-full rounded-xl border border-slate-200 overflow-hidden bg-slate-50 shadow-sm relative">
          <iframe
            src="https://campaigntemplate.com"
            title="Campaign Templates"
            className="w-full h-full border-none"
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          />
        </div>
      </div>
    </div>
  );
}

export default TemplatesPage;
