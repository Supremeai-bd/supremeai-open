import React from 'react';
import { MetricStrip, type MetricItem } from '../kit';
import { useCommandCenterStore } from '../state/useCommandCenterStore';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Bottom Status Deck
// বাংলা মন্তব্য: রিয়েল-টাইম KPI টিকার — RPS · P95 · ERR% · COST/HR · WS · LAST SYNC
// ═══════════════════════════════════════════════════════════════════════════

interface BottomDeckProps {
  metrics?: {
    requests_per_second?: number;
    latency_p95_ms?: number;
    error_rate?: number;
    cost_per_hour?: number;
    active_agents?: number;
  } | null;
  loading?: boolean;
}

export function BottomDeck({ metrics, loading }: BottomDeckProps) {
  const { wsStatus, lastSyncAt } = useCommandCenterStore();

  const items: MetricItem[] = [
    { label: 'RPS', value: metrics?.requests_per_second ?? null, tone: 'cyan' },
    { label: 'P95', value: metrics?.latency_p95_ms ?? null, unit: 'ms', tone: 'cyan' },
    { label: 'ERR%', value: metrics?.error_rate ?? null, tone: metrics?.error_rate && metrics.error_rate > 5 ? 'rose' : 'emerald' },
    { label: 'AGENTS', value: metrics?.active_agents ?? null, tone: 'cyan' },
    { label: 'COST/HR', value: metrics?.cost_per_hour ?? null, unit: '$', tone: 'amber' },
  ];

  const wsLabel = wsStatus === 'open' ? '●' : wsStatus === 'connecting' ? '◐' : '○';
  const wsColor = wsStatus === 'open' ? 'text-[#10b981]' : wsStatus === 'connecting' ? 'text-[#f59e0b]' : 'text-[#ef4444]';

  // বাংলা মন্তব্য: Date.now() ইমপিওর কল রেন্ডার বডি থেকে সরিয়ে useEffect-এ নেওয়া হলো।
  const [lastSync, setLastSync] = React.useState('—');
  React.useEffect(() => {
    if (!lastSyncAt) {
      setLastSync('—');
      return;
    }
    const diff = Math.max(0, Math.round((Date.now() - lastSyncAt) / 1000));
    setLastSync(`${diff}s`);
  }, [lastSyncAt]);

  return (
    <footer className="flex items-center justify-between h-9 border-t border-[var(--sa-line)] bg-[var(--sa-bg-1)]">
      <MetricStrip items={items} loading={loading} />
      <div className="flex items-center gap-4 px-4">
        <span className={`text-[10px] font-mono ${wsColor}`}>
          WS {wsLabel}
        </span>
        <span className="text-[9px] font-mono text-[var(--sa-text-2)]">
          LAST SYNC <span className="text-[var(--sa-text-1)]">{lastSync}</span>
        </span>
      </div>
    </footer>
  );
}
