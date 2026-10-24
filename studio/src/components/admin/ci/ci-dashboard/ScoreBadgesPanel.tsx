// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — score circle + earned badges + run info panel
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import {
  Award,
  GitBranch,
  User,
  Calendar,
  BarChart3,
} from 'lucide-react';
import { ScoreCircle } from './primitives';
import { timeAgo } from './utils';
import type { CISummaryData } from './types';

interface ScoreBadgesPanelProps {
  data: CISummaryData;
  lastUpdated: Date | null;
}

export function ScoreBadgesPanel({ data, lastUpdated }: ScoreBadgesPanelProps) {
  return (
    <div className="flex flex-col md:flex-row gap-6 mb-6 pb-6 border-b border-gray-200">
      <div className="flex flex-col items-center">
        <ScoreCircle score={data.metrics.score} grade={data.metrics.grade} size={100} />
        <p className="mt-2 text-sm text-gray-600">Pipeline Health</p>
      </div>

      <div className="flex-1">
        <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <Award className="w-5 h-5 text-yellow-500" />
          Earned Badges
        </h3>
        <div className="flex flex-wrap gap-2">
          {data.metrics.badges.map((badge, idx) => (
            <span
              key={idx}
              className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-gradient-to-r from-yellow-50 to-orange-50 text-orange-800 border border-orange-200"
            >
              {badge}
            </span>
          ))}
          {data.metrics.badges.length === 0 && (
            <span className="text-sm text-gray-500 italic">Complete more runs to earn badges!</span>
          )}
        </div>

        {/* Run Info */}
        <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
          <div className="flex items-center gap-2 text-gray-600">
            <GitBranch className="w-4 h-4" />
            <span className="truncate">{data.run.branch}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-600">
            <User className="w-4 h-4" />
            @{data.run.triggered_by}
          </div>
          <div className="flex items-center gap-2 text-gray-600">
            <Calendar className="w-4 h-4" />
            #{data.run.number}
          </div>
          <div className="flex items-center gap-2 text-gray-600">
            <BarChart3 className="w-4 h-4" />
            {data.run.event}
          </div>
        </div>

        {lastUpdated && (
          <p className="text-xs text-gray-400 mt-3">
            Last updated: {timeAgo(lastUpdated.toISOString())}
          </p>
        )}
      </div>
    </div>
  );
}
