import React from 'react';
import { AlertCircle, CheckCircle2, Zap } from 'lucide-react';

interface MiniDevToolsBarProps {
  errorCount: number;
  performanceScore: number;
  isMobile: boolean;
  onFixWithHumanEye: () => void;
  isFixing: boolean;
  language: 'bn' | 'en';
}

export const MiniDevToolsBar: React.FC<MiniDevToolsBarProps> = ({
  errorCount,
  performanceScore,
  isMobile,
  onFixWithHumanEye,
  isFixing,
}) => {
  return (
    <div className="h-9 bg-[#090d16] border-t border-white/10 px-4 flex items-center justify-between text-xs font-mono text-slate-400 select-none">
      {/* Left: Health and Diagnostics Badges */}
      <div className="flex items-center gap-4">
        {/* Errors indicator */}
        <div className="flex items-center gap-1.5">
          {errorCount > 0 ? (
            <AlertCircle className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          )}
          <span className={errorCount > 0 ? 'text-rose-300 font-semibold' : 'text-slate-300'}>
            Errors: {errorCount}
          </span>
        </div>

        <span className="text-slate-700" aria-hidden="true">|</span>

        {/* Lighthouse / Performance Score */}
        <div className="flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-slate-300">
            Performance: <span className="text-emerald-400 font-bold tabular-nums">{performanceScore}/100</span>
          </span>
        </div>

        <span className="text-slate-700 hidden sm:inline" aria-hidden="true">|</span>

        {/* Viewport status */}
        <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span>Viewport: {isMobile ? 'Mobile 390px' : 'Fluid Responsive'}</span>
        </div>
      </div>

      {/* Right: Automated Diagnostic Trigger */}
      <button
        type="button"
        onClick={onFixWithHumanEye}
        disabled={isFixing}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-cyan-500/30 bg-cyan-950/40 hover:bg-cyan-900/50 text-cyan-300 text-[11px] font-semibold transition-all hover:scale-105 disabled:opacity-50"
      >
        <span>{isFixing ? 'Auditing…' : 'Run Visual Audit'}</span>
      </button>
    </div>
  );
};
