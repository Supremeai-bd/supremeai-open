/* eslint-disable @typescript-eslint/no-explicit-any */
import { Card, Badge } from '../ui';
import { Play, RotateCcw, FlaskConical } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useStore } from '../../store/useStore';
import { useCIReports } from '../../hooks/useAdminApi';
import { getApiBaseUrl } from '../../utils/api';
import { adminTokenStore } from '../../services/adminTokenStore';
import { apiClient } from '../../services/apiClient';
import { CIDashboard } from './ci/CIDashboard';
import { RenderPreflightWidget } from './RenderPreflightWidget';

interface FeatureFlag {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  rollout: number;
  environment: 'staging' | 'production';
}

export function CICDVisualizer() {
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const { fetchGateStatus } = useStore();
  const { refetch: refetchCI } = useCIReports(15);

  const fetchFlags = async () => {
    try {
      const res = await apiClient.get<{ flags: FeatureFlag[] }>('/admin-api/feature-flags');
      setFlags(res.flags || []);
    } catch (e) {
      console.error("Failed to fetch feature flags", e);
    }
  };

  useEffect(() => {
    fetchGateStatus();
    fetchFlags();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFlag = async (id: string) => {
    const flag = flags.find(f => f.id === id);
    if (!flag) return;
    try {
      await apiClient.put(`/admin-api/feature-flags/${id}`, { enabled: !flag.enabled });
      await fetchFlags();
    } catch (e) {
      console.error("Failed to toggle flag", e);
    }
  };

  const updateRollout = async (id: string, rollout: number) => {
    try {
      await apiClient.put(`/admin-api/feature-flags/${id}`, { rollout });
      await fetchFlags();
    } catch (e) {
      console.error("Failed to update rollout", e);
    }
  };

  const handleDeploy = async () => {
    try {
      const API_BASE = getApiBaseUrl();
      const res = await fetch(`${API_BASE}/admin-api/deploy`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${adminTokenStore.getRawToken()}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        alert(`✅ ${data.message || 'Deployment triggered successfully!'}`);
      } else {
        alert('❌ Deployment failed (unauthorized or server error).');
      }
    } catch (e: any) {
      alert(`❌ Deployment failed: ${e.message}`);
    }
  };

  return (
    <div className="flex-grow p-6 overflow-y-auto bg-[#030611]">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-[#00f3ff]/15">
        <h2 className="text-lg font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          🚀 CI/CD & Deployment Control
        </h2>
        <div className="flex gap-2">
          <button
            onClick={() => refetchCI()}
            className="flex items-center gap-2 px-3 py-1.5 rounded border border-slate-800 text-slate-400 hover:text-white text-[10px] font-bold font-mono uppercase transition-colors"
          >
            <RotateCcw size={10} /> Refresh
          </button>
          <button
            onClick={handleDeploy}
            className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#00f3ff] text-black text-[10px] font-bold font-mono uppercase hover:bg-cyan-400 transition-colors"
          >
            <Play size={10} /> Deploy
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2 flex flex-col gap-6">
          <RenderPreflightWidget />
          <CIDashboard repoName="SaifulHaqueNiloy/supremeai" />
        </div>

        {/* Feature Flags Column */}
        <div>
          <Card title="Feature Flags" icon={<FlaskConical size={14} />}>
            <div className="flex flex-col gap-3">
              {flags.map(flag => (
                <div key={flag.id} className="p-3 rounded-lg border border-slate-800 bg-slate-900/30">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <div className="text-xs font-bold text-white font-mono">{flag.name}</div>
                      <div className="text-[10px] text-slate-400 mt-0.5">{flag.description}</div>
                    </div>
                    <button
                      onClick={() => toggleFlag(flag.id)}
                      className={`w-8 h-4 rounded-full transition-colors ${flag.enabled ? 'bg-[#00f3ff]' : 'bg-slate-700'}`}
                    >
                      <div className={`w-3 h-3 rounded-full bg-white transition-transform ${flag.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                  {flag.enabled && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] text-slate-400">Rollout</span>
                        <span className="text-[10px] text-white font-mono">{flag.rollout}%</span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1">
                        <div className="h-full rounded-full bg-[#00f3ff]" style={{ width: `${flag.rollout}%` }} />
                      </div>
                      <div className="flex gap-1 mt-2">
                        <button onClick={() => updateRollout(flag.id, Math.max(0, flag.rollout - 10))} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 hover:text-white">-10%</button>
                        <button onClick={() => updateRollout(flag.id, Math.min(100, flag.rollout + 10))} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 hover:text-white">+10%</button>
                      </div>
                    </div>
                  )}
                  <div className="mt-2">
                    <Badge variant={flag.environment === 'production' ? 'success' : 'info'}>{flag.environment}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

