import { useWorkspaces } from '../../data/hooks';
import { DataTable, EmptyState } from '../../kit';
import type {} from '../../data/types';

export function Workspaces() {
  const { data: workspaces, isLoading } = useWorkspaces();

  const columns = [
    { key: 'name', label: 'NAME', width: '30%' },
    { key: 'owner_id', label: 'OWNER', width: '20%' },
    { key: 'member_count', label: 'MEMBERS', width: '15%' },
    { key: 'created_at', label: 'CREATED', width: '20%' },
  ];

  if (!workspaces && isLoading) {
    return <EmptyState title="ওয়ার্কস্পেস লোড হচ্ছে..." message="ওয়ার্কস্পেস ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Workspaces</h2>
      <DataTable columns={columns} data={workspaces ?? []} rowKey={(w) => w.id} />
    </div>
  );
}
