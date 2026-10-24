// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — TRENDS TAB
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// FINAL-TEST HONESTY FIX: the charts used to render a hardcoded 7-run sample
// series whenever trends.available was true — fabricated numbers presented as
// real history. The charts now render ONLY real points from /api/ci/history
// (passed in via trendChartData); until the backend has run history the panel
// shows an honest "no history yet" state while the real aggregate stats
// (recent/overall success rate, direction, analyzed runs) stay visible.
// ══════════════════════════════════════════════════════════════════════════════

import {
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  History,
} from 'lucide-react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { COLORS } from '../constants';
import { EmptyState } from '../primitives';
import type { CISummaryData, TrendChartPoint } from '../types';

interface TrendsTabProps {
  data: CISummaryData;
  showTrends: boolean;
  trendChartData: TrendChartPoint[];
}

export function TrendsTab({ data, showTrends, trendChartData }: TrendsTabProps) {
  const hasRealHistory = trendChartData.length > 0;

  return (
    <div>
      {showTrends && data.trends?.available ? (
        <div className="space-y-6">
          {/* Success Rate Over Time — only with REAL history points */}
          {hasRealHistory ? (
            <div>
              <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-green-600" />
                Success Rate Trend
                <span className="text-xs font-normal text-gray-400">
                  (last {trendChartData.length} runs)
                </span>
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trendChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis domain={[60, 100]} tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{ borderRadius: 10, border: '1px solid #e5e7eb', fontSize: 12 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="success"
                    name="Success %"
                    stroke={COLORS.success}
                    strokeWidth={3}
                    dot={{ r: 4, fill: COLORS.success }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50/60 p-6 text-center">
              <History className="w-10 h-10 text-gray-300 mx-auto mb-2" />
              <p className="text-gray-600 text-sm font-medium">No run history yet</p>
              <p className="text-xs text-gray-400 mt-1">
                The chart plots real runs reported to /api/ci/history. Once CI reports
                a few runs, the success-rate and duration trends appear here — we don't
                show sample data.
              </p>
            </div>
          )}

          {/* Duration Trend — only with REAL history points */}
          {hasRealHistory && (
            <div>
              <h3 className="font-semibold text-gray-900 mb-3">Build Duration Trend</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={trendChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{ borderRadius: 10, border: '1px solid #e5e7eb', fontSize: 12 }}
                  />
                  <Bar dataKey="duration" name="Duration (s)" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Stats Summary — REAL aggregates from the latest summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 bg-blue-50 rounded-xl border border-blue-100/60">
              <p className="text-xs text-blue-600 font-medium">Recent Avg</p>
              <p className="text-2xl font-bold text-blue-900">
                {data.trends.recent_success_rate?.toFixed(0)}%
              </p>
            </div>
            <div className="p-4 bg-purple-50 rounded-xl border border-purple-100/60">
              <p className="text-xs text-purple-600 font-medium">Overall Avg</p>
              <p className="text-2xl font-bold text-purple-900">
                {data.trends.overall_success_rate?.toFixed(0)}%
              </p>
            </div>
            <div className="p-4 bg-green-50 rounded-xl border border-green-100/60">
              <p className="text-xs text-green-600 font-medium">Trend</p>
              <p className="text-2xl font-bold text-green-900 flex items-center gap-1 capitalize">
                {data.trends.trend_direction === 'improving' ? <TrendingUp /> :
                 data.trends.trend_direction === 'declining' ? <TrendingDown /> : <Minus />}
                {data.trends.trend_direction}
              </p>
            </div>
            <div className="p-4 bg-yellow-50 rounded-xl border border-yellow-100/60">
              <p className="text-xs text-yellow-600 font-medium">Analyzed Runs</p>
              <p className="text-2xl font-bold text-yellow-900">
                {data.trends.total_analyzed}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <EmptyState
          message="Trend analysis requires more historical data"
          icon={BarChart3}
        />
      )}
    </div>
  );
}
