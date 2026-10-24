import { convertToCSV } from './csv';

/**
 * ====================================================================================
 * SupremeAI CI Dashboard Component - Admin Integration
 * ====================================================================================
 *
 * 🎯 Real-time CI/CD Status Dashboard for the Admin Console
 * 🔌 REST API + optional WebSocket live updates (/ws/dashboard)
 * 📊 Trend charts built from the REAL /api/ci/history endpoint
 * 🎨 Animated UI with micro-interactions
 *
 * FEATURES:
 * ─────────────────────────────────────────────
 * ✅ Live CI summary via /api/ci/latest-summary
 * ✅ Real historical trend charts from /api/ci/history (no fabricated data —
 *    when no history exists the charts show an honest empty state)
 * ✅ Job-level details with working status filter + error drill-down
 * ✅ Badge & score system (gamification!)
 * ✅ Predictive insights ("will next build pass?")
 * ✅ Compact sidebar widget mode with expandable job list
 * ✅ JSON/CSV export
 *
 * PROPS API:
 * ─────────────────────────────────────────────
 * interface CIDashboardProps {
 *   repoName?: string;           // e.g., "SaifulHaqueNiloy/supremeai" (header subtitle)
 *   refreshInterval?: number;    // Auto-refresh in ms (default: 30000)
 *   showTrends?: boolean;        // Show historical trends (default: true)
 *   maxHistoryItems?: number;     // Max items in compact list (default: 20)
 *   onJobClick?: (job) => void;  // Callback when job clicked
 *   className?: string;          // Additional CSS classes
 *   compact?: boolean;            // Compact mode for sidebars
 * }
 *
 * @author SuperAI Toolkit v2.0
 * @version 2.1.0
 * ====================================================================================
 */

// ══════════════════════════════════════════════════════════════════════════════
// CIDashboard — main entry point.
// Mechanical split (no behavior change): types, constants, utils, primitives,
// cards and tab panels live in ./ci-dashboard/* — re-exported below so the
// public API of this module is unchanged.
// ══════════════════════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback, useMemo } from 'react';

