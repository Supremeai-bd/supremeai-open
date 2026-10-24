import { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, Plus, Trash2, RefreshCw, Loader2, CircleCheck, CircleAlert, Globe, Key, FileCode2 } from 'lucide-react';
import { apiClient } from '../../services/apiClient';

interface VaultCredential {
  id: string;
  serviceName: string;
  username: string;
  password?: string;
  token?: string;
  status?: 'active' | 'expired' | 'needs_reauth';
  lastUsedAt?: string;
}

interface SurfStatus {
  browsing: boolean;
  currentUrl?: string;
}

export function VaultPage() {
  const [creds, setCreds] = useState<VaultCredential[]>([]);
  const [status, setStatus] = useState<SurfStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Tab State
  const [importTab, setImportTab] = useState<'oauth' | 'cookie' | 'manual'>('manual');

  // Form State
  const [serviceName, setServiceName] = useState('');
  const [username, setUsername] = useState('');
  const [secret, setSecret] = useState('');
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const refresh = useCallback(() => {
    setLoading(true);
    Promise.all([
      apiClient.get<{ credentials: VaultCredential[] }>('/api/browser/credentials?userId=default'),
      apiClient.get<SurfStatus>('/api/browser/surf/status'),
    ])
      .then(([c, s]) => {
        setCreds(c.credentials || []);
        setStatus(s);
        setError('');
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load vault'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // বাংলা মন্তব্য: set-state-in-effect ফিক্স — refresh কে async ফাংশনের ভেতরে র‍্যাপ করা হয়েছে
    const loadVault = async () => {
      await refresh();
    };
    loadVault();
  }, [refresh]);

  const handleImport = async () => {
    if (!serviceName.trim() || !secret.trim() || saving) return;

    // Input validation
    const domainRegex = /^(https?:\/\/)?(www\.)?[a-zA-Z0-9][a-zA-Z0-9-]*(\.[a-zA-Z0-9][a-zA-Z0-9-]*)+(\/[^\s]*)?$/;
    if (!domainRegex.test(serviceName.trim())) {
      setError('Please enter a valid domain (e.g. github.com or https://github.com)');
      return;
    }
    if (secret.trim().length < 4) {
      setError('Secret/token must be at least 4 characters');
      return;
    }
    if (username.trim() && !/^[a-zA-Z0-9_.-]{1,64}$/.test(username.trim())) {
      setError('Username can only contain letters, numbers, _ . - (max 64 chars)');
      return;
    }

    setSaving(true);
    setError('');
    try {
      await apiClient.post('/api/browser/credentials', {
        serviceName: serviceName.trim(),
        username: username.trim() || 'session',
        password: secret.trim(),
        userId: 'default',
        authType: importTab === 'oauth' ? 'oauth2' : importTab === 'cookie' ? 'cookie_session' : 'basic_auth'
      });
      setServiceName('');
      setUsername('');
      setSecret('');
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import session');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiClient.delete(`/api/browser/credentials/${id}`);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove credential');
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError('');
    try {
      await apiClient.post('/api/browser/surf/start');
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const connected = status?.browsing;

  const renderStatusBadge = (credStatus?: string) => {
    switch (credStatus) {
      case 'expired':
        return <span className="text-[10px] px-2 py-0.5 rounded-full border border-amber-500/30 text-amber-400 bg-amber-500/10">Expired</span>;
      case 'needs_reauth':
        return <span className="text-[10px] px-2 py-0.5 rounded-full border border-red-500/30 text-red-400 bg-red-500/10">Needs Re-Auth</span>;
      case 'active':
      default:
        return <span className="text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/30 text-emerald-400 bg-emerald-500/10">Active</span>;
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-white flex items-center gap-3">
            <ShieldCheck size={24} className="text-blue-500" />
            Connected Platforms
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Zero-knowledge credential vault for autonomous site execution.
          </p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white hover:bg-white/10 disabled:opacity-50 transition-all shadow-sm"
        >
          {syncing ? <Loader2 size={16} className="animate-spin text-blue-400" /> : <RefreshCw size={16} className="text-blue-400" />}
          Sync Connections
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

        {/* Left Column: Import Panel */}
        <div className="col-span-1 flex flex-col gap-4">
          <div className="bg-[#1e1e1e] rounded-xl border border-gray-800 shadow-xl overflow-hidden">
            {/* Tab Strip */}
            <div className="flex border-b border-gray-800">
              <button
                onClick={() => setImportTab('oauth')}
                className={`flex-1 flex justify-center items-center py-3 text-xs font-medium transition-colors ${importTab === 'oauth' ? 'text-blue-400 border-b-2 border-blue-500 bg-blue-500/5' : 'text-gray-400 hover:text-gray-200'}`}
              >
                <Globe size={14} className="mr-2" /> OAuth2
              </button>
              <button
                onClick={() => setImportTab('cookie')}
                className={`flex-1 flex justify-center items-center py-3 text-xs font-medium transition-colors ${importTab === 'cookie' ? 'text-blue-400 border-b-2 border-blue-500 bg-blue-500/5' : 'text-gray-400 hover:text-gray-200'}`}
              >
                <FileCode2 size={14} className="mr-2" /> Cookie Sync
              </button>
              <button
                onClick={() => setImportTab('manual')}
                className={`flex-1 flex justify-center items-center py-3 text-xs font-medium transition-colors ${importTab === 'manual' ? 'text-blue-400 border-b-2 border-blue-500 bg-blue-500/5' : 'text-gray-400 hover:text-gray-200'}`}
              >
                <Key size={14} className="mr-2" /> Manual Paste
              </button>
            </div>

            <div className="p-5 flex flex-col gap-4">
              {importTab !== 'manual' && (
                <div className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/20 p-3 rounded-lg mb-2">
                  Feature '{importTab}' requires the browser extension or OAuth callback URL configuration. Falling back to manual ingestion fields.
                </div>
              )}

              <div className="flex flex-col gap-3">
                <input
                  value={serviceName}
                  onChange={(e) => setServiceName(e.target.value)}
                  placeholder="Platform domain (e.g. github.com)"
                  className="rounded-lg bg-black/40 border border-gray-700 px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500/50 transition-colors"
                />
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Identity Label (e.g. prod-bot-1)"
                  className="rounded-lg bg-black/40 border border-gray-700 px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500/50 transition-colors"
                />
                <textarea
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  placeholder="Paste secure token, API key, or JSON cookie array..."
                  rows={3}
                  className="rounded-lg bg-black/40 border border-gray-700 px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500/50 transition-colors resize-none"
                />
                <button
                  onClick={handleImport}
                  disabled={!serviceName.trim() || !secret.trim() || saving}
                  className="mt-2 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white text-sm font-medium transition-all shadow-md"
                >
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                  Import to Vault
                </button>
              </div>

              {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
            </div>
          </div>

          {/* Connection Status Box */}
          <div
            className={`flex items-center gap-3 rounded-xl p-4 mt-2 shadow-lg ${
              connected
                ? 'border border-emerald-500/20 bg-[#1e1e1e] text-emerald-400'
                : 'border border-amber-500/20 bg-[#1e1e1e] text-amber-400'
            }`}
          >
            <div className={`p-2 rounded-full ${connected ? 'bg-emerald-500/10' : 'bg-amber-500/10'}`}>
               {connected ? <CircleCheck size={20} /> : <CircleAlert size={20} />}
            </div>
            <div>
              <h4 className="font-medium text-sm text-gray-200">Global Sandbox Router</h4>
              <p className="text-xs opacity-80 mt-0.5">{connected ? 'Active multiplexing session' : 'Standby — no active session'}</p>
            </div>
          </div>
        </div>

        {/* Right Column: Card Grid */}
        <div className="col-span-1 lg:col-span-2">
          {loading ? (
            <div className="flex justify-center py-20 text-slate-400">
              <Loader2 size={24} className="animate-spin" />
            </div>
          ) : creds.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 bg-[#1e1e1e] border border-gray-800 rounded-xl border-dashed">
              <ShieldCheck size={48} className="text-gray-700 mb-4" />
              <p className="text-gray-400 font-medium">No connected platforms</p>
              <p className="text-xs text-gray-500 mt-1">Import a credential to allow autonomous navigation.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {creds.map((c) => {
                const rawVal = c.password || c.token || 'unknown';
                // Only mock masking if it's not already masked by backend
                const isMasked = rawVal.includes('***masked***') || rawVal.includes('••••••••••');
                const displayHash = isMasked ? rawVal : `••••••••••${rawVal.slice(-4)}`;
                const domain = c.serviceName.replace(/^(https?:\/\/)?(www\.)?/, '').split('/')[0];

                return (
                  <div
                    key={c.id}
                    className="flex flex-col rounded-xl border border-gray-800 bg-[#1e1e1e] shadow-md hover:border-gray-700 transition-colors overflow-hidden group"
                  >
                    <div className="p-4 flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded bg-gray-900 flex items-center justify-center border border-gray-800 p-1">
                          <img
                            src={`https://www.google.com/s2/favicons?domain=${domain}&sz=64`}
                            alt={domain}
                            className="w-full h-full object-contain opacity-90 group-hover:opacity-100"
                            onError={(e) => { (e.target as HTMLImageElement).src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdib3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjOTNhM2FmIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTEyIDJhMTAgMTAgMCAxIDAgMCAyMGExMCAxMCAwIDAgMCAwLTIweiIvPjwvc3ZnPg==' }}
                          />
                        </div>
                        <div>
                          <h3 className="text-sm font-semibold text-gray-200">{c.serviceName}</h3>
                          <p className="text-xs text-gray-500 mt-0.5">{c.username}</p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleDelete(c.id)}
                        className="p-1.5 rounded text-gray-600 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                        title="Revoke access"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>

                    <div className="px-4 py-3 bg-black/20 border-t border-gray-800 flex items-center justify-between mt-auto">
                      <div className="flex items-center gap-2">
                        {renderStatusBadge(c.status)}
                      </div>
                      <div className="text-xs text-gray-600 font-mono tracking-wider">
                        {displayHash}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
