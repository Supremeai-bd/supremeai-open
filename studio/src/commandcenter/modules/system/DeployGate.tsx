import { useState } from 'react';
import { useDeployGate, useToggleDeployGate } from '../../data/hooks';
import { GaugeRing, ConfirmModal, EmptyState } from '../../kit';

export function DeployGate() {
  const { data: gate, isLoading } = useDeployGate();
  const toggleGate = useToggleDeployGate();

  const [showToggle, setShowToggle] = useState(false);
  const [otp, setOtp] = useState('');
  const [reason, setReason] = useState('');

  const handleToggle = () => {
    if (gate) {
      toggleGate.mutate({ status: gate.status === 'LOCKED' ? 'UNLOCKED' : 'LOCKED', reason: otp || reason });
      setShowToggle(false);
      setOtp('');
      setReason('');
    }
  };

  if (!gate && isLoading) {
    return <EmptyState title="ডিপ্লয় গেট লোড হচ্ছে..." message="গেট স্ট্যাটাস ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Deploy Gate</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-8 flex flex-col items-center gap-4">
        <GaugeRing
          value={gate?.status === 'LOCKED' ? 0 : 100}
          size={120}
          label={gate?.status === 'LOCKED' ? 'LOCKED' : 'UNLOCKED'}
          sublabel="DEPLOY GATE"
          tone={gate?.status === 'LOCKED' ? 'rose' : 'emerald'}
        />
        <div className="text-[10px] font-mono text-[var(--sa-text-2)]">
          {gate?.updated_at && `Updated: ${gate.updated_at}`}
        </div>
        {gate?.reason && (
          <div className="text-[9px] font-mono text-[var(--sa-text-3)]">Reason: {gate.reason}</div>
        )}
        <button
          onClick={() => setShowToggle(true)}
          className={`px-4 py-2 rounded-lg text-[10px] font-mono border transition-colors ${
            gate?.status === 'LOCKED'
              ? 'border-[#10b981]/30 text-[#10b981] hover:bg-[#10b981]/10'
              : 'border-[#ef4444]/30 text-[#ef4444] hover:bg-[#ef4444]/10'
          }`}
        >
          {gate?.status === 'LOCKED' ? 'UNLOCK GATE (OTP)' : 'LOCK GATE (OTP)'}
        </button>
      </div>
      <ConfirmModal
        open={showToggle}
        title={gate?.status === 'LOCKED' ? 'গেট আনলক' : 'গেট লক'}
        message="নিশ্চিত করতে OTP দিন"
        onCancel={() => { setShowToggle(false); setOtp(''); setReason(''); }}
        onConfirm={handleToggle}
      />
    </div>
  );
}
