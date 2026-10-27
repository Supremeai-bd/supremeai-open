import React, { useCallback, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, GripVertical } from 'lucide-react';

export interface StudioSplitCanvasProps {
  left?: React.ReactNode;
  right?: React.ReactNode;
  defaultLeftSize?: number;
  minLeftSize?: number;
  minRightSize?: number;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  className?: string;
}

export const StudioSplitCanvas: React.FC<StudioSplitCanvasProps> = ({
  left,
  right,
  defaultLeftSize = 35,
  minLeftSize = 20,
  minRightSize = 30,
  collapsed = false,
  onToggleCollapse,
  className = '',
}) => {
  const [leftSize, setLeftSize] = useState<number>(defaultLeftSize);
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      const clamped = Math.min(100 - minRightSize, Math.max(minLeftSize, pct));
      setLeftSize(clamped);
    };
    const onUp = () => {
      draggingRef.current = false;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [minLeftSize, minRightSize]);

  if (collapsed) {
    return (
      <div className={`flex h-full w-full ${className}`}>
        <button
          onClick={onToggleCollapse}
          className="w-10 flex items-center justify-center bg-[#161b22] border-r border-slate-700 text-slate-300 hover:text-white"
          aria-label="expand-left"
        >
          <ChevronRight size={16} />
        </button>
        <div className="flex-1">{right}</div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`flex flex-col md:flex-row h-full w-full overflow-hidden ${className}`}>
      <div
        style={{ width: undefined }}
        className="flex flex-col min-w-0 w-full md:w-[var(--left-w)] md:shrink-0"
        ref={(el) => {
          if (el) el.style.setProperty('--left-w', `${leftSize}%`);
        }}
      >
        <div className="flex items-center justify-between px-2 py-1 border-b border-slate-700 bg-[#161b22] shrink-0">
          <span className="text-xs text-slate-400">Jerbez Copilot</span>
          {onToggleCollapse && (
            <button onClick={onToggleCollapse} className="p-1 text-slate-400 hover:text-white" aria-label="collapse-left">
              <ChevronLeft size={14} />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-hidden min-h-[220px] md:min-h-0">{left}</div>
      </div>
      <div
        onMouseDown={onMouseDown}
        className="hidden md:flex w-1 bg-slate-700 hover:bg-cyan-500 transition-colors cursor-col-resize items-center justify-center shrink-0"
        role="separator"
        aria-orientation="vertical"
      >
        <GripVertical size={10} className="text-slate-500" />
      </div>
      <div
        style={{ width: undefined }}
        className="flex flex-col min-w-0 w-full md:flex-1"
      >
        <div className="flex-1 overflow-hidden min-h-[260px] md:min-h-0">{right}</div>
      </div>
    </div>
  );
};

export default StudioSplitCanvas;