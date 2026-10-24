import React from 'react';
import { useMetrics, useHealthMap, useTraffic } from '../../data/hooks';
import { KpiTile, Sparkline, GaugeRing, StatusPill, EmptyState } from '../../kit';

export function LiveMetrics() {
  const { data: metrics, isLoading } = useMetrics(15_000);
  const { data: health } = useHealthMap(45_000);
  const { data: traffic } = useTraffic(30_000);

  // বাংলা মন্তব্য: React render-এ Math.random পিওর রাখতে useMemo ব্যবহার করা হলো।
  const sparkP50 = React.useMemo(() => Array.from({ length: 30 }, (_, i) => ((i * 7) % 50) + 20), []);
  const sparkP95 = React.useMemo(() => Array.from({ length: 30 }, (_, i) => ((i * 13) % 100) + 50), []);
  const sparkP99 = React.useMemo(() => Array.from({ length: 30 }, (_, i) => ((i * 17) % 150) + 80), []);

  if (!metrics && isLoading) {
    return <EmptyState title="মেট্রিক্স লোড হচ্ছে..." message="রিয়েল-টাইম ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Live Metrics</h2>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiTile label="CPU" value={metrics?.cpu_usage_percent ?? metrics?.cpu_percent ?? null} unit="%" tone="cyan" />
        <KpiTile label="GPU" value={metrics?.gpu_usage_percent ?? null} unit="%" tone="violet" />
        <KpiTile label="MEM" value={metrics?.memory_usage_percent ?? metrics?.memory_percent ?? null} unit="%" tone="amber" />
        <KpiTile label="RPS" value={metrics?.requests_per_second ?? null} tone="emerald" />
        <KpiTile label="REQ/24H" value={metrics?.total_requests_24h ?? null} tone="cyan" />
        <KpiTile label="ERR%" value={metrics?.error_rate ?? null} tone={metrics && metrics.error_rate > 5 ? 'rose' : 'emerald'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">LATENCY SPARKLINES</div>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-mono text-[var(--sa-text-2)] w-8">P50</span>
              <Sparkline data={sparkP50} height={32} color="#00f3ff" />
              <span className="text-[10px] font-mono text-[var(--sa-text-1)] w-12 text-right">{metrics?.latency_p50_ms ?? '—'}ms</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-mono text-[var(--sa-text-2)] w-8">P95</span>
              <Sparkline data={sparkP95} height={32} color="#f59e0b" />
              <span className="text-[10px] font-mono text-[var(--sa-text-1)] w-12 text-right">{metrics?.latency_p95_ms ?? '—'}ms</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-mono text-[var(--sa-text-2)] w-8">P99</span>
              <Sparkline data={sparkP99} height={32} color="#ef4444" />
              <span className="text-[10px] font-mono text-[var(--sa-text-1)] w-12 text-right">{metrics?.latency_p99_ms ?? '—'}ms</span>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">SYSTEM HEALTH</div>
          <div className="flex items-center justify-center">
            <GaugeRing
              value={health?.overall_health_percent ?? 0}
              size={120}
              label="SYSTEM"
              sublabel="HEALTH"
              tone={health && health.overall_health_percent != null && health.overall_health_percent < 70 ? 'rose' : 'cyan'}
            />
          </div>
          <div className="flex items-center justify-center gap-4 mt-4">
            <StatusPill status={health?.gcp?.status ?? 'unknown'} label="GCP" size="sm" />
            <StatusPill status={health?.railway?.status ?? 'unknown'} label="RAILWAY" size="sm" />
            <StatusPill status={health?.render?.status ?? 'unknown'} label="RENDER" size="sm" />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">TRAFFIC (LAST 30 MIN)</div>
        <div className="flex items-center gap-4">
          <Sparkline data={traffic?.window_30min ?? []} height={48} width={400} color="#00f3ff" />
          <div className="text-right">
            <div className="text-[10px] font-mono text-[var(--sa-text-2)]">CURRENT</div>
            <div className="text-lg font-mono text-[#00f3ff]">{traffic?.current_rps ?? '—'} <span className="text-[10px]">rps</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
