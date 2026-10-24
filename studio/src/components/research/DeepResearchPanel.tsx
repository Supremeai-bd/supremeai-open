import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Loader2,
  CheckCircle2,
  Circle,
  AlertCircle,
  History,
  ExternalLink,
  FileText,
  Microscope,
  ArrowLeft,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { getApiBaseUrl } from '../../utils/api';
import { getAdminToken, getUserToken } from '../../services/tokenStorage';
import { globalShowToastRef } from '../../contexts/ToastContext';
import { parseResearchSseLine } from './researchEventContract';

// ─── Types ───────────────────────────────────────────────────────────────

type StepStatus = 'pending' | 'running' | 'done' | 'error';

type TabType = 'research' | 'history';

interface ResearchStep {
  step_number: number;
  name: string;
  status: StepStatus;
  content_preview: string;
}

interface ResearchReport {
  title: string;
  sections: {
    heading: string;
    content: string;
  }[];
  sources: {
    title: string;
    url: string;
  }[];
  summary: string;
}

interface ResearchHistoryItem {
  id: string;
  query: string;
  status: 'completed' | 'failed' | 'running';
  created_at: string;
  report?: ResearchReport;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function getStepIcon(status: StepStatus) {
  switch (status) {
    case 'done':
      return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
    case 'running':
      return <Loader2 className="w-5 h-5 text-amber-500 animate-spin" />;
    case 'error':
      return <XCircle className="w-5 h-5 text-red-500" />;
    case 'pending':
    default:
      return <Circle className="w-5 h-5 text-slate-300 dark:text-slate-600" />;
  }
}

function _getStepLineClass(status: StepStatus): string {
  switch (status) {
    case 'done':
      return 'bg-emerald-500';
    case 'running':
      return 'bg-amber-500';
    case 'error':
      return 'bg-red-500';
    default:
      return 'bg-slate-200 dark:bg-slate-700';
  }
}

function getStepCardClass(status: StepStatus): string {
  switch (status) {
    case 'done':
      return 'border-emerald-200 dark:border-emerald-500/25';
    case 'running':
      return 'border-amber-200 dark:border-amber-500/25';
    case 'error':
      return 'border-red-200 dark:border-red-500/25';
    default:
      return 'border-slate-200 dark:border-slate-700/50';
  }
}

function getProgressPercent(steps: ResearchStep[]): number {
  if (steps.length === 0) return 0;
  const done = steps.filter((s) => s.status === 'done').length;
  const running = steps.filter((s) => s.status === 'running').length;
  return Math.round(((done + running * 0.5) / steps.length) * 100);
}

function formatHistoryDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ─── Component ───────────────────────────────────────────────────────────

export default function DeepResearchPanel() {
  const [activeTab, setActiveTab] = useState<TabType>('research');
  const [query, setQuery] = useState('');
  const [isResearching, setIsResearching] = useState(false);
  const [steps, setSteps] = useState<ResearchStep[]>([]);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ResearchHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [viewingReport, setViewingReport] = useState<ResearchReport | null>(null);
  const [viewingTitle, setViewingTitle] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  const fetchHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    try {
      const response = await apiClient.get<ResearchHistoryItem[]>('/api/research/history');
      setHistory(Array.isArray(response) ? response : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load research history';
      globalShowToastRef.current('error', message);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab, fetchHistory]);

  const handleStartResearch = useCallback(async () => {
    if (!query.trim() || isResearching) return;

    setIsResearching(true);
    setSteps([]);
    setReport(null);
    setError(null);
    setViewingReport(null);

    abortRef.current = new AbortController();

    try {
      // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
      const token = getUserToken() || getAdminToken();
      // Issue #452 fix: window.location.origin breaks whenever the API lives on
      // a different origin than the frontend — use the canonical base URL
      // helper like every other panel.
      const baseUrl = getApiBaseUrl();

      const response = await fetch(`${baseUrl}/api/research/deep/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ query: query.trim() }),
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`Research request failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          // M08 P-A: SSE parsing lives in researchEventContract.ts — the
          // single source of truth shared with the backend contract test
          // (backend/tests/api/test_deep_research_contract.py). মৃত
          // legacy নাম-শাখা ("step_update"/"complete") বাদ — প্রকৃত ব্যাকএন্ড
          // কখনো সেগুলো পাঠায় না (issue #452 পোস্ট-ফিক্স চুক্তি)।
          const parsed = parseResearchSseLine(line);
          if (parsed.kind === 'step') {
            const backendStep: ResearchStep = {
              step_number: parsed.step.step_number,
              name: parsed.step.name,
              status: 'done',
              content_preview: parsed.step.content_preview,
            };
            setSteps((prev) => {
              const exists = prev.findIndex((s) => s.step_number === backendStep.step_number);
              if (exists >= 0) {
                const updated = [...prev];
                updated[exists] = backendStep;
                return updated;
              }
              return [...prev, backendStep].sort((a, b) => a.step_number - b.step_number);
            });
          } else if (parsed.kind === 'report') {
            setReport({
              title: parsed.report.title,
              sections: parsed.report.sections,
              sources: parsed.report.sources,
              summary: parsed.report.summary,
            });
            setSteps((prev) =>
              prev.map((s) => (s.status !== 'error' ? { ...s, status: 'done' as const } : s))
            );
            globalShowToastRef.current('success', 'Research completed!');
          } else if (parsed.kind === 'error') {
            setError(parsed.message);
            globalShowToastRef.current('error', parsed.message);
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // User cancelled
        return;
      }
      const message = err instanceof Error ? err.message : 'Failed to start research';
      setError(message);
      globalShowToastRef.current('error', message);
    } finally {
      setIsResearching(false);
      abortRef.current = null;
    }
  }, [query, isResearching]);

  const handleCancelResearch = useCallback(() => {
    abortRef.current?.abort();
    setIsResearching(false);
  }, []);

  const handleViewHistoryReport = useCallback((item: ResearchHistoryItem) => {
    if (item.report) {
      setViewingReport(item.report);
      setViewingTitle(item.query);
    } else {
      globalShowToastRef.current('info', 'Report not available for this research item.');
    }
  }, []);

  const displayReport = viewingReport || report;
  const displayTitle = viewingTitle || query;
  const progressPercent = getProgressPercent(steps);

  return (
    <div className="flex flex-col h-full bg-white dark:bg-slate-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-200 dark:border-slate-800 px-6 py-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-cyan-100 dark:bg-cyan-500/10 text-cyan-600 dark:text-cyan-400">
            <Microscope className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
              Deep Research
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              AI-powered in-depth research with multi-step analysis
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-4">
          <button
            type="button"
            onClick={() => { setActiveTab('research'); setViewingReport(null); }}
            className={
              'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ' +
              (activeTab === 'research'
                ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900'
                : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800')
            }
          >
            <Microscope className="w-4 h-4" />
            Research
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('history')}
            className={
              'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ' +
              (activeTab === 'history'
                ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900'
                : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800')
            }
          >
            <History className="w-4 h-4" />
            Past Research
          </button>
        </div>

        {/* Search Input */}
        {activeTab === 'research' && !displayReport && (
          <div className="flex items-center gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="What would you like to research in depth?"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleStartResearch()}
                disabled={isResearching}
                className={
                  'w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border transition-colors ' +
                  'bg-slate-50 dark:bg-slate-900 border-slate-200 dark:border-slate-700 ' +
                  'text-slate-900 dark:text-white placeholder:text-slate-400 ' +
                  'focus:outline-none focus:ring-2 focus:ring-cyan-500/40 focus:border-cyan-500 ' +
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                }
              />
            </div>
            {isResearching ? (
              <button
                type="button"
                onClick={handleCancelResearch}
                className={
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl transition-all ' +
                  'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 border border-red-200 dark:border-red-500/25'
                }
              >
                Cancel
              </button>
            ) : (
              <button
                type="button"
                onClick={handleStartResearch}
                disabled={!query.trim()}
                className={
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl transition-all ' +
                  'text-white bg-cyan-600 hover:bg-cyan-500 shadow-lg shadow-cyan-500/20 ' +
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                }
              >
                <Sparkles className="w-4 h-4" />
                Start Deep Research
              </button>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Active Research View */}
        {activeTab === 'research' && (
          <AnimatePresence mode="wait">
            {/* Report View */}
            {displayReport ? (
              <motion.div
                key="report"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="p-6 space-y-6"
              >
                {/* Back button */}
                <button
                  type="button"
                  onClick={() => { setReport(null); setViewingReport(null); setSteps([]); setError(null); }}
                  className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to research
                </button>

                {/* Report Title */}
                <div>
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">
                    {displayReport.title || displayTitle}
                  </h2>
                  {displayReport.summary && (
                    <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                      {displayReport.summary}
                    </p>
                  )}
                </div>

                {/* Sections */}
                {displayReport.sections.map((section, i) => (
                  <div key={i} className="space-y-2">
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                      <FileText className="w-4 h-4 text-cyan-500 flex-shrink-0" />
                      {section.heading}
                    </h3>
                    <div className="pl-6 text-sm text-slate-700 dark:text-slate-200 leading-relaxed whitespace-pre-wrap">
                      {section.content}
                    </div>
                  </div>
                ))}

                {/* Sources */}
                {displayReport.sources.length > 0 && (
                  <div>
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white mb-3">
                      Sources
                    </h3>
                    <div className="space-y-2">
                      {displayReport.sources.map((source, i) => (
                        <a
                          key={i}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={
                            'flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ' +
                            'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700/50 ' +
                            'hover:border-cyan-300 dark:hover:border-cyan-500/50 hover:bg-cyan-50/50 dark:hover:bg-cyan-500/5 ' +
                            'text-slate-700 dark:text-slate-200'
                          }
                        >
                          <ExternalLink className="w-4 h-4 text-cyan-500 flex-shrink-0" />
                          <span className="text-sm truncate">{source.title || source.url}</span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </motion.div>
            ) : (
              /* Progress Timeline View */
              <motion.div
                key="progress"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="p-6"
              >
                {/* Error State */}
                {error && (
                  <div className="mb-6 px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-medium text-red-700 dark:text-red-400">Research Error</p>
                        <p className="text-xs text-red-600 dark:text-red-300 mt-0.5">{error}</p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Progress Bar */}
                {(isResearching || steps.length > 0) && (
                  <div className="mb-6">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        {isResearching ? 'Researching...' : 'Complete'}
                      </span>
                      <span className="text-sm text-slate-500 dark:text-slate-400">{progressPercent}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                      <motion.div
                        className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500"
                        initial={{ width: 0 }}
                        animate={{ width: `${progressPercent}%` }}
                        transition={{ duration: 0.5, ease: 'easeOut' }}
                      />
                    </div>
                  </div>
                )}

                {/* Steps Timeline */}
                {steps.length > 0 ? (
                  <div className="relative">
                    <div className="absolute left-[18px] top-4 bottom-4 w-0.5 bg-slate-200 dark:bg-slate-700" />
                    <div className="space-y-4">
                      {steps.map((step) => (
                        <div key={step.step_number} className="relative flex gap-4">
                          {/* Icon + Line */}
                          <div className="relative flex flex-col items-center z-10">
                            <div className="flex items-center justify-center w-9 h-9 rounded-full bg-white dark:bg-slate-900">
                              {getStepIcon(step.status)}
                            </div>
                          </div>

                          {/* Content */}
                          <motion.div
                            initial={{ opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.2 }}
                            className={
                              'flex-1 p-3 rounded-xl border transition-colors min-w-0 ' +
                              'bg-white dark:bg-slate-900 ' +
                              getStepCardClass(step.status)
                            }
                          >
                            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Step {step.step_number}</p>
                            <p className="text-sm font-medium text-slate-900 dark:text-white mb-1">{step.name}</p>
                            {step.content_preview && (
                              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed whitespace-pre-wrap line-clamp-4">
                                {step.content_preview}
                              </p>
                            )}
                          </motion.div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : !isResearching && !error ? (
                  /* Empty State */
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-cyan-50 dark:bg-cyan-500/10 mb-4">
                      <Microscope className="w-7 h-7 text-cyan-400" />
                    </div>
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">
                      Ready for deep research
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xs">
                      Enter a topic above to start a multi-step AI research process with live progress tracking
                    </p>
                  </div>
                ) : null}
              </motion.div>
            )}
          </AnimatePresence>
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <div className="p-6">
            {viewingReport ? (
              /* Viewing a past report */
              <div className="space-y-6">
                <button
                  type="button"
                  onClick={() => setViewingReport(null)}
                  className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to history
                </button>
                <div>
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">{viewingTitle}</h2>
                  {viewingReport.summary && (
                    <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{viewingReport.summary}</p>
                  )}
                </div>
                {viewingReport.sections.map((section, i) => (
                  <div key={i} className="space-y-2">
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                      <FileText className="w-4 h-4 text-cyan-500 flex-shrink-0" />
                      {section.heading}
                    </h3>
                    <div className="pl-6 text-sm text-slate-700 dark:text-slate-200 leading-relaxed whitespace-pre-wrap">
                      {section.content}
                    </div>
                  </div>
                ))}
                {viewingReport.sources.length > 0 && (
                  <div>
                    <h3 className="text-base font-semibold text-slate-900 dark:text-white mb-3">Sources</h3>
                    <div className="space-y-2">
                      {viewingReport.sources.map((source, i) => (
                        <a
                          key={i}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={
                            'flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ' +
                            'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700/50 ' +
                            'hover:border-cyan-300 dark:hover:border-cyan-500/50 text-slate-700 dark:text-slate-200'
                          }
                        >
                          <ExternalLink className="w-4 h-4 text-cyan-500 flex-shrink-0" />
                          <span className="text-sm truncate">{source.title || source.url}</span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : isLoadingHistory ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
              </div>
            ) : history.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-slate-100 dark:bg-slate-800 mb-4">
                  <History className="w-7 h-7 text-slate-400" />
                </div>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">No past research</p>
                <p className="text-xs text-slate-400 dark:text-slate-500 max-w-xs">
                  Your completed research sessions will appear here
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {history.map((item) => {
                  const statusColor =
                    item.status === 'completed'
                      ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
                      : item.status === 'running'
                        ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400'
                        : 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-400';
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleViewHistoryReport(item)}
                      className={
                        'w-full text-left px-4 py-3 rounded-xl border transition-all ' +
                        'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700/50 ' +
                        'hover:border-cyan-300 dark:hover:border-cyan-500/50 hover:shadow-md hover:shadow-cyan-500/5'
                      }
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                          {item.query}
                        </p>
                        <span className={
                          'inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md flex-shrink-0 ' + statusColor
                        }>
                          {item.status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                        {formatHistoryDate(item.created_at)}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
