/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect } from 'react';
import { Card, Badge } from '../ui';
import { RefreshCw, ShieldAlert, ShieldCheck, Clock, CheckCircle2, AlertTriangle } from 'lucide-react';
import { apiClient } from '../../services/apiClient';

interface RenderAccountStatus {
  role: string;
  account_key: string;
  plan: string;
  status: 'ready' | 'cooldown' | 'blocked' | 'recheck_required' | 'unknown' | 'error';
  reason?: string;
  usage_minutes?: number;
  safe_build_minutes?: number;
  recheck_at?: string;
  last_checked_at?: string;
  retry_count: number;
  source: string;
  confidence?: 'verified' | 'estimated' | 'unknown';
  state?: 'verified' | 'estimated' | 'unknown';
  billing_period_start?: string;
  billing_period_end?: string;
  remaining?: number;
  limit?: number;
}

interface PreflightOverview {
  deployment_allowed: boolean;
  required_roles: string[] | string;
  accounts: RenderAccountStatus[];
  checked_at: string;
}

export function RenderPreflightWidget() {
  const [overview, setOverview] = useState<PreflightOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionRole, setActionRole] = useState<string | null>(null);
  const [overrideModalRole, setOverrideModalRole] = useState<string | null>(null);
  const [overrideStatus, setOverrideStatus] = useState<'ready' | 'blocked' | 'cooldown'>('ready');
  const [overrideReason, setOverrideReason] = useState('');

  const fetchPreflight = async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<PreflightOverview>('/api/v1/admin/render/preflight');
      setOverview(data);
    } catch (err) {
      console.error('Failed to fetch Render preflight:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPreflight();
  }, []);

  const handleRecheck = async (role: string, force: boolean = false) => {
    setActionRole(role);
    try {
      await apiClient.post(`/api/v1/admin/render/accounts/${role}/recheck`, { force });
      await fetchPreflight();
    } catch (err: any) {
      alert(`Recheck failed: ${err?.message || err}`);
    } finally {
      setActionRole(null);
    }
  };

  const handleOverrideSubmit = async () => {
    if (!overrideModalRole || !overrideReason.trim()) return;
    setActionRole(overrideModalRole);
    try {
      await apiClient.post(`/api/v1/admin/render/accounts/${overrideModalRole}/override`, {
        status: overrideStatus,
        reason: overrideReason,
      });
      setOverrideModalRole(null);
      setOverrideReason('');
      await fetchPreflight();
    } catch (err: any) {
      alert(`Override failed: ${err?.message || err}`);
    } finally {
      setActionRole(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ready':
        return <Badge variant="success">READY</Badge>;
      case 'cooldown':
        return <Badge variant="warning">COOLDOWN</Badge>;
      case 'recheck_required':
        return <Badge variant="info">RECHECK REQ</Badge>;
      case 'blocked':
        return <Badge variant="danger">BLOCKED</Badge>;
      default:
        return <Badge variant="default">{status.toUpperCase()}</Badge>;
    }
  };

  return (
    <Card
      title="Render Account Preflight & Build Quotas"
      icon={overview?.deployment_allowed ? <ShieldCheck className="text-emerald-400" size={16} /> : <ShieldAlert className="text-amber-400" size={16} />}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-mono">Deploy Gate:</span>
          {overview?.deployment_allowed ? (
            <span className="text-xs font-bold text-emerald-400 flex items-center gap-1 font-mono">
              <CheckCircle2 size={12} /> ALLOWED
            </span>
          ) : (
            <span className="text-xs font-bold text-rose-400 flex items-center gap-1 font-mono">
              <AlertTriangle size={12} /> BLOCKED (Quota/Cooldown)
            </span>
          )}
        </div>
        <button
          onClick={fetchPreflight}
          disabled={loading}
          className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:text-white text-[10px] font-mono transition-colors"
        >
          <RefreshCw size={10} className={loading ? 'animate-spin' : ''} /> Refresh All
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        {overview?.accounts.map((acc) => (
          <div key={acc.role} className="p-3 rounded-lg border border-slate-800 bg-slate-900/50 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold font-mono text-[#00f3ff] uppercase tracking-wider">{acc.role}</span>
                {getStatusBadge(acc.status)}
              </div>
              <div className="text-[11px] text-slate-300 font-mono mb-1">
                Usage: <span className="text-white font-bold">{acc.usage_minutes ?? '—'}</span> / {acc.safe_build_minutes ?? acc.limit ?? 'unknown'}m
                <span className="text-slate-500 text-[10px] ml-1.5">({acc.plan} plan)</span>
              </div>
              <div className="text-[10px] text-slate-500 font-mono mb-1">
                Source: <span className={acc.confidence === 'verified' ? 'text-emerald-400' : 'text-amber-400'}>{acc.confidence ?? acc.state ?? 'unknown'}</span> · {acc.source || 'unknown'}
              </div>
              {acc.remaining != null && <div className="text-[10px] text-slate-400 font-mono mb-1">Remaining: {acc.remaining}m</div>}
              {acc.reason && <div className="text-[10px] text-slate-400 truncate mb-1">Reason: {acc.reason}</div>}
              {acc.recheck_at && (
                <div className="text-[10px] text-amber-400 flex items-center gap-1 font-mono mb-1">
                  <Clock size={10} /> Recheck at: {new Date(acc.recheck_at).toLocaleString()}
                </div>
              )}
            </div>

            <div className="flex gap-2 mt-3 pt-2 border-t border-slate-800/80">
              <button
                onClick={() => handleRecheck(acc.role, false)}
                disabled={actionRole === acc.role}
                className="flex-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono transition-colors"
              >
                Recheck
              </button>
              <button
                onClick={() => handleRecheck(acc.role, true)}
                disabled={actionRole === acc.role}
                className="px-2 py-1 rounded bg-cyan-950/60 border border-cyan-800/50 hover:bg-cyan-900/60 text-cyan-300 text-[10px] font-mono transition-colors"
                title="Force audit ignoring cooldown"
              >
                Force
              </button>
              <button
                onClick={() => {
                  setOverrideModalRole(acc.role);
                  setOverrideStatus(acc.status === 'ready' ? 'blocked' : 'ready');
                }}
                disabled={actionRole === acc.role}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-[10px] font-mono transition-colors"
              >
                Override
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Override Modal */}
      {overrideModalRole && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-sm rounded-xl border border-slate-800 bg-[#0a0f1d] p-5 shadow-2xl">
            <h3 className="text-sm font-bold font-mono text-white mb-2">
              Manual Override: <span className="text-[#00f3ff] uppercase">{overrideModalRole}</span>
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Explicit manual override creates an audit trail event in the database.
            </p>

            <div className="mb-3">
              <label className="text-[11px] font-mono text-slate-300 block mb-1">Target Status:</label>
              <select
                value={overrideStatus}
                onChange={(e) => setOverrideStatus(e.target.value as any)}
                className="w-full rounded border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-cyan-500"
              >
                <option value="ready">ready</option>
                <option value="blocked">blocked</option>
                <option value="cooldown">cooldown</option>
              </select>
            </div>

            <div className="mb-4">
              <label className="text-[11px] font-mono text-slate-300 block mb-1">Reason (required):</label>
              <input
                type="text"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="e.g. Approved monthly budget extension"
                className="w-full rounded border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setOverrideModalRole(null)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-400 hover:text-white text-xs font-mono"
              >
                Cancel
              </button>
              <button
                onClick={handleOverrideSubmit}
                disabled={!overrideReason.trim()}
                className="px-3 py-1.5 rounded bg-[#00f3ff] text-black font-bold text-xs font-mono hover:bg-cyan-400 disabled:opacity-50"
              >
                Apply Override
              </button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
