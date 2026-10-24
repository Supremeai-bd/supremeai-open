/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import { Activity, CheckCircle, XCircle, Clock } from 'lucide-react';

interface HealthReportWidgetProps {
  healthMap: Record<string, any>;
  isLoading?: boolean;
}

export const HealthReportWidget: React.FC<HealthReportWidgetProps> = ({ healthMap, isLoading }) => {
  return (
    <div className="bg-slate-950/60 border border-slate-900 rounded-xl p-5 flex flex-col justify-between min-h-[300px] shadow-[0_0_15px_rgba(0,0,0,0.3)]">
      <div className="flex justify-between items-center mb-3">
        <span className="text-[10px] text-[#00f3ff] uppercase font-bold tracking-wider flex items-center gap-2">
          <Activity size={14} /> System Health
        </span>
        <span className="text-[9px] text-emerald-400">REAL-TIME</span>
      </div>

      <div className="flex-grow space-y-3 overflow-y-auto max-h-[220px] pr-2">
        {isLoading ? (
          <div className="space-y-3 mt-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-12 w-full animate-pulse rounded bg-slate-800/50" />
            ))}
          </div>
        ) : !healthMap || Object.keys(healthMap).length === 0 ? (
          <div className="text-xs text-slate-500 text-center mt-10">No health data available.</div>
        ) : (
          Object.entries(healthMap).map(
            ([service, details]: [string, { status?: string; region?: string; latency?: number }]) => {
            const isHealthy = details.status === 'healthy';
            return (
              <div key={service} className="bg-[#040814] border border-slate-800/50 rounded-lg p-3 flex justify-between items-center transition-all hover:border-slate-700">
                <div className="flex items-center gap-3">
                  {isHealthy ? (
                    <CheckCircle className="text-emerald-500" size={16} />
                  ) : (
                    <XCircle className="text-rose-500" size={16} />
                  )}
                  <div>
                    <div className="font-bold text-slate-200 text-xs capitalize">{service}</div>
                    <div className="text-slate-500 text-[9px] mt-0.5 flex items-center gap-2">
                      <span className="uppercase">{details.region || 'Local'}</span>
                      {details.latency && (
                        <>
                          <span>•</span>
                          <span className="flex items-center gap-1"><Clock size={9} /> {details.latency}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className={`text-[10px] px-2 py-1 rounded border font-semibold ${
                  isHealthy
                    ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10'
                    : 'text-rose-400 border-rose-500/20 bg-rose-500/10'
                }`}>
                  {details.status?.toUpperCase() || 'UNKNOWN'}
                </div>
              </div>
            );
            }
          )
        )}
      </div>
    </div>
  );
};

