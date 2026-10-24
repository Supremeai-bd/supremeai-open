import React from 'react';
import { useMemoryStats, useKnowledgeStats } from '../../data/hooks';
import { KpiTile, StatusPill, EmptyState } from '../../kit';

export function MemoryKnowledge() {
  const { data: memory, isLoading: memoryLoading } = useMemoryStats(30_000);
  const { data: knowledge } = useKnowledgeStats(30_000);

  if (!memory && memoryLoading) {
    return <EmptyState title="মেমরি লোড হচ্ছে..." message="মেমরি স্ট্যাটস ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Memory & Knowledge</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile label="BANKS" value={memory?.banks?.length ?? null} tone="cyan" />
        <KpiTile label="CACHE HIT" value={memory?.semantic_cache_hit_rate != null ? Math.round(memory.semantic_cache_hit_rate * 100) : null} unit="%" tone="emerald" />
        <KpiTile label="TOKENS SAVED" value={memory?.tokens_saved ?? null} tone="amber" />
        <KpiTile label="DOCS" value={knowledge?.docs_count ?? null} tone="violet" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">MEMORY BANKS</div>
          <div className="space-y-2">
            {(memory?.banks ?? []).map((bank) => (
              <div key={bank.name} className="flex items-center justify-between py-1 border-b border-[var(--sa-line)] last:border-0">
                <span className="text-[10px] font-mono text-[var(--sa-text-1)]">{bank.name}</span>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] font-mono text-[var(--sa-text-2)]">{bank.entry_count} entries</span>
                  <span className="text-[9px] font-mono text-[var(--sa-text-3)]">{bank.recent_writes} writes</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)] mb-3">KNOWLEDGE BASE</div>
          <div className="flex items-center gap-3">
            <StatusPill
              status={knowledge?.rag_index_status === 'indexed' ? 'healthy' : knowledge?.rag_index_status === 'indexing' ? 'busy' : 'down'}
              label={knowledge?.rag_index_status?.toUpperCase() ?? 'UNKNOWN'}
              size="md"
            />
            <span className="text-[10px] font-mono text-[var(--sa-text-2)]">{knowledge?.docs_count ?? 0} docs indexed</span>
          </div>
        </div>
      </div>
    </div>
  );
}
