import { useEffect, useState } from 'react';
import { Search, Shield, Clock, User, Zap } from 'lucide-react';
import { useCommandCenterStore } from '../state/useCommandCenterStore';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Global Command Bar (Top)
// বাংলা মন্তব্য: সিস্টেম পালস, এনভি ব্যাজ, ⌘K প্যালেট, লাইভ ক্লক, অ্যাডমিন আইডেন্টিটি
// ═══════════════════════════════════════════════════════════════════════════

interface CommandBarProps {
  healthPercent?: number | null;
  env?: string;
  version?: string;
  adminName?: string;
  adminRole?: string;
  // Optional extra hook for consumers; the palette itself is now driven by
  // the store's isPaletteOpen + <CommandPalette /> (⌘K works globally).
  onOpenPalette?: () => void;
}

export function CommandBar({
  healthPercent,
  env = 'PROD',
  version,
  adminName = 'God',
  adminRole = 'god',
  onOpenPalette,
}: CommandBarProps) {
  const { wsStatus, setPaletteOpen } = useCommandCenterStore();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    // ROOT-CAUSE FIX (#2736): was 1000ms (1s) — caused full panel re-render
    // every second. 30s is sufficient for a clock display.
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const healthColor = healthPercent === null || healthPercent === undefined
    ? 'bg-[#94a3b8]'
    : healthPercent >= 90
      ? 'bg-[#10b981] shadow-[0_0_8px_rgba(16,185,129,0.5)]'
      : healthPercent >= 70
        ? 'bg-[#f59e0b] shadow-[0_0_8px_rgba(245,158,11,0.5)]'
        : 'bg-[#ef4444] shadow-[0_0_8px_rgba(239,68,68,0.5)]';

  const wsColor = wsStatus === 'open'
    ? 'bg-[#10b981]'
    : wsStatus === 'connecting'
      ? 'bg-[#f59e0b] animate-pulse'
      : 'bg-[#ef4444]';

  return (
    <header className="flex items-center gap-4 px-4 h-12 border-b border-[var(--sa-line)] bg-[var(--sa-bg-1)]">
      {/* Brand & System Pulse */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold tracking-wider font-mono text-[var(--sa-text-0)]">কমান্ড সেন্টার</span>
        <span className={`h-2.5 w-2.5 rounded-full ${healthColor}`} />
        <span className="text-[10px] font-mono font-bold text-[var(--sa-text-0)]">
          {healthPercent !== null && healthPercent !== undefined ? `${healthPercent}%` : '—'}
        </span>
      </div>

      {/* Env Badge */}
      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded border border-[#00f3ff]/30 bg-[#00f3ff]/5">
        <Zap size={10} className="text-[#00f3ff]" />
        <span className="text-[9px] font-mono font-bold text-[#00f3ff]">ENV:{env}</span>
        {version && <span className="text-[8px] font-mono text-[var(--sa-text-2)]">v{version}</span>}
      </div>

      {/* Command Palette Trigger */}
      <button
        onClick={() => {
          setPaletteOpen(true);
          onOpenPalette?.();
        }}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--sa-line)] hover:border-[#00f3ff]/40 transition-colors"
      >
        <Search size={12} className="text-[var(--sa-text-1)]" />
        <span className="text-[10px] font-mono text-[var(--sa-text-2)]">কমান্ড খুঁজুন...</span>
        <span className="text-[8px] font-mono px-1 py-0.5 rounded bg-[var(--sa-bg-2)] text-[var(--sa-text-2)]">⌘K</span>
      </button>

      <div className="flex-1" />

      {/* Live Clock */}
      <div className="flex items-center gap-1.5">
        <Clock size={12} className="text-[var(--sa-text-1)]" />
        <span className="text-xs font-mono text-[var(--sa-text-0)]">
          {now.toLocaleTimeString('bn-BD', { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      {/* WS Status */}
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${wsColor}`} />
        <span className="text-[9px] font-mono uppercase text-[var(--sa-text-2)]">WS</span>
      </div>

      {/* Admin Identity */}
      <div className="flex items-center gap-2 px-2 py-1 rounded-lg border border-[var(--sa-line)]">
        <User size={12} className="text-[#bc13fe]" />
        <span className="text-[10px] font-mono text-[var(--sa-text-0)]">{adminName}</span>
        <span className="text-[8px] font-mono uppercase px-1 py-0.5 rounded bg-[#bc13fe]/10 text-[#bc13fe]">
          {adminRole}
        </span>
      </div>

      {/* JIT OTP Button */}
      <button className="flex items-center gap-1 px-2 py-1 rounded-lg border border-[#bc13fe]/30 text-[#bc13fe] hover:bg-[#bc13fe]/10 transition-colors">
        <Shield size={12} />
        <span className="text-[9px] font-mono">JIT 🔐</span>
      </button>
    </header>
  );
}
