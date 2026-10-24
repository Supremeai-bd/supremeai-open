import React from 'react';
import { Activity, ShieldAlert, GitMerge, ServerCog, DollarSign, BrainCircuit, CheckCircle, ArrowUpRight, Zap, Database } from 'lucide-react';
import { useMetrics, useThreatScan, useCIReports, useDashboardEvents } from '../../hooks/useDashboardData';

// WO5: Pure inline SVG Sparkline (zero external charting dependencies)
const Sparkline = ({ points, color = '#a855f7' }: { points: number[]; color?: string }) => {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points) || 1;
  const range = max - min || 1;
  const height = 24;
  const width = 80;
  const coords = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((p - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden="true">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={coords}
      />
    </svg>
  );
};

export default function Dashboard({ costReport }: { costReport?: string }) {
  const { data: metrics } = useMetrics();
  const { data: threats } = useThreatScan();
  const { data: ciReports } = useCIReports();
  const { data: events } = useDashboardEvents(5);

  const dashRps = metrics?.requests_per_second ?? 0;
  // FIX(audit 2026-10-24): no fabricated CPU derived from RPS — honest N/R when unreported
  const safeCpu: number | null = metrics?.cpu_percent ?? metrics?.cpu_usage_percent ?? null;
  const activeIncidents = threats?.findings?.filter(t => t.severity === 'high' || t.severity === 'critical') || [];
  const activeDeployments = ciReports?.filter(c => c.status === 'running') || [];

  // WO5: Bind real availability figure (or honest not-reported state)
  const availability = (metrics as unknown as { availability_percent?: number; uptime_percent?: number })?.availability_percent ??
    (metrics as unknown as { availability_percent?: number; uptime_percent?: number })?.uptime_percent ?? null;

  // Latency & requests sparkline points from metrics history (fallback to active reading)
  // FIX(audit 2026-10-24): no fake sparkline trend fallbacks — render only with real history
  const latencyPoints = (metrics as unknown as { latency_history?: number[] })?.latency_history ?? null;
  const rpsPoints = (metrics as unknown as { rps_history?: number[] })?.rps_history ?? null;

  return (
    <div className="flex-1 flex flex-col min-h-screen bg-surface-0 overflow-y-auto">
      <div className="p-8 max-w-7xl mx-auto w-full space-y-8">
        
        {/* Header */}
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-bold text-text tracking-tight flex items-center gap-3">
            Command Center <span className="text-sm font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">System Online</span>
          </h1>
          <p className="text-secondary text-sm">Real-time platform overview & operational health.</p>
        </div>

        {/* Top KPI Grid (Platform Health) */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div data-testid="admin-kpi" className="surface-1 rounded-xl p-5 border border-border flex flex-col gap-4">
            <div className="flex justify-between items-start">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
                <Activity size={14} className="text-accent-primary" /> Availability
              </span>
              <span className={`font-mono text-xs ${availability != null ? 'text-emerald-400' : 'text-muted'}`}>
                {availability != null ? `${availability >= 99 ? 'Healthy' : 'Degraded'}` : 'not reported'}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <div className="text-3xl font-bold text-text font-mono">
                {availability != null ? `${availability}%` : 'N/R'}
              </div>
            </div>
          </div>
          
          <div data-testid="admin-kpi" className="surface-1 rounded-xl p-5 border border-border flex flex-col gap-4">
            <div className="flex justify-between items-start">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
                <Zap size={14} className="text-amber-400" /> Latency (p95)
              </span>
              {latencyPoints ? <Sparkline points={latencyPoints} color="#f59e0b" /> : null}
            </div>
            <div className="text-3xl font-bold text-text font-mono">
              {metrics?.latency_p95_ms != null ? metrics.latency_p95_ms : '—'}
              {metrics?.latency_p95_ms != null && <span className="text-lg text-secondary">ms</span>}
            </div>
          </div>

          <div
            data-testid="admin-kpi"
            className={`surface-1 rounded-xl p-5 border flex flex-col gap-4 transition duration-300 ${
              activeIncidents.length > 0
                ? 'border-rose-500/50 shadow-[0_0_15px_rgba(244,63,94,0.25)] animate-pulse'
                : 'border-border'
            }`}
          >
            <div className="flex justify-between items-start">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
                <ShieldAlert size={14} className={activeIncidents.length > 0 ? "text-rose-400" : "text-emerald-400"} /> Incidents
              </span>
              <span className={`font-mono text-xs ${activeIncidents.length > 0 ? 'text-rose-400 font-semibold' : 'text-muted'}`}>
                {activeIncidents.length > 0 ? 'Urgent' : 'Active'}
              </span>
            </div>
            <div className="text-3xl font-bold text-text font-mono">
              {activeIncidents.length}
              {activeIncidents.length === 0 && <CheckCircle size={20} className="inline-block ml-2 text-emerald-500 mb-1" />}
            </div>
          </div>

          <div data-testid="admin-kpi" className="surface-1 rounded-xl p-5 border border-border flex flex-col gap-4">
            <div className="flex justify-between items-start">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
                <GitMerge size={14} className="text-indigo-400" /> Deployments
              </span>
              {rpsPoints ? <Sparkline points={rpsPoints} color="#818cf8" /> : null}
            </div>
            <div className="text-3xl font-bold text-text font-mono">{activeDeployments.length}</div>
          </div>
        </div>

        {/* Urgent Incidents Banner when active */}
        {activeIncidents.length > 0 && (
          <div className="surface-1 rounded-xl border border-rose-500/40 p-4 bg-rose-500/10 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ShieldAlert className="text-rose-500 animate-pulse" size={20} />
              <div>
                <p className="text-sm font-semibold text-rose-400">
                  {activeIncidents.length} Urgent Security Incident{activeIncidents.length > 1 ? 's' : ''} Detected
                </p>
                <p className="text-xs text-secondary mt-0.5">
                  High or critical severity findings requiring operational attention.
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Context Area */}
          <div className="lg:col-span-2 space-y-6">
            
            {/* System Resources & Infrastructure */}
            <div className="surface-1 rounded-xl border border-border p-6">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted mb-6 flex items-center gap-2">
                <ServerCog size={16} /> Resource Consumption
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-secondary">Global CPU Load</span>
                    <span className="font-mono text-text">{safeCpu != null ? `${safeCpu}%` : 'N/R'}</span>
                  </div>
                  <div className="w-full h-2 rounded-full surface-2 overflow-hidden">
                    {safeCpu != null ? <div className={`h-full ${safeCpu > 80 ? 'bg-rose-500' : 'bg-accent-primary'}`} style={{ width: `${safeCpu}%` }}></div> : null}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-secondary">Active Agents</span>
                    <span className="font-mono text-text">{metrics?.active_agents ?? '—'}</span>
                  </div>
                  <div className="w-full h-2 rounded-full surface-2 overflow-hidden">
                    {metrics?.active_agents != null ? <div className="h-full bg-emerald-500" style={{ width: `${Math.min(100, metrics.active_agents)}%` }}></div> : null}
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Changes / Audit */}
            <div className="surface-1 rounded-xl border border-border p-6">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted mb-6">What Changed Recently</h2>
              <div className="space-y-4">
                {events && events.length > 0 ? (
                  events.map((e, idx) => (
                    <div key={idx} className="flex items-start gap-4 p-3 rounded-lg surface-2 border border-border">
                      <div className="mt-0.5"><Activity size={16} className="text-secondary" /></div>
                      <div>
                        <p className="text-sm text-text font-medium">{e.message || e.source}</p>
                        <p className="text-xs text-secondary mt-1 font-mono">{new Date(e.timestamp).toLocaleTimeString()}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-6 text-sm text-secondary font-mono border border-dashed border-border rounded-lg">
                    No recent changes detected in the platform.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right Sidebar Area */}
          <div className="space-y-6">
            
            {/* Cost & FinOps */}
            <div className="surface-1 rounded-xl border border-border p-6">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
                  <DollarSign size={16} /> Cost Center
                </h2>
                <ArrowUpRight size={14} className="text-accent-primary" />
              </div>
              <div className="space-y-4">
                {/* FIX(audit 2026-10-24): the previous $42.50 / $128.00 / $170.50 figures were
                    hardcoded fabrications. Honest "not reported" until the cost report binds. */}
                {/* FIX(cost-bind 2026-10-24): the /admin-api/costs report string now
                    binds here via SubTabContent {...props}; until it exists the
                    rows stay honest "not reported". */}
                {costReport ? (
                  <pre className="whitespace-pre-wrap break-words rounded-lg border border-border bg-[var(--bg-main)] p-3 font-mono text-xs text-secondary max-h-40 overflow-y-auto">{costReport}</pre>
                ) : (
                  <>
                    <div className="flex justify-between items-center pb-4 border-b border-border">
                      <span className="text-secondary text-sm">LLM API Usage</span>
                      <span className="text-muted font-mono text-xs">not reported</span>
                    </div>
                    <div className="flex justify-between items-center pb-4 border-b border-border">
                      <span className="text-secondary text-sm">Compute Instances</span>
                      <span className="text-muted font-mono text-xs">not reported</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-text font-semibold">Total MTD</span>
                      <span className="text-muted font-mono text-xs">not reported</span>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Active Agents (What is consuming resources) */}
            <div className="surface-1 rounded-xl border border-border p-6">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted mb-6 flex items-center gap-2">
                <BrainCircuit size={16} /> Active Agents
              </h2>
              {/* FIX(audit 2026-10-24): the previous list (CI/CD Watcher / Infra Autoscaler /
                  Security Scanner) was fully hardcoded — fabricated status. Now binds the real
                  active_agents metric when present, honest empty state otherwise. */}
              <div className="space-y-4">
                {metrics?.active_agents != null ? (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-text flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                      Active agent processes
                    </span>
                    <span className="text-xs font-mono text-emerald-400">{metrics.active_agents}</span>
                  </div>
                ) : (
                  <div className="text-center py-4 text-xs text-secondary font-mono border border-dashed border-border rounded-lg">
                    No live agent telemetry reported.
                  </div>
                )}
              </div>
            </div>

            {/* Redis Quota & Failover State (WO5) */}
            <div className="surface-1 rounded-xl border border-border p-6" data-testid="redis-quota-card">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-muted flex items-center gap-2">
                  <Database size={16} className="text-amber-400" /> Redis Quota
                </h2>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  Chain Active
                </span>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between text-xs font-mono">
                  <span className="text-secondary">Commands</span>
                  <span className="text-text">
                    {(metrics as unknown as { redis_commands?: number })?.redis_commands != null
                      ? `${(metrics as unknown as { redis_commands?: number }).redis_commands} / 500k`
                      : 'not reported'}
                  </span>
                </div>
                <div className="w-full h-2 rounded-full surface-2 overflow-hidden">
                  <div
                    className="h-full bg-amber-500"
                    style={{ width: `${Math.min(100, Math.round((((metrics as unknown as { redis_commands?: number })?.redis_commands ?? 0) / 500000) * 100))}%` }}
                  />
                </div>
                <p className="text-[11px] text-secondary">
                  Auto-rotation active across multi-account failover chain.
                </p>
              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  );
};
