import React, { useState } from 'react';
import { ChevronRight, BrainCircuit } from 'lucide-react';
import { useSessionCockpitStore } from '../../store/sessionCockpitStore';

export const ReasoningLog: React.FC = () => {
  const { reasoningChain } = useSessionCockpitStore();
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <div className="flex flex-col h-full bg-[#1e1e1e] border-l border-gray-800 w-12 items-center pt-2">
        <button
          onClick={() => setCollapsed(false)}
          className="p-2 hover:bg-gray-700 rounded text-gray-400 transition-colors"
          title="Expand Reasoning Log"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
        <div className="mt-4 writing-vertical-rl text-xs text-gray-500 tracking-widest uppercase">
          Reasoning
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#1e1e1e] border-l border-gray-800 w-80 shrink-0">
      <div className="flex items-center px-4 py-2 bg-[#252526] border-b border-gray-800 justify-between">
        <div className="flex items-center text-amber-500">
          <BrainCircuit className="w-4 h-4 mr-2" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-300">Agent Reasoning</h3>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="text-gray-400 hover:text-white"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {reasoningChain.length === 0 ? (
          <div className="text-gray-500 text-sm text-center mt-10 italic">
            Waiting for agent thought process...
          </div>
        ) : (
          reasoningChain.map((entry) => (
            <div key={entry.id} className="bg-[#2d2d2d] border border-[#3d3d3d] rounded p-3 relative shadow-sm">
              <div className="text-xs text-gray-500 mb-2 font-mono">
                {new Date(entry.ts).toLocaleTimeString()}
              </div>
              <div className="text-sm text-gray-300 leading-relaxed font-sans whitespace-pre-wrap">
                {entry.token}
              </div>
              {/* Optional timeline connector visual */}
              <div className="absolute left-[-16px] top-4 w-4 border-t border-dashed border-gray-600"></div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
