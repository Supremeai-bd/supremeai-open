import type { DashboardEvent } from '../data/types';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Event Timeline
// বাংলা মন্তব্য: ইভেন্ট টাইমলাইন — রঙ-কোডেড severity সহ
// ═══════════════════════════════════════════════════════════════════════════

interface TimelineProps {
  events: DashboardEvent[];
  loading?: boolean;
  limit?: number;
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'bg-[#ef4444] shadow-[0_0_8px_rgba(239,68,68,0.5)]',
  high: 'bg-[#f59e0b] shadow-[0_0_8px_rgba(245,158,11,0.5)]',
  medium: 'bg-[#6366f1] shadow-[0_0_8px_rgba(99,102,241,0.5)]',
  low: 'bg-[#00f3ff] shadow-[0_0_8px_rgba(0,243,255,0.5)]',
  info: 'bg-[#94a3b8]',
};

export function Timeline({ events, loading, limit = 20 }: TimelineProps) {
  if (loading) {
    return (
      <div className="space-y-2 p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)]">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-6 animate-pulse rounded bg-[var(--sa-bg-3)]" />
        ))}
      </div>
    );
  }

  const items = (events || []).slice(0, limit);

  if (items.length === 0) {
    return (
      <div className="p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] text-xs font-mono text-[var(--sa-text-1)]">
        কোনো ইভেন্ট নেই · NO EVENTS
      </div>
    );
  }

  return (
    <div className="p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)]">
      <div className="relative space-y-3">
        {items.map((event, idx) => (
          <div key={idx} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className={`h-2 w-2 rounded-full mt-1.5 ${SEVERITY_COLOR[event.level] || SEVERITY_COLOR.info}`} />
              {idx < items.length - 1 && <span className="w-px flex-1 bg-[var(--sa-line)]" />}
            </div>
            <div className="flex-1 pb-1">
              <div className="flex items-center gap-2">
                <span className="text-[9px] font-mono text-[var(--sa-text-1)]">
                  {new Date(event.timestamp).toLocaleTimeString('bn-BD')}
                </span>
                <span className="text-[9px] font-mono uppercase text-[var(--sa-text-2)]">{event.source}</span>
              </div>
              <p className="text-xs font-mono text-[var(--sa-text-0)] mt-0.5">{event.message}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
