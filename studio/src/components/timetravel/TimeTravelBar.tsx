import React from 'react';
import { History, ChevronLeft, ChevronRight } from 'lucide-react';
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
    <div className="bg-[#0b101b] border border-white/10 rounded-xl px-3 py-1.5 flex items-center justify-between gap-3 text-xs font-mono shadow-sm select-none">
      {/* Left: Time Travel Label & Controls */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 text-cyan-400 font-semibold">
          <History className="w-3.5 h-3.5" />
          <span className="font-sans text-slate-200">History:</span>
        </div>

        <div className="flex items-center gap-0.5 bg-black/40 p-0.5 rounded-lg border border-white/5">
          <button
            type="button"
            onClick={handlePrev}
            disabled={currentVersionIndex === 0}
            className="p-1 text-slate-400 hover:text-white disabled:opacity-30 rounded hover:bg-white/5 transition-colors"
            title="Rewind to previous snapshot"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleNext}
            disabled={currentVersionIndex === snapshots.length - 1}
            className="p-1 text-slate-400 hover:text-white disabled:opacity-30 rounded hover:bg-white/5 transition-colors"
            title="Fast-forward to next snapshot"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <span className="text-cyan-300 font-bold px-2 py-0.5 rounded-md bg-cyan-950/70 border border-cyan-800/60 text-[11px]">
          {currentSnap.version}
        </span>
      </div>

      {/* Middle: Snapshot Description */}
      <div className="hidden md:flex items-center gap-2 truncate text-slate-400">
        <span className="truncate text-[11px] text-slate-300">{currentSnap.title}</span>
      </div>

      {/* Right: Interactive Version Nodes */}
      <div className="flex items-center gap-1">
        {snapshots.map((snap, idx) => {
          const isActive = idx === currentVersionIndex;
          return (
            <button
              key={snap.version}
              type="button"
              onClick={() => onSelectSnapshot(idx)}
              className={`px-2 py-0.5 rounded-md text-[11px] font-semibold transition-all ${
                isActive
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-sm shadow-cyan-500/20'
                  : 'text-slate-400 hover:text-white hover:bg-white/5 border border-transparent'
              }`}
            >
              {snap.version}
            </button>
          );
        })}
      </div>
    </div>
  );
};
