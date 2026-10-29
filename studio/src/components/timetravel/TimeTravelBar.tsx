import React from 'react';
import { History, ChevronLeft, ChevronRight, RotateCcw, Check, Clock } from 'lucide-react';
import type { VersionSnapshot } from '../../types/worldclass';

interface TimeTravelBarProps {
  snapshots: VersionSnapshot[];
  currentVersionIndex: number;
  onSelectSnapshot: (index: number) => void;
  language: 'bn' | 'en';
}

export const TimeTravelBar: React.FC<TimeTravelBarProps> = ({
  snapshots,
  currentVersionIndex,
  onSelectSnapshot,
  language,
}) => {
  const currentSnap = snapshots[currentVersionIndex] || snapshots[snapshots.length - 1];

  const handlePrev = () => {
    if (currentVersionIndex > 0) {
      onSelectSnapshot(currentVersionIndex - 1);
    }
  };

  const handleNext = () => {
    if (currentVersionIndex < snapshots.length - 1) {
      onSelectSnapshot(currentVersionIndex + 1);
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-2 px-3 flex items-center justify-between gap-4 text-xs font-mono shadow-lg select-none">
      {/* Left: Time Travel Label & Controls */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 text-indigo-400 font-bold">
          <History className="w-3.5 h-3.5" />
          <span className="hidden sm:inline font-sans text-white">Time-Travel:</span>
        </div>

        <div className="flex items-center gap-1 bg-slate-950 p-0.5 rounded border border-slate-800">
          <button
            onClick={handlePrev}
            disabled={currentVersionIndex === 0}
            className="p-1 hover:text-white disabled:opacity-30 rounded hover:bg-slate-800 transition-colors"
            title="Rewind to previous snapshot"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleNext}
            disabled={currentVersionIndex === snapshots.length - 1}
            className="p-1 hover:text-white disabled:opacity-30 rounded hover:bg-slate-800 transition-colors"
            title="Fast-forward to next snapshot"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <span className="text-emerald-400 font-bold px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/80 text-[11px]">
          {currentSnap.version}
        </span>
      </div>

      {/* Middle: Snapshot Step Indicator Dots */}
      <div className="flex items-center gap-2">
        {snapshots.map((snap, idx) => {
          const isActive = idx === currentVersionIndex;
          return (
            <button
              key={snap.id}
              onClick={() => onSelectSnapshot(idx)}
              className={`group flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] transition-all ${
                isActive
                  ? 'bg-indigo-600 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
              title={`${snap.version}: ${snap.title}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-white' : 'bg-slate-600'}`} />
              <span className="hidden md:inline">{snap.version}</span>
            </button>
          );
        })}
      </div>

      {/* Right: Snapshot Info summary */}
      <div className="hidden lg:flex items-center gap-3 text-[11px] text-slate-400">
        <span className="text-slate-300 truncate max-w-[200px]" title={currentSnap.title}>
          {currentSnap.title}
        </span>
        <span className="text-slate-500">({currentSnap.timestamp})</span>
      </div>
    </div>
  );
};
