import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../../services/apiClient';
import { adminTokenStore } from '../../../services/adminTokenStore';

interface PendingApproval {
  id?: string;
  task_id?: string;
  proposed_action?: string;
  action?: string;
  target?: string;
  requester?: string;
  requester_id?: string;
  status?: string;
  expires_at?: string | number;
  created_at?: string | number;
  [key: string]: unknown;
}

const getId = (a: PendingApproval): string => String(a.id ?? a.task_id ?? '');

export function ApprovalQueue() {
  const qc = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [otp, setOtp] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const hasToken = () => !!adminTokenStore.getDecodedToken();

  const { data, isLoading, error: fetchError, refetch } = useQuery({
    queryKey: ['hitl-pending'],
    queryFn: () => apiClient.get<PendingApproval[] | { records?: PendingApproval[]; approvals?: PendingApproval[] }>('/api/v1/hitl/pending'),
    enabled: hasToken(),
    refetchInterval: 15_000,
  });

  const approvals: PendingApproval[] = Array.isArray(data)
    ? data
    : (data as { records?: PendingApproval[]; approvals?: PendingApproval[] })?.records
      || (data as { approvals?: PendingApproval[] })?.approvals
      || [];

  const approveMutation = useMutation({
    mutationFn: ({ id, otpCode }: { id: string; otpCode: string }) =>
      apiClient.post(`/api/v1/hitl/approve/${encodeURIComponent(id)}`, { resolved_by: 'admin', reason: reason || null, otp: otpCode || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl-pending'] });
      setActiveId(null);
      setOtp('');
      setReason('');
      setError(null);
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, r }: { id: string; r: string }) =>
      apiClient.post(`/api/v1/hitl/reject/${encodeURIComponent(id)}`, { resolved_by: 'admin', reason: r }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl-pending'] });
      setActiveId(null);
      setReason('');
      setError(null);
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
  });

  const cancelMutation = useMutation({
    mutationFn: ({ id, r }: { id: string; r: string }) =>
      apiClient.post(`/api/v1/hitl/cancel/${encodeURIComponent(id)}`, { resolved_by: 'admin', reason: r }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl-pending'] });
      setActiveId(null);
      setReason('');
      setError(null);
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
  });

  const fetchErrorMessage = fetchError
    ? (fetchError instanceof Error ? fetchError.message : String(fetchError))
    : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--sa-ink-muted)]">
          {approvals.length} pending
        </span>
        <button
          type="button"
          onClick={() => refetch()}
          className="text-xs text-cyan-300 hover:text-cyan-200"
        >
          Refresh
        </button>
      </div>

      {fetchErrorMessage && (
        <div className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">
          Approval fetch failed: {fetchErrorMessage}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </div>
      )}

      {isLoading && approvals.length === 0 && (
        <div className="text-xs text-[var(--sa-ink-muted)]">Loading approvals…</div>
      )}

      {!isLoading && approvals.length === 0 && !fetchErrorMessage && (
        <div className="rounded-xl border border-dashed border-[var(--sa-border)] p-6 text-center text-xs text-[var(--sa-ink-muted)]">
          No pending approvals.
        </div>
      )}

      <ul className="space-y-3">
        {approvals.map((a) => {
          const id = getId(a);
          const isActive = activeId === id;
          return (
            <li key={id} className="rounded-xl border border-[var(--sa-border)] bg-black/20 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-[var(--sa-ink)] truncate">
                    {String(a.proposed_action ?? a.action ?? 'Pending action')}
                  </p>
                  <p className="text-xs text-[var(--sa-ink-muted)]">
                    {a.target ? `target: ${String(a.target)} · ` : ''}
                    {a.requester ? `requester: ${String(a.requester)} · ` : ''}
                    {a.status ? `status: ${String(a.status)}` : ''}
                  </p>
                  {a.expires_at && (
                    <p className="text-xs text-[var(--sa-ink-muted)]">
                      expires: {String(a.expires_at)}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setActiveId(isActive ? null : id)}
                  className="text-xs text-cyan-300 hover:text-cyan-200"
                >
                  {isActive ? 'Close' : 'Decide'}
                </button>
              </div>

              {isActive && (
                <div className="mt-3 space-y-2">
                  <input
                    type="text"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    placeholder="OTP code (required to approve)"
                    className="w-full rounded-lg border border-[var(--sa-border)] bg-black/30 px-3 py-2 text-xs text-[var(--sa-ink)]"
                  />
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Reason (required to reject/cancel)"
                    className="w-full rounded-lg border border-[var(--sa-border)] bg-black/30 px-3 py-2 text-xs text-[var(--sa-ink)]"
                    rows={2}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={approveMutation.isPending || !otp.trim()}
                      onClick={() => approveMutation.mutate({ id, otpCode: otp.trim() })}
                      className="rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-semibold text-emerald-200 disabled:opacity-50"
                    >
                      {approveMutation.isPending ? 'Approving…' : 'Approve (OTP)'}
                    </button>
                    <button
                      type="button"
                      disabled={rejectMutation.isPending || !reason.trim()}
                      onClick={() => rejectMutation.mutate({ id, r: reason.trim() })}
                      className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3 py-1.5 text-xs font-semibold text-rose-200 disabled:opacity-50"
                    >
                      {rejectMutation.isPending ? 'Rejecting…' : 'Reject'}
                    </button>
                    <button
                      type="button"
                      disabled={cancelMutation.isPending}
                      onClick={() => cancelMutation.mutate({ id, r: reason.trim() || 'cancelled' })}
                      className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-xs font-semibold text-amber-200 disabled:opacity-50"
                    >
                      {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
                    </button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default ApprovalQueue;
