import { useQuery } from '@tanstack/react-query';
import { Loader2, Users, FileText, CheckCircle2, AlertCircle } from 'lucide-react';
import { Card, Badge } from '../../ui';
import { adminApi } from '../../../api/admin';
import { clsx } from 'clsx';

interface Step2Props {
  selectedListId: string | null;
  setSelectedListId: (id: string | null) => void;
}

export function StepSelectProspects({
  selectedListId,
  setSelectedListId,
}: Step2Props) {
  const { data: lists = [], isLoading } = useQuery({
    queryKey: ['admin', 'prospect-lists'],
    queryFn: () => adminApi.getProspectLists(),
  });

  const completedLists = lists.filter((l) => l.status === 'completed');

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 text-brand-purple animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Select Prospect List
        </h2>
        <p className="text-sm text-slate-500">
          Choose which prospect list to use for this campaign. Only completed
          lists are available.
        </p>
      </div>

      {completedLists.length === 0 ? (
        <Card className="py-12 text-center">
          <Users className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            No prospect lists available
          </h3>
          <p className="text-slate-500 max-w-md mx-auto">
            Upload and process a prospect list first from the Prospect Lists
            page. Only fully processed lists can be used for campaigns.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {completedLists.map((list) => (
            <button
              key={list.id}
              onClick={() => setSelectedListId(list.id)}
              className={clsx(
                'w-full text-left rounded-xl border-2 p-4 transition-all duration-150',
                selectedListId === list.id
                  ? 'border-brand-purple bg-brand-purple/5 ring-2 ring-brand-purple/20'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm'
              )}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={clsx(
                      'h-10 w-10 rounded-lg flex items-center justify-center',
                      selectedListId === list.id
                        ? 'bg-brand-purple/10'
                        : 'bg-slate-100'
                    )}
                  >
                    <FileText
                      className={clsx(
                        'h-5 w-5',
                        selectedListId === list.id
                          ? 'text-brand-purple'
                          : 'text-slate-400'
                      )}
                    />
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">
                      {list.name || list.filename}
                    </p>
                    <p className="text-sm text-slate-500">
                      {list.total_rows.toLocaleString()} prospects --
                      Uploaded{' '}
                      {new Date(list.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="success" size="sm">
                    {list.total_rows.toLocaleString()} contacts
                  </Badge>
                  {selectedListId === list.id && (
                    <CheckCircle2 className="h-5 w-5 text-brand-purple" />
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {lists.filter((l) => l.status !== 'completed').length > 0 && (
        <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-amber-700">
            {lists.filter((l) => l.status !== 'completed').length} list(s) are
            still processing and not available for selection.
          </p>
        </div>
      )}
    </div>
  );
}
