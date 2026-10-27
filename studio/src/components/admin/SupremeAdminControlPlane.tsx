import React, { useEffect, useRef, useState } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, CheckCircle2, Command, Cpu, Database, GitMerge, HeartPulse, LockKeyhole, MessageSquare, Mic, MicOff, Network, Send, ShieldCheck, Sliders, Sparkles, Terminal, Volume2, VolumeX } from 'lucide-react';
import { useMetrics, useThreatScan, useCIReports, useEpistemicTelemetry } from '../../hooks/useDashboardData';
import { ApprovalQueue } from '../../commandcenter/modules/secure/ApprovalQueue';
import { AdminAlertsTab } from './AdminAlertsTab';
import { ArcReactorOrb, LiveWaveform, orbLabel } from './jarvis/ArcReactorOrb';
import { useAdminVoice } from './jarvis/useAdminVoice';
import { TwoFASentinelModal } from './jarvis/TwoFASentinelModal';
import { generateAdminBriefing, isDestructiveCommand, detectDestructiveReason } from './jarvis/jarvisPersona';

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
  const { data: telemetry } = useEpistemicTelemetry();
  const activeIncidents = threats?.findings?.filter((item) => item.severity === 'high' || item.severity === 'critical') || [];
  const runningDeployments = ciReports?.filter((item) => item.status === 'running') || [];
  const serviceEntries = Object.entries(healthMap);
  const [freshness, setFreshness] = useState<string>(new Date().toISOString());
  useEffect(() => { setFreshness(new Date().toISOString()); }, [healthMap, metrics, threats, ciReports, telemetry]);
  const open = (tab: string) => setAdminSubTab?.(tab);
  const requestPermission = () => setAdminInput?.('Request permission for: ');
  const run = (cmd: string) => setAdminInput?.(cmd);

  // ── JARVIS Admin Voice Cockpit State & 2FA Sentinel ──
  const [sentinelModal, setSentinelModal] = useState<{
    isOpen: boolean;
    command: string;
    reason: string | null;
  }>({ isOpen: false, command: '', reason: null });
  const [graceUntil, setGraceUntil] = useState<number>(0);
  const voiceControlsRef = useRef<{
    speak: (text: string, onEnd?: () => void) => void;
  } | null>(null);

  const handleVoiceCommand = (spokenText: string) => {
    setAdminInput?.(spokenText);
    const reason = detectDestructiveReason(spokenText);
    if (reason && Date.now() > graceUntil) {
      setSentinelModal({ isOpen: true, command: spokenText, reason });
      voiceControlsRef.current?.speak('Authorization required for this command, Sir.');
      return;
    }
    setTimeout(() => {
      handleSendAdmin?.();
      voiceControlsRef.current?.speak(`Processing ${spokenText}, Sir.`);
    }, 400);
  };

  const {
    orbState,
    setOrbState,
    isListening,
    isSpeaking,
    transcript,
    isMuted,
    micAvailable,
    toggleListening,
    speak,
    stopSpeaking,
    toggleMute,
  } = useAdminVoice(handleVoiceCommand);

  useEffect(() => {
    voiceControlsRef.current = { speak };
  }, [speak]);

  // Auto-greeting & oral briefing upon initial admin dashboard mount
  const briefedRef = useRef(false);
  useEffect(() => {
    if (briefedRef.current) return;
    const timer = setTimeout(() => {
      if (briefedRef.current) return;
      briefedRef.current = true;
      setOrbState('boot');
      const briefing = generateAdminBriefing({
        activeIncidents: activeIncidents.length,
        runningDeployments: runningDeployments.length,
        latencyP95: metrics?.latency_p95_ms,
        totalServicesCount: serviceEntries.length,
      });
      speak(briefing, () => setOrbState('idle'));
    }, 1200);
    return () => clearTimeout(timer);
  }, [metrics, activeIncidents.length, runningDeployments.length, serviceEntries.length, speak, setOrbState]);

  // Safe send wrapper with 2FA check
  const safeSendAdmin = () => {
    const text = adminInput.trim();
    if (!text) return;
    const reason = detectDestructiveReason(text);
    if (reason && Date.now() > graceUntil) {
      setSentinelModal({ isOpen: true, command: text, reason });
      speak('Authorization required for this command, Sir.');
      return;
    }
    handleSendAdmin?.();
  };

  const on2FAAuthorized = () => {
    setGraceUntil(Date.now() + 5 * 60 * 1000); // 5 min clearance window
    setSentinelModal({ isOpen: false, command: '', reason: null });
    speak('Authorization confirmed. Executing now, Sir.');
    handleSendAdmin?.();
  };

  const on2FACancel = () => {
    setSentinelModal({ isOpen: false, command: '', reason: null });
    speak('Action cancelled, Sir.');
  };

  return <div className="min-h-full bg-[var(--sa-canvas)] px-5 py-6 sm:px-8 lg:px-10"><div className="mx-auto max-w-admin space-y-5"><header className="flex flex-col justify-between gap-4 rounded-2xl border border-cyan-400/20 bg-[radial-gradient(circle_at_78%_0%,rgba(34,211,238,0.12),transparent_42%),var(--sa-surface)] p-5 sm:p-7 lg:flex-row lg:items-end"><div><div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300"><Sparkles size={14} /> Supreme system control plane</div><h1 className="text-3xl font-semibold tracking-tight text-[var(--sa-ink)] sm:text-4xl">Super Admin Dashboard</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--sa-ink-muted)]">Command the system, review requested work, approve or reject safely, and inspect the whole operational picture from one protected surface.</p></div><div className="flex flex-wrap items-center gap-3"><div className="flex items-center gap-3 rounded-2xl border border-cyan-400/25 bg-black/40 px-3.5 py-2 backdrop-blur-md"><ArcReactorOrb state={orbState} size={56} onClick={toggleListening} /><div className="text-left"><div className="flex items-center gap-1.5 text-[10px] font-mono tracking-wider text-cyan-400 uppercase"><span className={`size-1.5 rounded-full ${orbState === 'alert' ? 'bg-red-400' : 'bg-cyan-400'} animate-ping`} />JARVIS {orbLabel(orbState)}</div><p className="text-[11px] text-[var(--sa-ink-muted)]">{isListening ? 'Listening to speech...' : isSpeaking ? 'Responding verbally...' : 'Voice cockpit ready'}</p><div className="mt-1 flex items-center gap-1.5"><button type="button" onClick={toggleListening} className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-mono font-medium transition ${isListening ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse' : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20'}`} title="Toggle Speech Recognition">{isListening ? <Mic size={10} /> : <MicOff size={10} />}{isListening ? 'LIVE' : 'MIC'}</button><button type="button" onClick={toggleMute} className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-mono font-medium bg-black/30 text-slate-400 border border-slate-700/50 hover:text-white" title={isMuted ? 'Unmute JARVIS Voice' : 'Mute JARVIS Voice'}>{isMuted ? <VolumeX size={10} /> : <Volume2 size={10} />}{isMuted ? 'MUTED' : 'VOICE'}</button></div></div></div><span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-300"><LockKeyhole size={14} /> MFA protected</span>{handleTriggerDeploy && <button type="button" onClick={handleTriggerDeploy} className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/25 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-400/20"><GitMerge size={14} /> Deploy</button>}</div></header>{actionStatus && <div role="status" className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-xs text-cyan-200">{actionStatus}</div>}

<section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Super admin live summary"><Summary icon={HeartPulse} label="Platform" value={metrics ? 'LIVE' : 'PENDING'} detail={metrics ? 'Telemetry connected' : 'Waiting for telemetry'} good={!!metrics} /><Summary icon={Activity} label="p95 latency" value={metrics?.latency_p95_ms != null ? `${metrics.latency_p95_ms} ms` : '—'} detail="Current metrics snapshot" /><Summary icon={AlertTriangle} label="Critical review" value={activeIncidents.length} detail={activeIncidents.length ? 'Action may be required' : 'No high-severity finding'} good={!activeIncidents.length} /><Summary icon={GitMerge} label="Deployments" value={runningDeployments.length} detail="Currently running" /></section>

{/* ── Way 10 & 12: Epistemic Engine Cockpit (Infinity HUD × ChronoFact × SPINE) ── */}
<section className="rounded-2xl border border-cyan-500/20 bg-[radial-gradient(ellipse_at_top_right,rgba(6,182,212,0.06),transparent_50%),var(--sa-surface)] p-5 sm:p-6" aria-label="Epistemic Engine Cockpit">
  <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
    <div>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
        <Cpu size={14} /> Cognitive Backbone Telemetry (ChronoFact × SPINE)
      </div>
      <h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">
        Epistemic Engine & Invariant Controls
      </h2>
    </div>
    <div className="flex items-center gap-2 text-xs text-[var(--sa-ink-muted)]">
      <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
      <span>Live Invariants Enforced</span>
    </div>
  </div>

  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <div className="rounded-xl border border-cyan-400/20 bg-black/20 p-4">
      <div className="flex items-center justify-between text-xs text-cyan-300">
        <span className="font-semibold uppercase tracking-wider">TF-IDF Tool Pruner</span>
        <Sliders size={15} />
      </div>
      <p className="mt-2 text-2xl font-mono font-semibold text-[var(--sa-ink)]">
        {telemetry?.counters?.tokens_saved ?? 0}
      </p>
      <p className="mt-1 text-[11px] text-[var(--sa-ink-muted)]">
        Tokens Saved ({telemetry?.rates?.token_savings_pct ?? 0}% cut · Target ≥70%)
      </p>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-emerald-300">
        <span>Pruned: {telemetry?.counters?.tools_pruned ?? 0} schemas</span>
      </div>
    </div>

    <div className="rounded-xl border border-emerald-400/20 bg-black/20 p-4">
      <div className="flex items-center justify-between text-xs text-emerald-300">
        <span className="font-semibold uppercase tracking-wider">Memory Relevance Gate</span>
        <Database size={15} />
      </div>
      <p className="mt-2 text-2xl font-mono font-semibold text-[var(--sa-ink)]">
        {telemetry?.invariants?.memory_cosine_threshold ?? 0.72}
      </p>
      <p className="mt-1 text-[11px] text-[var(--sa-ink-muted)]">
        Cosine Gate Threshold (0 Cross-Domain Leaks)
      </p>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-emerald-300">
        <span>Evaluated: {telemetry?.counters?.memory_evaluated ?? 0} memories</span>
      </div>
    </div>

    <div className="rounded-xl border border-purple-400/20 bg-black/20 p-4">
      <div className="flex items-center justify-between text-xs text-purple-300">
        <span className="font-semibold uppercase tracking-wider">SPINE Stream Sanitizer</span>
        <ShieldCheck size={15} />
      </div>
      <p className="mt-2 text-2xl font-mono font-semibold text-[var(--sa-ink)]">
        ACTIVE
      </p>
      <p className="mt-1 text-[11px] text-[var(--sa-ink-muted)]">
        Thoracic T1 Invariant (Zero Unearned Apology)
      </p>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-purple-300">
        <span>Interventions: {telemetry?.counters?.cushions_stripped ?? 0}</span>
      </div>
    </div>

    <div className="rounded-xl border border-amber-400/20 bg-black/20 p-4">
      <div className="flex items-center justify-between text-xs text-amber-300">
        <span className="font-semibold uppercase tracking-wider">Model Horizon Calibrated</span>
        <Terminal size={15} />
      </div>
      <p className="mt-2 text-2xl font-mono font-semibold text-[var(--sa-ink)]">
        FROZEN
      </p>
      <p className="mt-1 text-[11px] text-[var(--sa-ink-muted)]">
        Temporal Cutoff & Drift Auto-Interceptor
      </p>
      <div className="mt-2 flex items-center gap-2 text-[10px] text-amber-300">
        <span>Intercepts: {telemetry?.counters?.horizon_intercepts ?? 0}</span>
      </div>
    </div>
  </div>

  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--sa-border)] bg-black/30 px-4 py-2.5 text-xs font-mono text-[var(--sa-ink-muted)]">
    <span className="text-cyan-300 font-sans font-semibold">Invariant Locks:</span>
    <span>SAMPLING_LOGIC: <strong className="text-emerald-300">0.2</strong></span>
    <span>SAMPLING_CHAT: <strong className="text-emerald-300">0.4</strong></span>
    <span>MEMORY_COSINE_GATE: <strong className="text-emerald-300">0.72</strong></span>
    <span>REDUCTION_GOAL: <strong className="text-emerald-300">≥70%</strong></span>
  </div>
</section>

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

<section className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]"><article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><div className="flex items-start justify-between gap-4"><div><p className="sa-eyebrow">System command center</p><h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Tell SupremeAI what to do</h2></div><Command className="text-cyan-300" size={19} /></div><div className="mt-4 min-h-44 space-y-3 overflow-y-auto rounded-xl border border-[var(--sa-border)] bg-black/20 p-3">{adminMessages.length ? adminMessages.slice(-8).map((message) => <div key={message.id} className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${message.role === 'user' ? 'ml-auto bg-cyan-400/10 text-cyan-100' : 'bg-white/5 text-[var(--sa-ink)]'}`}><p>{message.content || '—'}</p></div>) : <div className="flex min-h-36 flex-col items-center justify-center text-center text-sm text-[var(--sa-ink-muted)]"><MessageSquare size={20} className="mb-2 text-cyan-300" /><p>No command session yet.</p><p className="mt-1 text-xs">Use the command box below to ask the system to inspect, explain, or prepare work.</p></div>}</div><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={requestPermission} className="inline-flex items-center gap-2 rounded-lg border border-amber-400/25 bg-amber-400/5 px-3 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-400/10"><ShieldCheck size={14} /> Request permission</button><button type="button" onClick={() => run('Give me a complete system status report')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><HeartPulse size={14} /> Full status</button><button type="button" onClick={() => run('Service health snapshot')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><Activity size={14} /> Service health</button><button type="button" onClick={() => run('Current incidents')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><AlertTriangle size={14} /> Incidents</button><button type="button" onClick={() => run('Recent audit activity')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><ShieldCheck size={14} /> Audit</button><button type="button" onClick={() => run('Current deployment status')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><GitMerge size={14} /> Deployments</button><button type="button" onClick={() => run('Active agents')} className="inline-flex items-center gap-2 rounded-lg border border-[var(--sa-border)] px-3 py-2 text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)]"><Cpu size={14} /> Agents</button></div><div className="mt-3 flex gap-2">
  <input
    value={adminInput}
    onChange={(event) => setAdminInput?.(event.target.value)}
    onKeyDown={(event) => { if (event.key === 'Enter') safeSendAdmin(); }}
    placeholder={isListening ? "Listening... (speak clearly in English or Bengali)" : "Command, inspect, diagnose..."}
    className={`min-w-0 flex-1 rounded-xl border bg-black/20 px-4 py-2.5 text-sm text-[var(--sa-ink)] outline-none transition ${isListening ? 'border-emerald-400/60 shadow-[0_0_12px_rgba(52,211,153,0.3)]' : 'border-[var(--sa-border)] focus:border-cyan-400/40'}`}
  />
  {micAvailable && (
    <button
      type="button"
      onClick={toggleListening}
      className={`inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2.5 text-xs font-semibold transition ${
        isListening
          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse'
          : 'bg-cyan-500/10 text-cyan-200 border border-cyan-500/25 hover:bg-cyan-500/20'
      }`}
      title={isListening ? "Stop Listening" : "Speak to JARVIS"}
    >
      {isListening ? <Mic size={15} /> : <MicOff size={15} />}
      <span className="hidden sm:inline">{isListening ? 'Listening...' : 'Voice'}</span>
    </button>
  )}
  <button
    type="button"
    onClick={safeSendAdmin}
    disabled={loading}
    className="inline-flex items-center gap-2 rounded-xl bg-cyan-400/15 px-4 py-2.5 text-xs font-semibold text-cyan-100 hover:bg-cyan-400/25 disabled:opacity-50"
  >
    <Send size={14} /> Send
  </button>
</div>

{(isListening || isSpeaking || transcript) && (
  <div className="mt-2.5 rounded-xl border border-cyan-500/20 bg-black/30 p-2.5">
    <div className="flex items-center justify-between text-[10px] font-mono text-cyan-400/80 mb-1">
      <span>JARVIS AUDIO CHANNEL</span>
      <span className="uppercase">{orbLabel(orbState)}</span>
    </div>
    <LiveWaveform state={orbState} height={28} barCount={40} />
    {transcript && (
      <p className="mt-1.5 text-xs text-cyan-200 font-mono italic">
        "{transcript}"
      </p>
    )}
  </div>
)}
</article>
<article className="max-h-[60vh] overflow-hidden rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><AdminAlertsTab /></article></section>

<section className="grid gap-5 xl:grid-cols-2"><article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><div><p className="sa-eyebrow">Requested work</p><h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Approve or reject</h2></div><CheckCircle2 size={19} className="text-emerald-300" /></div><ApprovalQueue /></article><article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><div><p className="sa-eyebrow">Quick access</p><h2 className="mt-1 text-lg font-semibold text-[var(--sa-ink)]">Controlled modules</h2></div></div><div className="grid gap-2 sm:grid-cols-2"><QuickAction icon={Cpu} label="Agents / swarm" onClick={() => open('agents-swarm')} /><QuickAction icon={ShieldCheck} label="Security & guardrails" onClick={() => open('security')} /><QuickAction icon={Activity} label="Audit trail" onClick={() => open('audit')} /><QuickAction icon={ArrowUpRight} label="Customer / RBAC" onClick={() => open('tenants-rbac')} /></div></article></section>

{sentinelModal.isOpen && (
  <TwoFASentinelModal
    command={sentinelModal.command}
    reason={sentinelModal.reason}
    onAuthorized={on2FAAuthorized}
    onCancel={on2FACancel}
  />
)}

</div></div>;
}

function Summary({ icon: Icon, label, value, detail, good = false }: { icon: React.ElementType; label: string; value: string | number; detail: string; good?: boolean }) { return <article className="rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-4"><div className="flex items-start justify-between"><div><p className="sa-eyebrow">{label}</p><p className="mt-2 text-2xl font-semibold text-[var(--sa-ink)]">{value}</p><p className="mt-1 text-xs text-[var(--sa-ink-muted)]">{detail}</p></div><Icon size={18} className={good ? 'text-emerald-300' : 'text-cyan-300'} /></div></article>; }
function QuickAction({ icon: Icon, label, onClick }: { icon: React.ElementType; label: string; onClick: () => void }) { return <button type="button" onClick={onClick} className="rounded-xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-4 text-left text-sm text-[var(--sa-ink)] transition hover:border-cyan-400/30 hover:bg-cyan-400/5"><Icon size={17} className="mb-3 text-cyan-300" /><span className="block font-medium">{label}</span><span className="mt-1 block text-xs text-[var(--sa-ink-muted)]">Open controlled module</span></button>; }
