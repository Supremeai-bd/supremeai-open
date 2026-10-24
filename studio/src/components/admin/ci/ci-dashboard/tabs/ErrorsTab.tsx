// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — ERRORS TAB
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import { useMemo } from 'react';
import {
  ChevronRight,
  CheckCircle2,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { COLORS } from '../constants';
import { Badge, EmptyState } from '../primitives';
import type { CISummaryData } from '../types';

interface ErrorsTabProps {
  data: CISummaryData;
}

export function ErrorsTab({ data }: ErrorsTabProps) {
  const hasErrors = data.errors && data.errors.total > 0;

  const severityPieData = useMemo(() => {
    if (!data?.errors?.by_severity) return [];

    return Object.entries(data.errors.by_severity).map(([name, value]) => ({
      name: `P${name}`,
      value,
      color: name === 'P0' ? COLORS.failure : name === 'P1' ? '#f97316' : name === 'P2' ? COLORS.warning : COLORS.success,
    }));
  }, [data]);

  return (
    <div>
      {hasErrors ? (
        <>
          {/* Severity Breakdown */}
          {severityPieData.length > 0 && (
            <div className="mb-6">
              <h3 className="font-semibold text-gray-900 mb-3">Error Severity Distribution</h3>
              <div className="flex items-center gap-6">
                <ResponsiveContainer width={200} height={200}>
                  <PieChart>
                    <Pie
                      data={severityPieData}
                      cx="100"
                      cy="100"
                      innerRadius={40}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {severityPieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>

                <div className="flex-1 space-y-2">
                  {severityPieData.map((item, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: item.color }}
                      />
                      <span className="text-sm font-medium text-gray-700">{item.name}</span>
                      <span className="text-sm text-gray-500 ml-auto">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Category Breakdown */}
          {Object.keys(data.errors.by_category).length > 0 && (
            <div className="mb-6">
              <h3 className="font-semibold text-gray-900 mb-3">By Category</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(data.errors.by_category).map(([cat, count], idx) => (
                  <div key={idx} className="p-3 bg-red-50 rounded-lg border border-red-100">
                    <p className="text-sm font-medium text-red-900">{cat}</p>
                    <p className="text-2xl font-bold text-red-700">{count}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error List */}
          <details className="group">
            <summary className="cursor-pointer list-none flex items-center gap-2 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
              <ChevronRight className="w-4 h-4 transform group-open:rotate-90 transition-transform" />
              <span className="font-medium text-gray-900">View All Errors ({data.errors.total})</span>
            </summary>

            <div className="mt-3 space-y-2 max-h-[400px] overflow-y-auto">
              {data.errors.items.map((err, idx) => (
                <div key={idx} className="p-3 bg-white rounded-lg border border-gray-200 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <span>{err.severity_icon}</span>
                    <span className="font-medium text-gray-900">{err.category}</span>
                    <Badge variant={err.severity === 'P0' || err.severity === 'P1' ? 'failure' : 'warning'}>
                      {err.severity}
                    </Badge>
                  </div>
                  <p className="text-gray-600 font-mono text-xs break-all mt-1">
                    {err.message}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    Job: {err.job} • Line: {err.line_number}
                  </p>
                </div>
              ))}
            </div>
          </details>
        </>
      ) : (
        <EmptyState message="No errors detected! 🎉" icon={CheckCircle2} />
      )}
    </div>
  );
}
