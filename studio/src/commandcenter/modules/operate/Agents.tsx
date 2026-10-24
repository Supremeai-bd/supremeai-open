import { useState } from 'react';
import { useAgents } from '../../data/hooks';
import { DataTable, StatusPill, EmptyState } from '../../kit';
import type { Agent } from '../../data/types';

export function Agents() {
  const { data: agents, isLoading } = useAgents(5_000);
  const [search, setSearch] = useState('');

  const filtered = (agents ?? []).filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.role.toLowerCase().includes(search.toLowerCase()),
  );

  const columns = [
    { key: 'name', label: 'NAME', width: '25%' },
    { key: 'role', label: 'ROLE', width: '20%' },
    { key: 'status', label: 'STATUS', width: '15%', render: (agent: Agent) => <StatusPill status={agent.status} size="sm" /> },
    { key: 'current_task', label: 'TASK', width: '25%' },
    { key: 'queue_depth', label: 'QUEUE', width: '8%' },
    { key: 'memory_load_percent', label: 'MEM%', width: '7%' },
  ];

  if (!agents && isLoading) {
    return <EmptyState title="অ্যাজেন্ট লোড হচ্ছে..." message="অ্যাজেন্ট রেজিস্ট্রি ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Agents</h2>
        <input
          type="text"
          placeholder="Search agents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-[var(--sa-bg-1)] border border-[var(--sa-line)] text-[10px] font-mono rounded px-3 py-1.5 w-64"
        />
      </div>
      <DataTable columns={columns} data={filtered} rowKey={(a) => a.id} />
    </div>
  );
}
