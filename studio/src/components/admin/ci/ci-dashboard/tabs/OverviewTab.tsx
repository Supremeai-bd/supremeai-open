// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — OVERVIEW TAB
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import {
  Brain,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Target,
  BarChart3,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { COLORS } from '../constants';
import { ProgressBar } from '../primitives';
import { InsightCard } from '../cards';
import type { CISummaryData, TrendChartPoint } from '../types';

interface OverviewTabProps {
  data: CISummaryData;
  showTrends: boolean;
  trendChartData: TrendChartPoint[];
}

export function OverviewTab({ data, showTrends, trendChartData }: OverviewTabProps) {
  const hasInsights = data.insights && data.insights.length > 0;

  return (
    <div className="grid md:grid-cols-2 gap-6">
      {/* Insights */}
      <div>
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Brain className="w-5 h-5 text-purple-500" />
          Intelligent Insights
        </h3>

        {hasInsights ? (
          <div className="space-y-3">
            {data.insights.slice(0, 4).map((insight, idx) => (
              <InsightCard key={idx} insight={insight} />
            ))}
          </div>
        ) : (
          <div className="bg-gray-50 rounded-xl p-6 text-center">
            <Brain className="w-10 h-10 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">No insights yet</p>
          </div>
        )}
      </div>

      {/* Prediction & Trends */}
      <div>
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-blue-500" />
          Prediction & Trends
        </h3>

        {data.trends?.available ? (
          <div className="space-y-4">
            {/* Prediction Card */}
            {data.trends.prediction && (
              <div className={`p-4 rounded-xl border ${
                data.trends.prediction.verdict === 'likely_pass'
                  ? 'border-green-200 bg-green-50'
                  : data.trends.prediction.verdict === 'risk_of_failure'
                  ? 'border-red-200 bg-red-50'
                  : 'border-yellow-200 bg-yellow-50'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-900">Next Build Prediction</span>
                  <span className={`text-lg font-bold ${
                    data.trends.prediction.verdict === 'likely_pass' ? 'text-green-700' :
                    data.trends.prediction.verdict === 'risk_of_failure' ? 'text-red-700' : 'text-yellow-700'
                  }`}>
                    {data.trends.prediction.success_probability}% Success
                  </span>
                </div>
                <ProgressBar
                  value={data.trends.prediction.success_probability}
                  color={
                    data.trends.prediction.verdict === 'likely_pass' ? COLORS.success :
                    data.trends.prediction.verdict === 'risk_of_failure' ? COLORS.failure : COLORS.warning
                  }
                />
                <p className="text-xs text-gray-600 mt-2">
                  Confidence: {data.trends.prediction.confidence}%
                </p>
              </div>
            )}

            {/* Mini Trend Chart */}
            {showTrends && trendChartData.length > 0 && (
              <div className="bg-gray-50 rounded-xl p-4">
                <p className="text-xs font-medium text-gray-600 mb-2">Recent Success Rate</p>
                <ResponsiveContainer width="100%" height={120}>
                  <AreaChart data={trendChartData}>
                    <defs>
                      <linearGradient id="successGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.success} stopOpacity={0.3}/>
                        <stop offset="95%" stopColor={COLORS.success} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="name" hide />
                    <YAxis domain={[60, 100]} hide />
                    <Tooltip />
                    <Area
                      type="monotone"
                      dataKey="success"
                      stroke={COLORS.success}
                      fillOpacity={1}
                      fill="url(#successGradient)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {data.trends.recommendations && data.trends.recommendations.length > 0 && (
              <div className="space-y-2">
                {data.trends.recommendations.map((rec, idx) => (
                  <div key={idx} className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                    <span className="text-gray-700">{rec}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="bg-gray-50 rounded-xl p-6 text-center">
            <BarChart3 className="w-10 h-10 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">Trend data not available</p>
            <p className="text-xs text-gray-400 mt-1">Need more historical runs</p>
          </div>
        )}
      </div>

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <div className="md:col-span-2">
          <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <Target className="w-5 h-5 text-green-500" />
            Recommended Actions
          </h3>
          <div className="grid md:grid-cols-2 gap-3">
            {data.recommendations.map((rec, idx) => (
              <div key={idx} className="flex items-start gap-2 p-3 bg-blue-50 rounded-lg border border-blue-100">
                <CheckCircle2 className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                <span className="text-sm text-blue-900">{rec}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
