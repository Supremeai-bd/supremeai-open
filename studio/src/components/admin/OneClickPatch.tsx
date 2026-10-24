import React, { useState } from 'react';
import { apiClient } from '../../services/apiClient';

interface FixProposal {
  id: string;
  issueId: string;
  description: string;
  beforeCode: string;
  afterCode: string;
  status: 'pending_review' | 'applied' | 'rejected';
}

interface OneClickPatchProps {
  proposals: FixProposal[];
  onPatchApplied: () => void;
}

export const OneClickPatch: React.FC<OneClickPatchProps> = ({ proposals, onPatchApplied }) => {
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleApplyPatch = async (id: string) => {
    if (!window.confirm('Apply this self-heal patch? It modifies production code and cannot be undone automatically.')) {
      return;
    }
    setApplyingId(id);
    setError(null);
    try {
      await apiClient.post(`/api/admin/fixes/apply`, { fixId: id });
      onPatchApplied();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to apply patch.');
    } finally {
      setApplyingId(null);
    }
  };

  if (proposals.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center">
        <h3 className="text-sm font-semibold text-slate-400">No Pending Fixes</h3>
        <p className="text-xs text-slate-500 mt-1">SelfHealer Service has not detected any issues requiring manual review.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded border border-red-900 bg-red-900/20 p-3 text-xs text-red-400">
          {error}
        </div>
      )}
      {proposals.map((proposal) => (
        <div key={proposal.id} className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden">
          <div className="flex items-center justify-between bg-slate-950 p-4 border-b border-slate-800">
            <div>
              <h4 className="text-sm font-bold text-cyan-400 font-mono">SelfHealer Proposal #{proposal.id.slice(0,6)}</h4>
              <p className="text-xs text-slate-400 mt-1">{proposal.description}</p>
            </div>
            <button
              onClick={() => handleApplyPatch(proposal.id)}
              disabled={applyingId === proposal.id || proposal.status !== 'pending_review'}
              className="rounded bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition-colors"
            >
              {applyingId === proposal.id ? 'Applying...' : 'Apply Patch'}
            </button>
          </div>

          {/* Diff Viewer */}
          <div className="grid grid-cols-2 divide-x divide-slate-800">
            <div className="p-4">
              <span className="text-[10px] uppercase tracking-widest text-red-400 font-bold mb-2 block">Before (Issue)</span>
              <pre className="text-[11px] font-mono text-slate-300 overflow-x-auto bg-slate-950 p-3 rounded border border-red-900/30 whitespace-pre-wrap">
                {proposal.beforeCode}
              </pre>
            </div>
            <div className="p-4">
              <span className="text-[10px] uppercase tracking-widest text-emerald-400 font-bold mb-2 block">After (Fix)</span>
              <pre className="text-[11px] font-mono text-slate-300 overflow-x-auto bg-slate-950 p-3 rounded border border-emerald-900/30 whitespace-pre-wrap">
                {proposal.afterCode}
              </pre>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};