import { getApiBaseUrl } from '../../../utils/api';  // roadmap 1.5 (#1180)
import {
  RefreshCw,
  GitBranch,
  Shield,
  Loader2,
  XCircle,
  Download,
  Activity,
  ListChecks,
  Bug,
  TrendingUp,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

import { ConnectionBadge, EmptyState } from './ci-dashboard/primitives';
import { JobRow } from './ci-dashboard/cards';
import { DashboardHeader } from './ci-dashboard/DashboardHeader';
import { ScoreBadgesPanel } from './ci-dashboard/ScoreBadgesPanel';
import { useDashboardWebSocket } from './ci-dashboard/useDashboardWebSocket';
import { OverviewTab } from './ci-dashboard/tabs/OverviewTab';
import { JobsTab } from './ci-dashboard/tabs/JobsTab';
import { ErrorsTab } from './ci-dashboard/tabs/ErrorsTab';
import { TrendsTab } from './ci-dashboard/tabs/TrendsTab';
import type {
  CISummaryData,
  CIDashboardProps,
  ConnectionStatus,
  JobResult,
  TrendChartPoint,
} from './ci-dashboard/types';

export function CIDashboard({
  repoName,
  refreshInterval = 30000,
  showTrends = true,
  maxHistoryItems = 20,
  onJobClick,
  className = '',
  compact = false,
  apiUrl,
  wsUrl,
}: CIDashboardProps) {
  // State
  const [data, setData] = useState<CISummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'jobs' | 'errors' | 'trends'>('overview');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showAllJobs, setShowAllJobs] = useState(false); // compact-mode expansion

  // Chart data preparation — REAL run history from /api/ci/history.
  // FINAL-TEST FIX: this used to render a hardcoded 7-point sample series
  // whenever trends.available was true, i.e. the charts displayed fabricated
  // numbers. Now the points come from the backend's real run history and the
  // tabs render an honest empty state until at least one point exists.
  const [historyPoints, setHistoryPoints] = useState<TrendChartPoint[]>([]);

  const trendChartData = useMemo<TrendChartPoint[]>(() => historyPoints, [historyPoints]);

  // Fetch run history for the trend charts (oldest → newest for charting)
  const fetchHistory = useCallback(async () => {
    try {
      const base = apiUrl
        ? apiUrl.replace(/\/api\/ci\/latest-summary$/, '')
        : getApiBaseUrl();  // roadmap 1.5 (#1180): canonical resolver
      const response = await fetch(`${base}/api/ci/history?limit=12`);
      if (!response.ok) return; // history is optional — never block the dashboard
      const payload = await response.json();
      const runs: Array<Record<string, unknown>> = Array.isArray(payload)
        ? payload
        : payload.history || payload.items || payload.runs || [];
      const points = runs
        .map((run) => {
          const successRate = typeof run.success_rate === 'number' ? run.success_rate : Number(run.success_rate) || 0;
          const score = typeof run.score === 'number' ? run.score : Number(run.score) || 0;
          const duration = typeof run.duration === 'number' ? run.duration : Number(run.duration) || 0;
          const runNumber = run.run_number ?? run.run_id ?? '';
          return {
            name: runNumber !== '' ? `Run #${runNumber}` : 'Run',
            success: Math.round(successRate || score),
            duration: Math.round(duration),
          };
        })
        .filter((p) => p.success > 0 || p.duration > 0)
        .reverse(); // backend returns newest-first; charts read oldest→newest
      setHistoryPoints(points);
    } catch {
      // History endpoint unavailable — charts will show the honest empty state.
      setHistoryPoints([]);
    }
  }, [apiUrl]);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const url = apiUrl || `${getApiBaseUrl()}/api/ci/latest-summary`;  // roadmap 1.5 (#1180)
      const response = await fetch(url);

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result: CISummaryData = await response.json();
      setData(result);
      setError(null);
      setLastUpdated(new Date());
      setConnectionStatus('connected');
    } catch (err) {
      console.error('Failed to fetch CI data:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch');
      setConnectionStatus('error');
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  // WebSocket connection for real-time updates
  useDashboardWebSocket({
    wsUrl,
    fetchData,
    setConnectionStatus,
    setData,
    setLastUpdated,
  });


  // Auto-refresh polling
  useEffect(() => {
    if (!autoRefresh || !apiUrl) return;

    const interval = setInterval(fetchData, refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, fetchData, apiUrl]);

  // Initial fetch
  useEffect(() => {
    if (!wsUrl) {
      fetchData();
      fetchHistory();
    }
  }, [fetchData, fetchHistory, wsUrl]);

  // Handlers
  const handleRefresh = () => {
    setLoading(true);
    fetchData();
    fetchHistory();
  };

  const handleJobClick = (job: JobResult) => {
    if (onJobClick) onJobClick(job);
  };

  const handleExport = async (format: 'json' | 'csv') => {
    if (!data) return;

    const content = format === 'json'
      ? JSON.stringify(data, null, 2)
      : convertToCSV(data);

    const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ci-report-${new Date().toISOString().split('T')[0]}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Loading State
  if (loading && !data) {
    return (
      <div className={`bg-white rounded-2xl border border-gray-200 p-8 ${className}`}>
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
          <p className="text-lg font-medium text-gray-700">Loading CI Dashboard...</p>
          <p className="text-sm text-gray-500 mt-1">Fetching latest pipeline data</p>
        </div>
      </div>
    );
  }

  // Error State
  if (error && !data) {
    return (
      <div className={`bg-white rounded-2xl border border-red-200 p-8 ${className}`}>
        <EmptyState
          message={error}
          icon={XCircle}
        />
        <button
          onClick={handleRefresh}
          className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2 mx-auto"
        >
          <RefreshCw className="w-4 h-4" />
          Try Again
        </button>
      </div>
    );
  }

  // Compact Mode (for sidebars/widgets)
  if (compact && data) {
    const visibleJobs = showAllJobs ? data.jobs : data.jobs.slice(0, maxHistoryItems);
    return (
      <div className={`bg-white rounded-xl border border-gray-200 p-4 ${className}`}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <GitBranch className="w-4 h-4" />
            CI Status
          </h3>
          <ConnectionBadge status={connectionStatus} />
        </div>

        <div className="space-y-2">
          {visibleJobs.map((job, idx) => (
            <JobRow key={idx} job={job} onClick={() => handleJobClick(job)} compact />
          ))}
        </div>

        {data.jobs.length > maxHistoryItems && (
          <button
            onClick={() => setShowAllJobs((v) => !v)}
            className="w-full mt-2 text-xs font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg py-1.5 transition-colors flex items-center justify-center gap-1"
          >
            {showAllJobs ? (
              <>
                Show fewer <ChevronUp className="w-3 h-3" />
              </>
            ) : (
              <>
                View all {data.jobs.length} jobs <ChevronDown className="w-3 h-3" />
              </>
            )}
          </button>
        )}
      </div>
    );
  }

  // Full Dashboard
  return (
    <div className={`bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden ${className}`}>
      {/* Header */}
      <DashboardHeader
        data={data}
        repoName={repoName}
        connectionStatus={connectionStatus}
        autoRefresh={autoRefresh}
        onToggleAutoRefresh={() => setAutoRefresh(!autoRefresh)}
        onRefresh={handleRefresh}
      />

      {/* Main Content */}
      {data && (
        <div className="p-6">
          {/* Score & Badges Section */}
          <ScoreBadgesPanel data={data} lastUpdated={lastUpdated} />

          {/* Tabs */}
          <div className="flex gap-1 p-1 bg-gray-100 rounded-xl mb-6 overflow-x-auto">
            {([
              { key: 'overview' as const, label: 'Overview', icon: Activity },
              { key: 'jobs' as const, label: 'Jobs', icon: ListChecks },
              { key: 'errors' as const, label: 'Errors', icon: Bug },
              { key: 'trends' as const, label: 'Trends', icon: TrendingUp },
            ]).map(({ key, label, icon: TabIcon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                aria-selected={activeTab === key}
                role="tab"
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap ${
                  activeTab === key
                    ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-200'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-white/60'
                }`}
              >
                <TabIcon className={`w-4 h-4 ${activeTab === key ? 'text-blue-600' : 'text-gray-400'}`} />
                {label}
                {key === 'errors' && data.errors.total > 0 && (
                  <span className="ml-0.5 px-1.5 py-0.5 bg-red-100 text-red-700 rounded-full text-xs font-semibold">
                    {data.errors.total}
                  </span>
                )}
                {key === 'jobs' && (
                  <span className="ml-0.5 px-1.5 py-0.5 bg-gray-200 text-gray-600 rounded-full text-xs">
                    {data.metrics.total_jobs}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="min-h-[400px]">
            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <OverviewTab
                data={data}
                showTrends={showTrends}
                trendChartData={trendChartData}
              />
            )}

            {/* Jobs Tab */}
            {activeTab === 'jobs' && (
              <JobsTab data={data} onJobClick={handleJobClick} />
            )}

            {/* Errors Tab */}
            {activeTab === 'errors' && (
              <ErrorsTab data={data} />
            )}

            {/* Trends Tab */}
            {activeTab === 'trends' && (
              <TrendsTab
                data={data}
                showTrends={showTrends}
                trendChartData={trendChartData}
              />
            )}
          </div>

          {/* Footer Actions */}
          <div className="mt-6 pt-6 border-t border-gray-200 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Shield className="w-4 h-4" />
              <span>SuperAI Enhanced CI Summary v2.0</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => handleExport('json')}
                className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-1"
              >
                <Download className="w-4 h-4" />
                JSON
              </button>
              <button
                onClick={() => handleExport('csv')}
                className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors flex items-center gap-1"
              >
                <Download className="w-4 h-4" />
                CSV
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// EXPORTS (public API unchanged from the pre-split monolith)
// ══════════════════════════════════════════════════════════════════════════════

export default CIDashboard;

// Sub-components export for standalone use
export { JobRow, InsightCard } from './ci-dashboard/cards';
export { ScoreCircle, ProgressBar, Badge, EmptyState, ConnectionBadge } from './ci-dashboard/primitives';

// Types export
export type { CISummaryData, JobResult, CIError, CIInsight, ConnectionStatus } from './ci-dashboard/types';
