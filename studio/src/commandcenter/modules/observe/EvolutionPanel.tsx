import React from 'react';
import { useEvolutionMetrics } from '../../data/hooks';
import { EmptyState, KpiTile, StatusPill } from '../../kit';

/**
 * AETHEL — Evolution Observability (Self-Evolution Zero-Cost plan §20).
 *
 * Single autonomous-evolution dashboard: measured learning/telemetry counts,
 * cache effectiveness, cost estimate vs actual, provider performance, and the
 * AUTONOMOUS CHANGES lifecycle (proposed / promoted / rejected / rolled back).
 * Every number comes from the durable learning store — nothing fabricated.
 */
export function EvolutionPanel() {
  const { data, isLoading, isError } = useEvolutionMetrics(30_000);

  const unavailable = !data || data.available === false;

  if (isLoading) {
    return (
      <EmptyState
        title="ইভোলিউশন মেট্রিক্স লোড হচ্ছে..."
        message="লার্নিং স্টোর থেকে পরিমাপকৃত ডেটা আনা হচ্ছে..."
        loading
      />
    );
  }

  if (isError || unavailable) {
    return (
      <div className="space-y-4">
        <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">
          Evolution Observability
        </h2>
        <EmptyState
          title="লার্নিং স্টোর অপলব্ধ"
          message={
            data?.error
              ? `স্টোর পাওয়া যায়নি: ${data.error}`
              : 'লার্নিং ইভেন্ট স্টোর এখনো উপলব্ধ নয় — টেলিমেট্রি বাফার হচ্ছে, ডেটা আসা মাত্রই এখানে দেখা যাবে।'
          }
        />
      </div>
    );
  }

  const ac = data.autonomous_changes;
  const store = data.learning_store;
  const providers = data.providers_24h ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">
          Evolution Observability
        </h2>
        <StatusPill status={store?.db_ok ? 'healthy' : 'warning'} label={store?.db_ok ? 'store healthy' : 'degraded'} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiTile label="EVENTS/24H" value={data.learning_events_24h ?? 0} tone="cyan" />
        <KpiTile label="SUCCESS" value={data.successful_tasks ?? 0} tone="emerald" />
        <KpiTile label="FAILED" value={data.failed_tasks ?? 0} tone={data.failed_tasks ? 'rose' : 'emerald'} />
        <KpiTile
          label="CACHE HIT"
          value={data.cache_hit_rate_24h != null ? Math.round(data.cache_hit_rate_24h * 100) : null}
          unit="%"
          tone="violet"
        />
        <KpiTile label="FEEDBACK" value={data.feedback_events_24h ?? 0} tone="amber" />
        <KpiTile
          label="TOK EST ERR"
          value={data.token_estimation_error != null ? Math.round(data.token_estimation_error * 100) : null}
          unit="%"
          tone="cyan"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
            COST — ESTIMATED VS ACTUAL (24H)
          </div>
          <div className="grid grid-cols-2 gap-3">
            <KpiTile label="ESTIMATED" value={data.estimated_cost_24h ?? 0} unit="$" tone="cyan" />
            <KpiTile label="ACTUAL" value={data.actual_cost_24h ?? 0} unit="$" tone="emerald" />
          </div>
          <div className="mt-3 text-[10px] font-mono text-[var(--sa-text-2)]">
            buffer: {store?.queued ?? 0} queued · {store?.flushed ?? 0} flushed · {store?.dropped ?? 0} dropped
            {store?.last_flush_at ? ` · last flush ${new Date(store.last_flush_at).toLocaleTimeString()}` : ''}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
            AUTONOMOUS CHANGES
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiTile label="TOTAL" value={ac?.total_proposals ?? 0} tone="cyan" />
            <KpiTile label="PROMOTED" value={ac?.promoted ?? 0} tone="emerald" />
            <KpiTile label="REJECTED" value={ac?.rejected ?? 0} tone="amber" />
            <KpiTile label="ROLLED BACK" value={ac?.rolled_back ?? 0} tone="rose" />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(ac?.proposals_by_status ?? {}).map(([status, count]) => (
              <span
                key={status}
                className="rounded-md border border-[var(--sa-line)] px-2 py-1 text-[10px] font-mono text-[var(--sa-text-1)]"
              >
                {status}: {count}
              </span>
            ))}
            {!ac?.total_proposals && (
              <span className="text-[10px] font-mono text-[var(--sa-text-2)]">
                এখনো কোনো improvement proposal নেই — error-pattern/learning loop চালু হলে এখানে জমা হবে।
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
          PROVIDER PERFORMANCE (24H)
        </div>
        {providers.length === 0 ? (
          <div className="text-[10px] font-mono text-[var(--sa-text-2)]">
            ২৪ ঘণ্টায় কোনো provider metric জমা হয়নি।
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] font-mono">
              <thead>
                <tr className="text-[var(--sa-text-2)] uppercase tracking-widest text-[9px]">
                  <th className="py-2 pr-4">Provider</th>
                  <th className="py-2 pr-4">Model</th>
                  <th className="py-2 pr-4">Req</th>
                  <th className="py-2 pr-4">Success</th>
                  <th className="py-2 pr-4">429s</th>
                  <th className="py-2 pr-4">P95</th>
                  <th className="py-2 pr-4">Cost (est/act)</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((p, i) => (
                  <tr key={`${p.provider}-${p.model}-${i}`} className="border-t border-[var(--sa-line)]">
                    <td className="py-2 pr-4 text-[var(--sa-text-1)]">{p.provider ?? '—'}</td>
                    <td className="py-2 pr-4 text-[var(--sa-text-1)]">{p.model ?? '—'}</td>
                    <td className="py-2 pr-4">{p.requests ?? '—'}</td>
                    <td className="py-2 pr-4">{p.success_rate != null ? `${Math.round(p.success_rate * 100)}%` : '—'}</td>
                    <td className="py-2 pr-4">{p.rate_limited ?? 0}</td>
                    <td className="py-2 pr-4">{p.latency_p95_ms != null ? `${p.latency_p95_ms}ms` : '—'}</td>
                    <td className="py-2 pr-4">
                      {p.estimated_cost ?? 0} / {p.actual_cost ?? 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default EvolutionPanel;
