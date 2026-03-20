/**
 * ColumnMapper — lets users map file headers to system fields.
 *
 * Shows a table: left = file column name, right = dropdown of system fields.
 * Auto-mapping is pre-filled. Missing required fields are highlighted red.
 * Below the table a sample-data preview confirms the mapping looks right.
 */

import { useState, useMemo } from 'react';
import {
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Minus,
} from 'lucide-react';
import { clsx } from 'clsx';
import { SYSTEM_FIELDS, type SystemField } from '../../validations';

// Human-readable labels for system fields
const FIELD_LABELS: Record<string, string> = {
  email: 'Email (required)',
  first_name: 'First Name',
  last_name: 'Last Name',
  company_name: 'Company Name',
  company_domain: 'Company Domain',
  title: 'Job Title',
  phone: 'Phone',
  linkedin_url: 'LinkedIn URL',
  industry: 'Industry',
  company_size: 'Company Size',
};

interface ColumnMapperProps {
  headers: string[];
  sampleRows: string[][];
  autoMapping: Record<string, string>;
  onMappingChange: (mapping: Record<string, string>) => void;
}

export function ColumnMapper({
  headers,
  sampleRows,
  autoMapping,
  onMappingChange,
}: ColumnMapperProps) {
  const [mapping, setMapping] = useState<Record<string, string>>(autoMapping);

  const handleChange = (header: string, value: string) => {
    const next = { ...mapping };
    if (value === '') {
      delete next[header];
    } else {
      next[header] = value;
    }
    setMapping(next);
    onMappingChange(next);
  };

  // Track which system fields are already used (so we don't double-map)
  const usedFields = useMemo(() => new Set(Object.values(mapping)), [mapping]);
  const hasEmail = usedFields.has('email');

  return (
    <div className="space-y-4">
      {/* Validation banner */}
      {!hasEmail && (
        <div className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>You must map at least one column to <strong>Email</strong>.</span>
        </div>
      )}

      {/* Mapping table */}
      <div className="border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-4 py-2.5 text-left font-medium text-slate-600">
                File Column
              </th>
              <th className="px-2 py-2.5 w-8" />
              <th className="px-4 py-2.5 text-left font-medium text-slate-600">
                Map To
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-slate-600 w-28">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {headers.map((header) => {
              const mappedTo = mapping[header] || '';
              const isMapped = !!mappedTo;
              const isEmail = mappedTo === 'email';

              return (
                <tr
                  key={header}
                  className={clsx(
                    'transition-colors',
                    isEmail && 'bg-green-50/50',
                    !isMapped && 'bg-amber-50/30',
                  )}
                >
                  <td className="px-4 py-2.5 font-mono text-slate-800">
                    {header}
                  </td>
                  <td className="px-2 py-2.5 text-center text-slate-400">
                    <ArrowRight className="h-3.5 w-3.5" />
                  </td>
                  <td className="px-4 py-2.5">
                    <select
                      value={mappedTo}
                      onChange={(e) => handleChange(header, e.target.value)}
                      className={clsx(
                        'w-full rounded-md border px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-purple/40',
                        isMapped
                          ? 'border-slate-300 bg-white'
                          : 'border-amber-300 bg-amber-50',
                      )}
                    >
                      <option value="">-- Skip this column --</option>
                      {SYSTEM_FIELDS.map((field) => {
                        const taken = usedFields.has(field) && mapping[header] !== field;
                        return (
                          <option key={field} value={field} disabled={taken}>
                            {FIELD_LABELS[field] || field}
                            {taken ? ' (already mapped)' : ''}
                          </option>
                        );
                      })}
                    </select>
                  </td>
                  <td className="px-4 py-2.5">
                    {isMapped ? (
                      <span className="inline-flex items-center gap-1 text-green-600 text-xs font-medium">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Mapped
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-600 text-xs font-medium">
                        <Minus className="h-3.5 w-3.5" />
                        Skipped
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Sample data preview */}
      {sampleRows.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
            Sample Data Preview ({sampleRows.length} rows)
          </h4>
          <div className="border border-slate-200 rounded-lg overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  {headers.map((h) => {
                    const field = mapping[h];
                    return (
                      <th
                        key={h}
                        className={clsx(
                          'px-3 py-2 text-left font-medium whitespace-nowrap',
                          field ? 'text-slate-700' : 'text-slate-400',
                        )}
                      >
                        {field ? FIELD_LABELS[field] || field : h}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sampleRows.map((row, ri) => (
                  <tr key={ri}>
                    {headers.map((h, ci) => {
                      const field = mapping[h];
                      return (
                        <td
                          key={ci}
                          className={clsx(
                            'px-3 py-1.5 whitespace-nowrap max-w-[200px] truncate',
                            field ? 'text-slate-700' : 'text-slate-400',
                          )}
                        >
                          {row[ci] || ''}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
