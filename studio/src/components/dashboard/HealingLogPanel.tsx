import { useState, useEffect } from 'react';
import { Activity, ShieldAlert, CheckCircle, XCircle, ArrowRight } from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { useToast } from '../../contexts/useToast';
interface HealingEvent {
  id: string;
  ts: string;
  action_id: number;
  original_selector: string;
  healed_selector: string;
  confidence_score: number;
  auto_applied: boolean;
  screenshot_before_base64?: string;
  screenshot_after_base64?: string;
}

export function HealingLogPanel() {
  const [events, setEvents] = useState<HealingEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const { showToast } = useToast();

  useEffect(() => {
    apiClient.get<{items: HealingEvent[]}>('/api/admin/selector-healing')
      .then(data => setEvents(data.items || []))
      .catch(err => {
        console.error("Failed to load healing events", err);
        showToast('error', 'Failed to load healing events');
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDecision = async (id: string, approve: boolean) => {
    try {
      await apiClient.post(`/api/admin/selector-healing/${id}/decision`, { approve });
      setEvents(events.map(e => e.id === id ? { ...e, auto_applied: approve } : e));
      showToast('success', 'Decision applied successfully');
    } catch (err) {
      console.error("Decision failed", err);
      showToast('error', 'Failed to apply decision');
    }
  };

  const CircularProgress = ({ score }: { score: number }) => {
    const radius = 16;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (score / 100) * circumference;
    const color = score > 80 ? 'text-emerald-500' : score > 50 ? 'text-amber-500' : 'text-red-500';

    return (
      <div className="relative w-10 h-10 flex items-center justify-center">
        <svg className="w-full h-full transform -rotate-90">
          <circle cx="20" cy="20" r="16" className="text-gray-800" strokeWidth="4" stroke="currentColor" fill="transparent" />
          <circle cx="20" cy="20" r="16" className={color} strokeWidth="4" strokeDasharray={circumference} strokeDashoffset={strokeDashoffset} stroke="currentColor" fill="transparent" />
        </svg>
        <span className="absolute text-[10px] font-bold text-gray-300">{score}%</span>
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Activity size={24} className="text-amber-500" />
        <div>
          <h1 className="text-2xl font-semibold text-white">Self-Healing Trail Log</h1>
          <p className="text-sm text-slate-400">Autonomous DOM re-anchoring telemetry</p>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20 text-slate-400">
          <Activity size={24} className="animate-spin" />
        </div>
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 bg-[#1e1e1e] border border-gray-800 rounded-xl border-dashed">
          <ShieldAlert size={48} className="text-gray-700 mb-4" />
          <p className="text-gray-400 font-medium">No healing events recorded</p>
          <p className="text-xs text-gray-500 mt-1">Selectors are currently robust.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {events.map((evt) => (
            <div key={evt.id} className="bg-[#1e1e1e] border border-gray-800 rounded-xl overflow-hidden shadow-lg">
              {/* Header */}
              <div className="px-5 py-3 border-b border-gray-800 bg-[#252526] flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <span className="text-xs text-gray-500 font-mono">{new Date(evt.ts).toLocaleString()}</span>
                  <span className="text-sm font-semibold text-gray-300">Action ID: {evt.action_id}</span>
                </div>
                <div className="flex items-center gap-3">
                  {!evt.auto_applied && (
                    <div className="flex gap-2">
                      <button onClick={() => handleDecision(evt.id, true)} className="flex items-center gap-1 px-3 py-1 rounded bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs font-medium transition-colors">
                        <CheckCircle size={14} /> Approve
                      </button>
                      <button onClick={() => handleDecision(evt.id, false)} className="flex items-center gap-1 px-3 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 text-xs font-medium transition-colors">
                        <XCircle size={14} /> Reject
                      </button>
                    </div>
                  )}
                  {evt.auto_applied && (
                    <span className="text-xs text-emerald-500 flex items-center gap-1 bg-emerald-500/10 px-2 py-1 rounded">
                      <CheckCircle size={12} /> Auto-Applied
                    </span>
                  )}
                </div>
              </div>

              {/* Body */}
              <div className="p-5 flex flex-col lg:flex-row gap-6">

                {/* Data Column */}
                <div className="flex-1 flex flex-col justify-center">
                  <div className="flex items-center gap-4 mb-6">
                    <CircularProgress score={evt.confidence_score} />
                    <div>
                      <h4 className="text-sm font-medium text-gray-200">Confidence Score</h4>
                      <p className="text-xs text-gray-500">LLM layout semantic matching</p>
                    </div>
                  </div>

                  <div className="bg-black/30 border border-gray-800 rounded-lg p-4">
                    <div className="mb-3">
                      <p className="text-[10px] uppercase text-gray-500 tracking-wider mb-1">Broken Selector</p>
                      <p className="text-sm font-mono text-red-400 break-all">{evt.original_selector}</p>
                    </div>
                    <div className="flex justify-center mb-3">
                      <ArrowRight size={16} className="text-gray-600" />
                    </div>
                    <div>
                      <p className="text-[10px] uppercase text-gray-500 tracking-wider mb-1">Healed Selector</p>
                      <p className="text-sm font-mono text-emerald-400 break-all">{evt.healed_selector}</p>
                    </div>
                  </div>
                </div>

                {/* Screenshots Column */}
                <div className="flex-1 flex gap-4">
                  <div className="flex-1 flex flex-col">
                    <span className="text-xs text-gray-500 mb-2 text-center">Before (Broken)</span>
                    <div className="flex-1 bg-black rounded-lg border border-gray-800 flex items-center justify-center min-h-[150px] overflow-hidden">
                      {evt.screenshot_before_base64 ? (
                        <img src={`data:image/jpeg;base64,${evt.screenshot_before_base64}`} alt="Before" className="object-contain w-full h-full opacity-70" />
                      ) : (
                        <span className="text-xs text-gray-700">No Image</span>
                      )}
                    </div>
                  </div>
                  <div className="flex-1 flex flex-col">
                    <span className="text-xs text-gray-500 mb-2 text-center">After (Healed)</span>
                    <div className="flex-1 bg-black rounded-lg border border-emerald-900 flex items-center justify-center min-h-[150px] overflow-hidden">
                      {evt.screenshot_after_base64 ? (
                        <img src={`data:image/jpeg;base64,${evt.screenshot_after_base64}`} alt="After" className="object-contain w-full h-full" />
                      ) : (
                        <span className="text-xs text-gray-700">No Image</span>
                      )}
                    </div>
                  </div>
                </div>

              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
