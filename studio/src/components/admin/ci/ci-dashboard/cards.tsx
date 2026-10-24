// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — SUB-COMPONENTS (data cards)
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Target,
  Clock,
  Activity,
  ExternalLink,
  Shuffle,
} from 'lucide-react';
import { STATUS_CONFIG } from './constants';
import { formatDuration } from './utils';
import { Badge, AnimatedStatus } from './primitives';
import type { CIInsight, JobResult } from './types';

/** Severity → accent border color for insight cards. */
function severityBorder(severity: string): string {
  switch ((severity || '').toLowerCase()) {
    case 'critical':
      return 'border-l-4 border-l-red-500';
    case 'warning':
      return 'border-l-4 border-l-amber-400';
    case 'info':
      return 'border-l-4 border-l-blue-400';
    default:
      return 'border-l-4 border-l-gray-300';
  }
}

export function InsightCard({ insight }: { insight: CIInsight }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow ${severityBorder(insight.severity)}`}>
      <div className="flex items-start gap-3">
        <span className="text-2xl">{insight.icon}</span>
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-gray-900 text-sm">{insight.title}</h4>
          <p className="text-xs text-gray-600 mt-1">{insight.description}</p>

          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 mt-2 text-xs text-blue-600 hover:text-blue-800"
          >
            {expanded ? 'Less' : 'More'}
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>

          {expanded && (
            <div className="mt-3 p-3 bg-gray-50 rounded-lg space-y-2">
              <div className="flex items-start gap-2">
                <Target className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-gray-700">Action Item</p>
                  <p className="text-xs text-gray-600">{insight.action_item}</p>
                </div>
              </div>
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Category: {insight.category}</span>
                <span>Confidence: {(insight.confidence * 100).toFixed(0)}%</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function JobRow({ job, onClick, compact = false }: { job: JobResult; onClick?: () => void; compact?: boolean }) {
  const config = STATUS_CONFIG[job.status];
  const Icon = config.icon;

  if (compact) {
    return (
      <button
        onClick={onClick}
        className="w-full flex items-center gap-2 p-2 rounded-lg hover:bg-gray-50 transition-colors text-left border-l-2"
        style={{ borderLeftColor: config.color }}
      >
        <Icon className="w-4 h-4 flex-shrink-0" style={{ color: config.color }} />
        <span className="truncate text-sm flex-1">{job.name}</span>
        {job.is_flaky && (
          <Shuffle className="w-3 h-3 text-amber-400 flex-shrink-0" aria-label="flaky job" />
        )}
        <span className="text-xs text-gray-500">{formatDuration(job.duration)}</span>
      </button>
    );
  }

  return (
    <div
      onClick={onClick}
      className="relative flex items-center gap-4 p-4 pl-5 bg-white rounded-xl border border-gray-200 hover:border-gray-300 hover:shadow-md hover:-translate-y-px transition-all cursor-pointer group overflow-hidden"
    >
      {/* status accent bar */}
      <span
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{ backgroundColor: config.color }}
        aria-hidden="true"
      />
      <AnimatedStatus status={job.status} />

      <div className="flex-1 min-w-0">
        <h4 className="font-medium text-gray-900 group-hover:text-blue-600 transition-colors truncate">
          {job.name}
        </h4>
        <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(job.duration)}
          </span>
          {job.runner_name && (
            <span className="flex items-center gap-1">
              <Activity className="w-3 h-3" />
              {job.runner_name}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {job.is_flaky && (
          <Badge variant="warning">flaky</Badge>
        )}
        {(job.error_count > 0 || job.warning_count > 0) && (
          <div className="flex gap-1">
            {job.error_count > 0 && (
              <Badge variant="failure">{job.error_count} errors</Badge>
            )}
            {job.warning_count > 0 && (
              <Badge variant="warning">{job.warning_count} warnings</Badge>
            )}
          </div>
        )}

        {job.url && (
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-1.5 rounded-lg hover:bg-gray-100 opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <ExternalLink className="w-4 h-4 text-gray-400" />
          </a>
        )}
      </div>
    </div>
  );
}
