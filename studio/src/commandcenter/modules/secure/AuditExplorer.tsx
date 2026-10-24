import { useAuditLogs } from '../../data/hooks';
import { DataTable, EmptyState } from '../../kit';
import type {} from '../../data/types';

export function AuditExplorer() {
  const { data: audit, isLoading } = useAuditLogs(100);

  const columns = [
    { key: 'timestamp', label: 'TIMESTAMP', width: '18%' },
    { key: 'admin', label: 'ADMIN', width: '12%' },
    { key: 'role', label: 'ROLE', width: '10%' },
    { key: 'action', label: 'ACTION', width: '15%' },
    { key: 'target', label: 'TARGET', width: '20%' },
    { key: 'result', label: 'RESULT', width: '10%' },
    { key: 'ip', label: 'IP', width: '15%' },
  ];

  if (!audit && isLoading) {
    return <EmptyState title="অডিট লোড হচ্ছে..." message="অডিট লগ ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Audit Explorer</h2>
      <DataTable columns={columns} data={audit ?? []} rowKey={(a) => `${a.timestamp}-${a.admin}-${a.action}`} />
    </div>
  );
}
