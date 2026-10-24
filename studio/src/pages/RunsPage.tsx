// RunsPage — real run observer (ERR-B04 fix)
// বাংলা মন্তব্য: /runs পেজটি আগে স্ট্যাটিক মক কার্ড ছিল (ERR-B04, canonical
// defect register 2026-09-15) — run observer, execution list, step retry
// কিছুই ছিল না। এখন real Mission Orchestration API-র ওপরে: execution list
// (state filter সহ), per-run step observer (trace events), এবং state-machine
// দ্বারা validated retry (failed → repair) ও cancel অ্যাকশন।

import { useState } from 'react';
import { ChevronDown, ChevronRight, LifeBuoy, Play, RefreshCw } from 'lucide-react';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { HoldToKillButton } from '../components/swarm/HoldToKillButton';
import { useListResource } from '../hooks/useListResource';
import {
  runService,
  type MissionRun,
  type TraceEvent,
} from '../services/runService';

const STATE_BADGE: Record<string, string> = {
  planned: 'text-[var(--sa-ink-muted)] bg-[var(--sa-surface)]',
  approved: 'text-emerald-400 bg-emerald-400/10',
  assigned: 'text-emerald-400 bg-emerald-400/10',
  running: 'text-[var(--sa-primary)] bg-[var(--sa-primary-soft)]',
  repairing: 'text-amber-400 bg-amber-400/10',
  succeeded: 'text-emerald-400 bg-emerald-400/10',
  failed: 'text-red-400 bg-red-500/10',
  cancelled: 'text-[var(--sa-ink-muted)] bg-[var(--sa-surface)]',
};

