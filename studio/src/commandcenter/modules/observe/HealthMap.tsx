import { useHealthMap } from '../../data/hooks';
import { GaugeRing, StatusPill, EmptyState } from '../../kit';

export function HealthMap() {
  const { data: health, isLoading } = useHealthMap(30_000);

  if (!health && isLoading) {
    return <EmptyState title="হেল্থ ম্যাপ লোড হচ্ছে..." message="ইনফ্রা স্ট্যাটাস ফেচ করা হচ্ছে..." loading />;
  }

  const nodes = [
    { name: 'GCP', status: health?.gcp?.status ?? 'unknown', latency: health?.gcp?.latency },
    { name: 'RAILWAY', status: health?.railway?.status ?? 'unknown', latency: health?.railway?.latency },
    { name: 'RENDER', status: health?.render?.status ?? 'unknown', latency: health?.render?.latency },
  ];

  if (health?.core_services) {
    Object.entries(health.core_services).forEach(([name, node]) => {
      nodes.push({ name: name.toUpperCase(), status: node.status, latency: node.latency });
    });
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Health Map</h2>
      <div className="flex items-center justify-center">
        <GaugeRing
          value={health?.overall_health_percent ?? 0}
          size={140}
          label="SYSTEM"
          sublabel="HEALTH"
          tone={health && health.overall_health_percent != null && health.overall_health_percent < 70 ? 'rose' : 'cyan'}
        />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {nodes.map((node) => (
          <div key={node.name} className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-3 flex flex-col items-center gap-2">
            <StatusPill status={node.status} label={node.name} size="md" />
            {node.latency != null && (
              <span className="text-[10px] font-mono text-[var(--sa-text-2)]">{node.latency}ms</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
