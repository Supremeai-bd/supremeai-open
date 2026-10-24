import { useState } from 'react';
import { useFeatureFlags, useUpdateFeatureFlag } from '../../data/hooks';
import { ConfirmModal, EmptyState } from '../../kit';

export function FeatureFlags() {
  const { data: flags, isLoading } = useFeatureFlags(120_000);
  const updateFlag = useUpdateFeatureFlag();
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [otp, setOtp] = useState('');
  const [rollout, setRollout] = useState(0);
  const [enabled, setEnabled] = useState(false);

  const handleSave = () => {
    if (editingKey) {
      updateFlag.mutate({ key: editingKey, enabled, rollout_percent: rollout, otp });
      setEditingKey(null);
      setOtp('');
    }
  };

  if (!flags && isLoading) {
    return <EmptyState title="ফ্ল্যাগ লোড হচ্ছে..." message="ফিচার ফ্ল্যাগ ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Feature Flags</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] overflow-hidden">
        <div className="divide-y divide-[var(--sa-line)]">
          {(flags ?? []).map((flag) => (
            <div key={flag.key} className="p-3 flex items-center justify-between">
              <div className="flex-1">
                <div className="text-[10px] font-mono text-[var(--sa-text-0)]">{flag.key}</div>
                <div className="text-[9px] font-mono text-[var(--sa-text-3)]">
                  {flag.environment.toUpperCase()} · Rollout: {flag.rollout_percent}%
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-[9px] font-mono px-2 py-1 rounded ${flag.enabled ? 'bg-[#10b981]/10 text-[#10b981]' : 'bg-[var(--sa-bg-0)] text-[var(--sa-text-2)]'}`}>
                  {flag.enabled ? 'ON' : 'OFF'}
                </span>
                <button
                  onClick={() => { setEditingKey(flag.key); setEnabled(flag.enabled); setRollout(flag.rollout_percent); setOtp(''); }}
                  className="px-2 py-1 rounded border border-[var(--sa-line)] text-[9px] font-mono text-[var(--sa-text-2)] hover:text-[var(--sa-text-0)]"
                >
                  EDIT
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
      <ConfirmModal
        open={!!editingKey}
        title="ফ্ল্যাগ আপডেট"
        message={`${editingKey} আপডেট করতে OTP দিন`}
        onCancel={() => { setEditingKey(null); setOtp(''); }}
        onConfirm={handleSave}
      />
    </div>
  );
}
