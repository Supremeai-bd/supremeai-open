import { useEffect, useRef } from 'react';
import { useCostBreakdown } from '../../hooks';
import { getSupremeModelLabel } from '../../lib/modelBranding';
import { useUnifiedStore } from '../../store/unifiedStore';

interface CostAuditorProps {
  costReport: string;
}

export function CostAuditor({ costReport }: CostAuditorProps) {
  const { data: breakdown } = useCostBreakdown();
  const addAlert = useUnifiedStore(s => s.addAlert);
  const alertedRef = useRef(false);

  const spent = breakdown?.spent ?? 0.0;
  const limit = breakdown?.limit ?? 150.00;
  const percentage = breakdown?.percentage ?? 0.0;

  useEffect(() => {
    if (percentage >= 80 && !alertedRef.current) {
      addAlert({
        severity: 'warning',
        source: 'CostAuditor',
        message: `Budget warning: You have used ${percentage.toFixed(1)}% of your limit.`
      });
      alertedRef.current = true;
    }
  }, [percentage, addAlert]);

  const providerCosts = breakdown?.providerCosts ?? [];
  const recentCharges = breakdown?.recentCharges ?? [];

  return (
    <div className="flex-grow bg-[#030611] p-6 overflow-y-auto font-sans">
      <div className="flex items-center justify-between mb-6 pb-2 border-b border-slate-800">
        <h3 className="text-sm font-bold text-slate-200 tracking-wider font-mono">📊 COST & BUDGET REPORT</h3>
        <span className="text-[10px] text-slate-400 font-mono bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">
          Billing Cycle: {new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' }).format(new Date())}
        </span>
      </div>

      {/* Main Budget Card */}
      <div className="bg-gradient-to-br from-[#0c0d14] to-[#12131f] border border-slate-900 rounded-xl p-6 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Total Spent</span>
            <span className="text-3xl font-extrabold text-white mt-1 font-mono">${spent.toFixed(2)}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Budget Cap</span>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-2xl font-bold text-slate-300 font-mono">${limit.toFixed(2)}</span>
            </div>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-400 font-mono uppercase tracking-wider">Usage Percentage</span>
            <span className="text-2xl font-bold text-[#00ff66] mt-1 font-mono">{percentage.toFixed(1)}%</span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-slate-950 border border-slate-900 h-2.5 rounded-full overflow-hidden">
          <div
            className="bg-gradient-to-r from-[#00f3ff] to-[#00ff66] h-full transition-all duration-500 shadow-[0_0_10px_rgba(0,243,255,0.3)]"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      {/* Provider Quotas */}
      <h4 className="text-xs font-bold text-slate-400 mb-4 tracking-wider uppercase font-mono">Provider Quotas & Consumption</h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {Array.isArray(providerCosts) && providerCosts.map(prov => {
          const provPercent = Math.min((prov.spent / prov.quota) * 100, 100);
          return (
            <div key={prov.name} className="bg-[#090a0f] border border-slate-900/60 rounded-xl p-4 flex flex-col gap-3">
              <div className="flex justify-between items-center">
                <span className="font-bold text-xs text-white">{prov.name}</span>
                <span className="text-[10px] font-bold text-slate-400 font-mono">${prov.spent.toFixed(2)} / ${prov.quota.toFixed(0)}</span>
              </div>
              <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden">
                <div
                  className={`bg-gradient-to-r ${prov.color} h-full`}
                  style={{ width: `${provPercent}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Recent Usage Logs */}
      <h4 className="text-xs font-bold text-slate-400 mb-4 tracking-wider uppercase font-mono">Recent Query Charges</h4>
      <div className="bg-[#090a0f] border border-slate-900/60 rounded-xl overflow-hidden mb-6">
        <table className="w-full text-left font-mono text-[10px] text-slate-300">
          <thead>
            <tr className="bg-slate-900/50 border-b border-slate-800 text-slate-400">
              <th className="p-3">Timestamp</th>
              <th className="p-3">User/System</th>
              <th className="p-3">Model</th>
              <th className="p-3">Tokens</th>
              <th className="p-3 text-right">Cost</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-900">
            {Array.isArray(recentCharges) && recentCharges.map((chg, idx) => (
              <tr key={idx} className="hover:bg-slate-800/10">
                <td className="p-3 text-slate-400">{chg.time}</td>
                <td className="p-3 font-bold text-slate-200">{chg.user}</td>
                 <td className="p-3 text-cyan-400">{getSupremeModelLabel(chg.model)}</td>
                <td className="p-3">{chg.tokens.toLocaleString()}</td>
                <td className="p-3 text-right text-[#00ff66] font-bold">${chg.cost.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Raw Output Log */}
      <details className="mt-4">
        <summary className="text-[10px] text-slate-400 cursor-pointer font-mono select-none uppercase hover:text-slate-400">Show raw console output</summary>
        <pre className="bg-[#0c0d12] border border-slate-900 rounded-lg p-4 mt-2 text-slate-400 font-mono text-[10px] whitespace-pre-wrap leading-relaxed">
          {costReport || "No raw cost reports currently in buffer."}
        </pre>
      </details>
    </div>
  );
}
