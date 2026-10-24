import { useSwarm } from '../../data/hooks';
import { EmptyState, StatusPill } from '../../kit';

export function Swarm() {
  const { data: swarm, isLoading } = useSwarm();

  if (!swarm && isLoading) {
    return <EmptyState title="সোয়ার্ম লোড হচ্ছে..." message="নোড গ্রাফ ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Swarm Graph</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-8 flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="text-[var(--sa-text-2)] text-[10px] font-mono">
            {(swarm?.nodes?.length ?? 0)} NODES · {(swarm?.edges?.length ?? 0)} EDGES
          </div>
          <div className="flex flex-wrap justify-center gap-2">
            {(swarm?.nodes ?? []).map((node) => (
              <div
                key={node.id}
                className="px-3 py-2 rounded-lg border border-[var(--sa-line)] bg-[var(--sa-bg-0)] flex items-center gap-2"
              >
                <StatusPill status={node.status} label={node.name} size="sm" />
                {node.load != null && (
                  <span className="text-[9px] font-mono text-[var(--sa-text-2)]">{Math.round(node.load * 100)}%</span>
                )}
              </div>
            ))}
          </div>
          <div className="text-[9px] font-mono text-[var(--sa-text-3)]">
            ReactFlow integration pending — placeholder view
          </div>
        </div>
      </div>
    </div>
  );
}
