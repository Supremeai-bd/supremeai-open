import { Card, Badge } from '../ui';
import { GitBranch, Clock, ArrowRight, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';

interface Repo { id: string; name: string; branch: string; updated: string; commits: number; }
interface Commit { hash: string; message: string; author: string; time: string; }

export function GithubIntegration() {
  const { data: repos, isLoading: reposLoading, refetch: refetchRepos } = useQuery({
    queryKey: ['github', 'repos'],
    queryFn: () => apiClient.get<Repo[]>('/github/repos'),
  });

  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const selectedRepo = repos?.find(r => r.id === selectedRepoId) ?? repos?.[0] ?? null;

  const { data: commits, isLoading: commitsLoading } = useQuery({
    queryKey: ['github', 'commits', selectedRepo?.id],
    queryFn: () => apiClient.get<Commit[]>(`/github/repos/${selectedRepo!.id}/commits?limit=4`),
    enabled: !!selectedRepo,
  });

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          🔗 GitHub Integration
        </h2>
        <button
          onClick={() => refetchRepos()}
          className="flex items-center gap-2 px-3 py-1.5 rounded border border-[#00f3ff]/30 text-[#00f3ff] hover:bg-[#00f3ff]/10 text-[10px] font-bold font-mono uppercase transition-colors"
        >
          <RefreshCw size={10} /> Sync
        </button>
      </div>

      {reposLoading && <p className="text-slate-400 text-xs font-mono">Loading repositories…</p>}
      {!reposLoading && (!repos || repos.length === 0) && (
        <p className="text-slate-400 text-xs font-mono">No repositories connected. Connect one from Settings.</p>
      )}

      {repos && repos.length > 0 && selectedRepo && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card title="Repositories" className="lg:col-span-1">
            <div className="flex flex-col gap-2">
              {repos.map(repo => (
                <button
                  key={repo.id}
                  onClick={() => setSelectedRepoId(repo.id)}
                  className={`text-left p-3 rounded-lg border transition-all ${
                    selectedRepo.id === repo.id
                      ? 'border-[#00f3ff]/50 bg-[#00f3ff]/10'
                      : 'border-slate-800 bg-slate-900/30 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-white font-mono">{repo.name}</span>
                    <Badge variant="info">{repo.branch}</Badge>
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono flex items-center gap-2">
                    <span className="flex items-center gap-1"><GitBranch size={10} /> {repo.commits} commits</span>
                    <span className="flex items-center gap-1"><Clock size={10} /> {repo.updated}</span>
                  </div>
                </button>
              ))}
            </div>
          </Card>

          <Card title={`Commits: ${selectedRepo.name}`} className="lg:col-span-2">
            <div className="flex flex-col gap-2">
              {commitsLoading && <p className="text-slate-400 text-xs font-mono">Loading commits…</p>}
              {commits?.map((commit) => (
                <div key={commit.hash} className="flex items-center gap-3 p-3 rounded-lg border border-slate-800 bg-slate-900/30">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 rounded-full bg-[#24292e] flex items-center justify-center">
                      <GitBranch size={12} className="text-white" />
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-mono text-white truncate">{commit.message}</div>
                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                      {commit.hash} by {commit.author} • {commit.time}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-between items-center mt-4 pt-3 border-t border-slate-800">
              <span className="text-[10px] text-slate-400 font-mono">
                Showing {commits?.length ?? 0} of {selectedRepo.commits} commits
              </span>
              <button className="text-[10px] text-[#00f3ff] hover:text-cyan-300 font-mono flex items-center gap-1">
                View all <ArrowRight size={10} />
              </button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
