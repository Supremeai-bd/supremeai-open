import { useState, useEffect } from 'react';
import { Card, Badge } from '../../ui';
import {  ShieldAlert, Cpu, Database, RefreshCw, Server, Loader2, DollarSign } from 'lucide-react';
import { apiClient } from '../../../services/apiClient';
import { useUnifiedStore } from '../../../store/unifiedStore';

interface TaskReference {
  id: string;
  name: string;
  strongRef: boolean;
  status: string;
  startedAt: string;
}

interface MemoryMetrics {
  heapUsed: string | null;
  heapTotal: string | null;
  heapSource: string;
  zombieTasksDetected: number;
  failuresBlocked: number;
  trackedTasks: number;
  untrackedTasks: number;
}

export function SecurityDashboard() {
  const [activeTasks, setActiveTasks] = useState<TaskReference[]>([]);
  const [memoryMetrics, setMemoryMetrics] = useState<MemoryMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const lastSecurityScan = useUnifiedStore(s => s.lastSecurityScan);

  const fetchData = async () => {
    setLoading(true);
    setError('');
    try {
      const [tasksRes, metricsRes] = await Promise.all([
        apiClient.get<{ tasks: TaskReference[] }>('/admin-api/security/tasks'),
        apiClient.get<MemoryMetrics>('/admin-api/security/memory'),
      ]);
      setActiveTasks(tasksRes.tasks || []);
      setMemoryMetrics(metricsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load security data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex-grow p-6 overflow-y-auto bg-[#030611] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <Loader2 size={24} className="animate-spin text-[#00f3ff]" />
          <span className="text-xs font-mono">Loading security dashboard...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-grow p-6 overflow-y-auto bg-[#030611] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-rose-400">
          <ShieldAlert size={24} />
          <span className="text-xs font-mono">{error}</span>
          <button
            onClick={fetchData}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#00f3ff]/10 hover:bg-[#00f3ff]/20 text-[#00f3ff] text-xs font-mono border border-[#00f3ff]/30 transition-colors"
          >
            <RefreshCw size={12} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-grow overflow-y-auto bg-[var(--sa-canvas)] p-6 text-[var(--sa-ink)]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          Memory & background security
        </h2>
        <div className="flex gap-2">
          <Badge variant={memoryMetrics && memoryMetrics.untrackedTasks === 0 ? 'success' : 'warning'}>
            {memoryMetrics ? `${memoryMetrics.trackedTasks} Tracked / ${memoryMetrics.untrackedTasks} Untracked` : 'Task telemetry unavailable'}
          </Badge>
          <Badge variant={memoryMetrics && memoryMetrics.zombieTasksDetected > 0 ? 'danger' : 'info'}>
            {memoryMetrics ? `${memoryMetrics.zombieTasksDetected} Zombie Tasks` : 'Zombie telemetry unavailable'}
          </Badge>
        </div>
      </div>

      <Card title="Manual Security Follow-up" className="mb-6">
        <div className="flex flex-col gap-3">
          <div className="flex items-start gap-3 rounded-lg border border-amber-400/20 bg-amber-400/5 p-3">
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-amber-400" aria-hidden="true" />
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-amber-200">Audit only — no credentials were changed</span>
                <Badge variant="warning">Manual task list</Badge>
              </div>
              <p className="text-xs leading-relaxed text-slate-400">
                Complete these actions manually after reviewing the current production environment and Git history.
              </p>
            </div>
          </div>
          <ul className="grid gap-2 text-xs text-slate-300 md:grid-cols-2" aria-label="Manual security follow-up tasks">
            {[
              'Rotate Render, GitHub, and any other exposed credentials.',
              'Remove exposed values from the working tree and deployment configuration.',
              'Clean affected Git history, then rescan the repository and deployment logs.',
              'Review destructive operational scripts and require explicit confirmation or move them to protected tooling.',
            ].map((task) => (
              <li key={task} className="flex items-start gap-2 rounded-md border border-slate-800 bg-slate-900/30 p-3">
                <span className="mt-0.5 text-amber-400" aria-hidden="true">□</span>
                <span>{task}</span>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card title="Background Task Group">
          <div className="flex items-center gap-3">
            <Cpu size={20} className="text-cyan-400" />
            <div>
              <div className="text-xs text-slate-400">Active Tasks (Strong References)</div>
              <div className="text-xl font-bold text-cyan-400 font-mono">
                {activeTasks.filter(t => t.status === 'running').length} Active
              </div>
            </div>
          </div>
        </Card>

        <Card title="Zombie/Fire-And-Forget Checks">
          <div className="flex items-center gap-3">
            <ShieldAlert size={20} className={memoryMetrics && memoryMetrics.zombieTasksDetected > 0 ? 'text-red-400' : 'text-emerald-400'} />
            <div>
              <div className="text-xs text-slate-400">Untracked Tasks / Blocked Failures</div>
              <div className={`text-xl font-bold font-mono ${memoryMetrics && memoryMetrics.zombieTasksDetected > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                {memoryMetrics ? `${memoryMetrics.zombieTasksDetected} Untracked / ${memoryMetrics.failuresBlocked} Blocked` : '—'}
              </div>
            </div>
          </div>
        </Card>

        <Card title="Active Memory Usage">
          <div className="flex items-center gap-3">
            <Database size={20} className="text-yellow-400" />
            <div>
              <div className="text-xs text-slate-400">Memory Heap</div>
              <div className="text-xl font-bold text-yellow-400 font-mono">
                {memoryMetrics ? memoryMetrics.heapUsed : '—'}
              </div>
            </div>
          </div>
        </Card>

        <Card title="Database OCC Engine">
          <div className="flex items-center gap-3">
            <Server size={20} className="text-slate-500" />
            <div>
              <div className="text-xs text-slate-400">Optimistic Locks Active</div>
              <div className="text-xl font-bold text-slate-400 font-mono">
                No telemetry source
              </div>
              <div className="text-[10px] text-slate-500">Real OCC contention metrics require a DB probe — not fabricated as "0".</div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Monitored Async Background Tasks">
          <div className="flex flex-col gap-2">
            {activeTasks.length === 0 ? (
              <div className="text-xs text-slate-400 font-mono text-center py-4">No active tasks monitored.</div>
            ) : (
              activeTasks.map(t => (
                <div key={t.id} className="p-3 rounded-lg border border-slate-800 bg-slate-900/30 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-bold text-white font-mono">{t.name}</div>
                    <div className="text-[10px] text-slate-400 mt-1">
                      ID: {t.id} • Started: {t.startedAt}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={t.strongRef ? 'info' : 'warning'}>
                      {t.strongRef ? 'Strong Reference' : 'Weak Reference'}
                    </Badge>
                    <Badge variant={t.status === 'running' ? 'success' : 'info'}>
                      {t.status.toUpperCase()}
                    </Badge>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card title="Real-time Security Guard Signals">
          <div className="flex flex-col gap-3 text-xs font-mono text-slate-300">
            {lastSecurityScan?.issues && lastSecurityScan.issues.length > 0 ? (
              lastSecurityScan.issues.map((issue, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className={issue.severity === 'critical' ? 'text-rose-500' : (issue.severity === 'high' || issue.severity === 'medium') ? 'text-amber-400' : 'text-emerald-400'}>
                    [{issue.severity.toUpperCase()}]
                  </span>
                  <span>{issue.message}</span>
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 font-mono text-center py-4">
                No security scan data yet — signals appear here after the first scan
                (POST /admin-api/security-scan). Static "OK" placeholders removed
                (issue #1242): absence of a scan is not evidence of safety.
              </div>
            )}
            {lastSecurityScan?.score !== undefined && (
              <div className="mt-2 pt-2 border-t border-slate-800">
                <span className="text-cyan-400">Last Scan Score: {lastSecurityScan.score}/100</span>
                <div className="text-[10px] text-slate-500">URL: {lastSecurityScan.url}</div>
              </div>
            )}
          </div>
        </Card>
      </div>

      <div className="mt-8 flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase flex items-center gap-2">
          <DollarSign size={20} />
          Free-Tier Monitor
        </h2>
        <div className="flex gap-2">
          <Badge variant="info">Live quota telemetry not connected</Badge>
        </div>
      </div>

      {/* Wave 2.5 (issue #1242): the fabricated quota numbers below ("~200-400 MB",
          "513.6/750.0", "64.2/100") were removed — provider quota APIs are not
          wired yet, and inventing numbers is worse than showing nothing. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {['Supabase', 'Upstash Redis', 'Render'].map((provider) => (
          <Card key={provider} title={provider}>
            <div className="text-xs text-slate-400 mb-2">Quota usage: no live source</div>
            <div className="h-2 bg-slate-800 rounded overflow-hidden">
              <div className="h-full bg-slate-700 w-[0%]"></div>
            </div>
          </Card>
        ))}
      </div>

    </div>
  );
}
