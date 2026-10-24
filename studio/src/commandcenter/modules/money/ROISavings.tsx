import { useROI } from '../../data/hooks';
import { KpiTile, EmptyState } from '../../kit';

export function ROISavings() {
  const { data: roi, isLoading } = useROI(60_000);

  if (!roi && isLoading) {
    return <EmptyState title="ROI লোড হচ্ছে..." message="সেমান্টিক ক্যাচ হিট-রেট ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">ROI Savings</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile label="CACHE HITS" value={roi?.semantic_cache_hits ?? null} tone="cyan" />
        <KpiTile label="USD SAVED" value={roi?.estimated_usd_saved ?? null} unit="$" tone="emerald" />
        <KpiTile label="PREVENTED" value={roi?.duplicate_executions_prevented ?? null} tone="amber" />
        <KpiTile label="COST REDUCTION" value={roi?.api_cost_reduction_ratio != null ? Math.round(roi.api_cost_reduction_ratio * 100) : null} unit="%" tone="violet" />
      </div>
    </div>
  );
}
