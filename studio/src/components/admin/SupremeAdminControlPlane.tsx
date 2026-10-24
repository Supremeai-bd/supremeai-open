import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, CheckCircle2, Command, Cpu, GitMerge, HeartPulse, LockKeyhole, MessageSquare, Network, Send, ShieldCheck, Sparkles } from 'lucide-react';
import { useMetrics, useThreatScan, useCIReports } from '../../hooks/useDashboardData';
import { ApprovalQueue } from '../../commandcenter/modules/secure/ApprovalQueue';
import { AdminAlertsTab } from './AdminAlertsTab';

interface HealthRecord { status?: string; latency?: string | number; region?: string; [key: string]: unknown }
interface AdminControlPlaneProps {
  healthMap?: Record<string, HealthRecord>;
  adminMessages?: Array<{ id: string; role?: string; content?: string; timestamp?: number }>;
  loading?: boolean;
  adminInput?: string;
  setAdminInput?: (value: string) => void;
  handleSendAdmin?: () => void;
  handleTriggerDeploy?: () => void;
  actionStatus?: string;
  setAdminSubTab?: (tab: string) => void;
}

const tone = (status?: string) => {
  const value = (status || 'unknown').toLowerCase();
  if (['healthy', 'operational', 'online', 'ok', 'ready'].includes(value)) return 'text-emerald-300 border-emerald-400/20 bg-emerald-400/5';
  if (['degraded', 'warning', 'partial'].includes(value)) return 'text-amber-300 border-amber-400/20 bg-amber-400/5';
  if (['down', 'offline', 'error', 'critical'].includes(value)) return 'text-rose-300 border-rose-400/20 bg-rose-400/5';
  return 'text-slate-400 border-[var(--sa-border)] bg-black/10';
};

export default function SupremeAdminControlPlane({ healthMap = {}, adminMessages = [], loading = false, adminInput = '', setAdminInput, handleSendAdmin, handleTriggerDeploy, actionStatus, setAdminSubTab }: AdminControlPlaneProps) {
  const { data: metrics } = useMetrics();
  const { data: threats } = useThreatScan();
  const { data: ciReports } = useCIReports();
  const activeIncidents = threats?.findings?.filter((item) => item.severity === 'high' || item.severity === 'critical') || [];
  const runningDeployments = ciReports?.filter((item) => item.status === 'running') || [];
  const serviceEntries = Object.entries(healthMap);
  const [freshness, setFreshness] = useState<string>(new Date().toISOString());
  useEffect(() => { setFreshness(new Date().toISOString()); }, [healthMap, metrics, threats, ciReports]);
  const open = (tab: string) => setAdminSubTab?.(tab);
  const requestPermission = () => setAdminInput?.('Request permission for: ');
  const run = (cmd: string) => setAdminInput?.(cmd);

  return <div className="min-h-full bg-[var(--sa-canvas)] px-5 py-6 sm:px-8 lg:px-10"><div className="mx-auto max-w-[1600px] space-y-5"><header className="flex flex-col justify-between gap-4 rounded-2xl border border-cyan-400/20 bg-[radial-gradient(circle_at_78%_0%,rgba(34,211,238,0.12),transparent_42%),var(--sa-surface)] p-5 sm:p-7 lg:flex-row lg:items-end"><div><div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300"><Sparkles size={14} /> Supreme system control plane</div><h1 className="text-3xl font-semibold tracking-tight text-[var(--sa-ink)] sm:text-4xl">Super Admin Dashboard</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--sa-ink-muted)]">Command the system, review requested work, approve or reject safely, and inspect the whole operational picture from one protected surface.</p></div><div className="flex flex-wrap gap-2"><span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-300"><LockKeyhole size={14} /> MFA protected</span>{handleTriggerDeploy && <button type="button" onClick={handleTriggerDeploy} className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/25 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/20"><GitMerge size={14} /> Deploy</button>}</div></header>{actionStatus && <div role="status" className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-xs text-cyan-200">{actionStatus}</div>}

<section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Super admin live summary"><Summary icon={HeartPulse} label="Platform" value={metrics ? 'LIVE' : 'PENDING'} detail={metrics ? 'Telemetry connected' : 'Waiting for telemetry'} good={!!metrics} /><Summary icon={Activity} label="p95 latency" value={metrics?.latency_p95_ms != null ? `${metrics.latency_p95_ms} ms` : '—'} detail="Current metrics snapshot" /><Summary icon={AlertTriangle} label="Critical review" value={activeIncidents.length} detail={activeIncidents.length ? 'Action may be required' : 'No high-severity finding'} good={!activeIncidents.length} /><Summary icon={GitMerge} label="Deployments" value={runningDeployments.length} detail="Currently running" /></section>

<section className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6">
  <div className="mb-3 flex items-center justify-between">
    <div>
      <p className="sa-eyebrow">Service health snapshot</p>
      <h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Live status (unknown is never shown as healthy)</h2>
    </div>
    <span className="text-xs text-[var(--sa-ink-muted)]">Refreshed {new Date(freshness).toLocaleTimeString()}</span>
  </div>
  {serviceEntries.length === 0 ? (
    <p className="text-xs text-[var(--sa-ink-muted)]">No health data yet.</p>
  ) : (
    <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {serviceEntries.map(([name, rec]) => (
        <li key={name} className={`rounded-xl border px-3 py-2 text-xs ${tone(rec?.status)}`}>
          <div className="flex items-center justify-between">
            <span className="font-medium">{name}</span>
            <span className="uppercase">{String(rec?.status || 'unknown')}</span>
          </div>
          <div className="mt-1 text-[10px] opacity-80">
            {rec?.latency != null ? `latency: ${rec.latency} · ` : ''}
            {rec?.region ? `region: ${rec.region}` : ''}
          </div>
        </li>
      ))}
    </ul>
  )}
</section>

<section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]"><article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><div className="flex items-start justify-between gap-4"><div><p className="sa-eyebrow">System command center</p><h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Tell SupremeAI what to do</h2></div><Command className="text-cyan-300" size={19} /></div><div className="mt-4 min-h-44 space-y-3 overflow-y-auto rounded-xl border border-[var(--sa-border)] bg-black/20 p-3">{adminMessages.length ? adminMessages.slice(-8).map((message) => <div key={message.id} className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${message.role === 'user' ? 'ml-auto bg-cyan-400/10 text-cyan-100' : 'bg-white/5 text-[var(--sa-ink)]'}`}><p>{message.content || '—'}</p></div>) : <div className="flex min-h-36 flex-col items-center justify-center text-center text-sm text-[var(--sa-ink-muted)]"><MessageSquare size={20} className="mb-2 text-cyan-300" /><p>No command session yet.</p><p className="mt-1 text-xs">Use the command box below to ask the system to inspect, explain, or prepare work.</p></div>}</div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={requestPermission} className="inline-flex items-center gap-2 rounded-lg border border-amber-400/25 bg-amber-400/5 px-3 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-400/10"><ShieldCheck size={14} /> Request permission</button><button type="button" onClick={() => run('Give me a complete system status report')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><HeartPulse size={14} /> Full status</button><button type="button" onClick={() => run('Service health snapshot')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><Activity size={14} /> Service health</button><button type="button" onClick={() => run('Current incidents')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><AlertTriangle size={14} /> Incidents</button><button type="button" onClick={() => run('Recent audit activity')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><ShieldCheck size={14} /> Audit</button><button type="button" onClick={() => run('Current deployment status')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><GitMerge size={14} /> Deployments</button><button type="button" onClick={() => run('Active agents')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><Cpu size={14} /> Agents</button></div><div className="mt-3 flex gap-2"><input value={adminInput} onChange={(event) => setAdminInput?.(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') handleSendAdmin?.(); }} placeholder="Command, inspect, diagnose..." className="min-w-0 flex-1 rounded-xl border border-[var(--sa-border)] bg-black/20 px-4 py-2.5 text-sm text-[var(--sa-ink)] outline-none focus:border-cyan-400/40" /><button type="button" onClick={() => handleSendAdmin?.()} disabled={loading} className="inline-flex items-center gap-2 rounded-xl bg-cyan-400/15 px-4 py-2.5 text-xs font-semibold text-cyan-100 hover:bg-cyan-400/25 disabled:opacity-50"><Send size={14} /> Send</button></div></article><article className="max-h-[620px] overflow-hidden rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><AdminAlertsTab /></article></section>

