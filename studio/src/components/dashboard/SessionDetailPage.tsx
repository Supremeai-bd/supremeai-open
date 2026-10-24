import { useEffect } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useSessionCockpitStore } from '../../store/sessionCockpitStore';
import { FileTreePanel } from './FileTreePanel';
import { ExecutionShell } from './ExecutionShell';
import { ReasoningLog } from './ReasoningLog';
import { AgentStatePill } from './AgentStatePill';

interface SessionDetailPageProps {
  sessionId: string;
  onBack: () => void;
}

export function SessionDetailPage({ sessionId, onBack }: SessionDetailPageProps) {
  const {
    resetSessionState,
    connectSSE,
    agentState
  } = useSessionCockpitStore();

  useEffect(() => {
    // Connect SSE stream for log events
    connectSSE(sessionId);

    // Strict cleanup on unmount - zero ghost channels, prevents memory drift
    return () => {
      resetSessionState();
    };
  }, [sessionId, connectSSE, resetSessionState]);

  return (
    <div className="flex flex-col h-full bg-[#1e1e1e] overflow-hidden">
      {/* Top Navigation Bar */}
      <div className="flex items-center gap-4 px-4 py-3 bg-[#252526] border-b border-gray-800 shrink-0">
        <button
          onClick={onBack}
          aria-label="Back to sessions"
          className="text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft size={16} />
        </button>
        <h1 className="text-sm font-medium text-gray-200 truncate flex-1">
          Session Cockpit: <span className="text-gray-400 font-mono">{sessionId}</span>
        </h1>
        <AgentStatePill state={agentState} />
      </div>

      {/* 3-Pane Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: File Tree Panel (approx 20%) */}
        <div className="w-1/5 min-w-[200px] max-w-[300px] shrink-0 border-r border-gray-800">
          <FileTreePanel />
        </div>

        {/* Center: Execution Shell (approx 55%) */}
        <div className="flex-1 min-w-[400px]">
          <ExecutionShell />
        </div>

        {/* Right: Reasoning Log Panel (approx 25%) */}
        <ReasoningLog />
      </div>

      {/* Bottom Timeline Scrubber (Placeholder for future iteration) */}
      <div className="h-10 bg-[#252526] border-t border-gray-800 flex items-center px-4 shrink-0">
        <div className="w-full h-1 bg-gray-800 rounded-full overflow-hidden relative cursor-not-allowed">
           <div className="absolute top-0 left-0 h-full bg-blue-600/50 w-full" title="Replay scrubber coming in next phase"></div>
        </div>
      </div>
    </div>
  );
}
