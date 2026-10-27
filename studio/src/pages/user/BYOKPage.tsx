import React, { useEffect, useState } from 'react';
import { 
  KeyRound, 
  ExternalLink, 
  CheckCircle2, 
  AlertTriangle,
  Loader2, 
  ShieldCheck, 
  Zap, 
  Sparkles,
  RefreshCw,
  Trash2,
  Info
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { useToast } from '../../contexts/useToast';
import { WorkspaceLayout } from '../../components/layout/WorkspaceLayout';

interface ProviderConfig {
  id: string;
  name: string;
  category: 'ultra_fast' | 'flagship' | 'open_source' | 'specialized';
  logoText: string;
  accentColor: string;
  borderColor: string;
  tagColor: string;
  keyPortalUrl: string;
  description: string;
  freeTierPerks: string;
  keyPlaceholder: string;
  keyPrefixHint: string;
}

const PROVIDERS: ProviderConfig[] = [
  {
    id: 'gemini',
    name: 'Google Gemini',
    category: 'flagship',
    logoText: '♊',
    accentColor: 'from-blue-600/20 to-indigo-600/20 text-blue-400',
    borderColor: 'hover:border-blue-500/40',
    tagColor: 'bg-blue-500/10 text-blue-300 border-blue-500/20',
    keyPortalUrl: 'https://aistudio.google.com/app/apikey',
    description: 'Gemini 1.5 Pro & Flash with massive 1M-2M context tokens window.',
    freeTierPerks: '15 RPM / 1M TPM Generous Free Tier',
    keyPlaceholder: 'AIzaSy...',
    keyPrefixHint: 'Starts with AIzaSy',
  },
  {
    id: 'groq',
    name: 'Groq LPU',
    category: 'ultra_fast',
    logoText: '⚡',
    accentColor: 'from-orange-600/20 to-amber-600/20 text-orange-400',
    borderColor: 'hover:border-orange-500/40',
    tagColor: 'bg-orange-500/10 text-orange-300 border-orange-500/20',
    keyPortalUrl: 'https://console.groq.com/keys',
    description: 'Blazing-fast inference (500+ tokens/s) on Llama 3.3, 3.1 & Mixtral.',
    freeTierPerks: '30 RPM Free Tier for Open Models',
    keyPlaceholder: 'gsk_...',
    keyPrefixHint: 'Starts with gsk_',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    category: 'flagship',
    logoText: '🟢',
    accentColor: 'from-emerald-600/20 to-teal-600/20 text-emerald-400',
    borderColor: 'hover:border-emerald-500/40',
    tagColor: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
    keyPortalUrl: 'https://platform.openai.com/api-keys',
    description: 'Industry benchmark models including GPT-4o, GPT-4o-mini and o1 reasoning.',
    freeTierPerks: 'Free Tier Credits / Tier 1 access',
    keyPlaceholder: 'sk-proj-...',
    keyPrefixHint: 'Starts with sk-',
  },
  {
    id: 'anthropic',
    name: 'Anthropic Claude',
    category: 'flagship',
    logoText: '🟣',
    accentColor: 'from-purple-600/20 to-pink-600/20 text-purple-400',
    borderColor: 'hover:border-purple-500/40',
    tagColor: 'bg-purple-500/10 text-purple-300 border-purple-500/20',
    keyPortalUrl: 'https://console.anthropic.com/settings/keys',
    description: 'Exceptional coding, reasoning, and instruction following with Claude 3.5 Sonnet.',
    freeTierPerks: 'Initial free test balance on signup',
    keyPlaceholder: 'sk-ant-...',
    keyPrefixHint: 'Starts with sk-ant-',
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    category: 'open_source',
    logoText: '🌐',
    accentColor: 'from-cyan-600/20 to-blue-600/20 text-cyan-400',
    borderColor: 'hover:border-cyan-500/40',
    tagColor: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
    keyPortalUrl: 'https://openrouter.ai/settings/keys',
    description: 'Unified gateway aggregating 100+ AI models including free tiers.',
    freeTierPerks: 'Dozens of :free suffix open LLMs',
    keyPlaceholder: 'sk-or-v1-...',
    keyPrefixHint: 'Starts with sk-or-',
  },
  {
    id: 'cerebras',
    name: 'Cerebras',
    category: 'ultra_fast',
    logoText: '🧠',
    accentColor: 'from-rose-600/20 to-red-600/20 text-rose-400',
    borderColor: 'hover:border-rose-500/40',
    tagColor: 'bg-rose-500/10 text-rose-300 border-rose-500/20',
    keyPortalUrl: 'https://cloud.cerebras.ai/platform/',
    description: 'Wafer-scale engine with lightning-fast 1,800+ tokens/sec throughput.',
    freeTierPerks: 'Generous free daily requests',
    keyPlaceholder: 'csk-...',
    keyPrefixHint: 'Starts with csk-',
  },
  {
    id: 'mistral',
    name: 'Mistral AI',
    category: 'flagship',
    logoText: '🌊',
    accentColor: 'from-amber-600/20 to-yellow-600/20 text-amber-400',
    borderColor: 'hover:border-amber-500/40',
    tagColor: 'bg-amber-500/10 text-amber-300 border-amber-500/20',
    keyPortalUrl: 'https://console.mistral.ai/api-keys/',
    description: 'Mistral Large 2, Codestral and Pixtral for versatile multimodal development.',
    freeTierPerks: 'Free tier with rate-limit for Codestral',
    keyPlaceholder: '••••••••••••••••',
    keyPrefixHint: '32-character hex key',
  },
  {
    id: 'together',
    name: 'Together AI',
    category: 'open_source',
    logoText: '🤝',
    accentColor: 'from-sky-600/20 to-indigo-600/20 text-sky-400',
    borderColor: 'hover:border-sky-500/40',
    tagColor: 'bg-sky-500/10 text-sky-300 border-sky-500/20',
    keyPortalUrl: 'https://api.together.ai/settings/api-keys',
    description: 'Fast open-source foundation model hosting with low latency.',
    freeTierPerks: '$5.00 free credit on new accounts',
    keyPlaceholder: '••••••••••••••••',
    keyPrefixHint: '64-character token',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    category: 'flagship',
    logoText: '🐋',
    accentColor: 'from-blue-700/20 to-cyan-600/20 text-blue-300',
    borderColor: 'hover:border-blue-400/40',
    tagColor: 'bg-blue-400/10 text-blue-200 border-blue-400/20',
    keyPortalUrl: 'https://platform.deepseek.com/api_keys',
    description: 'DeepSeek-V3 and DeepSeek-R1 math, logic, and full reasoning power.',
    freeTierPerks: 'High-token allocation free credits',
    keyPlaceholder: 'sk-...',
    keyPrefixHint: 'Starts with sk-',
  },
  {
    id: 'cohere',
    name: 'Cohere',
    category: 'specialized',
    logoText: '🧬',
    accentColor: 'from-emerald-700/20 to-teal-700/20 text-emerald-300',
    borderColor: 'hover:border-emerald-400/40',
    tagColor: 'bg-emerald-400/10 text-emerald-200 border-emerald-400/20',
    keyPortalUrl: 'https://dashboard.cohere.com/api-keys',
    description: 'Command R+ multilingual models, Embeddings & Rerank technology.',
    freeTierPerks: 'Trial Key: 100 free requests/min',
    keyPlaceholder: '••••••••••••••••',
    keyPrefixHint: 'Trial / Production key',
  },
  {
    id: 'perplexity',
    name: 'Perplexity AI',
    category: 'specialized',
    logoText: '🔍',
    accentColor: 'from-teal-600/20 to-cyan-700/20 text-teal-300',
    borderColor: 'hover:border-teal-400/40',
    tagColor: 'bg-teal-400/10 text-teal-200 border-teal-400/20',
    keyPortalUrl: 'https://www.perplexity.ai/settings/api',
    description: 'Sonar models powered by live web search synthesis and citations.',
    freeTierPerks: 'Included in pro accounts / initial API access',
    keyPlaceholder: 'pplx-...',
    keyPrefixHint: 'Starts with pplx-',
  },
  {
    id: 'huggingface',
    name: 'Hugging Face',
    category: 'open_source',
    logoText: '🤗',
    accentColor: 'from-yellow-600/20 to-amber-600/20 text-yellow-300',
    borderColor: 'hover:border-yellow-400/40',
    tagColor: 'bg-yellow-400/10 text-yellow-200 border-yellow-400/20',
    keyPortalUrl: 'https://huggingface.co/settings/tokens',
    description: 'Access 300,000+ open-source models via Serverless Inference API.',
    freeTierPerks: 'Free community tier with rate limit',
    keyPlaceholder: 'hf_...',
    keyPrefixHint: 'Starts with hf_',
  },
];

interface UserKeyRecord {
  provider: string;
  created_at: string;
  status?: 'active' | 'revoked' | 'invalid';
}

export const BYOKManager: React.FC = () => {
  const { showToast } = useToast();
  const [userKeys, setUserKeys] = useState<Record<string, UserKeyRecord>>({});
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submittingProvider, setSubmittingProvider] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<string>('all');

  const fetchKeys = async () => {
    try {
      setLoading(true);
      const res = await apiClient.get<UserKeyRecord[]>('/keys/');
      const keyMap: Record<string, UserKeyRecord> = {};
      if (Array.isArray(res)) {
        res.forEach((k) => {
          keyMap[k.provider.toLowerCase()] = k;
        });
      }
      setUserKeys(keyMap);
    } catch {
      // Non-blocking in dev or if keys table is newly provisioned
      setUserKeys({});
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleSaveKey = async (providerId: string) => {
    const rawKey = inputValues[providerId]?.trim();
    if (!rawKey) {
      showToast('error', 'Please enter an API key before saving.');
      return;
    }

    try {
      setSubmittingProvider(providerId);
      await apiClient.post('/keys/', {
        provider: providerId,
        api_key: rawKey,
      });

      showToast('success', `${providerId.toUpperCase()} API Key encrypted and linked to pool!`);
      setInputValues((prev) => ({ ...prev, [providerId]: '' }));
      await fetchKeys();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save API key';
      showToast('error', msg);
    } finally {
      setSubmittingProvider(null);
    }
  };

  const handleDeleteKey = async (providerId: string) => {
    try {
      setSubmittingProvider(providerId);
      await apiClient.delete(`/keys/${providerId}`);
      showToast('success', `${providerId.toUpperCase()} key removed from pool.`);
      await fetchKeys();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to remove API key';
      showToast('error', msg);
    } finally {
      setSubmittingProvider(null);
    }
  };

  const [isAuditing, setIsAuditing] = useState(false);
  const handleDailyRecheck = async () => {
    try {
      setIsAuditing(true);
      const results = await apiClient.post<Array<{ provider: string; status: string; message: string }>>('/keys/audit/daily-recheck');
      const invalidOnes = (results || []).filter((r) => r.status === 'invalid');
      if (invalidOnes.length > 0) {
        showToast('error', `Audit Alert: ${invalidOnes.length} key(s) are invalid/revoked! Bonus quota decreased.`);
      } else {
        showToast('success', 'All registered keys are healthy! Full bonus quota active.');
      }
      await fetchKeys();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Daily audit check failed';
      showToast('error', msg);
    } finally {
      setIsAuditing(false);
    }
  };

  const activeKeys = Object.values(userKeys).filter((k) => k.status !== 'invalid');
  const invalidKeys = Object.values(userKeys).filter((k) => k.status === 'invalid');
  const activeKeysCount = activeKeys.length;
  const quotaBonusRequests = activeKeysCount * 200;
  const quotaBonusTokens = activeKeysCount * 500;

  const filteredProviders = PROVIDERS.filter((p) => {
    if (filterCategory === 'all') return true;
    return p.category === filterCategory;
  });

  return (
    <div className="w-full max-w-7xl mx-auto px-4 py-8 space-y-8">
      {/* 🌟 HERO & STATS BANNER */}
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-950/90 to-cyan-950/40 p-8 backdrop-blur-xl shadow-2xl">
        <div className="absolute top-0 right-0 -mt-10 -mr-10 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 -mb-10 -ml-10 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
          <div className="space-y-3 max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-medium">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Collective AI Infrastructure • BYOK</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Bring Your Own API Key & Boost Quota
            </h1>
            <p className="text-sm text-slate-300 leading-relaxed">
              Top 10-12টি AI প্রোভাইডারের ফ্রি-টিয়ার কি ১-ক্লিকে তৈরি করে যোগ করুন। আপনার কী সম্পূর্ণ এনক্রিপ্ট হয়ে 
              <span className="text-cyan-400 font-medium"> Infisical Vault</span> ও আমাদের রোটেটিং API পুলে যুক্ত হবে। 
              প্রতিটি কি যুক্ত করায় আনলক হবে অতিরিক্ত দৈনিক কোটা ও সর্বোচ্চ থ্রুপুট!
            </p>
          </div>

          {/* Quota Multiplier Card */}
          <div className="w-full lg:w-auto min-w-0 sm:min-w-[280px] p-5 rounded-2xl bg-white/[0.04] border border-white/10 backdrop-blur-md space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-slate-400 font-semibold">Active Pool Keys</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30">
                {activeKeysCount} / {PROVIDERS.length} Connected
              </span>
            </div>

            {/* Progress Bar */}
            <div className="space-y-1.5">
              <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(100, (activeKeysCount / PROVIDERS.length) * 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-slate-400">
                <span>Default: Unlimited</span>
                <span className="text-cyan-300 font-medium">+{quotaBonusRequests} req/day boost</span>
              </div>
            </div>

            <div className="pt-2 border-t border-white/10 flex items-center justify-between text-xs">
              <span className="text-slate-300 flex items-center gap-1.5">
                <Zap className="w-4 h-4 text-amber-400" /> Token Multiplier
              </span>
              <span className="font-semibold text-white">+{quotaBonusTokens}K Tokens / day</span>
            </div>
          </div>
        </div>
      </div>

      {/* 🧭 FILTER TABS */}
      <div className="flex items-center justify-between flex-wrap gap-4 border-b border-white/10 pb-4">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {[
            { id: 'all', label: 'All Providers (12)' },
            { id: 'flagship', label: 'Flagship (Gemini, Claude, GPT, Mistral, DeepSeek)' },
            { id: 'ultra_fast', label: 'Ultra Fast (Groq, Cerebras)' },
            { id: 'open_source', label: 'Open Source (Together, OpenRouter, HF)' },
            { id: 'specialized', label: 'Specialized (Cohere, Perplexity)' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilterCategory(tab.id)}
              className={`px-4 py-2 text-xs font-medium rounded-xl transition-all whitespace-nowrap ${
                filterCategory === tab.id
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/20'
                  : 'bg-white/[0.02] text-slate-400 border border-transparent hover:text-slate-200 hover:bg-white/[0.05]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleDailyRecheck}
            disabled={isAuditing || loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 rounded-lg transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isAuditing ? 'animate-spin' : ''}`} />
            <span>{isAuditing ? 'Rechecking Keys...' : 'Run Daily Audit Recheck'}</span>
          </button>

          <button
            onClick={fetchKeys}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-white bg-white/[0.03] hover:bg-white/[0.08] border border-white/10 rounded-lg transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      {/* ⚠️ INVALID KEYS ALERT NOTICE */}
      {invalidKeys.length > 0 && (
        <div className="rounded-2xl border border-red-500/30 bg-red-950/30 p-4 flex items-start gap-3 backdrop-blur-md">
          <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="space-y-1 text-xs">
            <p className="font-semibold text-red-300">
              Notice: {invalidKeys.length} API Key(s) were marked Invalid during Daily Auto-Audit!
            </p>
            <p className="text-slate-300">
              নিম্নলিখিত কী-গুলো প্রভাইডার কনসোল থেকে এক্সপায়ার্ড বা রিভোকড হয়ে গেছে: 
              <span className="font-mono text-red-300 ml-1">
                {invalidKeys.map((k) => k.provider.toUpperCase()).join(', ')}
              </span>
              । এর ফলে সাময়িকভাবে বোনাস কোটা রিমুভ হয়েছে। দয়া করে নতুন কী যোগ করে আপডেট করুন।
            </p>
          </div>
        </div>
      )}

      {/* 🧩 PROVIDERS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredProviders.map((provider) => {
          const isConnected = !!userKeys[provider.id.toLowerCase()];
          const isSubmitting = submittingProvider === provider.id;
          const currentInput = inputValues[provider.id] || '';

          return (
            <div
              key={provider.id}
              className={`group flex flex-col justify-between rounded-2xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-md transition-all duration-200 ${provider.borderColor} hover:shadow-xl hover:shadow-black/40`}
            >
              {/* Card Header */}
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-11 h-11 rounded-xl flex items-center justify-center text-xl bg-gradient-to-br ${provider.accentColor} border border-white/10 shadow-inner`}>
                      {provider.logoText}
                    </div>
                    <div>
                      <h3 className="font-semibold text-white text-base flex items-center gap-2">
                        {provider.name}
                      </h3>
                      <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium border ${provider.tagColor}`}>
                        {provider.freeTierPerks}
                      </span>
                    </div>
                  </div>

                  {isConnected ? (
                    <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-1 rounded-full">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Active</span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[11px] font-medium text-slate-400 bg-white/5 border border-white/10 px-2 py-1 rounded-full">
                      <KeyRound className="w-3.5 h-3.5" />
                      <span>Not Set</span>
                    </span>
                  )}
                </div>

                <p className="text-xs text-slate-400 leading-relaxed min-h-[36px]">
                  {provider.description}
                </p>
              </div>

              {/* Card Action & Input Section */}
              <div className="mt-5 pt-4 border-t border-white/10 space-y-3">
                {/* 1-Click Direct Shortcut Link */}
                <a
                  href={provider.keyPortalUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-medium text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 rounded-xl transition duration-150 group-hover:border-cyan-400/50"
                >
                  <span>1-Click: Get {provider.name} Key</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>

                {/* Key Input / Masked Status */}
                {isConnected ? (
                  <div className="space-y-2">
                    <div className={`flex items-center justify-between px-3 py-2 rounded-xl bg-black/40 border text-xs ${
                      userKeys[provider.id].status === 'invalid'
                        ? 'border-red-500/40 text-red-300'
                        : 'border-emerald-500/20 text-emerald-300'
                    }`}>
                      <div className="flex items-center gap-2 font-mono">
                        {userKeys[provider.id].status === 'invalid' ? (
                          <AlertTriangle className="w-4 h-4 text-red-400" />
                        ) : (
                          <ShieldCheck className="w-4 h-4 text-emerald-400" />
                        )}
                        <span>•••••••••••••••• (Encrypted)</span>
                      </div>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                        userKeys[provider.id].status === 'invalid'
                          ? 'bg-red-500/20 text-red-400'
                          : 'bg-emerald-500/10 text-emerald-400'
                      }`}>
                        {userKeys[provider.id].status === 'invalid' ? 'Invalid / Revoked' : 'In Pool'}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                      <span>Linked {new Date(userKeys[provider.id].created_at).toLocaleDateString()}</span>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => {
                            setUserKeys((prev) => {
                              const copy = { ...prev };
                              delete copy[provider.id];
                              return copy;
                            });
                          }}
                          className="text-cyan-400 hover:text-cyan-300 hover:underline"
                        >
                          Update
                        </button>
                        <button
                          onClick={() => handleDeleteKey(provider.id)}
                          disabled={submittingProvider === provider.id}
                          className="text-red-400 hover:text-red-300 hover:underline flex items-center gap-1"
                          title="Remove key from pool"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Remove</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="relative">
                      <input
                        type="password"
                        value={currentInput}
                        onChange={(e) =>
                          setInputValues((prev) => ({
                            ...prev,
                            [provider.id]: e.target.value,
                          }))
                        }
                        placeholder={provider.keyPlaceholder}
                        className="w-full px-3 py-2 pr-16 rounded-xl bg-black/40 border border-white/10 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/60 font-mono transition"
                      />
                      <button
                        onClick={() => handleSaveKey(provider.id)}
                        disabled={isSubmitting || !currentInput}
                        className="absolute right-1 top-1 bottom-1 px-3 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-semibold text-xs rounded-lg transition flex items-center gap-1"
                      >
                        {isSubmitting ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-white" />
                        ) : (
                          <span>Save</span>
                        )}
                      </button>
                    </div>
                    <p className="text-[10px] text-slate-500 flex items-center gap-1">
                      <Info className="w-3 h-3" />
                      <span>{provider.keyPrefixHint}</span>
                    </p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 🛡️ SECURITY & POOL POLICY NOTICE */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5 flex items-start gap-4 text-xs text-slate-400">
        <ShieldCheck className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-medium text-slate-200">
            SupremeAI End-to-End Vault & Collective Pool Guarantee
          </p>
          <p className="leading-relaxed">
            আপনার প্রদান করা সমস্ত API Key শিল্প-মান Fernet ও SHA-256 দিয়ে এনক্রিপ্ট হয়ে আমাদের Infisical Cloud Vault-এ সংরক্ষিত হয়। 
            কী-গুলো শুধুমাত্র আমাদের সেন্ট্রাল প্রক্সি ও রেট-লিমিট অপটিমাইজারে রাউন্ড-রবিন উপায়ে ব্যবহৃত হবে, যাতে যেকোনো প্রোভাইডার ডাউন হলেও 
            আপনি ও কমিউনিটি সর্বদা নির্বিঘ্ন সেবা উপভোগ করতে পারেন।
          </p>
        </div>
      </div>
    </div>
  );
};

export const BYOKPage: React.FC = () => {
  return (
    <WorkspaceLayout>
      <BYOKManager />
    </WorkspaceLayout>
  );
};

export default BYOKPage;
