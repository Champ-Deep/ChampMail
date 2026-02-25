import { useState } from 'react';
import { Search, CheckCircle2, XCircle, ChevronRight, Lightbulb } from 'lucide-react';
import { Card, Button, Badge } from '../../ui';
import type { ResearchResult } from '../../../api/admin';
import { clsx } from 'clsx';

interface Step3Props {
  researchResults: ResearchResult[];
  onStartResearch: () => void;
  isResearching: boolean;
  researchComplete: boolean;
}

export function StepResearch({
  researchResults,
  onStartResearch,
  isResearching,
  researchComplete,
}: Step3Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900 mb-1">
          Prospect Research
        </h2>
        <p className="text-sm text-slate-500">
          The AI will research each prospect's company, role, and recent
          activity to generate personalized outreach.
        </p>
      </div>

      {!researchComplete && researchResults.length === 0 && (
        <Card className="text-center py-10">
          <Search className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-900 mb-2">
            Ready to Research
          </h3>
          <p className="text-slate-500 max-w-md mx-auto mb-6">
            The AI will analyze each prospect using real-time data from the web
            -- company info, industry trends, hiring signals, and more.
          </p>
          <Button
            onClick={onStartResearch}
            disabled={isResearching}
            isLoading={isResearching}
            leftIcon={<Search className="h-4 w-4" />}
          >
            {isResearching ? 'Researching Prospects...' : 'Start Research'}
          </Button>
          {isResearching && (
            <p className="text-xs text-slate-400 mt-3">
              This may take a few minutes depending on list size...
            </p>
          )}
        </Card>
      )}

      {researchResults.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              <span className="text-sm font-medium text-slate-700">
                {researchResults.length} prospect(s) researched
              </span>
            </div>
            {researchComplete && (
              <Badge variant="success">Research Complete</Badge>
            )}
          </div>

          <div className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
            {researchResults.map((result) => {
              const hasError = !!result.research_data?.error;
              const isExpanded = expandedId === result.prospect_id;
              const companyDesc =
                result.research_data?.company_info?.description || 'N/A';

              return (
                <Card
                  key={result.prospect_id || result.prospect_email}
                  padding="none"
                  className={clsx(
                    'transition-all',
                    hasError && 'border-red-200'
                  )}
                >
                  <button
                    onClick={() =>
                      setExpandedId(isExpanded ? null : result.prospect_id)
                    }
                    className="w-full text-left p-4 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {hasError ? (
                        <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                      ) : (
                        <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 truncate">
                          {result.prospect_email}
                        </p>
                        <p className="text-xs text-slate-500 truncate">
                          {companyDesc.substring(0, 100)}
                          {companyDesc.length > 100 ? '...' : ''}
                        </p>
                      </div>
                    </div>
                    <ChevronRight
                      className={clsx(
                        'h-4 w-4 text-slate-400 transition-transform flex-shrink-0 ml-2',
                        isExpanded && 'rotate-90'
                      )}
                    />
                  </button>

                  {isExpanded && (
                    <div className="px-4 pb-4 pt-0 border-t border-slate-100 mt-0 pt-3">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                            Company
                          </p>
                          <p className="text-slate-700">{companyDesc}</p>
                          {result.research_data?.company_info?.industry && (
                            <Badge variant="default" size="sm" className="mt-1">
                              {result.research_data.company_info.industry}
                            </Badge>
                          )}
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                            Personalization Hooks
                          </p>
                          <ul className="space-y-0.5">
                            {(
                              result.research_data?.personalization_hooks || []
                            ).map((hook, i) => (
                              <li
                                key={i}
                                className="text-slate-700 flex items-start gap-1.5"
                              >
                                <Lightbulb className="h-3 w-3 text-amber-500 mt-0.5 flex-shrink-0" />
                                {hook}
                              </li>
                            ))}
                          </ul>
                        </div>
                        {result.research_data?.triggers && (
                          <div className="col-span-full">
                            <p className="text-xs font-medium text-slate-500 uppercase mb-1">
                              Triggers
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {result.research_data.triggers.funding && (
                                <Badge variant="info" size="sm">
                                  Funding:{' '}
                                  {result.research_data.triggers.funding}
                                </Badge>
                              )}
                              {result.research_data.triggers.expansion && (
                                <Badge variant="success" size="sm">
                                  Growth:{' '}
                                  {result.research_data.triggers.expansion}
                                </Badge>
                              )}
                              {result.research_data.triggers
                                .leadership_changes && (
                                <Badge variant="warning" size="sm">
                                  Leadership Change
                                </Badge>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
