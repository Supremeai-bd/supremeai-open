import { useState } from 'react';
import { useThreatScan, useSecurityFindings } from '../../data/hooks';
import { useSecurityRescan } from '../../data/hooks';
import { StatusPill, EmptyState } from '../../kit';
import type { SecurityFinding, ThreatScanResult } from '../../data/types';

export function Threats() {
  const { data: scan, isLoading } = useThreatScan(30_000);
  const { data: findings } = useSecurityFindings();
  const rescan = useSecurityRescan();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const severityCount = (sev: SecurityFinding['severity']) =>
    (findings ?? []).filter((f) => f.severity === sev).length;

  if (!scan && isLoading) {
    return <EmptyState title="সিকিউরিটি স্ক্যান লোড হচ্ছে..." message="স্ক্যান রেজাল্ট ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Security Threats</h2>
        <button
          onClick={() => rescan.mutate({})}
          className="px-3 py-1.5 rounded-lg border border-[#f59e0b]/30 text-[#f59e0b] text-[9px] font-mono hover:bg-[#f59e0b]/10 transition-colors"
        >
          RE-SCAN
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-3 text-center">
          <div className="text-lg font-mono text-[var(--sa-text-0)]">{(scan as ThreatScanResult | undefined)?.total_findings ?? 0}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Total</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-3 text-center">
          <div className="text-lg font-mono text-[#ef4444]">{severityCount('critical')}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Critical</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-3 text-center">
          <div className="text-lg font-mono text-[#f59e0b]">{severityCount('high')}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">High</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-3 text-center">
          <div className="text-lg font-mono text-[#facc15]">{severityCount('medium') + severityCount('low')}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Med/Low</div>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] overflow-hidden">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] p-3 border-b border-[var(--sa-line)]">Findings</div>
        <div className="divide-y divide-[var(--sa-line)]">
          {(findings ?? []).map((finding) => (
            <div key={finding.id}>
              <div
                className="flex items-center justify-between p-3 cursor-pointer hover:bg-[var(--sa-bg-active)]"
                onClick={() => setExpandedId(expandedId === finding.id ? null : finding.id)}
              >
                <div className="flex items-center gap-2">
                  <StatusPill status={finding.severity === 'critical' ? 'down' : finding.severity === 'high' ? 'degraded' : 'healthy'} label={finding.severity.toUpperCase()} size="sm" />
                  <span className="text-[10px] font-mono text-[var(--sa-text-1)]">{finding.title}</span>
                </div>
                <span className="text-[9px] font-mono text-[var(--sa-text-3)]">{expandedId === finding.id ? '▲' : '▼'}</span>
              </div>
              {expandedId === finding.id && (
                <div className="px-3 pb-3 text-[10px] font-mono text-[var(--sa-text-2)] bg-[var(--sa-bg-0)]">
                  {finding.description}
                </div>
              )}
            </div>
          ))}
          {(findings ?? []).length === 0 && (
            <div className="p-4 text-center text-[var(--sa-text-2)] text-[10px] font-mono">কোন ফাইন্ডিং নেই</div>
          )}
        </div>
      </div>
    </div>
  );
}
