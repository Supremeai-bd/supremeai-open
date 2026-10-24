import React, { useMemo } from 'react';
import {
  Rocket,
  DatabaseBackup,
  ShieldCheck,
  Lock,
  LockOpen,
  Users,
  AlertTriangle,
  Cpu,
  Activity,
} from 'lucide-react';
import { KpiTile, StatusPill, Sparkline, GaugeRing, EmptyState, ConfirmModal } from '../../kit';
import { useCommandCenterStore } from '../../state/useCommandCenterStore';
import {
  useMetrics,
  useHealthMap,
  useCIReports,
  useDashboardEvents,
  useProviders,
  useTraffic,
  useDeployGate,
  useDeploy,
  useCreateBackup,
  useSecurityRescan,
  useToggleDeployGate,
  useAcknowledgeAlert,
} from '../../data/hooks';
import { InfraTopology } from './InfraTopology';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — CommandDeck Home Module (P3)
// বাংলা মন্তব্য: সব রিয়েল ডেটা এক জায়গায় — সত্যিকারের কমান্ড সেন্টার হোম
// ═══════════════════════════════════════════════════════════════════════════

function getHealthPercent(health: { overall_health_percent?: number } | undefined): number | null {
  return health?.overall_health_percent ?? null;
}

export function CommandDeck() {
  const setActiveModule = useCommandCenterStore(s => s.setActiveModule);

  // ── Realtime data (React Query) ──
  const { data: metrics, isLoading: metricsLoading } = useMetrics(15_000);
  const { data: health } = useHealthMap(45_000);
  const { data: ciReports } = useCIReports(5, 30_000);
  const { data: events } = useDashboardEvents(20, 30_000);
  const { data: providers } = useProviders(30_000);
  const { data: traffic } = useTraffic(30_000);
  const { data: deployGate } = useDeployGate();

  // ── Mutations ──
  const deploy = useDeploy();
  const backup = useCreateBackup();
  const rescan = useSecurityRescan();
  const toggleGate = useToggleDeployGate();
  const ackAlert = useAcknowledgeAlert();

  const [confirmAction, setConfirmAction] = React.useState<string | null>(null);
  const [otp, setOtp] = React.useState('');

  const healthPercent = getHealthPercent(health);

  const criticalAlerts = useMemo(
    () => (events ?? []).filter(e => e.level === 'critical' || e.level === 'high'),
    [events],
  );

  const providerDonut = useMemo(() => {
    if (!metrics?.model_call_distribution) return [];
    const dist = metrics.model_call_distribution;
    const total = Object.values(dist).reduce((a, b) => a + b, 0);
    return Object.entries(dist).map(([name, value]) => ({
      name,
      pct: total > 0 ? Math.round((value / total) * 100) : 0,
    }));
  }, [metrics]);

  const quickActions = [
    {
      id: 'deploy' as const,
      label: 'ডিপ্লয়',
      icon: <Rocket size={14} />,
      color: '#00f3ff',
      run: () => setConfirmAction('deploy'),
    },
    {
      id: 'backup' as const,
      label: 'ব্যাকআপ',
      icon: <DatabaseBackup size={14} />,
      color: '#10b981',
      run: () => setConfirmAction('backup'),
    },
    {
      id: 'scan' as const,
      label: 'সিকিউরিটি স্ক্যান',
      icon: <ShieldCheck size={14} />,
      color: '#f59e0b',
      run: () => setConfirmAction('scan'),
    },
    {
      id: 'gate' as const,
      label: deployGate?.status === 'LOCKED' ? 'গেট আনলক' : 'গেট লক',
      icon: deployGate?.status === 'LOCKED' ? <LockOpen size={14} /> : <Lock size={14} />,
      color: deployGate?.status === 'LOCKED' ? '#10b981' : '#ef4444',
      run: () => setConfirmAction('gate'),
    },
    {
      id: 'tenant' as const,
      label: 'নতুন টেন্যান্ট',
      icon: <Users size={14} />,
      color: '#bc13fe',
      run: () => setActiveModule('tenants' as never),
    },
  ];

  // ── Render ──
  if (!metrics && metricsLoading) {
    return (
      <EmptyState
        title="কমান্ড ডেক লোড হচ্ছে..."
        message="রিয়েল-টাইম মেট্রিক্স স্ট্রিমের অপেক্ষায়..."
        loading
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Alert Banner Zone ── */}
      {criticalAlerts.length > 0 && (
        <div className="flex flex-col gap-2">
          {criticalAlerts.slice(0, 3).map((alert, i) => (
            <div
              key={i}
              className={`flex items-center justify-between px-4 py-2 rounded-lg border ${
                alert.level === 'critical'
                  ? 'border-[#ef4444]/30 bg-[#ef4444]/10 text-[#ef4444]'
                  : 'border-[#f59e0b]/30 bg-[#f59e0b]/10 text-[#f59e0b]'
              }`}
            >
              <div className="flex items-center gap-2">
                <AlertTriangle size={14} />
                <span className="text-[10px] font-mono">{alert.message}</span>
              </div>
              <button
                onClick={() => ackAlert.mutate({ alert_id: String(i) })}
                className="text-[9px] font-mono px-2 py-1 rounded border border-current hover:opacity-70"
              >
                ACKNOWLEDGE
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── KPI Strip (6 tiles) ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiTile
          label="ACTIVE AGENTS"
          value={metrics?.active_agents ?? null}
          icon={Cpu}
          tone="cyan"
          loading={metricsLoading}
          onClick={() => setActiveModule('agents' as never)}
        />
        <KpiTile
          label="ACTIVE TASKS"
          value={metrics?.active_tasks ?? null}
          icon={Activity}
          tone="violet"
          loading={metricsLoading}
          onClick={() => setActiveModule('tasks' as never)}
        />
        <KpiTile
          label="REQ/SEC"
          value={metrics?.requests_per_second ?? null}
          tone="emerald"
          loading={metricsLoading}
          onClick={() => setActiveModule('metrics' as never)}
        />
        <KpiTile
          label="P95 LATENCY"
          value={metrics?.latency_p95_ms ?? null}
          unit="ms"
          tone="amber"
          loading={metricsLoading}
          onClick={() => setActiveModule('metrics' as never)}
        />
        <KpiTile
          label="ERROR RATE"
          value={metrics?.error_rate ?? null}
          unit="%"
          tone={metrics && metrics.error_rate > 5 ? 'rose' : 'emerald'}
          loading={metricsLoading}
          onClick={() => setActiveModule('metrics' as never)}
        />
        <KpiTile
          label="COST/HR"
          value={metrics?.cost_per_hour ?? null}
          unit="$"
          tone="indigo"
          loading={metricsLoading}
          onClick={() => setActiveModule('cost' as never)}
        />
      </div>

      {/* ── Row 2: Health + Traffic + CI ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* System Health Ring */}
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 flex items-center justify-center gap-6">
          <GaugeRing
            value={healthPercent ?? 0}
            size={100}
            label="SYSTEM"
            sublabel="OVERALL HEALTH"
            tone={healthPercent !== null && healthPercent < 70 ? 'rose' : 'cyan'}
          />
          <div className="space-y-2">
            {health && (
              <>
                <div className="flex items-center gap-2">
                  <StatusPill status={health.gcp?.status ?? 'unknown'} label="GCP" size="sm" />
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill status={health.railway?.status ?? 'unknown'} label="RAILWAY" size="sm" />
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill status={health.render?.status ?? 'unknown'} label="RENDER" size="sm" />
                </div>
              </>
            )}
          </div>
        </div>

        {/* Traffic Sparkline */}
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)]">
              TRAFFIC (LAST 30 MIN)
            </span>
            <span className="text-[10px] font-mono text-[#00f3ff]">
              {traffic?.current_rps ?? '—'} rps
            </span>
          </div>
          <Sparkline
            data={traffic?.window_30min ?? []}
            height={60}
            width={220}
            color="#00f3ff"
          />
        </div>

        {/* CI/CD */}
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)]">
              CI/CD PIPELINE
            </span>
            <span className="text-[10px] font-mono text-[var(--sa-text-1)]">
              {ciReports?.length ?? 0} runs
            </span>
          </div>
          <div className="space-y-1.5">
            {(ciReports ?? []).slice(0, 4).map(run => (
              <div key={run.id} className="flex items-center gap-2">
                <StatusPill status={run.status} size="sm" />
                <span className="text-[9px] font-mono text-[var(--sa-text-1)] truncate flex-1">
                  {run.message}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 3: Provider Donut + Quick Actions ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Provider Load Donut */}
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
            PROVIDER LOAD DISTRIBUTION
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {providerDonut.length === 0 && (
              <span className="text-[10px] font-mono text-[var(--sa-text-2)]">
                কোন Provider কল ডিস্ট্রিবিউশন ডেটা নেই
              </span>
            )}
            {providerDonut.slice(0, 6).map(item => (
              <div key={item.name} className="flex flex-col items-center gap-1">
                <div
                  className="w-14 h-14 rounded-full flex items-center justify-center border-2 border-[#00f3ff]/40 bg-[#00f3ff]/5"
                  style={{ width: 48, height: 48 }}
                >
                  <span className="text-[12px] font-mono font-bold text-[#00f3ff]">{item.pct}%</span>
                </div>
                <span className="text-[8px] font-mono text-[var(--sa-text-2)] max-w-16 truncate">
                  {item.name}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Action Grid */}
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
            QUICK ACTIONS
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {quickActions.map(action => (
              <button
                key={action.id}
                onClick={action.run}
                className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-[var(--sa-line)] hover:bg-[var(--sa-bg-active)] transition-colors"
                style={{ color: action.color }}
              >
                {action.icon}
                <span className="text-[9px] font-mono">{action.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Live Event Feed ── */}
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
          LIVE EVENT FEED
        </div>
        <div className="space-y-1 max-h-56 overflow-y-auto font-mono text-[10px]">
          {(events ?? []).slice(0, 20).map((event, i) => (
            <div
              key={i}
              className={`flex items-start gap-2 px-2 py-1 rounded ${
                event.level === 'critical'
                  ? 'text-[#ef4444]'
                  : event.level === 'high'
                    ? 'text-[#f59e0b]'
                    : event.level === 'medium'
                      ? 'text-[#facc15]'
                      : 'text-[var(--sa-text-1)]'
              }`}
            >
              <span className="text-[var(--sa-text-3)] shrink-0">
                {new Date(event.timestamp).toLocaleTimeString('bn-BD')}
              </span>
              <span className="shrink-0">[{event.level.toUpperCase()}]</span>
              <span className="text-[var(--sa-text-0)]">{event.message}</span>
            </div>
          ))}
          {(events ?? []).length === 0 && (
            <div className="text-[var(--sa-text-2)]">কোন ইভেন্ট নেই — অপেক্ষা করা হচ্ছে...</div>
          )}
        </div>
      </div>

      {/* ── Mini Infra Topology ── */}
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">
          INFRA TOPOLOGY
        </div>
        <InfraTopology health={health} providers={providers} onNavigate={setActiveModule} />
      </div>

      {/* ── Action Confirmation Modal ── */}
      <ConfirmModal
        open={confirmAction !== null}
        title="নিশ্চিত করুন"
        message={
          confirmAction === 'deploy'
            ? 'আপনি কি প্রোডাকশনে ডিপ্লয় করতে চান?'
            : confirmAction === 'backup'
              ? 'আপনি কি একটি নতুন ব্যাকআপ তৈরি করতে চান?'
              : confirmAction === 'scan'
                ? 'আপনি কি সিকিউরিটি রিস্ক্যান চালাতে চান?'
                : 'আপনি কি ডিপ্লয় গেট টগল করতে চান?'
        }
        confirmLabel={
          confirmAction === 'deploy' ? 'ডিপ্লয়' :
          confirmAction === 'backup' ? 'ব্যাকআপ' :
          confirmAction === 'scan' ? 'স্ক্যান' : 'টগল'
        }
        onCancel={() => setConfirmAction(null)}
        onConfirm={() => {
          if (confirmAction === 'deploy') deploy.mutate();
          if (confirmAction === 'backup') backup.mutate();
          if (confirmAction === 'scan') rescan.mutate();
          if (confirmAction === 'gate') {
            toggleGate.mutate({
              status: deployGate?.status === 'LOCKED' ? 'UNLOCKED' : 'LOCKED',
              reason: otp,
            });
          }
          setConfirmAction(null);
          setOtp('');
        }}
      />
    </div>
  );
}
