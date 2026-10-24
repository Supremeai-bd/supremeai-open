import type { LucideIcon } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — KPI Tile
// বাংলা মন্তব্য: একটি KPI কার্ড — লোডিং/ডিগ্রেডেড স্টেট সহ
// ═══════════════════════════════════════════════════════════════════════════

interface KpiTileProps {
  label: string;
  value: string | number | null;
  unit?: string;
  icon?: LucideIcon;
  tone?: 'cyan' | 'violet' | 'emerald' | 'amber' | 'rose' | 'indigo';
  loading?: boolean;
  hint?: string;
  onClick?: () => void;
}

const TONE_MAP: Record<string, { text: string; glow: string; border: string; bg: string }> = {
  cyan:    { text: 'text-[#00f3ff]',    glow: 'drop-shadow-[0_0_8px_rgba(0,243,255,0.5)]',    border: 'border-[#00f3ff]/20',    bg: 'bg-[#00f3ff]/5' },
  violet:  { text: 'text-[#bc13fe]',    glow: 'drop-shadow-[0_0_8px_rgba(188,19,254,0.5)]', border: 'border-[#bc13fe]/20',    bg: 'bg-[#bc13fe]/5' },
  emerald: { text: 'text-[#10b981]',    glow: 'drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]', border: 'border-[#10b981]/20',    bg: 'bg-[#10b981]/5' },
  amber:   { text: 'text-[#f59e0b]',    glow: 'drop-shadow-[0_0_8px_rgba(245,158,11,0.5)]', border: 'border-[#f59e0b]/20',    bg: 'bg-[#f59e0b]/5' },
  rose:    { text: 'text-[#ef4444]',    glow: 'drop-shadow-[0_0_8px_rgba(239,68,68,0.5)]',  border: 'border-[#ef4444]/20',    bg: 'bg-[#ef4444]/5' },
  indigo:  { text: 'text-[#6366f1]',    glow: 'drop-shadow-[0_0_8px_rgba(99,102,241,0.5)]', border: 'border-[#6366f1]/20',    bg: 'bg-[#6366f1]/5' },
};

export function KpiTile({ label, value, unit, icon: Icon, tone = 'cyan', loading, hint, onClick }: KpiTileProps) {
  const t = TONE_MAP[tone] || TONE_MAP.cyan;

  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`relative flex flex-col justify-between p-4 rounded-xl border ${t.border} ${t.bg} ${t.glow} transition-all duration-300 ${onClick ? 'hover:scale-[1.02] cursor-pointer hover:bg-[var(--sa-bg-active)]' : 'cursor-default'} min-w-[140px] min-h-[90px]`}
    >
      <div className="flex items-center justify-between w-full">
        <span className="text-[9px] uppercase tracking-widest text-[var(--sa-text-1)] font-bold font-mono">
          {label}
        </span>
        {Icon && <Icon size={14} className={`${t.text} opacity-80`} />}
      </div>

      <div className="flex items-baseline gap-1 mt-2">
        {loading ? (
          <div className="h-6 w-16 animate-pulse rounded bg-[var(--sa-bg-3)]" />
        ) : (
          <>
            <span className={`text-2xl font-bold font-mono ${t.text} ${t.glow}`}>
              {value ?? '—'}
            </span>
            {unit && <span className="text-[10px] text-[var(--sa-text-2)] font-mono">{unit}</span>}
          </>
        )}
      </div>

      {hint && <span className="text-[8px] text-[var(--sa-text-2)] font-mono mt-1">{hint}</span>}
    </button>
  );
}
