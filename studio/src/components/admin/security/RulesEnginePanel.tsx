import { useState } from 'react';
import { X, SlidersHorizontal, Shield, Zap, DollarSign, Save } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useDashboardStore } from '../../../store/dashboardStore';
import { apiClient } from '../../../services/apiClient';

interface RulesState {
  autoRemediate: boolean;
  threatThreshold: number;
  maxCostPerHour: number;
  maxLatencyMs: number;
  errorRateThreshold: number;
}

const defaultRules: RulesState = {
  autoRemediate: true,
  threatThreshold: 5,
  maxCostPerHour: 50,
  maxLatencyMs: 500,
  errorRateThreshold: 1,
};

const RulesEnginePanel: React.FC = () => {
  const activePanel = useDashboardStore((s) => s.activePanel);
  const setActivePanel = useDashboardStore((s) => s.setActivePanel);

  const [rules, setRules] = useState<RulesState>(defaultRules);
  const [saved, setSaved] = useState(false);

  const qc = useQueryClient();
  const updateMutation = useMutation({
    mutationFn: (updated: RulesState) =>
      apiClient.post<{ message: string }>('/admin-api/rules', updated),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  // ✅ শুধুমাত্র Rules Panel সক্রিয় হলে প্রিরেন্ডার আসবে
  if (activePanel !== 'Rules') return null;

  const handleSave = () => {
    updateMutation.mutate(rules);
  };

  const updateRule = <K extends keyof RulesState>(key: K, value: RulesState[K]) => {
    setRules((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <AnimatePresence>
      {activePanel === 'Rules' && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', damping: 20, stiffness: 100 }}
          className="fixed right-0 top-0 h-full w-[28rem] sci-fi-glass-panel p-6 z-50 shadow-2xl flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[rgba(0,243,255,0.2)] pb-4 mb-4">
            <div className="flex items-center gap-2 text-[#00f3ff]">
              <SlidersHorizontal size={16} />
              <h3 className="text-sm font-mono font-bold text-white uppercase tracking-widest">
                Adaptive Rules Engine
              </h3>
            </div>
            <button
              onClick={() => setActivePanel(null)}
              className="text-[#00f3ff] hover:text-white bg-[#00f3ff]/10 hover:bg-[#00f3ff]/30 p-1.5 rounded-lg transition-colors border border-[#00f3ff]/30"
            >
              <X size={18} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto space-y-5">
            {/* Auto-Remediate Toggle */}
            <div className="sci-fi-glass rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Shield size={14} className="text-[#00ff66]" />
                  <span className="text-xs font-mono text-[#00ff66] uppercase tracking-widest">
                    Auto-Remediate
                  </span>
                </div>
                <button
                  onClick={() => updateRule('autoRemediate', !rules.autoRemediate)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    rules.autoRemediate ? 'bg-[#00ff66]/40 border-[#00ff66]' : 'bg-slate-700 border-slate-500'
                  } border`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full transition-transform ${
                      rules.autoRemediate ? 'translate-x-5 bg-[#00ff66]' : 'translate-x-0 bg-slate-400'
                    }`}
                  />
                </button>
              </div>
              <p className="text-[10px] text-slate-400 font-mono mt-2">
                {rules.autoRemediate
                  ? 'Central Orc will auto-fix detected threats'
                  : 'Auto-remediation disabled; manual intervention required'}
              </p>
            </div>

            {/* Threat Threshold */}
            <div className="sci-fi-glass rounded-lg p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Shield size={14} className="text-[#ff0055]" />
                <span className="text-xs font-mono text-[#ff0055] uppercase tracking-widest">
                  Threat Threshold
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="20"
                value={rules.threatThreshold}
                onChange={(e) => updateRule('threatThreshold', parseInt(e.target.value))}
                className="w-full accent-[#ff0055]"
              />
              <div className="text-right text-[10px] font-mono text-[#ff0055] font-bold">
                {rules.threatThreshold} findings
              </div>
            </div>

            {/* Max Cost Per Hour */}
            <div className="sci-fi-glass rounded-lg p-4 space-y-2">
              <div className="flex items-center gap-2">
                <DollarSign size={14} className="text-[#00f3ff]" />
                <span className="text-xs font-mono text-[#00f3ff] uppercase tracking-widest">
                  Max Cost Per Hour
                </span>
              </div>
              <input
                type="range"
                min="10"
                max="200"
                step="5"
                value={rules.maxCostPerHour}
                onChange={(e) => updateRule('maxCostPerHour', parseInt(e.target.value))}
                className="w-full accent-[#00f3ff]"
              />
              <div className="text-right text-[10px] font-mono text-[#00f3ff] font-bold">
                ${rules.maxCostPerHour}/hr
              </div>
            </div>

            {/* Max Latency */}
            <div className="sci-fi-glass rounded-lg p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Zap size={14} className="text-[#00ff66]" />
                <span className="text-xs font-mono text-[#00ff66] uppercase tracking-widest">
                  Max Latency (ms)
                </span>
              </div>
              <input
                type="range"
                min="100"
                max="2000"
                step="50"
                value={rules.maxLatencyMs}
                onChange={(e) => updateRule('maxLatencyMs', parseInt(e.target.value))}
                className="w-full accent-[#00ff66]"
              />
              <div className="text-right text-[10px] font-mono text-[#00ff66] font-bold">
                {rules.maxLatencyMs}ms
              </div>
            </div>

            {/* Error Rate Threshold */}
            <div className="sci-fi-glass rounded-lg p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Shield size={14} className="text-[#ffaa00]" />
                <span className="text-xs font-mono text-[#ffaa00] uppercase tracking-widest">
                  Error Rate Threshold
                </span>
              </div>
              <input
                type="range"
                min="0.1"
                max="5"
                step="0.1"
                value={rules.errorRateThreshold}
                onChange={(e) => updateRule('errorRateThreshold', parseFloat(e.target.value))}
                className="w-full accent-[#ffaa00]"
              />
              <div className="text-right text-[10px] font-mono text-[#ffaa00] font-bold">
                {rules.errorRateThreshold}%
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="mt-4 pt-4 border-t border-[rgba(0,243,255,0.2)] flex gap-3">
            <button
              onClick={() => setActivePanel(null)}
              className="flex-1 bg-slate-900/50 hover:bg-slate-800/50 text-slate-400 hover:text-white font-mono font-bold py-2.5 rounded-lg transition-colors border border-slate-700 uppercase tracking-widest text-xs"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="flex-1 bg-[#00f3ff]/20 hover:bg-[#00f3ff]/40 text-[#00f3ff] hover:text-white font-mono font-bold py-2.5 rounded-lg transition-colors border border-[#00f3ff] shadow-[0_0_15px_rgba(0,243,255,0.3)] hover:shadow-[0_0_25px_rgba(0,243,255,0.6)] uppercase tracking-widest text-xs disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saved ? (
                <span className="flex items-center justify-center gap-2">
                  <Save size={12} className="text-[#00ff66]" />
                  Saved
                </span>
              ) : updateMutation.isPending ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="animate-spin rounded-full h-3 w-3 border border-[#00f3ff] border-t-transparent" />
                  Saving...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  <Save size={12} />
                  Apply Rules
                </span>
              )}
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default RulesEnginePanel;
