import type { HealthNode } from '../data/types';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Health Strip
// বাংলা মন্তব্য: ইনফ্রা হেলথ স্ট্যাটাস স্ট্রিপ — GCP/Railway/Render + core services
// ═══════════════════════════════════════════════════════════════════════════

interface HealthStripProps {
  nodes: Record<string, HealthNode>;
  loading?: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  healthy: 'bg-[#10b981] shadow-[0_0_8px_rgba(16,185,129,0.5)]',
  degraded: 'bg-[#f59e0b] shadow-[0_0_8px_rgba(245,158,11,0.5)]',
  down: 'bg-[#ef4444] shadow-[0_0_8px_rgba(239,68,68,0.5)]',
  unknown: 'bg-[#94a3b8]',
};

export function HealthStrip({ nodes, loading }: HealthStripProps) {
  if (loading) {
    return (
      <div className="flex gap-3 p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)]">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-8 w-24 animate-pulse rounded bg-[var(--sa-bg-3)]" />
        ))}
      </div>
    );
  }

  const entries = Object.entries(nodes || {});

  if (entries.length === 0) {
    return (
      <div className="p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] text-xs font-mono text-[var(--sa-text-1)]">
        কোনো হেলথ ডেটা নেই · NO HEALTH DATA
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-3 p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)]">
      {entries.map(([name, node]) => (
        <div key={name} className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--sa-bg-2)]">
          <span className={`h-2 w-2 rounded-full ${STATUS_COLOR[node.status] || STATUS_COLOR.unknown}`} />
          <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--sa-text-0)]">{name}</span>
          {node.latency !== undefined && (
            <span className="text-[9px] font-mono text-[var(--sa-text-1)]">{node.latency}ms</span>
          )}
        </div>
      ))}
    </div>
  );
}
