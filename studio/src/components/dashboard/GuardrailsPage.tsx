import { useState, useEffect } from 'react';
import { Shield, Save, Loader2, Globe, Server, Code2 } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { useToast } from '../../contexts/useToast';

interface ExecutionPolicy {
  id: string;
  scope: 'global' | 'platform' | 'action';
  target_name: string; // e.g. '*' for global, 'github.com' for platform, 'login_btn' for action
  max_timeout_ms: number;
  max_compute_usd: number;
  max_retries: number;
  cb_failure_threshold: number;
  cooldown_window_sec: number;
}

export function GuardrailsPage() {
  const [policies, setPolicies] = useState<ExecutionPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const { showToast } = useToast();

  const [activeScope, setActiveScope] = useState<'global' | 'platform' | 'action'>('global');

  useEffect(() => {
    apiClient.get<{items: ExecutionPolicy[]}>('/api/admin/execution-policies')
      .then(data => setPolicies(data.items || []))
      .catch(err => console.error("Failed to load policies", err))
      .finally(() => setLoading(false));
  }, []);

  const handleUpdate = async (id: string, updates: Partial<ExecutionPolicy>) => {
    setSavingId(id);
    try {
      const updated = await apiClient.put<ExecutionPolicy>(`/api/admin/execution-policies/${id}`, updates);
      setPolicies(policies.map(p => p.id === id ? updated : p));
      // বাংলা মন্তব্য: Toast এর সঠিক প্যারামিটার অর্ডার (type, message) পাস করা হলো
      showToast('success', 'Policy updated successfully');
    } catch (err) {
      console.error("Policy update failed", err);
      showToast('error', 'Failed to update policy');
    } finally {
      setSavingId(null);
    }
  };

  const filteredPolicies = policies.filter(p => p.scope === activeScope);

  const PolicyCard = ({ policy }: { policy: ExecutionPolicy }) => (
    <div className="bg-[#1e1e1e] border border-gray-800 rounded-xl p-6 shadow-lg mb-4">
      <div className="flex items-center justify-between border-b border-gray-800 pb-4 mb-5">
        <div>
          <h3 className="text-lg font-semibold text-gray-200 flex items-center gap-2">
            {policy.scope === 'global' ? <Globe size={18} className="text-blue-500" /> :
             policy.scope === 'platform' ? <Server size={18} className="text-emerald-500" /> :
             <Code2 size={18} className="text-purple-500" />}
            {policy.target_name === '*' ? 'Global Default Baseline' : `Target: ${policy.target_name}`}
          </h3>
          <p className="text-xs text-gray-500 mt-1">ID: {policy.id}</p>
        </div>
        <button
          disabled={savingId === policy.id}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm text-white transition-colors"
        >
          {savingId === policy.id ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          Force Save
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">

        {/* Sliders */}
        <div className="space-y-6">
          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-300">Max Compute Budget (USD)</span>
              <span className="text-emerald-400 font-mono">${policy.max_compute_usd.toFixed(2)}</span>
            </div>
            <input
              type="range" min="0" max="10" step="0.01"
              value={policy.max_compute_usd}
              onChange={(e) => handleUpdate(policy.id, { max_compute_usd: parseFloat(e.target.value) })}
              className="w-full accent-emerald-500"
            />
          </div>

          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-300">Max Execution Timeout (ms)</span>
              <span className="text-amber-400 font-mono">{policy.max_timeout_ms.toLocaleString()} ms</span>
            </div>
            <input
              type="range" min="1000" max="60000" step="1000"
              value={policy.max_timeout_ms}
              onChange={(e) => handleUpdate(policy.id, { max_timeout_ms: parseInt(e.target.value) })}
              className="w-full accent-amber-500"
            />
          </div>

          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-300">Max Retries</span>
              <span className="text-blue-400 font-mono">{policy.max_retries} attempts</span>
            </div>
            <input
              type="range" min="0" max="10" step="1"
              value={policy.max_retries}
              onChange={(e) => handleUpdate(policy.id, { max_retries: parseInt(e.target.value) })}
              className="w-full accent-blue-500"
            />
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-300">Circuit Breaker Threshold</span>
              <span className="text-red-400 font-mono">{policy.cb_failure_threshold} consecutive failures</span>
            </div>
            <input
              type="range" min="1" max="20" step="1"
              value={policy.cb_failure_threshold}
              onChange={(e) => handleUpdate(policy.id, { cb_failure_threshold: parseInt(e.target.value) })}
              className="w-full accent-red-500"
            />
          </div>

          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-300">Cooldown Window (Seconds)</span>
              <span className="text-purple-400 font-mono">{policy.cooldown_window_sec}s lock</span>
            </div>
            <input
              type="range" min="10" max="3600" step="10"
              value={policy.cooldown_window_sec}
              onChange={(e) => handleUpdate(policy.id, { cooldown_window_sec: parseInt(e.target.value) })}
              className="w-full accent-purple-500"
            />
          </div>
        </div>

      </div>
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Shield size={28} className="text-blue-500" />
        <div>
          <h1 className="text-2xl font-semibold text-white">Execution Guardrails</h1>
          <p className="text-sm text-slate-400">Strict runtime budget limits and circuit breakers.</p>
        </div>
      </div>

      {/* Scope Swapper */}
      <div className="flex gap-2 mb-8 p-1 bg-black/40 border border-gray-800 rounded-lg inline-flex">
        <button
          onClick={() => setActiveScope('global')}
          className={`px-6 py-2 text-sm font-medium rounded-md transition-all ${activeScope === 'global' ? 'bg-gray-800 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
        >
          <Globe size={14} className="inline mr-2" /> Global
        </button>
        <button
          onClick={() => setActiveScope('platform')}
          className={`px-6 py-2 text-sm font-medium rounded-md transition-all ${activeScope === 'platform' ? 'bg-gray-800 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
        >
          <Server size={14} className="inline mr-2" /> Per-Platform
        </button>
        <button
          onClick={() => setActiveScope('action')}
          className={`px-6 py-2 text-sm font-medium rounded-md transition-all ${activeScope === 'action' ? 'bg-gray-800 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
        >
          <Code2 size={14} className="inline mr-2" /> Per-Action
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-20 text-slate-400">
          <Loader2 size={24} className="animate-spin" />
        </div>
      ) : (
        <div>
           {filteredPolicies.length === 0 ? (
             <div className="text-center py-20 bg-[#1e1e1e] border border-gray-800 border-dashed rounded-xl text-gray-500">
               No policies defined for this scope.
             </div>
           ) : (
             filteredPolicies.map(p => <PolicyCard key={p.id} policy={p} />)
           )}
        </div>
      )}
    </div>
  );
}
