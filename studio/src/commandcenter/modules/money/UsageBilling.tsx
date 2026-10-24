import { useState } from 'react';
import { useUsage, useBudgetCaps, useUpdateBudgetCap } from '../../data/hooks';
import { ConfirmModal, EmptyState, Sparkline } from '../../kit';

export function UsageBilling() {
  const { data: usage, isLoading } = useUsage(60_000);
  const { data: budget } = useBudgetCaps();
  const updateBudget = useUpdateBudgetCap();

  const [showEdit, setShowEdit] = useState(false);
  const [otp, setOtp] = useState('');
  const [newCap, setNewCap] = useState(budget?.default_cap?.toString() ?? '');

  const last30Days = usage?.daily?.slice(-30) ?? [];

  if (!usage && isLoading) {
    return <EmptyState title="ব্যবহার লোড হচ্ছে..." message="ব্যবহার ও বিলিং ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  const handleSave = () => {
    updateBudget.mutate({ default_cap: parseFloat(newCap) || 0, otp });
    setShowEdit(false);
    setOtp('');
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Usage & Billing</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#00f3ff]">${usage?.cost_per_hour?.toFixed(2) ?? '0.00'}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Cost / Hour</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#f59e0b]">${usage?.cost_projected_monthly?.toFixed(2) ?? '0.00'}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Forecast / Month</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#10b981]">{last30Days.reduce((s, d) => s + d.total_cost, 0).toFixed(2)}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">30d Total</div>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)]">DAILY SPEND (30 DAYS)</div>
          <button
            onClick={() => setShowEdit(true)}
            className="px-2 py-1 rounded border border-[#bc13fe]/30 text-[#bc13fe] text-[9px] font-mono hover:bg-[#bc13fe]/10"
          >
            EDIT CAP (OTP)
          </button>
        </div>
        <Sparkline
          data={last30Days.map(d => d.total_cost)}
          height={60}
          width={500}
          color="#00f3ff"
        />
      </div>

      <ConfirmModal
        open={showEdit}
        title="বাজেট ক্যাপ আপডেট"
        message="নিশ্চিত করতে OTP এবং নতুন ক্যাপ দিন"
        onCancel={() => { setShowEdit(false); setOtp(''); }}
        onConfirm={handleSave}
      >
        <div className="space-y-2 mt-2">
          <input
            type="number"
            value={newCap}
            onChange={e => setNewCap(e.target.value)}
            placeholder="নতুন ক্যাপ ($)"
            className="w-full bg-[var(--sa-bg-0)] border border-[var(--sa-line)] rounded px-2 py-1 text-xs text-[var(--sa-text-0)] font-mono"
          />
          <input
            type="text"
            value={otp}
            onChange={e => setOtp(e.target.value)}
            placeholder="OTP Code"
            className="w-full bg-[var(--sa-bg-0)] border border-[var(--sa-line)] rounded px-2 py-1 text-xs text-[var(--sa-text-0)] font-mono"
          />
        </div>
      </ConfirmModal>
    </div>
  );
}
