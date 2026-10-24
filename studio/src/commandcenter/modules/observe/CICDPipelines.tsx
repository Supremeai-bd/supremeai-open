import { useCIReports } from '../../data/hooks';
import { StatusPill, EmptyState } from '../../kit';

export function CICDPipelines() {
  const { data: ciReports, isLoading } = useCIReports(20, 15_000);

  if (!ciReports && isLoading) {
    return <EmptyState title="CI/CD লোড হচ্ছে..." message="পাইপলাইন ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">CI/CD Pipelines</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] overflow-hidden">
        <table className="w-full text-[10px] font-mono">
          <thead className="bg-[var(--sa-bg-2)] text-[var(--sa-text-2)]">
            <tr>
              <th className="text-left p-2">STATUS</th>
              <th className="text-left p-2">MESSAGE</th>
              <th className="text-left p-2">BRANCH</th>
              <th className="text-left p-2">DURATION</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--sa-line)]">
            {(ciReports ?? []).map((run) => (
              <tr key={run.id} className="hover:bg-[var(--sa-bg-active)]">
                <td className="p-2"><StatusPill status={run.status} size="sm" /></td>
                <td className="p-2 text-[var(--sa-text-1)]">{run.message}</td>
                <td className="p-2 text-[var(--sa-text-2)]">{run.branch ?? '—'}</td>
                <td className="p-2 text-[var(--sa-text-2)]">{run.duration_sec ? `${run.duration_sec}s` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(ciReports ?? []).length === 0 && (
          <div className="p-4 text-center text-[var(--sa-text-2)]">কোন CI রান নেই</div>
        )}
      </div>
    </div>
  );
}
