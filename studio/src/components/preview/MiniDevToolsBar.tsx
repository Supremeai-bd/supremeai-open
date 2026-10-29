import React from 'react';
import { AlertCircle, CheckCircle2, ShieldCheck, Terminal, Eye, Zap, RefreshCw } from 'lucide-react';

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
  language,
}) => {
  return (
    <div className="h-10 bg-slate-950 border-t border-slate-800 px-4 flex items-center justify-between text-xs font-mono text-slate-400 select-none">
      {/* Left: Health and Diagnostics Badges */}
      <div className="flex items-center gap-4">
        {/* Errors indicator */}
        <div className="flex items-center gap-1.5">
          {errorCount > 0 ? (
            <AlertCircle className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          )}
          <span className={errorCount > 0 ? 'text-rose-300 font-bold' : 'text-slate-300'}>
            Errors: {errorCount}
          </span>
        </div>

        <span className="text-slate-700" aria-hidden="true">|</span>

        {/* Lighthouse / Performance Score */}
        <div className="flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-slate-300">
            Score: <span className="text-emerald-400 font-bold tabular-nums">{performanceScore}/100</span>
          </span>
        </div>

        <span className="text-slate-700 hidden sm:inline" aria-hidden="true">|</span>

        {/* Viewport status */}
        <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-400">
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
          <span>{isMobile ? 'Mobile: 390x844 (Retina)' : 'Desktop: Fluid 100%'}</span>
        </div>
      </div>

      {/* Right: Human-Eye Autonomous Auditor CTA */}
      <div className="flex items-center gap-2">
        {errorCount > 0 ? (
          <button
            onClick={onFixWithHumanEye}
            disabled={isFixing}
            className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-sans font-semibold text-white bg-rose-600 hover:bg-rose-500 rounded transition-colors"
          >
            <Eye className="w-3 h-3" />
            <span>{isFixing ? 'Fixing...' : (language === 'bn' ? 'Human-Eye দিয়ে ফিক্স করুন' : 'Fix with Human-Eye')}</span>
          </button>
        ) : (
          <button
            onClick={onFixWithHumanEye}
            disabled={isFixing}
            className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-sans text-slate-300 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded transition-colors"
          >
            {isFixing ? <RefreshCw className="w-3 h-3 animate-spin text-indigo-400" /> : <Eye className="w-3 h-3 text-indigo-400" />}
            <span>{language === 'bn' ? 'Human-Eye অডিট' : 'Audit UI (Human-Eye)'}</span>
          </button>
        )}
      </div>
    </div>
  );
};
