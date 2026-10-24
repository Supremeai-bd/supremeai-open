/**
 * AI Surface Assignment — Admin Dashboard
 * 
 * Shows all AI providers + API key status.
 * Admin can assign which AI serves which surface (Web/IDE/Telegram/API).
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, Badge } from '../ui';
import { apiClient } from '../../services/apiClient';
import { adminTokenStore } from '../../services/adminTokenStore';
import { Bot, Globe, MessageSquare, Terminal, Search, Cpu, CheckCircle2, XCircle, Zap, RefreshCw } from 'lucide-react';

const hasToken = (): boolean => !!adminTokenStore.getDecodedToken();

interface Surface {
  id: string;
  name: string;
  icon: string;
  description: string;
  assigned_provider: string;
  assigned_provider_name: string;
  assigned_provider_tier: number;
}

interface Provider {
  id: string;
  name: string;
  env_key: string;
  tier: number;
  speed: string;
  cost: string;
  has_api_key: boolean;
  key_preview: string;
}

interface Overview {
  surfaces: Surface[];
  providers: Provider[];
  assignment: Record<string, string>;
  summary: {
    total_surfaces: number;
    total_providers: number;
    working_providers: number;
    missing_providers: number;
    working_provider_names: string[];
    missing_provider_names: string[];
  };
}

const SURFACE_ICONS: Record<string, React.ReactNode> = {
  web_chat: <MessageSquare className="h-5 w-5" />,
  ide: <Terminal className="h-5 w-5" />,
  telegram: <MessageSquare className="h-5 w-5" />,
  api: <Globe className="h-5 w-5" />,
  research: <Search className="h-5 w-5" />,
  automation: <Cpu className="h-5 w-5" />,
};

const TIER_COLORS: Record<number, string> = {
  1: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  2: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  3: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
};

export function AISurfaceAssignment() {
  const qc = useQueryClient();
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  const { data: overview, isLoading } = useQuery<Overview>({
    queryKey: ['ai-assignment-overview'],
    queryFn: () => apiClient.get('/api/admin/ai/overview'),
    enabled: hasToken(),
    staleTime: 15_000,
  });

  const assignMutation = useMutation({
    mutationFn: (payload: { surface: string; provider: string }) =>
      apiClient.post('/api/admin/ai/assign', payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-assignment-overview'] }),
  });

  const handleAssign = (surfaceId: string, providerId: string) => {
    assignMutation.mutate({ surface: surfaceId, provider: providerId });
  };

  const handleTest = async (providerId: string) => {
    setTestingProvider(providerId);
    try {
      // Type the post() generic explicitly — untyped T infers `unknown` and
      // `result.status` failed the typecheck gate.
      const result = await apiClient.post<{ status: string }>(`/api/admin/ai/test/${providerId}`, {});
      setTestResult(prev => ({ ...prev, [providerId]: result.status }));
    } catch (e) {
      setTestResult(prev => ({ ...prev, [providerId]: '❌ error' }));
    }
    setTestingProvider(null);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
        <span className="ml-2 text-slate-400">Loading AI surfaces...</span>
      </div>
    );
  }

  const surfaces = overview?.surfaces || [];
  const providers = overview?.providers || [];
  const summary = overview?.summary;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Bot className="h-6 w-6 text-cyan-400" />
        <div>
          <h2 className="text-xl font-bold text-white">AI Surface Assignment</h2>
          <p className="text-sm text-slate-400">কোন AI কোন surface-এ কাজ করবে — admin নির্ধারণ করবে</p>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Card className="p-4">
            <div className="text-2xl font-bold text-white">{summary.total_surfaces}</div>
            <div className="text-xs text-slate-400">AI Surfaces</div>
          </Card>
          <Card className="p-4">
            <div className="text-2xl font-bold text-emerald-400">{summary.working_providers}</div>
            <div className="text-xs text-slate-400">Working AI Providers</div>
          </Card>
          <Card className="p-4">
            <div className="text-2xl font-bold text-red-400">{summary.missing_providers}</div>
            <div className="text-xs text-slate-400">Missing API Keys</div>
          </Card>
          <Card className="p-4">
            <div className="text-2xl font-bold text-cyan-400">{summary.total_providers}</div>
            <div className="text-xs text-slate-400">Total Providers</div>
          </Card>
        </div>
      )}

      {/* Surfaces Grid */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-slate-300">🎯 Surfaces — কোথায় AI ব্যবহৃত হয়</h3>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {surfaces.map((surface) => (
            <Card key={surface.id} className="p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className="text-2xl">{surface.icon}</div>
                  <div>
                    <div className="font-semibold text-white">{surface.name}</div>
                    <div className="text-xs text-slate-500">{surface.description}</div>
                  </div>
                </div>
                <Badge className={TIER_COLORS[surface.assigned_provider_tier] || 'bg-slate-500/20'}>
                  Tier {surface.assigned_provider_tier || 0}
                </Badge>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xs text-slate-400">Assigned:</span>
                <span className="text-sm font-medium text-cyan-300">{surface.assigned_provider_name}</span>
              </div>
              <select
                className="mt-2 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-white"
                value={surface.assigned_provider}
                onChange={(e) => handleAssign(surface.id, e.target.value)}
                disabled={assignMutation.isPending}
              >
                <option value="auto">🤖 Auto (failover chain)</option>
                {providers.filter(p => p.has_api_key).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} (Tier {p.tier}, {p.speed})
                  </option>
                ))}
              </select>
            </Card>
          ))}
        </div>
      </div>

      {/* Providers Table */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-slate-300">🔌 AI Providers — API Key Status</h3>
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="px-4 py-2 text-left">Provider</th>
                <th className="px-4 py-2 text-left">Tier</th>
                <th className="px-4 py-2 text-left">Speed</th>
                <th className="px-4 py-2 text-left">Cost</th>
                <th className="px-4 py-2 text-left">API Key</th>
                <th className="px-4 py-2 text-left">Test</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {providers.map((p) => (
                <tr key={p.id} className="hover:bg-slate-900/50">
                  <td className="px-4 py-2 font-medium text-white">{p.name}</td>
                  <td className="px-4 py-2">
                    <Badge className={TIER_COLORS[p.tier]}>T{p.tier}</Badge>
                  </td>
                  <td className="px-4 py-2 text-slate-400">{p.speed}</td>
                  <td className="px-4 py-2">
                    <span className={p.cost === 'free' ? 'text-emerald-400' : 'text-amber-400'}>{p.cost}</span>
                  </td>
                  <td className="px-4 py-2">
                    {p.has_api_key ? (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 className="h-4 w-4" /> {p.key_preview}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-400">
                        <XCircle className="h-4 w-4" /> missing
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => handleTest(p.id)}
                      disabled={testingProvider === p.id || !p.has_api_key}
                      className="flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                    >
                      {testingProvider === p.id ? (
                        <RefreshCw className="h-3 w-3 animate-spin" />
                      ) : (
                        <Zap className="h-3 w-3" />
                      )}
                      Test
                    </button>
                    {testResult[p.id] && (
                      <span className="ml-2 text-xs">{testResult[p.id]}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
