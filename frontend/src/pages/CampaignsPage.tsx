import { useNavigate } from 'react-router-dom';
import { Plus, Mail } from 'lucide-react';
import { Header } from '../components/layout';
import { Card, Button } from '../components/ui';

export function CampaignsPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full">
      <Header
        title="Campaigns"
        subtitle="Manage your email campaigns"
        actions={
          <Button leftIcon={<Plus className="h-4 w-4" />}>
            New Campaign
          </Button>
        }
      />

      <div className="p-6">
        {/* Placeholder - Coming Soon */}
        <Card className="text-center py-16">
          <Mail className="h-16 w-16 text-slate-300 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-slate-900 mb-2">
            Campaigns Coming Soon
          </h2>
          <p className="text-slate-500 max-w-md mx-auto">
            Campaign management will be available after the backend API is connected.
            For now, use Sequences to automate your outreach.
          </p>
          <Button
            variant="outline"
            className="mt-6"
            onClick={() => navigate('/sequences')}
          >
            Go to Sequences
          </Button>
        </Card>
      </div>
    </div>
  );
}

export default CampaignsPage;
