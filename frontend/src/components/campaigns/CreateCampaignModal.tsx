import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { X } from 'lucide-react';
import { Button, Input, Textarea } from '../ui';
import { campaignsApi } from '../../api/campaigns';
import { templatesApi } from '../../api/templates';

interface CreateCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateCampaignModal({ isOpen, onClose }: CreateCampaignModalProps) {
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [fromName, setFromName] = useState('');
  const [fromAddress, setFromAddress] = useState('');
  const [dailyLimit, setDailyLimit] = useState('100');
  const [templateId, setTemplateId] = useState('');

  // Fetch templates for dropdown
  const { data: templateData } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templatesApi.list(100, 0),
    enabled: isOpen,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      campaignsApi.create({
        name,
        description: description || undefined,
        from_name: fromName || undefined,
        from_address: fromAddress || undefined,
        daily_limit: parseInt(dailyLimit) || 100,
        template_id: templateId || undefined,
      }),
    onSuccess: () => {
      toast.success('Campaign created successfully');
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      resetAndClose();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create campaign');
    },
  });

  const resetAndClose = () => {
    setName('');
    setDescription('');
    setFromName('');
    setFromAddress('');
    setDailyLimit('100');
    setTemplateId('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={resetAndClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">Create New Campaign</h2>
          <button
            onClick={resetAndClose}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <X className="h-5 w-5 text-slate-500" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-5">
          <Input
            label="Campaign Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Q1 Outreach - Tech Startups"
          />

          <Textarea
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief description of this campaign..."
            rows={3}
          />

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Email Template
            </label>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-slate-300 text-sm bg-white focus:border-brand-purple focus:ring-1 focus:ring-brand-purple outline-none"
            >
              <option value="">None (add later)</option>
              {templateData?.templates?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="From Name"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder="Your Name"
            />
            <Input
              label="From Email"
              type="email"
              value={fromAddress}
              onChange={(e) => setFromAddress(e.target.value)}
              placeholder="you@company.com"
            />
          </div>

          <Input
            label="Daily Send Limit"
            type="number"
            value={dailyLimit}
            onChange={(e) => setDailyLimit(e.target.value)}
            placeholder="100"
            helperText="Maximum emails to send per day"
          />
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t border-slate-200">
          <Button variant="outline" onClick={resetAndClose}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            isLoading={createMutation.isPending}
            disabled={!name.trim()}
          >
            Create Campaign
          </Button>
        </div>
      </div>
    </div>
  );
}
