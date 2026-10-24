import { useAgents } from '../../data/hooks';

export function TasksQueues() {
  const { data: agents } = useAgents(5_000);

  const totalQueue = agents?.reduce((sum, a) => sum + a.queue_depth, 0) ?? 0;

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Tasks & Queues</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#00f3ff]">{agents?.length ?? 0}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Agents</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#f59e0b]">{totalQueue}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Queued</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#10b981]">{(agents ?? []).filter(a => a.status === 'busy').length}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Busy</div>
        </div>
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 text-center">
          <div className="text-2xl font-mono text-[#ef4444]">{(agents ?? []).filter(a => a.status === 'dead').length}</div>
          <div className="text-[9px] font-mono text-[var(--sa-text-2)] uppercase mt-1">Dead</div>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">AGENT QUEUES</div>
        <div className="space-y-2">
          {(agents ?? []).map((agent) => (
            <div key={agent.id} className="flex items-center justify-between py-1 border-b border-[var(--sa-line)] last:border-0">
              <span className="text-[10px] font-mono text-[var(--sa-text-1)]">{agent.name}</span>
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono text-[var(--sa-text-2)]">{agent.current_task ?? 'idle'}</span>
                <span className="text-[10px] font-mono text-[var(--sa-text-2)] w-8 text-right">{agent.queue_depth}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
