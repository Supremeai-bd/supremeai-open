// বাংলা মন্তব্য: Devin-স্টাইল Secrets পেজ — ব্যাকএন্ড /api/api-keys দিয়ে API কী তৈরি, তালিকা, রিভোক ও ডিলিট করা হয়
import { useState, useEffect, useCallback } from 'react';
import { KeyRound, Plus, Trash2, Ban, Copy, Loader2 } from 'lucide-react';
import { apiClient } from '../../services/apiClient';

interface ApiKeyRecord {
  id: number;
  name: string;
  key_masked: string;
  rate_limit_rps: number;
  is_active?: boolean;
  revoked?: boolean;
  created_at?: string | number;
  expires_at?: string | number | null;
}

interface CreatedKey {
  key: string;
  name: string;
}

export function SecretsPage() {
  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreatedKey | null>(null);

  const fetchKeys = useCallback(() => {
    setLoading(true);
    apiClient
      .get<{ keys: ApiKeyRecord[] }>('/api/api-keys/')
      .then((data) => {
        setKeys(data.keys || []);
        setError('');
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load API keys'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // বাংলা মন্তব্য: set-state-in-effect ফিক্স — fetchKeys কে async ফাংশনের ভেতরে র‍্যাপ করা হয়েছে
    const loadKeys = async () => {
      await fetchKeys();
    };
    loadKeys();
  }, [fetchKeys]);

  const handleCreate = async () => {
    if (!newName.trim() || creating) return;
    setCreating(true);
    setError('');
    try {
      const res = await apiClient.post<{ key: string; name: string }>('/api/api-keys/create', {
        user_id: 'default',
        name: newName.trim(),
        rate_limit_rps: 6,
      });
      setCreatedKey({ key: res.key, name: res.name });
      setNewName('');
      fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: number) => {
    try {
      await apiClient.post(`/api/api-keys/${id}/revoke`);
      fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke key');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await apiClient.delete(`/api/api-keys/${id}`);
      fetchKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete key');
    }
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-lg font-semibold text-white mb-1">Secrets & API Keys</h1>
      <p className="text-xs text-slate-400 mb-6">
        Create and manage API keys for programmatic access. Keys are shown only once at creation.
      </p>

      <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 mb-6 flex items-center gap-2">
        <input
          data-testid="new-key-name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          placeholder="Key name (e.g. CI pipeline)"
          className="flex-1 rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-xs text-white placeholder-slate-500 outline-none focus:border-blue-500/50"
        />
        <button
          data-testid="create-key-btn"
          onClick={handleCreate}
          disabled={!newName.trim() || creating}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white text-xs font-medium transition-colors"
        >
          {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          Create key
        </button>
      </div>

      {createdKey && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/[0.06] p-4 mb-6">
          <p className="text-xs text-emerald-300 mb-2">
            Key "{createdKey.name}" created. Copy it now — it will not be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-[11px] text-white bg-black/40 rounded px-2 py-1.5 break-all">
              {createdKey.key}
            </code>
            <button
              aria-label="Copy key"
              onClick={() => navigator.clipboard?.writeText(createdKey.key)}
              className="p-1.5 rounded text-slate-300 hover:text-white hover:bg-white/[0.08] transition-colors"
            >
              <Copy size={13} />
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-rose-400 mb-4">{error}</p>}

      {loading ? (
        <div className="flex justify-center py-10 text-slate-400">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : keys.length === 0 ? (
        <p className="text-sm text-slate-400 text-center py-8">No API keys yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {keys.map((k) => (
            <li
              key={k.id}
              className="flex items-center gap-3 p-3 rounded-lg border border-white/[0.06] bg-white/[0.02]"
            >
              <KeyRound size={14} className="text-slate-400" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-white truncate">{k.name}</p>
                <p className="text-[11px] text-slate-400 font-mono">{k.key_masked}</p>
              </div>
              <span className="text-[10px] text-slate-400">{k.rate_limit_rps} rps</span>
              <button
                aria-label="Revoke key"
                title="Revoke"
                onClick={() => handleRevoke(k.id)}
                className="p-1.5 rounded text-slate-400 hover:text-amber-400 transition-colors"
              >
                <Ban size={13} />
              </button>
              <button
                aria-label="Delete key"
                title="Delete"
                onClick={() => handleDelete(k.id)}
                className="p-1.5 rounded text-slate-400 hover:text-rose-400 transition-colors"
              >
                <Trash2 size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
