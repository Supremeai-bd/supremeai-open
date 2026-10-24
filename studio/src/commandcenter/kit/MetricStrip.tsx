
// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Metric Strip
// বাংলা মন্তব্য: রিয়েল-টাইম KPI টিকার — বটম স্ট্যাটাস ডেকের জন্য
// ═══════════════════════════════════════════════════════════════════════════

export interface MetricItem {
  label: string;
  value: string | number | null;
  unit?: string;
  tone?: 'cyan' | 'emerald' | 'amber' | 'rose';
}

interface MetricStripProps {
  items: MetricItem[];
  loading?: boolean;
}

const TONE_TEXT: Record<string, string> = {
  cyan: 'text-[#00f3ff]',
  emerald: 'text-[#10b981]',
  amber: 'text-[#f59e0b]',
  rose: 'text-[#ef4444]',
};

export function MetricStrip({ items, loading }: MetricStripProps) {
  return (
    <div className="flex items-center gap-6 px-4 py-2 overflow-x-auto">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5 whitespace-nowrap">
          <span className="text-[9px] font-mono uppercase tracking-wider text-[var(--sa-text-2)]">
            {item.label}
          </span>
          {loading ? (
            <span className="h-3 w-10 animate-pulse rounded bg-[var(--sa-bg-3)]" />
          ) : (
            <span className={`text-xs font-mono font-bold ${TONE_TEXT[item.tone || 'cyan']}`}>
              {item.value ?? '—'}
              {item.unit && <span className="text-[9px] text-[var(--sa-text-2)] ml-0.5">{item.unit}</span>}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
