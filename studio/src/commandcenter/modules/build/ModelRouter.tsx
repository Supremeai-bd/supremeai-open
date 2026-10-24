import React, { useState } from 'react';
import { useRouterConfig, useProviders } from '../../data/hooks';
import { useUpdateRules } from '../../data/hooks';
import { StatusPill, ConfirmModal, EmptyState } from '../../kit';

export function ModelRouter() {
  const { data: router, isLoading: routerLoading } = useRouterConfig();
  const { data: providers } = useProviders();
  const updateRules = useUpdateRules();

  const [showOverride, setShowOverride] = useState(false);
  const [otp, setOtp] = useState('');
  const [costQuality, setCostQuality] = useState(router?.cost_quality_preference ?? 0.5);

  if (routerLoading && !router) {
    return <EmptyState title="রাউটার লোড হচ্ছে..." message="মডেল রাউটার কনফিগ ফেচ করা হচ্ছে..." loading />;
  }

  const handleSaveRules = () => {
    updateRules.mutate({ cost_quality_preference: costQuality, otp });
    setShowOverride(false);
    setOtp('');
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Model Router</h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">PROVIDER ORDER</div>
          <div className="space-y-2">
            {(router?.provider_order ?? []).map((provider, i) => (
              <div key={provider} className="flex items-center gap-3 px-3 py-2 rounded-lg border border-[var(--sa-line)] bg-[var(--sa-bg-0)]">
                <span className="text-[10px] font-mono text-[var(--sa-text-2)] w-4">{i + 1}</span>
                <span className="text-[10px] font-mono text-[var(--sa-text-1)] flex-1">{provider}</span>
                <StatusPill status={providers?.find(p => p.name === provider)?.status ?? 'unknown'} size="sm" />
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 space-y-4">
          <div>
            <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-2">COST / QUALITY SLIDER</div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={costQuality}
              onChange={(e) => setCostQuality(parseFloat(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-[9px] font-mono text-[var(--sa-text-2)] mt-1">
              <span>COST</span>
              <span>QUALITY</span>
            </div>
          </div>
          {router?.a_b_split && Object.keys(router.a_b_split).length > 0 && (
            <div>
              <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-2">A/B SPLIT</div>
              <div className="space-y-1">
                {Object.entries(router.a_b_split).map(([provider, pct]) => (
                  <div key={provider} className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-[var(--sa-text-1)]">{provider}</span>
                    <span className="text-[10px] font-mono text-[#00f3ff]">{Math.round(pct * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={() => setShowOverride(true)}
            className="w-full px-3 py-2 rounded-lg border border-[#bc13fe]/30 text-[#bc13fe] text-[9px] font-mono hover:bg-[#bc13fe]/10 transition-colors"
          >
            OVERRIDE ROUTER (OTP)
          </button>
        </div>
      </div>

      <ConfirmModal
        open={showOverride}
        title="রাউটার ওভাররাইড"
        message="রাউটার কনফিগ আপডেট করতে OTP দিন"
        onCancel={() => { setShowOverride(false); setOtp(''); }}
        onConfirm={handleSaveRules}
      />
    </div>
  );
}
