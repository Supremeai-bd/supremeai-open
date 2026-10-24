// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — JOBS TAB
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// FINAL-TEST FEATURE FIX: the status <select> used to be decorative — it had no
// value/state and no filtering logic. It now actually filters the job list and
// shows a proper empty state when nothing matches.
// ══════════════════════════════════════════════════════════════════════════════

import { useMemo, useState } from 'react';
import { Filter, ListChecks } from 'lucide-react';
import { JobRow } from '../cards';
import type { CISummaryData, JobResult } from '../types';

type StatusFilter = 'all' | 'passed' | 'failed' | 'in_progress';

const FILTER_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All Status' },
  { value: 'passed', label: 'Passed Only' },
  { value: 'failed', label: 'Failed Only' },
  { value: 'in_progress', label: 'In Progress' },
];

function matchesFilter(job: JobResult, filter: StatusFilter): boolean {
  switch (filter) {
    case 'passed':
      return job.status === 'success';
    case 'failed':
      return job.status === 'failure';
    case 'in_progress':
      return job.status === 'in_progress';
    default:
      return true;
  }
}

interface JobsTabProps {
  data: CISummaryData;
  onJobClick: (job: JobResult) => void;
}

export function JobsTab({ data, onJobClick }: JobsTabProps) {
  const [filter, setFilter] = useState<StatusFilter>('all');

  const filteredJobs = useMemo(
    () => data.jobs.filter((job) => matchesFilter(job, filter)),
    [data.jobs, filter],
  );

  const passedCount = data.jobs.filter((j) => j.status === 'success').length;
  const failedCount = data.jobs.filter((j) => j.status === 'failure').length;
  const inProgressCount = data.jobs.filter((j) => j.status === 'in_progress').length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h3 className="font-semibold text-gray-900">
          All Jobs ({filteredJobs.length}
          {filter !== 'all' && filteredJobs.length !== data.jobs.length && (
            <span className="text-gray-400 font-normal"> of {data.jobs.length}</span>
          )}
          )
        </h3>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as StatusFilter)}
            aria-label="Filter jobs by status"
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-400 transition-colors cursor-pointer"
          >
            {FILTER_OPTIONS.map((opt) => {
              const count =
                opt.value === 'all'
                  ? data.jobs.length
                  : opt.value === 'passed'
                    ? passedCount
                    : opt.value === 'failed'
                      ? failedCount
                      : inProgressCount;
              return (
                <option key={opt.value} value={opt.value}>
                  {opt.label} ({count})
                </option>
              );
            })}
          </select>
        </div>
      </div>

      {filteredJobs.length > 0 ? (
        filteredJobs.map((job, idx) => (
          <JobRow key={job.id ?? idx} job={job} onClick={() => onJobClick(job)} />
        ))
      ) : (
        <div className="bg-gray-50 rounded-xl p-8 text-center">
          <ListChecks className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-gray-500 text-sm">No jobs match the “{FILTER_OPTIONS.find((o) => o.value === filter)?.label}” filter</p>
          <button
            onClick={() => setFilter('all')}
            className="mt-3 text-xs font-medium text-blue-600 hover:text-blue-800"
          >
            Reset filter
          </button>
        </div>
      )}
    </div>
  );
}
