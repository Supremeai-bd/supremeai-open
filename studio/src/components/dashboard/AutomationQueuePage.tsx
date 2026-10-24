import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, Loader2, ListChecks, AlertOctagon, Terminal, Clock } from 'lucide-react';
import { apiClient, getRawToken } from '../../services/apiClient';
import { createSecureEventSource } from '../../lib/secureSse';
import { setSujonState } from '../sujon-utils';
import { getApiBaseUrl } from '../../utils/api';


interface AutomationTask {
  id: string;
  goal: string;
  status: string;
  createdAt?: string;
  durationMs?: number;
  failure_payload?: {
    root_cause: string;
    failed_log_tick: string;
    reset_eta_sec: number;
    stack_trace: string;
  };
}

const EXECUTION_CAP_MS = 45000;

const stateBadge = (status: string): string => {
  const s = status.toUpperCase();
  if (s === 'RUNNING' || s === 'ACTIVE') return 'bg-blue-500/15 text-blue-300 border-blue-500/30';
  if (s === 'SUCCESS') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  if (s === 'FAILED') return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
  if (s === 'CIRCUIT_OPEN') return 'bg-red-600/20 text-red-300 border-red-600/40';
  return 'bg-slate-500/15 text-slate-300 border-slate-500/30';
};

export function AutomationQueuePage() {
  const [tasks, setTasks] = useState<AutomationTask[]>([]);
  const [goal, setGoal] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    apiClient
      .get<{ tasks: AutomationTask[] }>('/api/browser/tasks')
      .then((data) => {
        // Audit F-02 fix (2026-09-17): the fabricated failure_payload injection
        // was removed — the UI previously INVENTED a root cause ("DOM Element
        // Timeout"), stack trace and reset ETA for any CIRCUIT_OPEN task.
        // Real diagnostics render only when the backend actually provides them.
        const list = data.tasks || [];

        setTasks(list);
        setError('');
        const states = list.map((t) => t.status.toUpperCase());
        if (states.includes('CIRCUIT_OPEN')) setSujonState('circuit_open');
        else if (states.some((s) => s === 'RUNNING' || s === 'ACTIVE')) setSujonState('processing');
        else setSujonState('idle');
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load tasks'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const backendUrl = getApiBaseUrl();
    const token = getRawToken();
    const sse = createSecureEventSource(`${backendUrl}/api/dashboard/stream`, token, {
      onMessage: (e) => {
        if (e.type === 'browser_tasks') {
          refresh();
        }
      }
    });

    return () => {
      sse.close();
      setSujonState('idle');
    };
  }, [refresh]);

  const handleCreate = async () => {
    if (!goal.trim() || creating) return;
    setCreating(true);
    setError('');
    try {
      await apiClient.post('/api/browser/tasks', { goal: goal.trim() });
      setGoal('');
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to queue task');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiClient.delete(`/api/browser/tasks/${id}`);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete task');
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-white flex items-center gap-3 mb-2">
        <ListChecks size={24} className="text-blue-500" />
        Automation Workflow Queue
      </h1>
      <p className="text-sm text-slate-400 mb-6">
        Active Playwright automation sequences. Each task is capped at{' '}
        {EXECUTION_CAP_MS / 1000}s of execution time.
      </p>

      <div className="rounded-xl border border-gray-800 bg-[#1e1e1e] p-4 mb-8 flex items-center gap-3 shadow-lg">
        <input
          data-testid="automation-goal"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          placeholder="Describe an automation goal (e.g. 'Extract latest orders from dashboard')"
          className="flex-1 rounded-lg bg-black/40 border border-gray-700 px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500/50 transition-colors"
        />
        <button
          data-testid="automation-queue-btn"
          onClick={handleCreate}
          disabled={!goal.trim() || creating}
          className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-500 text-white text-sm font-medium transition-colors shadow-md"
        >
          {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
          Queue Execution
        </button>
      </div>

      {error && <p className="text-sm text-red-400 mb-6 bg-red-500/10 p-3 rounded-lg border border-red-500/20">{error}</p>}

      <div className="flex items-center justify-between mb-4 px-1">
        <h2 className="text-sm font-medium text-gray-300">Active Workflow Sequences</h2>
        <span className="text-xs font-mono bg-gray-800 text-gray-400 px-2 py-1 rounded">{tasks.length} total</span>
      </div>

      {loading ? (
        <div className="flex justify-center py-20 text-slate-400">
          <Loader2 size={24} className="animate-spin" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-[#1e1e1e] border border-gray-800 rounded-xl border-dashed text-gray-500">
           <ListChecks size={40} className="mb-4 text-gray-700" />
           <p className="font-medium text-gray-400">No automation tasks queued.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {tasks.map((t) => (
            <div key={t.id} className="flex flex-col rounded-xl border border-gray-800 bg-[#1e1e1e] overflow-hidden shadow-md">
              <div className="flex items-center p-4">
                <div className="flex-1 min-w-0 pr-4">
                  <p className="text-sm font-medium text-gray-200 truncate">{t.goal}</p>
                  <p className="text-xs text-gray-500 mt-1 font-mono">
                    {t.createdAt ? new Date(t.createdAt).toLocaleString() : '—'}
                    {typeof t.durationMs === 'number' && ` · ${(t.durationMs / 1000).toFixed(1)}s`}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <span className={`text-[10px] px-2.5 py-1 rounded-full border font-bold tracking-wider ${stateBadge(t.status)}`}>
                    {t.status.toUpperCase()}
                  </span>
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="p-2 rounded bg-gray-800 text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    title="Terminate Task"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              {/* Circuit Breaker Diagnostic Panel — only with REAL backend payload.
                  When the backend provides no failure_payload, show an honest
                  unavailability notice instead of invented diagnostics (F-02). */}
              {t.status.toUpperCase() === 'CIRCUIT_OPEN' && !t.failure_payload && (
                <div className="border-t border-red-900/30 bg-red-950/10 p-4">
                  <p className="text-xs text-gray-400">
                    <span className="font-bold text-red-400 uppercase tracking-wider">Breaker tripped.</span>{' '}
                    Detailed diagnostics (root cause, stack trace, reset ETA) are not provided by
                    the backend for this task yet — no invented data is shown.
                  </p>
                </div>
              )}
              {t.status.toUpperCase() === 'CIRCUIT_OPEN' && t.failure_payload && (
                <div className="bg-red-950/20 border-t border-red-900/30 p-5 flex flex-col md:flex-row gap-6">

                  {/* Left: Summary */}
                  <div className="w-full md:w-1/3 flex flex-col gap-4">
                    <div className="flex items-start gap-2">
                       <AlertOctagon size={20} className="text-red-500 shrink-0 mt-0.5" />
                       <div>
                         <h4 className="text-sm font-bold text-red-400 uppercase tracking-wider">Breaker Tripped</h4>
                         <p className="text-xs text-gray-400 mt-1">Protection mechanisms activated due to repeated failures.</p>
                       </div>
                    </div>

                    <div className="bg-black/40 rounded-lg p-3 border border-red-900/50">
                       <p className="text-[10px] uppercase text-gray-500 mb-1">Root Cause</p>
                       <p className="text-sm text-gray-300 font-semibold">{t.failure_payload.root_cause}</p>
                    </div>

                    <div className="flex items-center gap-3">
                       <Clock size={16} className="text-amber-500" />
                       <div className="text-sm text-gray-300">
                         Reset ETA: <span className="font-mono text-amber-400 font-bold">{t.failure_payload.reset_eta_sec}s</span>
                       </div>
                    </div>
                  </div>

                  {/* Right: Stack Trace & Logs */}
                  <div className="w-full md:w-2/3 flex flex-col gap-2">
                     <div className="flex justify-between items-center text-xs">
                        <span className="text-gray-400 uppercase tracking-wider font-semibold flex items-center gap-2">
                          <Terminal size={14} /> Diagnostic Dump
                        </span>
                        <a href={`#/session/${t.id}`} className="text-blue-400 hover:text-blue-300 underline">View Full Execution Log →</a>
                     </div>
                     <div className="flex-1 bg-black/60 rounded-lg border border-red-900/30 p-3 overflow-x-auto custom-scrollbar">
                        <div className="text-xs font-mono text-red-300/80 whitespace-pre-wrap">
                          {t.failure_payload.stack_trace}
                        </div>
                     </div>
                     <div className="text-xs text-gray-500 font-mono mt-1 flex items-center justify-end gap-2">
                       Failed at tick: <span className="text-red-400 font-bold bg-red-950 px-2 py-0.5 rounded">{t.failure_payload.failed_log_tick}</span>
                     </div>
                  </div>

                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
