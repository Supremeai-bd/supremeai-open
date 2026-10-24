import React, { useEffect, useRef, useState } from 'react';
import { useSessionCockpitStore } from '../../store/sessionCockpitStore';
import { SandboxViewport } from './SandboxViewport';

// Simple ANSI color mapping (cyan, red, green, violet, amber)
const colorMap: Record<string, string> = {
  shell_cmd: 'text-cyan-400 font-bold',
  shell_stderr: 'text-red-400',
  file_write: 'text-emerald-400',
  file_delete: 'text-red-500',
  dom_action: 'text-purple-400',
  reasoning_token: 'text-amber-400',
  shell_stdout: 'text-gray-300',
};

const ITEM_HEIGHT = 24;

export const ExecutionShell: React.FC = React.memo(() => {
  const { logBuffer } = useSessionCockpitStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [autoScroll, setAutoScroll] = useState(true);

  // Virtualization logic
  const containerHeight = containerRef.current?.clientHeight || 600;

  const startIndex = Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - 5);
  const visibleCount = Math.ceil(containerHeight / ITEM_HEIGHT) + 10;
  const endIndex = Math.min(logBuffer.length, startIndex + visibleCount);

  const visibleItems = logBuffer.slice(startIndex, endIndex);

  // Scroll handler to detect manual scroll up
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    setScrollTop(target.scrollTop);

    // If scrolled up from bottom by more than 10px, disable auto scroll
    const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 10;
    setAutoScroll(isAtBottom);
  };

  // Auto-scroll effect
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logBuffer.length, autoScroll]);

  return (
    <div className="flex flex-col h-full bg-[#121212] font-mono text-sm relative">
      <div className="flex items-center px-4 py-2 bg-[#1e1e1e] border-b border-gray-800 shrink-0">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Execution Shell</h3>
        <div className="ml-auto flex space-x-2">
          <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse mt-1"></span>
          <span className="text-xs text-gray-500">{logBuffer.length} events</span>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Top: Viewport */}
        <div className="h-1/2 border-b border-gray-800">
          <SandboxViewport />
        </div>

        {/* Bottom: Logs */}
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-1/2 overflow-y-auto custom-scrollbar p-2 relative bg-[#121212]"
        >
          <div style={{ height: `${logBuffer.length * ITEM_HEIGHT}px`, position: 'relative' }}>
          {visibleItems.map((log, idx) => {
            const absoluteIndex = startIndex + idx;
            const colorClass = colorMap[log.log_type] || colorMap.shell_stdout;

            return (
              <div
                key={log.id}
                className={`absolute w-full px-2 flex whitespace-pre-wrap leading-6 hover:bg-white/5`}
                style={{ top: `${absoluteIndex * ITEM_HEIGHT}px`, height: `${ITEM_HEIGHT}px` }}
              >
                <span className="text-gray-600 mr-4 select-none">
                  {new Date(log.ts).toISOString().substring(11, 23)}
                </span>
                <span className={`${colorClass} flex-1 truncate`}>
                  {typeof log.payload === 'string' ? log.payload : JSON.stringify(log.payload)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      </div>

      {!autoScroll && (
        <button
          onClick={() => {
            setAutoScroll(true);
            if (containerRef.current) {
              containerRef.current.scrollTop = containerRef.current.scrollHeight;
            }
          }}
          className="absolute bottom-4 right-4 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-full shadow-lg text-xs font-bold flex items-center"
        >
          ↓ Jump to bottom
        </button>
      )}
    </div>
  );
});

ExecutionShell.displayName = 'ExecutionShell';
