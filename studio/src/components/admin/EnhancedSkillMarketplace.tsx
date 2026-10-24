/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Skeleton } from '../ui';
import { Star, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import SkillGraph from '../graph/SkillGraph';
import { apiClient } from '../../services/apiClient';

export function EnhancedSkillMarketplace() {
  const { data: skills, isLoading } = useQuery({
    queryKey: ['skills', 'marketplace'],
    queryFn: () => apiClient.get('/api/skills/search'),
  });

  const [filter, setFilter] = useState<'all' | 'installed' | 'available'>('all');
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const skillAction = useMutation({
    mutationFn: ({ skillId, action }: { skillId: string; action: 'APPROVE' | 'APPROVE_AS_EPHEMERAL' }) =>
      apiClient.post('/api/admin/librarian/process', { skill_id: skillId, action }),
    onSuccess: () => {
      setActionMessage('Skill action queued successfully.');
      queryClient.invalidateQueries({ queryKey: ['skills', 'marketplace'] });
    },
    onError: (error: Error) => setActionMessage(error.message || 'Skill action failed.'),
  });

  const filtered = (Array.isArray(skills) ? skills : [])?.filter((s: any) => {
    if (filter === 'installed') return s.installed;
    if (filter === 'available') return !s.installed;
    return true;
  }) || [];

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          🛠️ Skill Marketplace
        </h2>
        <div className="flex gap-2">
          {(['all', 'installed', 'available'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-1 text-[10px] font-bold rounded font-mono uppercase transition-colors ${
                filter === f ? 'bg-[#00f3ff]/20 text-[#00f3ff]' : 'text-slate-400 hover:text-white'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {actionMessage && (
        <div role="status" className="mb-4 rounded border border-[#00f3ff]/30 bg-[#00f3ff]/10 px-3 py-2 text-xs text-[#00f3ff]">
          {actionMessage}
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((skill: any) => (
            <div key={skill.id} className="bg-[#080b11]/80 backdrop-blur-md border border-slate-800 rounded-xl p-5 hover:border-[#00f3ff]/30 transition-all duration-300">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-sm font-bold text-white font-mono">{skill.name}</h3>
                  <div className="text-[10px] text-slate-400 mt-0.5">v{skill.version}</div>
                </div>
                {skill.installed ? (
                  <Badge variant="success">Installed</Badge>
                ) : (
                  <Badge variant="info">Available</Badge>
                )}
              </div>
              <p className="text-xs text-slate-400 mb-4 leading-relaxed">{skill.description}</p>
              {skill.installed && (
                <div className="grid grid-cols-3 gap-2 mb-4 text-center">
                  <div className="p-1.5 rounded bg-slate-900/50">
                    <div className="text-[10px] text-slate-400">Success</div>
                    <div className="text-xs font-bold text-emerald-400 font-mono">98%</div>
                  </div>
                  <div className="p-1.5 rounded bg-slate-900/50">
                    <div className="text-[10px] text-slate-400">Avg Time</div>
                    <div className="text-xs font-bold text-[#00f3ff] font-mono">120ms</div>
                  </div>
                  <div className="p-1.5 rounded bg-slate-900/50">
                    <div className="text-[10px] text-slate-400">Errors</div>
                    <div className="text-xs font-bold text-yellow-400 font-mono">2%</div>
                  </div>
                </div>
              )}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map(star => (
                    <Star key={star} size={10} className={star <= 4 ? 'text-yellow-400 fill-yellow-400' : 'text-slate-700'} />
                  ))}
                  <span className="text-[9px] text-slate-400 ml-1">4.0</span>
                </div>
                {!skill.installed ? (
                  <button
                    disabled={skillAction.isPending}
                    onClick={() => skillAction.mutate({ skillId: skill.id, action: 'APPROVE' })}
                    className="bg-[#00f3ff]/10 hover:bg-[#00f3ff]/20 disabled:opacity-50 text-[#00f3ff] border border-[#00f3ff]/30 text-[10px] font-bold px-3 py-1 rounded transition-all font-mono"
                  >
                    {skillAction.isPending ? 'QUEUING…' : 'INSTALL'}
                  </button>
                ) : (
                  <button
                    disabled={skillAction.isPending}
                    onClick={() => skillAction.mutate({ skillId: skill.id, action: 'APPROVE_AS_EPHEMERAL' })}
                    className="text-[10px] text-slate-400 hover:text-white disabled:opacity-50 font-mono flex items-center gap-1"
                  >
                    <RefreshCw size={10} /> {skillAction.isPending ? 'QUEUING…' : 'UPDATE'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* বাংলা মন্তব্য: ইন্টারেক্টিভ রিলেশনশিপ এবং স্কিল চেইন দেখার জন্য গ্রাফ রেন্ডারিং */}
      <div className="mt-10 border-t border-[#00f3ff]/15 pt-6">
        <h3 className="text-sm font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase mb-4">
          🌐 Skill Dependency Graph
        </h3>
        <SkillGraph />
      </div>
    </div>
  );
}

