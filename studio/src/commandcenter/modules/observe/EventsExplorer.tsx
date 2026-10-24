import { useDashboardEvents } from '../../data/hooks';
import { Timeline, EmptyState } from '../../kit';

export function EventsExplorer() {
  const { data: events, isLoading } = useDashboardEvents(100, 10_000);

  if (!events && isLoading) {
    return <EmptyState title="ইভেন্ট লোড হচ্ছে..." message="ইভেন্ট স্ট্রিম অপেক্ষায়..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Events Explorer</h2>
      <Timeline events={(events ?? []).map(e => ({ ...e, id: `${e.timestamp}-${e.source}` }))} />
    </div>
  );
}
