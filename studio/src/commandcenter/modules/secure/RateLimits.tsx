import { useRateLimits } from '../../data/hooks';
import { EmptyState } from '../../kit';

export function RateLimits() {
  const { data: limits, isLoading } = useRateLimits(30_000);

  if (!limits && isLoading) {
    return <EmptyState title="রেট লিমিট লোড হচ্ছে..." message="রেট লিমিট ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Rate Limits</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">429 EVENTS</div>
          <div className="text-3xl font-mono text-[#f59e0b]">{limits?.current_429_events ?? 0}</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">PER-IP LIMITS</div>
          <div className="space-y-1">
            {limits?.per_ip && Object.keys(limits.per_ip).length > 0 ? (
              Object.entries(limits.per_ip).map(([ip, info]) => (
                <div key={ip} className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-[var(--sa-text-1)]">{ip}</span>
                  <span className="text-[var(--sa-text-2)]">{info.used}/{info.limit}</span>
                </div>
              ))
            ) : (
              <div className="text-[10px] font-mono text-[var(--sa-text-2)]">কোন IP ডেটা নেই</div>
            )}
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">PER-TENANT LIMITS</div>
        <div className="space-y-1">
          {limits?.per_tenant && Object.keys(limits.per_tenant).length > 0 ? (
            Object.entries(limits.per_tenant).map(([tenant, info]) => (
              <div key={tenant} className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-[var(--sa-text-1)]">{tenant}</span>
                <span className="text-[var(--sa-text-2)]">{info.used}/{info.limit}</span>
              </div>
            ))
          ) : (
            <div className="text-[10px] font-mono text-[var(--sa-text-2)]">কোন টেন্যান্ট ডেটা নেই</div>
          )}
        </div>
      </div>
    </div>
  );
}