function formatWhen(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/** Action buttons allowed for a run, per the mission state machine. */
function availableActions(state: string): Array<'approve' | 'start' | 'retry' | 'cancel'> {
  switch (state) {
    case 'planned':
      return ['cancel'];
    case 'approved':
      return ['start', 'cancel'];
    case 'assigned':
      return ['start', 'cancel'];
    case 'failed':
      return ['retry'];
    case 'running':
    case 'repairing':
      return ['cancel'];
    default:
      return [];
  }
}

export function RunsPage() {
  // বাংলা (Wave 3 dedup): runs/isLoading/loadError + load + useEffect ক্লাস্টারটি
  // এখন useListResource হুকে — পেজের বাকি সব state (trace observer, actions)
  // আগের মতোই page-local। limit 50 contract অপরিবর্তিত।
  const {
    items: runs,
    isLoading,
    loadError,
    reload: loadRuns,
  } = useListResource<MissionRun>({
    fetcher: async () => (await runService.listRuns({ limit: 50 })).items,
  });
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [trace, setTrace] = useState<Record<string, TraceEvent[]>>({});
  const [traceLoadingId, setTraceLoadingId] = useState<string | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const toggleTrace = async (run: MissionRun) => {
    if (expandedId === run.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(run.id);
    setTraceError(null);
    if (trace[run.id]) return; // cached
    setTraceLoadingId(run.id);
    try {
      const res = await runService.getTrace(run.id);
      setTrace((prev) => ({ ...prev, [run.id]: res.items }));
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : 'Failed to load trace');
    } finally {
      setTraceLoadingId(null);
    }
  };

  const doAction = async (run: MissionRun, action: 'retry' | 'cancel' | 'start') => {
    setActionBusyId(run.id);
    setActionError(null);
    try {
      if (action === 'retry') await runService.repairRun(run.id);
      else if (action === 'cancel') await runService.cancelRun(run.id);
      else await runService.startRun(run.id);
      await loadRuns();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setActionBusyId(null);
    }
  };

  return (
    <WorkspaceLayout>
      <div className="mx-auto w-full max-w-5xl px-5 py-8 text-[var(--sa-ink)] sm:px-8 lg:py-10">
        <header className="flex flex-col gap-4 border-b border-[var(--sa-border)] pb-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="sa-eyebrow">Observe / Runs</p>
            <h1 className="mt-2 max-w-3xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              Follow work from trigger to outcome.
            </h1>
            <p className="mt-2 max-w-2xl text-[var(--sa-ink-muted)]">
              Track running and completed executions, inspect each step, and
              retry or cancel straight from the observer.
            </p>
          </div>
          <button
            type="button"
            data-testid="runs-refresh-btn"
            onClick={() => void loadRuns()}
            className="inline-flex items-center justify-center gap-2 rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--sa-primary)]"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        </header>

        {actionError && (
          <p role="alert" data-testid="runs-action-error" className="mt-4 border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
            {actionError}
          </p>
        )}

        <section className="mt-6 flex flex-col gap-3" aria-label="Execution runs">
          {isLoading ? (
            <div className="flex flex-col gap-3">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="sa-surface-raised h-20 animate-pulse rounded-[var(--sa-radius-sm)]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : loadError ? (
            <div
              role="alert"
              data-testid="runs-error"
              className="flex flex-col gap-3 border border-red-500/40 bg-red-500/5 p-4 text-sm sm:flex-row sm:items-center"
            >
              <span className="text-red-400">{loadError}</span>
              <button
                type="button"
                onClick={() => void loadRuns()}
                className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 font-medium transition hover:border-[var(--sa-primary)] sm:ml-auto"
              >
                Try again
              </button>
            </div>
          ) : runs.length === 0 ? (
            <div
              data-testid="runs-empty"
              className="sa-surface-raised flex flex-col items-center gap-2 p-10 text-center"
            >
              <Play size={22} className="text-[var(--sa-primary)]" />
              <h2 className="text-lg font-semibold">No runs yet</h2>
              <p className="max-w-md text-sm text-[var(--sa-ink-muted)]">
                Approve and start a mission and it will appear here with full
                step-by-step observability.
              </p>
            </div>
          ) : (
            runs.map((run) => {
              const actions = availableActions(run.state);
              const isOpen = expandedId === run.id;
              return (
                <div
                  key={run.id}
                  data-testid="run-card"
                  className="sa-surface-raised overflow-hidden"
                >
                  <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
                    <button
                      type="button"
                      data-testid={`run-expand-btn-${run.id}`}
                      aria-expanded={isOpen}
                      aria-label={`Inspect run ${run.title}`}
                      onClick={() => void toggleTrace(run)}
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                    >
                      {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold">{run.title}</span>
                        <span className="mt-0.5 block text-xs text-[var(--sa-ink-muted)]">
                          {formatWhen(run.updated_at)} · Phase {run.current_phase}/
                          {run.phases.length || 0}
                          {run.repair_count > 0 && (
                            <span className="text-amber-400"> · {run.repair_count} repair(s)</span>
                          )}
                        </span>
                      </span>
                    </button>
                    <span
                      data-testid={`run-state-${run.id}`}
                      className={`w-fit rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${STATE_BADGE[run.state] ?? STATE_BADGE.planned}`}
                    >
                      {run.state}
                    </span>
                    <div className="flex items-center gap-2">
                      {actions.includes('retry') && (
                        <button
                          type="button"
                          data-testid={`run-retry-btn-${run.id}`}
                          onClick={() => void doAction(run, 'retry')}
                          disabled={actionBusyId === run.id}
                          className="inline-flex items-center gap-1 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
                        >
                          <LifeBuoy size={13} />
                          {actionBusyId === run.id ? 'Retrying…' : 'Retry'}
                        </button>
                      )}
                      {actions.includes('start') && (
                        <button
                          type="button"
                          data-testid={`run-start-btn-${run.id}`}
                          onClick={() => void doAction(run, 'start')}
                          disabled={actionBusyId === run.id}
                          className="inline-flex items-center gap-1 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
                        >
                          <Play size={13} />
                          Start
                        </button>
                      )}
                      {actions.includes('cancel') && (
                        /* বাংলা মন্তব্য: Task-12 ghost activation — cancel একটি irreversible
                           অ্যাকশন (POST /api/v1/runs/{run_id}/cancel), তাই এক-ক্লিকের বদলে
                           hold-to-confirm (২ সেকেন্ড) gesture ব্যবহার করা হলো। এটিই আগে
                           অব্যবহৃত HoldToKillButton কম্পোনেন্টের প্রথম প্রকৃত ব্যবহার। */
                        <HoldToKillButton
                          testId={`run-cancel-btn-${run.id}`}
                          label="Cancel"
                          holdingLabel="Keep holding to cancel…"
                          disabled={actionBusyId === run.id}
                          onTrigger={() => void doAction(run, 'cancel')}
                        />
                      )}
                    </div>
                  </div>

                  {run.failure_reason && (
                    <p className="border-t border-[var(--sa-border)] px-4 py-2 text-xs text-red-400">
                      Failure reason: {run.failure_reason}
                    </p>
                  )}

                  {isOpen && (
                    <div
                      className="border-t border-[var(--sa-border)] bg-[var(--sa-canvas)] p-4"
                      data-testid={`run-trace-${run.id}`}
                    >
                      <p className="sa-eyebrow">Step observer</p>
                      {traceLoadingId === run.id ? (
                        <p className="mt-2 text-sm text-[var(--sa-ink-muted)]">Loading trace…</p>
                      ) : traceError && isOpen ? (
                        <p role="alert" className="mt-2 text-sm text-red-400">
                          {traceError}
                        </p>
                      ) : (trace[run.id]?.length ?? 0) === 0 ? (
                        <p className="mt-2 text-sm text-[var(--sa-ink-muted)]">
                          No trace events recorded for this run yet.
                        </p>
                      ) : (
                        <ol className="mt-3 flex flex-col gap-2 border-l border-[var(--sa-border)] pl-4">
                          {(trace[run.id] ?? []).map((ev) => (
                            <li key={ev.id} className="text-xs" data-testid="trace-event">
                              <span className="font-mono text-[var(--sa-ink-muted)]">
                                #{ev.seq}
                              </span>{' '}
                              <span className="font-semibold">{ev.event}</span>{' '}
                              <span className="text-[var(--sa-ink-muted)]">
                                (phase {ev.phase}, {formatWhen(ev.created_at)})
                              </span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </section>
      </div>
    </WorkspaceLayout>
  );
}

export default RunsPage;
