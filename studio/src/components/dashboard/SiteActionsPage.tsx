import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, Pencil, Loader2, Table2, X, Check, Target, Activity } from 'lucide-react';
import { apiClient } from '../../services/apiClient';

interface SiteAction {
  id: number;
  site_name: string;
  url_pattern: string;
  action_name: string;
  selector: string;
  action_type: string;
  notes: string;
  enabled: boolean;
  fallback_selectors: string[];
  selector_strategy: 'exact' | 'fuzzy' | 'llm_fallback' | 'visual_anchor';
  health_score: number;
}

type DraftAction = Omit<SiteAction, 'id'> & { id?: number; fallback_input?: string };

const EMPTY_DRAFT: DraftAction = {
  site_name: '',
  url_pattern: '',
  action_name: '',
  selector: '',
  action_type: 'click',
  notes: '',
  enabled: true,
  fallback_selectors: [],
  selector_strategy: 'exact',
  health_score: 100,
  fallback_input: ''
};

const ACTION_TYPES = ['click', 'type', 'navigate', 'extract', 'wait', 'scroll', 'hover'];
const STRATEGIES = ['exact', 'fuzzy', 'llm_fallback', 'visual_anchor'];

export function SiteActionsPage() {
  const [actions, setActions] = useState<SiteAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<DraftAction>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // Test Selector Preview Modal
  const [testModal, setTestModal] = useState<{
    show: boolean;
    loading: boolean;
    screenshotUrl?: string;
    error?: string;
    selectorTested?: string;
  }>({ show: false, loading: false });

  const refresh = useCallback(() => {
    setLoading(true);
    apiClient
      .get<{ items: SiteAction[] }>('/api/admin/site-actions/')
      .then((data) => {
        setActions(data.items || []);
        setError('');
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load registry'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // বাংলা মন্তব্য: set-state-in-effect ফিক্স — refresh কে async ফাংশনের ভেতরে র‍্যাপ করা হয়েছে
    const loadActions = async () => {
      await refresh();
    };
    loadActions();
  }, [refresh]);

  const resetForm = () => {
    setDraft(EMPTY_DRAFT);
    setEditingId(null);
  };

  const handleSave = async () => {
    if (!draft.site_name.trim() || !draft.url_pattern.trim() || !draft.selector.trim() || saving) return;
    setSaving(true);
    setError('');

    // Clean up draft payload
    const { fallback_input: _fallback_input, ...payload } = draft;

    try {
      if (editingId != null) {
        await apiClient.put(`/api/admin/site-actions/${editingId}`, payload);
      } else {
        await apiClient.post('/api/admin/site-actions/', payload);
      }
      resetForm();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save action');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (a: SiteAction) => {
    setEditingId(a.id);
    const { id: _id, ...rest } = a;
    void _id;
    setDraft({ ...rest, fallback_input: '' });
  };

  const handleDelete = async (id: number) => {
    try {
      await apiClient.delete(`/api/admin/site-actions/${id}`);
      if (editingId === id) resetForm();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete action');
    }
  };

  const handleTestSelector = async (a: SiteAction) => {
    setTestModal({ show: true, loading: true, selectorTested: a.selector });
    try {
      const res = await apiClient.post<{ screenshot_base64: string, found: boolean }>('/api/admin/site-actions/test', {
        action_id: a.id
      });
      if (res.found && res.screenshot_base64) {
         setTestModal({
            show: true,
            loading: false,
            selectorTested: a.selector,
            screenshotUrl: `data:image/jpeg;base64,${res.screenshot_base64}`
         });
      } else {
         setTestModal({ show: true, loading: false, selectorTested: a.selector, error: "Selector not found on live page." });
      }
    } catch (err) {
      setTestModal({
        show: true,
        loading: false,
        selectorTested: a.selector,
        error: err instanceof Error ? err.message : "Test execution failed."
      });
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const setField = (field: keyof DraftAction, value: any) =>
    setDraft((d) => ({ ...d, [field]: value }));

  const handleAddFallback = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && draft.fallback_input?.trim()) {
       e.preventDefault();
       setField('fallback_selectors', [...draft.fallback_selectors, draft.fallback_input.trim()]);
       setField('fallback_input', '');
    }
  };

  const removeFallback = (idx: number) => {
    const newArr = [...draft.fallback_selectors];
    newArr.splice(idx, 1);
    setField('fallback_selectors', newArr);
  };

  const renderHealthScore = (score: number) => {
    const color = score > 80 ? 'text-emerald-400' : score > 50 ? 'text-amber-400' : 'text-red-400';
    return (
      <div className="flex items-center gap-1.5">
        <Activity size={12} className={color} />
        <span className={`${color} font-mono font-semibold`}>{score}%</span>
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold text-white flex items-center gap-3 mb-2">
        <Table2 size={24} className="text-blue-500" />
        Site Actions Registry
      </h1>
      <p className="text-sm text-slate-400 mb-6">
        Database-driven DOM interaction rules with strict validation strategies and self-healing telemetry mapping.
      </p>

      {/* Editor Form */}
      <div className="rounded-xl border border-gray-800 bg-[#1e1e1e] p-5 mb-8 shadow-xl">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">{editingId ? 'Edit Mapping Rule' : 'New Mapping Rule'}</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <input
            value={draft.site_name}
            onChange={(e) => setField('site_name', e.target.value)}
            placeholder="Site Name (e.g. Stripe Dash)"
            className="rounded-lg bg-black/40 border border-gray-700 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500/50"
          />
          <input
            value={draft.url_pattern}
            onChange={(e) => setField('url_pattern', e.target.value)}
            placeholder="URL Pattern (Regex/Glob)"
            className="rounded-lg bg-black/40 border border-gray-700 px-3 py-2 text-sm font-mono text-white placeholder-slate-500 outline-none focus:border-blue-500/50"
          />
          <input
            value={draft.action_name}
            onChange={(e) => setField('action_name', e.target.value)}
            placeholder="Action Identity (login_btn)"
            className="rounded-lg bg-black/40 border border-gray-700 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none focus:border-blue-500/50"
          />
          <div className="flex gap-2">
            <select
              value={draft.action_type}
              onChange={(e) => setField('action_type', e.target.value)}
              className="rounded-lg bg-black/40 border border-gray-700 px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50 flex-1"
            >
              {ACTION_TYPES.map((t) => (
                <option key={t} value={t} className="bg-gray-900">{t}</option>
              ))}
            </select>
            <select
              value={draft.selector_strategy}
              onChange={(e) => setField('selector_strategy', e.target.value)}
              className="rounded-lg bg-black/40 border border-gray-700 px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50 flex-1"
            >
              {STRATEGIES.map((t) => (
                <option key={t} value={t} className="bg-gray-900">{t}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
           <div>
             <input
                value={draft.selector}
                onChange={(e) => setField('selector', e.target.value)}
                placeholder="Primary CSS/XPath Selector"
                className="w-full rounded-lg bg-black/40 border border-gray-700 px-3 py-2 text-sm font-mono text-white placeholder-slate-500 outline-none focus:border-blue-500/50"
              />
           </div>

           {/* Tags Input */}
           <div className="flex items-center flex-wrap gap-2 p-2 rounded-lg bg-black/40 border border-gray-700 min-h-[42px]">
              {draft.fallback_selectors.map((sel, i) => (
                 <span key={i} className="flex items-center gap-1 bg-gray-800 text-gray-300 px-2 py-0.5 rounded text-xs font-mono">
                   {sel}
                   <button onClick={() => removeFallback(i)} className="text-gray-500 hover:text-red-400"><X size={10}/></button>
                 </span>
              ))}
              <input
                 value={draft.fallback_input}
                 onChange={(e) => setField('fallback_input', e.target.value)}
                 onKeyDown={handleAddFallback}
                 placeholder="Type fallback selector & press Enter..."
                 className="flex-1 bg-transparent outline-none text-sm text-white font-mono min-w-[200px]"
              />
           </div>
        </div>

        <div className="flex items-center justify-between border-t border-gray-800 pt-4 mt-2">
          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setField('enabled', e.target.checked)}
              className="accent-blue-500 w-4 h-4"
            />
            Execution Enabled
          </label>
          <div className="flex items-center gap-3">
            {editingId != null && (
              <button
                onClick={resetForm}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-700 text-sm text-gray-300 hover:bg-gray-800 transition-colors"
              >
                <X size={16} />
                Cancel
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={
                !draft.site_name.trim() ||
                !draft.url_pattern.trim() ||
                !draft.selector.trim() ||
                saving
              }
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-gray-800 disabled:text-gray-500 text-white text-sm font-semibold transition-all shadow-md"
            >
              {saving ? <Loader2 size={16} className="animate-spin" /> : (editingId != null ? <Check size={16} /> : <Plus size={16} />)}
              {editingId != null ? 'Commit Update' : 'Register Rule'}
            </button>
          </div>
        </div>
      </div>

      {error && <p className="text-sm text-red-400 mb-6 bg-red-500/10 p-3 rounded-lg border border-red-500/20">{error}</p>}

      {/* Registry Table */}
      {loading ? (
        <div className="flex justify-center py-10 text-gray-500">
          <Loader2 size={24} className="animate-spin" />
        </div>
      ) : actions.length === 0 ? (
        <div className="text-center py-16 border border-gray-800 border-dashed rounded-xl bg-[#1e1e1e]">
           <Table2 size={40} className="mx-auto text-gray-700 mb-4" />
           <p className="text-gray-400 font-medium">Registry Empty</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-800 shadow-lg bg-[#1e1e1e]">
          <table className="w-full text-left text-sm">
            <thead className="bg-black/40 text-gray-400 border-b border-gray-800">
              <tr>
                <th className="px-4 py-3 font-semibold">Site / Action</th>
                <th className="px-4 py-3 font-semibold">Selector (Primary)</th>
                <th className="px-4 py-3 font-semibold">Strategy</th>
                <th className="px-4 py-3 font-semibold">Health</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {actions.map((a) => (
                <tr key={a.id} className="hover:bg-white/5 transition-colors group">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-gray-200">{a.site_name}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{a.action_name} ({a.action_type})</div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-blue-300 max-w-[200px] truncate" title={a.selector}>
                    {a.selector}
                  </td>
                  <td className="px-4 py-3">
                    <span className="bg-gray-800 text-gray-300 px-2 py-1 rounded text-xs">
                      {a.selector_strategy}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {renderHealthScore(a.health_score || 100)}
                  </td>
                  <td className="px-4 py-3">
                    {a.enabled ? (
                      <span className="text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded text-xs">Active</span>
                    ) : (
                      <span className="text-gray-500 bg-gray-800 px-2 py-1 rounded text-xs">Disabled</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleTestSelector(a)}
                        className="px-2 py-1.5 rounded bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 text-xs flex items-center font-medium transition-colors"
                        title="Dry Run DOM Test"
                      >
                        <Target size={14} className="mr-1" /> Test
                      </button>
                      <button
                        onClick={() => handleEdit(a)}
                        className="p-1.5 rounded bg-gray-800 text-gray-400 hover:text-white transition-colors"
                        title="Edit rule"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(a.id)}
                        className="p-1.5 rounded bg-gray-800 text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        title="Delete rule"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Selector Test Modal */}
      {testModal.show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6">
           <div className="bg-[#1e1e1e] border border-gray-800 rounded-2xl w-full max-w-4xl shadow-2xl flex flex-col overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center bg-[#252526]">
                 <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                   <Target className="text-purple-400" />
                   Live DOM Selector Test
                 </h2>
                 <button onClick={() => setTestModal({ show: false, loading: false })} className="text-gray-400 hover:text-white">
                   <X size={20} />
                 </button>
              </div>
              <div className="p-6 flex-1 flex flex-col items-center justify-center min-h-[400px] bg-black/40">
                 {testModal.loading ? (
                    <div className="flex flex-col items-center">
                       <Loader2 size={40} className="animate-spin text-purple-500 mb-4" />
                       <p className="text-gray-400">Executing headless browser targeting...</p>
                       <p className="text-xs text-gray-500 mt-2 font-mono">{testModal.selectorTested}</p>
                    </div>
                 ) : testModal.error ? (
                    <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 max-w-lg text-center">
                       <h3 className="text-red-400 font-semibold mb-2">Selector Engine Miss</h3>
                       <p className="text-gray-400 text-sm">{testModal.error}</p>
                    </div>
                 ) : testModal.screenshotUrl ? (
                    <div className="relative w-full h-full flex flex-col">
                       <p className="text-emerald-400 text-sm font-semibold mb-3 flex items-center justify-center gap-2">
                         <Check size={16} /> Selector Hit Registered
                       </p>
                       <div className="border border-gray-700 rounded-lg overflow-hidden bg-black shadow-inner flex-1 relative">
                          <img
                            src={testModal.screenshotUrl}
                            alt="DOM Preview"
                            className="w-full h-full object-contain"
                          />
                          {/* The backend actually draws the red box in the screenshot base64, so we just display it */}
                       </div>
                    </div>
                 ) : null}
              </div>
           </div>
        </div>
      )}
    </div>
  );
}
