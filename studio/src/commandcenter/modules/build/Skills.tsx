import React from 'react';
import { useSkills } from '../../data/hooks';
import { StatusPill, EmptyState } from '../../kit';

export function Skills() {
  const { data: skills, isLoading } = useSkills();

  if (!skills && isLoading) {
    return <EmptyState title="স্কিল লোড হচ্ছে..." message="স্কিল মার্কেটপ্লেস ডেটা ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Skills Marketplace</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(skills ?? []).map((skill) => (
          <div key={skill.id} className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono font-bold text-[var(--sa-text-0)]">{skill.name}</span>
              <StatusPill status={skill.enabled ? 'healthy' : 'degraded'} label={skill.enabled ? 'ENABLED' : 'DISABLED'} size="sm" />
            </div>
            <div className="text-[9px] font-mono text-[var(--sa-text-2)]">v{skill.version} · {skill.source.toUpperCase()}</div>
            <div className="text-[9px] font-mono text-[var(--sa-text-2)]">
              {skill.installed ? 'INSTALLED' : 'NOT INSTALLED'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
