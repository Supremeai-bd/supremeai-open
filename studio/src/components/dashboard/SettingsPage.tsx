import { useState, useEffect } from 'react';
import { Save, Loader2, Shield, Trash2, Cpu } from 'lucide-react';
import { useWorkspaceSettings, WORKSPACE_MODULES, type WorkspaceModuleId } from '../../hooks/useWorkspaceSettings';
import { apiClient } from '../../services/apiClient';
import { connectionsApi } from '../../services/connectionsApi';
import {
  EXECUTION_MODES,
  EXECUTION_MODE_LABELS,
  DEFAULT_EXECUTION_MODE,
  type ExecutionMode,
} from '../../types/contracts/execution-mode';
// বাংলা মন্তব্য: বাহিরের মডেল নামের বদলে SupremeAI ব্র্যান্ডেড নাম + ক্যানোনিক্যাল মডেল লিস্ট
import { getSupremeModelLabel, SUPREME_AVAILABLE_MODELS } from '../../lib/modelBranding';

interface Preferences {
  theme: string;
  default_model: string;
  max_tokens: number;
  auto_save: boolean;
  verbosity: string;
}

const DEFAULT_PREFS: Preferences = {
  theme: 'dark',
  default_model: 'gpt-4o',
  max_tokens: 4096,
  auto_save: true,
  verbosity: 'normal',
};

const MODELS = SUPREME_AVAILABLE_MODELS;

interface SettingsPageProps {
  /* RESTORE-AND-WIRE (2026-09-14): widened to the app's full Theme union
     (contexts/ThemeConstants.ts) so the page can be routed from App.tsx; the
     dark/light toggles below still key off 'dark' exactly as before. */
  theme: 'dark' | 'light' | 'sunset' | 'matrix';
  toggleTheme: () => void;
}