<section className="grid gap-5 xl:grid-cols-2"><article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><div><p className="sa-eyebrow">Requested work</p><h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Approve or reject</h2></div><CheckCircle2 size={19} className="text-emerald-300" /></div><ApprovalQueue /></article><article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><div><p className="sa-eyebrow">Quick access</p><h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Controlled modules</h2></div></div><div className="grid gap-2 sm:grid-cols-2"><QuickAction icon={Cpu} label="Agents / swarm" onClick={() => open('agents-swarm')} /><QuickAction icon={ShieldCheck} label="Security & guardrails" onClick={() => open('security')} /><QuickAction icon={Activity} label="Audit trail" onClick={() => open('audit')} /><QuickAction icon={ArrowUpRight} label="Customer / RBAC" onClick={() => open('tenants-rbac')} /></div></article></section>

</div></div>;
}

function Summary({ icon: Icon, label, value, detail, good = false }: { icon: React.ElementType; label: string; value: string | number; detail: string; good?: boolean }) { return <article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-4"><div className="flex items-start justify-between"><div><p className="sa-eyebrow">{label}</p><p className="mt-2 text-2xl font-semibold text-[var(--sa-ink)]">{value}</p><p className="mt-1 text-xs text-[var(--sa-ink-muted)]">{detail}</p></div><Icon size={18} className={good ? 'text-emerald-300' : 'text-cyan-300'} /></div></article>; }
function QuickAction({ icon: Icon, label, onClick }: { icon: React.ElementType; label: string; onClick: () => void }) { return <button type="button" onClick={onClick} className="rounded-xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-4 text-left text-sm text-[var(--sa-ink)] transition hover:border-cyan-400/30 hover:bg-cyan-400/5"><Icon size={17} className="mb-3 text-cyan-300" /><span className="block font-medium">{label}</span><span className="mt-1 block text-xs text-[var(--sa-ink-muted)]">Open controlled module</span></button>; }
