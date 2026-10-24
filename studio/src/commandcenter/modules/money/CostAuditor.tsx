import { useCostReport, useBudgetCaps } from '../../data/hooks';
import { EmptyState } from '../../kit';

export function CostAuditor() {
  const { data: cost, isLoading } = useCostReport();
  const { data: budget } = useBudgetCaps();

  if (!cost && isLoading) {
    return <EmptyState title="কস্ট লোড হচ্ছে..." message="কস্ট রিপোর্ট ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Cost Auditor</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <pre className="text-[10px] font-mono text-[var(--sa-text-1)] whitespace-pre-wrap">
          {cost?.report ?? 'কোন কস্ট রিপোর্ট নেই'}
        </pre>
        {cost?.generated_at && (
          <div className="text-[9px] font-mono text-[var(--sa-text-3)] mt-2">Generated: {cost.generated_at}</div>
        )}
      </div>
      {budget && (
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-2">BUDGET CAPS</div>
          <div className="text-[10px] font-mono text-[var(--sa-text-1)]">
            Default cap: ${budget.default_cap}
          </div>
          <div className="text-[9px] font-mono text-[var(--sa-text-3)] mt-1">
            Per-tenant caps: {Object.keys(budget.per_tenant).length} configured
          </div>
        </div>
      )}
    </div>
  );
}