export function SettingsPage({ theme, toggleTheme }: SettingsPageProps) {
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [trustedBrowsers, setTrustedBrowsers] = useState<Array<{ id: string; created_at: number }>>([]);
  const [trustedBrowserStatus, setTrustedBrowserStatus] = useState('');
  const [executionMode, setExecutionMode] = useState<ExecutionMode>(DEFAULT_EXECUTION_MODE);
  const [executionModeStatus, setExecutionModeStatus] = useState('');
  const [savingMode, setSavingMode] = useState(false);
  const enabledModules = useWorkspaceSettings((state) => state.enabledModules);
  const toggleModule = useWorkspaceSettings((state) => state.toggleModule);
  const resetModules = useWorkspaceSettings((state) => state.resetModules);

  useEffect(() => {
    connectionsApi
      .getMyWorkspace()
      .then((data) => {
        if (data?.executionMode) {
          setExecutionMode(data.executionMode);
        }
      })
      .catch(() => {
        // Non-blocking fallback to default execution mode
      });
  }, []);

  useEffect(() => {
    apiClient
      .get<Partial<Preferences>>('/api/preferences/?user_id=default')
      .then((data) => setPrefs({ ...DEFAULT_PREFS, ...data }))
      .catch(() => setStatus('Failed to load preferences — using defaults.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    apiClient.get<{ browsers: Array<{ id: string; created_at: number }> }>('/admin/trusted-browsers')
      .then((data) => setTrustedBrowsers(data.browsers || []))
      // Issue #1819: no longer silently swallow load errors — the empty-list
      // render must not mask a dead endpoint (this exact silence hid the
      // path mismatch that kept the feature dead).
      .catch(() => {
        setTrustedBrowsers([]);
        setTrustedBrowserStatus('Unable to load trusted browsers.');
      });
  }, []);

  const revokeBrowser = async (id: string) => {
    setTrustedBrowserStatus('Revoking...');
    try {
      await apiClient.delete(`/admin/trusted-browsers/${encodeURIComponent(id)}`);
      setTrustedBrowsers((items) => items.filter((item) => item.id !== id));
      setTrustedBrowserStatus('Browser revoked.');
    } catch (error) {
      setTrustedBrowserStatus(error instanceof Error ? error.message : 'Unable to revoke browser.');
    }
  };

  const revokeAllBrowsers = async () => {
    setTrustedBrowserStatus('Revoking all...');
    try {
      await apiClient.delete('/admin/trusted-browsers');
      setTrustedBrowsers([]);
      setTrustedBrowserStatus('All trusted browsers revoked.');
    } catch (error) {
      setTrustedBrowserStatus(error instanceof Error ? error.message : 'Unable to revoke browsers.');
    }
  };

  const handleExecutionModeChange = async (mode: ExecutionMode) => {
    setExecutionMode(mode);
    setSavingMode(true);
    setExecutionModeStatus('Updating execution mode...');
    try {
      const res = await connectionsApi.setExecutionMode(mode);
      setExecutionModeStatus(res.message || `Execution mode set to ${mode}.`);
    } catch (error) {
      setExecutionModeStatus(`Failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setSavingMode(false);
      setTimeout(() => setExecutionModeStatus(''), 4000);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setStatus('');
    try {
      await apiClient.post('/api/preferences/?user_id=default', {
        theme: prefs.theme,
        default_model: prefs.default_model,
        max_tokens: prefs.max_tokens,
        auto_save: prefs.auto_save,
        verbosity: prefs.verbosity,
      });
      setStatus('Preferences saved.');
    } catch (error) {
      setStatus(`Save failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
      setTimeout(() => setStatus(''), 3000);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-lg font-semibold text-text mb-1">Settings</h1>
      <p className="text-xs text-secondary mb-6">Manage your workspace preferences.</p>

      <div className="flex flex-col gap-5">
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="text-sm font-medium text-text mb-3">Appearance</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-text">Theme</p>
              <p className="text-[11px] text-secondary">Switch between dark, light, sunset, and matrix themes.</p>
            </div>
            <button
              data-testid="settings-theme-toggle"
              type="button"
              onClick={() => {
                toggleTheme();
              }}
              className="px-3 py-1.5 rounded-lg border border-border text-xs text-text hover:opacity-80 transition-opacity capitalize"
            >
              {theme === 'dark' ? 'Switch to Light' : 'Switch to Dark'}
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5 flex flex-col gap-4">
          <h2 className="text-sm font-medium text-white">AI Model</h2>
          <div>
            <label className="block text-xs text-slate-300 mb-1" htmlFor="default-model">
              Default model
            </label>
            <select
              id="default-model"
              value={prefs.default_model}
              onChange={(e) => setPrefs((p) => ({ ...p, default_model: e.target.value }))}
              className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-xs text-white outline-none focus:border-blue-500/50"
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>
                  {getSupremeModelLabel(m)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-300 mb-1" htmlFor="max-tokens">
              Max tokens per response
            </label>
            <input
              id="max-tokens"
              type="number"
              min={256}
              max={128000}
              value={prefs.max_tokens}
              onChange={(e) => setPrefs((p) => ({ ...p, max_tokens: Number(e.target.value) }))}
              className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-xs text-white outline-none focus:border-blue-500/50"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-300 mb-1" htmlFor="verbosity">
              Response verbosity
            </label>
            <select
              id="verbosity"
              value={prefs.verbosity}
              onChange={(e) => setPrefs((p) => ({ ...p, verbosity: e.target.value }))}
              className="w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-xs text-white outline-none focus:border-blue-500/50"
            >
              <option value="concise">Concise</option>
              <option value="normal">Normal</option>
              <option value="detailed">Detailed</option>
            </select>
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 className="text-sm font-medium text-white">Workspace tools</h2>
              <p className="text-[11px] text-slate-400">Choose which capabilities appear in your workspace. Advanced tools stay off until you opt in.</p>
            </div>
            <button type="button" onClick={resetModules} className="text-[11px] text-blue-300 hover:text-blue-200">Reset</button>
          </div>
          <div className="flex flex-col gap-3">
            {WORKSPACE_MODULES.map((module) => {
              const checked = enabledModules.includes(module.id);
              const isCore = ['ask', 'projects', 'files', 'activity', 'agents'].includes(module.id);
              return (
                <label key={module.id} className="flex items-center justify-between gap-4 cursor-pointer">
                  <span>
                    <span className="block text-xs text-slate-300">{module.label}{module.advanced ? ' (advanced)' : ''}</span>
                    <span className="block text-[11px] text-slate-500">{module.description}</span>
                  </span>
                  <input
                    type="checkbox"
                    aria-label={`Enable ${module.label}`}
                    checked={checked}
                    disabled={isCore}
                    onChange={() => toggleModule(module.id as WorkspaceModuleId)}
                    className="w-4 h-4 accent-blue-600"
                  />
                </label>
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
          <h2 className="text-sm font-medium text-white mb-3">Workspace</h2>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <p className="text-xs text-slate-300">Auto-save</p>
              <p className="text-[11px] text-slate-400">Automatically save workspace changes.</p>
            </div>
            <input
              type="checkbox"
              checked={prefs.auto_save}
              onChange={(e) => setPrefs((p) => ({ ...p, auto_save: e.target.checked }))}
              className="w-4 h-4 accent-blue-600"
            />
          </label>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
          <div className="flex items-start justify-between gap-4 mb-3">
            <div className="flex items-start gap-2">
              <Cpu size={16} className="text-blue-400 mt-0.5" />
              <div>
                <h2 className="text-sm font-medium text-white">Execution Mode</h2>
                <p className="text-[11px] text-slate-400">
                  Control the autonomy level of AI agent actions in your workspace.
                </p>
              </div>
            </div>
            {savingMode && <Loader2 size={14} className="animate-spin text-blue-400 mt-1" />}
          </div>

          <div className="space-y-2 mt-3" data-testid="execution-mode-options">
            {EXECUTION_MODES.map((mode) => {
              const isSelected = executionMode === mode;
              return (
                <label
                  key={mode}
                  data-testid={`execution-mode-${mode}`}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    isSelected
                      ? 'border-blue-500/50 bg-blue-500/10'
                      : 'border-white/10 hover:bg-white/[0.02]'
                  }`}
                >
                  <input
                    type="radio"
                    name="execution_mode"
                    value={mode}
                    checked={isSelected}
                    disabled={savingMode}
                    onChange={() => handleExecutionModeChange(mode)}
                    className="w-4 h-4 accent-blue-600 mt-0.5"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-slate-200 capitalize">
                        {mode.replace(/_/g, ' ')}
                      </span>
                      {mode === DEFAULT_EXECUTION_MODE && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-slate-400">
                          Default
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {EXECUTION_MODE_LABELS[mode]}
                    </p>
                  </div>
                </label>
              );
            })}
          </div>
          {executionModeStatus && (
            <p className="text-[11px] text-slate-400 mt-3" data-testid="execution-mode-status">
              {executionModeStatus}
            </p>
          )}
        </div>

        <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.04] p-5">
          <div className="flex items-start justify-between gap-4 mb-3">
            <div className="flex items-start gap-2">
              <Shield size={16} className="text-amber-300 mt-0.5" />
              <div>
                <h2 className="text-sm font-medium text-white">Authorized browsers</h2>
                <p className="text-[11px] text-slate-400">Admin browsers trusted for seven days without another TOTP prompt.</p>
              </div>
            </div>
            {trustedBrowsers.length > 0 && <button onClick={revokeAllBrowsers} className="text-[11px] text-red-300 hover:text-red-200">Revoke all</button>}
          </div>
          {trustedBrowsers.length === 0 ? (
            <p className="text-xs text-slate-500">No trusted browsers found, or this account is not an admin.</p>
          ) : (
            <div className="space-y-2">
              {trustedBrowsers.map((browser) => (
                <div key={browser.id} className="flex items-center justify-between rounded-lg border border-white/10 px-3 py-2">
                  <span className="text-xs text-slate-300">Browser authorized {new Date(browser.created_at * 1000).toLocaleDateString()}</span>
                  <button aria-label="Revoke browser" onClick={() => revokeBrowser(browser.id)} className="text-slate-400 hover:text-red-300"><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
          )}
          {trustedBrowserStatus && <p className="text-[11px] text-slate-400 mt-3">{trustedBrowserStatus}</p>}
        </div>

        <div className="flex items-center gap-3">
          <button
            data-testid="settings-save-btn"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white text-xs font-medium transition-colors"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            Save preferences
          </button>
          {status && <span className="text-xs text-slate-400">{status}</span>}
        </div>
      </div>
    </div>
  );
}
