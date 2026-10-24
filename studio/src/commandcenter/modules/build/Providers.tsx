import React from 'react';
import { useProviders } from '../../data/hooks';
import { Sparkline, StatusPill, EmptyState } from '../../kit';

export function Providers() {
  const { data: providers, isLoading } = useProviders(10_000);

  if (!providers && isLoading) {
    return <EmptyState title="প্রোভাইডার লোড হচ্ছে..." message="প্রোভাইডার ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Providers</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(providers ?? []).map((provider) => (
          <div key={provider.id} className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold text-[var(--sa-text-0)]">{provider.name}</span>
              <StatusPill status={provider.status} size="sm" />
            </div>
            <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase">Mode: {provider.mode}</div>
            {provider.latency_history && provider.latency_history.length > 0 && (
              <Sparkline data={provider.latency_history} height={32} color="#00f3ff" />
            )}
            <div className="flex items-center justify-between text-[9px] font-mono">
              <span className="text-[var(--sa-text-2)]">LATENCY</span>
              <span className="text-[var(--sa-text-1)]">{provider.latency_ms ?? '—'}ms</span>
            </div>
            <div className="flex items-center justify-between text-[9px] font-mono">
              <span className="text-[var(--sa-text-2)]">RATE LIMIT</span>
              <span className="text-[var(--sa-text-1)]">{provider.rate_limit_remaining ?? '—'}/{provider.rate_limit_max ?? '—'}</span>
            </div>
            <div className="flex flex-wrap gap-1">
              {provider.models.map((model) => (
                <span key={model} className="px-2 py-0.5 rounded bg-[var(--sa-bg-0)] text-[8px] font-mono text-[var(--sa-text-2)] border border-[var(--sa-line)]">
                  {model}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
