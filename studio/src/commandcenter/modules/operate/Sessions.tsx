import { useSessions } from '../../data/hooks';
import { DataTable, EmptyState } from '../../kit';
import type {} from '../../data/types';

export function Sessions() {
  const { data: sessions, isLoading } = useSessions();

  const columns = [
    { key: 'id', label: 'ID', width: '20%' },
    { key: 'user_id', label: 'USER', width: '20%' },
    { key: 'status', label: 'STATUS', width: '15%' },
    { key: 'started_at', label: 'STARTED', width: '20%' },
    { key: 'last_active', label: 'LAST ACTIVE', width: '20%' },
    { key: 'ip', label: 'IP', width: '15%' },
  ];

  if (!sessions && isLoading) {
    return <EmptyState title="সেশন লোড হচ্ছে..." message="সেশন ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Sessions</h2>
      <DataTable columns={columns} data={sessions ?? []} rowKey={(s) => s.id} />
    </div>
  );
}
