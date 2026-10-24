import { Card, Badge, BanglaHint } from '../ui';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { GitBranch, ArrowRight, Settings } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { adminTokenStore } from '../../services/adminTokenStore';

// বাংলা মন্তব্য: টোকেন গার্ড — টোকেন ছাড়া admin-api কল হবে না, 401 storm ঠেকাতে
const hasToken = (): boolean => !!adminTokenStore.getDecodedToken();

interface ModelRouterConfig {
  override_active?: boolean;
  override_provider?: string;
  override_remaining_requests?: number;
  ab_test_active?: boolean;
}

interface ProviderStatus {
  id: string;
  name: string;
  status: string;
  latency_ms: number;
  api_key_valid: boolean;
  rate_limit_remaining: number;
  rate_limit_max: number;
  models: string[];
}

const PROVIDER_LIST = [
  { id: 'openrouter', label: 'OpenRouter', color: 'bg-cyan-500' },
  { id: 'gemini', label: 'Gemini', color: 'bg-purple-500' },
  { id: 'groq', label: 'Groq', color: 'bg-emerald-500' },
  { id: 'deepseek', label: 'DeepSeek', color: 'bg-amber-500' },
];

export function ModelRouter() {
  const routerQuery = useQuery({
    queryKey: ['model-router'],
    queryFn: () => apiClient.get<ModelRouterConfig>('/admin-api/model-router'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
  const providersQuery = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiClient.get('/admin-api/providers'),
    enabled: hasToken(),
    staleTime: 30_000,
  });

  const config = routerQuery.data;
  const providers = providersQuery.data as ProviderStatus[] | undefined;
  const [overrideProvider, setOverrideProvider] = useState('');
  const [overrideModel, setOverrideModel] = useState('');
  const [overrideRemaining, setOverrideRemaining] = useState(10);
  const qc = useQueryClient();

  const overrideMutation = useMutation({
    mutationFn: (payload: { provider: string; model: string; remaining_requests: number }) =>
      apiClient.post('/admin-api/model-router/override', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['model-router'] });
    },
  });

  const activeProvider = config?.override_active
    ? PROVIDER_LIST.find(p => p.id === config.override_provider)
    : null;

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase flex items-center gap-2">
          🔀 AI Model Router
          <BanglaHint text="কোন রিকোয়েস্ট কোন SupremeAI মডেলে (Core/Vision) যাবে, তা এখান থেকে কন্ট্রোল করুন।" />
        </h2>
        <Badge variant={config?.ab_test_active ? 'warning' : 'info'}>
          {config?.ab_test_active ? 'A/B TEST ACTIVE' : 'STANDARD MODE'}
        </Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <Card title="Routing Flow">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <div className="flex-1 p-2 rounded border border-slate-800 bg-slate-900/50 text-xs font-mono text-center">
                Incoming Request
              </div>
              <ArrowRight size={14} className="text-slate-400" />
              <div className="flex-1 p-2 rounded border border-[#00f3ff]/50 bg-[#00f3ff]/10 text-xs font-mono text-center text-[#00f3ff]">
                Intent Classifier
              </div>
              <ArrowRight size={14} className="text-slate-400" />
              <div className="flex-1 p-2 rounded border border-purple-500/50 bg-purple-500/10 text-xs font-mono text-center text-purple-400">
                Provider Selector
              </div>
              <ArrowRight size={14} className="text-slate-400" />
              <div className="flex-1 p-2 rounded border border-emerald-500/50 bg-emerald-500/10 text-xs font-mono text-center text-emerald-400">
                Model Execution
              </div>
            </div>
            {activeProvider && (
              <div className="p-2 rounded bg-amber-950/30 border border-amber-900/50 text-[10px] font-mono text-amber-400">
                ⚡ OVERRIDE ACTIVE: All traffic → {activeProvider.label} for {config?.override_remaining_requests} more requests
              </div>
            )}
          </div>
        </Card>

        <Card title="Force Override" icon={<Settings size={14} />}>
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 uppercase flex items-center gap-1">
                  Provider
                  <BanglaHint text="SupremeAI প্রোভাইডার নির্বাচন করুন (যেমন: OpenRouter, Gemini, Groq)।" />
                </label>
                <select
                  value={overrideProvider}
                  onChange={e => setOverrideProvider(e.target.value)}
                  className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none text-xs font-mono"
                >
                  <option value="">Select...</option>
                  {PROVIDER_LIST.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 uppercase flex items-center gap-1">
                  Model
                  <BanglaHint text="SupremeAI মডেল আইডি লিখুন (যেমন: supremeai-core, supremeai-vision)।" />
                </label>
                <input
                  type="text"
                  value={overrideModel}
                  onChange={e => setOverrideModel(e.target.value)}
                  placeholder="e.g. supremeai-core"
                  className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none text-xs font-mono"
                />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] text-slate-400 uppercase flex items-center gap-1">
                Remaining Requests
                <BanglaHint text="কতবার ওভাররাইড পর্যন্ত রাখবেন, সেটি ঠিক করুন।" />
              </label>
              <input
                type="number"
                min={1}
                max={1000}
                value={overrideRemaining}
                onChange={e => setOverrideRemaining(parseInt(e.target.value) || 0)}
                className="bg-[#06080b] border border-slate-800 rounded px-3 py-1.5 text-white outline-none text-xs font-mono w-32"
              />
            </div>
            <button
              onClick={() => overrideMutation.mutate({ provider: overrideProvider, model: overrideModel, remaining_requests: overrideRemaining })}
              disabled={!overrideProvider || !overrideModel}
              className="bg-[#00f3ff] hover:bg-cyan-400 text-black font-bold px-4 py-1.5 rounded text-xs uppercase font-mono disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Apply Override
            </button>
          </div>
        </Card>
      </div>

      <Card title="Provider Health" icon={<GitBranch size={14} />}>
        {providersQuery.isLoading ? (
          <div className="text-xs text-slate-400 font-mono">Loading provider status...</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            {providers?.map(p => (
              <div key={p.id} className="p-3 rounded-lg border border-slate-800 bg-slate-900/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white">{p.name}</span>
                  <Badge variant={p.status === 'healthy' ? 'success' : 'warning'}>{p.status}</Badge>
                </div>
                <div className="text-[10px] text-slate-400 font-mono mb-1">Latency: {p.latency_ms}ms</div>
                <div className="w-full bg-slate-800 rounded-full h-1 mb-2">
                  <div
                    className={`h-full rounded-full ${p.latency_ms < 200 ? 'bg-emerald-500' : p.latency_ms < 300 ? 'bg-amber-500' : 'bg-red-500'}`}
                    style={{ width: `${Math.min(100, (p.latency_ms / 400) * 100)}%` }}
                  />
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  API Key: {p.api_key_valid ? '✅ Valid' : '❌ Invalid'}
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  Rate Limit: {p.rate_limit_remaining}/{p.rate_limit_max}
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {p.models.slice(0, 2).map((m: string) => (
                    <span key={m} className="px-1.5 py-0.5 text-[9px] rounded bg-slate-800 text-slate-300 font-mono">
                      {m}
                    </span>
                  ))}
                  {p.models.length > 2 && (
                    <span className="px-1.5 py-0.5 text-[9px] rounded bg-slate-800 text-slate-400 font-mono">
                      +{p.models.length - 2}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
