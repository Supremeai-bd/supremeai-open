import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import { adminTokenStore } from "../../services/adminTokenStore";

export function ConfigEditor() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery({
    queryKey: ['admin-config'],
    queryFn: () => apiClient.get<Record<string, string>>('/admin-api/config'),
    enabled: !!adminTokenStore.getDecodedToken(),
    staleTime: 20_000,
  });

  const saveMutation = useMutation({
    mutationFn: (cfg: Record<string, string>) => apiClient.post('/admin-api/config', cfg),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-config'] });
      window.dispatchEvent(new CustomEvent('supremeai-toast', { detail: { message: 'Configuration saved.', type: 'success' } }));
    },
  });

  const config = data || {};
  const merged = { ...config, ...draft };

  if (isLoading) {
    return <div className="flex-grow bg-[#030611] p-6 text-slate-400 font-mono text-xs">Loading configuration...</div>;
  }

  return (
    <div className="flex-grow bg-[#030611] p-6 overflow-y-auto font-mono text-xs">
      <div className="flex justify-between items-center mb-4 pb-2 border-b border-slate-800">
        <h3 className="text-sm font-bold text-slate-200">⚙️ ENVIRONMENTAL CONFIGURATION</h3>
        <button
          onClick={() => saveMutation.mutate(merged)}
          disabled={saveMutation.isPending}
          className="bg-emerald-500 hover:bg-emerald-400 text-black font-bold px-3 py-1.5 rounded transition-colors uppercase disabled:opacity-50"
        >
          {saveMutation.isPending ? 'SAVING...' : 'SAVE CONFIG'}
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {Object.keys(merged).length === 0 ? (
          <div className="text-slate-400 italic">No configuration keys returned from backend.</div>
        ) : (
          Object.keys(merged).map(k => (
            <div key={k} className="flex flex-col md:flex-row md:items-center gap-2 bg-[#0c0d12] border border-slate-900 p-3 rounded-lg">
              <span className="font-bold text-slate-300 min-w-[200px] select-all">{k}</span>
              <input
                type={merged[k] === '********' ? 'password' : 'text'}
                value={merged[k]}
                onChange={e => setDraft(prev => ({ ...prev, [k]: e.target.value }))}
                className="flex-grow bg-[#06080b] border border-slate-800 rounded px-3 py-1 text-white outline-none focus:border-[#00f3ff] font-mono"
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
