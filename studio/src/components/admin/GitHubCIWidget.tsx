/* eslint-disable @typescript-eslint/no-explicit-any */
import React from 'react';
import { GitCommit, CheckCircle2, XCircle, CircleDashed } from 'lucide-react';

interface GitHubCIWidgetProps {
  reports: any[];
  isLoading?: boolean;
}

export const GitHubCIWidget: React.FC<GitHubCIWidgetProps> = ({ reports, isLoading }) => {
  return (
    <div className="bg-slate-950/60 border border-slate-900 rounded-xl p-5 flex flex-col justify-between min-h-[300px] shadow-[0_0_15px_rgba(0,0,0,0.3)]">
      <div className="flex justify-between items-center mb-3">
        <span className="text-[10px] text-[#00f3ff] uppercase font-bold tracking-wider flex items-center gap-2">
          <GitCommit size={14} /> GitHub CI Pipeline
        </span>
        <span className="text-[9px] text-slate-400">SUPREME-CORE-CI</span>
      </div>

      <div className="flex-grow space-y-2.5 overflow-y-auto max-h-[220px] pr-2">
        {isLoading ? (
          <div className="space-y-3 mt-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-14 w-full animate-pulse rounded bg-slate-800/50" />
            ))}
          </div>
        ) : !reports || reports.length === 0 ? (
          <div className="text-xs text-slate-500 text-center mt-10">No CI reports available.</div>
        ) : (
          reports.map((report, idx) => {
            const isSuccess = report.status === 'success' || report.status === 'passed';
            const isFailed = report.status === 'failure' || report.status === 'failed';

            return (
              <div key={report.id || idx} className="bg-[#040814] border border-slate-800/50 rounded-lg p-3 flex flex-col gap-2 transition-all hover:border-slate-700">
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-2">
                    {isSuccess ? <CheckCircle2 size={14} className="text-emerald-500" /> :
                     isFailed ? <XCircle size={14} className="text-rose-500" /> :
                     <CircleDashed size={14} className="text-cyan-500 animate-spin-slow" />}

                    <span className="text-xs font-semibold text-slate-200">
                      {report.workflow_name || 'supreme-core-ci.yml'}
                    </span>
                  </div>

                  <span className="text-[9px] text-slate-500">
                    {report.created_at ? new Date(report.created_at).toLocaleTimeString() : 'Just now'}
                  </span>
                </div>

                <div className="flex justify-between items-center pl-6">
                  <span className="text-[10px] text-slate-400 truncate max-w-[150px]">
                    {report.commit_message || 'Automatic pipeline run'}
                  </span>
                  <div className={`text-[9px] px-2 py-0.5 rounded ${
                    isSuccess ? 'bg-emerald-900/30 text-emerald-400' :
                    isFailed ? 'bg-rose-900/30 text-rose-400' :
                    'bg-cyan-900/30 text-cyan-400'
                  }`}>
                    {report.status?.toUpperCase() || 'RUNNING'}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

