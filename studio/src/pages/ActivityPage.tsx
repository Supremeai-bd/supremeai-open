// ActivityPage — real event timeline (ERR-B03 fix)
// বাংলা মন্তব্য: /activity পেজটি আগে স্ট্যাটিক মক কার্ড ছিল (ERR-B03, canonical
// defect register 2026-09-15) — কোনো event timeline, audit-log বা event-bus
// কানেকশন ছিল না। এখন real Mission Orchestration API (/api/v1/missions) থেকে
// owner-scoped mission লাইফসাইকেল টাইমলাইন রেন্ডার হয়: state badge, phase
// progress, failure reason, repair count — সবই backend-সত্য।

import { useEffect, useState } from 'react';
import {
  Ban,
  CheckCircle2,
  CircleDot,
  Clock,
  LifeBuoy,
  Play,
  RefreshCw,
  ThumbsUp,
  UserCheck,
  XCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { useListResource } from '../hooks/useListResource';
import {
  activityService,
  MISSION_STATES,
  type MissionActivity,
  type MissionState,
} from '../services/activityService';

const STATE_META: Record<
  MissionState,
  { icon: typeof Clock; className: string; label: string }
> = {
  planned: { icon: Clock, className: 'text-[var(--sa-ink-muted)] bg-[var(--sa-surface)]', label: 'Planned' },
  approved: { icon: ThumbsUp, className: 'text-emerald-400 bg-emerald-400/10', label: 'Approved' },
  assigned: { icon: UserCheck, className: 'text-emerald-400 bg-emerald-400/10', label: 'Assigned' },
  running: { icon: Play, className: 'text-[var(--sa-primary)] bg-[var(--sa-primary-soft)]', label: 'Running' },
  repairing: { icon: LifeBuoy, className: 'text-amber-400 bg-amber-400/10', label: 'Repairing' },
  succeeded: { icon: CheckCircle2, className: 'text-emerald-400 bg-emerald-400/10', label: 'Succeeded' },
  failed: { icon: XCircle, className: 'text-red-400 bg-red-500/10', label: 'Failed' },
  cancelled: { icon: Ban, className: 'text-[var(--sa-ink-muted)] bg-[var(--sa-surface)]', label: 'Cancelled' },
};

function formatWhen(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function ActivityPage() {
  const [stateFilter, setStateFilter] = useState<MissionState | 'all'>('all');
  // বাংলা (Wave 3 dedup): events/isLoading/loadError + load + useEffect ক্লাস্টারটি
  // এখন useListResource হুকে। state filter পেজ-লোকাল state — filter বদলালে
  // নিচের effect নতুন filter-সহ fresh fetcher দিয়ে reload করে (limit 50 অপরিবর্তিত)।
  const {
    items: events,
    isLoading,
    loadError,
    reload: loadEvents,
  } = useListResource<MissionActivity>({
    fetcher: async () =>
      (
        await activityService.listActivity({
          state: stateFilter === 'all' ? undefined : stateFilter,
          limit: 50,
        })
      ).items,
  });

  useEffect(() => {
    void loadEvents();
  }, [loadEvents, stateFilter]);

  return (
    <WorkspaceLayout>
      <div className="mx-auto w-full max-w-5xl px-5 py-8 text-[var(--sa-ink)] sm:px-8 lg:py-10">
        <header className="flex flex-col gap-4 border-b border-[var(--sa-border)] pb-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="sa-eyebrow">Build / Activity</p>
            <h1 className="mt-2 max-w-3xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
              See what changed.
            </h1>
            <p className="mt-2 max-w-2xl text-[var(--sa-ink-muted)]">
              A focused timeline of your missions — approvals, execution,
              repairs, and outcomes straight from the orchestration engine.
            </p>
          </div>
          <button
            type="button"
            data-testid="activity-refresh-btn"
            onClick={() => void loadEvents()}
            className="inline-flex items-center justify-center gap-2 rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-4 py-2.5 text-sm font-semibold transition hover:border-[var(--sa-primary)]"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        </header>

        {/* State filter chips */}
        <div
          className="mt-6 flex flex-wrap gap-2"
          role="group"
          aria-label="Filter by mission state"
        >
          <button
            type="button"
            data-testid="activity-filter-all"
            onClick={() => setStateFilter('all')}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
              stateFilter === 'all'
                ? 'bg-[var(--sa-primary)] text-white'
                : 'border border-[var(--sa-border)] text-[var(--sa-ink-muted)] hover:border-[var(--sa-primary)]'
            }`}
          >
            All
          </button>
          {MISSION_STATES.map((s) => (
            <button
              key={s}
              type="button"
              data-testid={`activity-filter-${s}`}
              onClick={() => setStateFilter(s)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition ${
                stateFilter === s
                  ? 'bg-[var(--sa-primary)] text-white'
                  : 'border border-[var(--sa-border)] text-[var(--sa-ink-muted)] hover:border-[var(--sa-primary)]'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Timeline */}
        <section className="mt-6" aria-label="Mission activity timeline">
          {isLoading ? (
            <div className="flex flex-col gap-4">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="sa-surface-raised h-24 animate-pulse rounded-[var(--sa-radius-sm)]"
                  aria-hidden="true"
                />
              ))}
            </div>
          ) : loadError ? (
            <div
              role="alert"
              data-testid="activity-error"
              className="flex flex-col gap-3 border border-red-500/40 bg-red-500/5 p-4 text-sm sm:flex-row sm:items-center"
            >
              <span className="text-red-400">{loadError}</span>
              <button
                type="button"
                onClick={() => void loadEvents()}
                className="rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] px-3 py-1.5 font-medium transition hover:border-[var(--sa-primary)] sm:ml-auto"
              >
                Try again
              </button>
            </div>
          ) : events.length === 0 ? (
            <div
              data-testid="activity-empty"
              className="sa-surface-raised flex flex-col items-center gap-2 p-10 text-center"
            >
              <CircleDot size={22} className="text-[var(--sa-primary)]" />
              <h2 className="text-lg font-semibold">No activity yet</h2>
              <p className="max-w-md text-sm text-[var(--sa-ink-muted)]">
                Missions you start will appear here as a live timeline of what
                changed and why.
              </p>
              <Link
                to="/workspace/live"
                className="mt-2 inline-flex items-center gap-2 rounded-[var(--sa-radius-sm)] bg-[var(--sa-primary)] px-4 py-2.5 text-sm font-semibold text-white transition hover:opacity-90"
              >
                Start a mission
              </Link>
            </div>
          ) : (
            <ol className="relative flex flex-col gap-4 border-l border-[var(--sa-border)] pl-6">
              {events.map((mission) => {
                const meta = STATE_META[mission.state] ?? STATE_META.planned;
                const Icon = meta.icon;
                const donePhases = mission.phases.filter(
                  (p) => p.status === 'done' || p.status === 'succeeded',
                ).length;
                return (
                  <li key={mission.id} className="relative" data-testid="activity-event">
                    <span
                      className={`absolute -left-[2.1rem] flex size-7 items-center justify-center rounded-full ${meta.className}`}
                      aria-hidden="true"
                    >
                      <Icon size={14} />
                    </span>
                    <div className="sa-surface-raised p-4 transition hover:border-[var(--sa-primary)]">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h2 className="text-sm font-semibold">{mission.title}</h2>
                        <span
                          data-testid={`activity-state-${mission.id}`}
                          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ${meta.className}`}
                        >
                          {meta.label}
                        </span>
                      </div>
                      {mission.failure_reason && (
                        <p className="mt-1.5 text-xs text-red-400">
                          Failure reason: {mission.failure_reason}
                        </p>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--sa-ink-muted)]">
                        <span data-testid="activity-when">{formatWhen(mission.updated_at)}</span>
                        {mission.phases.length > 0 && (
                          <span>
                            Phases: {mission.current_phase}/{mission.phases.length} (
                            {donePhases} done)
                          </span>
                        )}
                        {mission.repair_count > 0 && (
                          <span className="text-amber-400">
                            {mission.repair_count} repair
                            {mission.repair_count > 1 ? 's' : ''}
                          </span>
                        )}
                        <span>Priority {mission.priority}/9</span>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>
    </WorkspaceLayout>
  );
}

export default ActivityPage;
