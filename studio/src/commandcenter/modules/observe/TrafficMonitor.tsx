import { useTraffic } from '../../data/hooks';
import { Sparkline, EmptyState } from '../../kit';

export function TrafficMonitor() {
  const { data: traffic, isLoading } = useTraffic(5_000);

  if (!traffic && isLoading) {
    return <EmptyState title="ট্রাফিক লোড হচ্ছে..." message="লাইভ ট্রাফিক ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Traffic Monitor</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">CURRENT RPS</div>
          <div className="flex items-center gap-4">
            <div className="text-4xl font-mono text-[#00f3ff]">{traffic?.current_rps ?? '—'}</div>
            <span className="text-[10px] font-mono text-[var(--sa-text-2)]">REQUESTS / SEC</span>
          </div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">DISTRIBUTION</div>
          <div className="space-y-2">
            {traffic?.distribution && Object.entries(traffic.distribution).length > 0 ? (
              Object.entries(traffic.distribution).map(([provider, count]) => (
                <div key={provider} className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-[var(--sa-text-1)]">{provider}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-[var(--sa-bg-0)] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#00f3ff] rounded-full"
                        style={{ width: `${Math.min(100, (count / (traffic.current_rps || 1)) * 100)}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-[var(--sa-text-2)] w-8 text-right">{count}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[10px] font-mono text-[var(--sa-text-2)]">কোন ডিস্ট্রিবিউশন ডেটা নেই</div>
            )}
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">30 MIN WINDOW</div>
        <Sparkline data={traffic?.window_30min ?? []} height={60} width={600} color="#00f3ff" />
      </div>
    </div>
  );
}
