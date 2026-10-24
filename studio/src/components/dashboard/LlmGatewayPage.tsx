// বাংলা মন্তব্য: LLM Gateway & System Rules Controller (Super-Admin) — ফলব্যাক রাউটিং চেইন,
// লাইভ AI মডেল সুইচ এবং কেন্দ্রীয় সিস্টেম রুল রিয়েল-টাইমে পরিবর্তন করা যায়।
// এন্ডপয়েন্ট /api/admin/llm/* — স্টুডিও ড্যাশবোর্ড থেকে সরাসরি রিচেবল।
import { useState, useEffect, useCallback } from 'react';
import { Cpu, Loader2, Save, Zap } from 'lucide-react';
import { apiClient } from '../../services/apiClient';

interface Provider {
  id: string;
  name: string;
  status: string;
  latency_ms: number;
  models: string[];
  mode: string;
}

interface ModelRouter {
  current_override: { provider: string; model: string } | null;
  provider_order: string[];
  cost_quality_preference: number;
}

export function LlmGatewayPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [router, setRouter] = useState<ModelRouter | null>(null);
  const [rulesText, setRulesText] = useState('');
  const [rulesKeyCount, setRulesKeyCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [savingRules, setSavingRules] = useState(false);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiClient.get<Provider[]>('/api/admin/llm/providers'),
      apiClient.get<ModelRouter>('/api/admin/llm/router'),
      apiClient.get<Record<string, unknown>>('/api/admin/llm/rules'),
    ])
      .then(([p, r, ru]) => {
        setProviders(Array.isArray(p) ? p : []);
        setRouter(r);
        setRulesKeyCount(Object.keys(ru || {}).length);
        setRulesText(JSON.stringify(ru || {}, null, 2));
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load gateway data'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // বাংলা মন্তব্য: set-state-in-effect ফিক্স — loadAll কে async ফাংশনের ভেতরে র‍্যাপ করা হয়েছে
    const initializeGateway = async () => {
      await loadAll();
    };
    initializeGateway();
  }, [loadAll]);

  // বাংলা মন্তব্য: লাইভ মডেল সুইচ — নির্দিষ্ট প্রোভাইডার/মডেলে রাউটার ওভাররাইড সেট করা হয়
  const handleSwitchModel = async (provider: string, model: string) => {
    setStatus('');
    setError('');
    try {
      await apiClient.post('/api/admin/llm/router/override', {
        provider,
        model,
        remaining_requests: 100,
      });
      setStatus(`Routing switched to ${provider}/${model} for next 100 requests.`);
      loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to switch model');
    }
  };

  // বাংলা মন্তব্য: সিস্টেম রুল স্কিমা রিয়েল-টাইমে মিউটেট করে সেভ করা হয়
  const handleSaveRules = async () => {
    setSavingRules(true);
    setStatus('');
    setError('');
    try {
      const parsed = JSON.parse(rulesText);
      await apiClient.post('/api/admin/llm/rules', { rules: parsed });
      setRulesKeyCount(Object.keys(parsed).length);
      setStatus('System rules saved successfully.');
    } catch (err) {
      setError(
        err instanceof SyntaxError
          ? 'Invalid JSON in rules editor.'
          : err instanceof Error
            ? err.message
            : 'Failed to save rules'
      );
    } finally {
      setSavingRules(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-lg font-semibold text-white flex items-center gap-2">
          <Cpu size={17} className="text-blue-400" />
          LLM Gateway & System Rules
        </h1>
        <button
          data-testid="gateway-refresh"
          onClick={loadAll}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg border border-white/10 text-xs text-slate-300 hover:bg-white/[0.05] disabled:opacity-50 transition-colors"
        >
          Refresh
        </button>
      </div>
      <p className="text-xs text-slate-400 mb-5">
        Toggle fallback routing chains, switch the live AI model, and mutate central system rules.
      </p>

      {error && <p className="text-xs text-rose-400 mb-3">{error}</p>}
      {status && <p className="text-xs text-emerald-400 mb-3">{status}</p>}

      {loading ? (
        <div className="flex justify-center py-10 text-slate-400">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : (
        <>
          {router && (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 mb-5">
              <h2 className="text-xs font-medium text-slate-300 mb-2">Fallback routing chain</h2>
              <div className="flex flex-wrap items-center gap-2">
                {router.provider_order.map((p, i) => (
                  <span key={p} className="flex items-center gap-2 text-[11px] text-slate-300">
                    <span className="px-2 py-0.5 rounded-full bg-white/[0.06] border border-white/10">
                      {i + 1}. {p}
                    </span>
                    {i < router.provider_order.length - 1 && (
                      <span className="text-slate-600">→</span>
                    )}
                  </span>
                ))}
              </div>
              {router.current_override && (
                <p
                  data-testid="gateway-active-override"
                  className="text-[11px] text-emerald-400 mt-2"
                >
                  Active override: {router.current_override.provider}/
                  {router.current_override.model}
                </p>
              )}
            </div>
          )}

          <h2 className="text-xs font-medium text-slate-300 mb-2">Providers & live model switch</h2>
          <ul className="flex flex-col gap-2 mb-6">
            {providers.length === 0 ? (
              <p className="text-sm text-slate-400 py-4">No providers with configured API keys.</p>
            ) : (
              providers.map((p) => (
                <li
                  key={p.id}
                  data-testid="gateway-provider"
                  className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        p.status === 'healthy' ? 'bg-emerald-400' : 'bg-rose-400'
                      }`}
                    />
                    <span className="text-xs text-white flex-1">{p.name}</span>
                    <span className="text-[10px] text-slate-400">{p.latency_ms}ms</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {p.models.map((m) => (
                      <button
                        key={m}
                        data-testid="gateway-switch-model"
                        onClick={() => handleSwitchModel(p.id, m)}
                        className="flex items-center gap-1 px-2 py-1 rounded-md bg-blue-600/15 border border-blue-500/30 text-[10px] text-blue-200 hover:bg-blue-600/30 transition-colors"
                      >
                        <Zap size={10} />
                        {m}
                      </button>
                    ))}
                  </div>
                </li>
              ))
            )}
          </ul>

          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-medium text-slate-300">
              System rules ({rulesKeyCount} keys)
            </h2>
            <button
              data-testid="gateway-save-rules"
              onClick={handleSaveRules}
              disabled={savingRules}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white text-xs font-medium transition-colors"
            >
              {savingRules ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              Save rules
            </button>
          </div>
          <textarea
            data-testid="gateway-rules-editor"
            value={rulesText}
            onChange={(e) => setRulesText(e.target.value)}
            rows={12}
            spellCheck={false}
            className="w-full rounded-xl bg-black/40 border border-white/10 px-3 py-2 text-[11px] font-mono text-white outline-none focus:border-blue-500/50 resize-y"
          />
        </>
      )}
    </div>
  );
}
