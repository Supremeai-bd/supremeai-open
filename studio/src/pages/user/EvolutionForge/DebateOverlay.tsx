import React from 'react';

interface DebateLog {
  agentName: string;
  message: string;
  status: 'PROPOSING' | 'JUDGING' | 'CONSENSUS' | 'RETHINKING';
}

interface DebateOverlayProps {
  isOpen: boolean;
  logs: DebateLog[];
}

export const DebateOverlay: React.FC<DebateOverlayProps> = ({ isOpen, logs }) => {
  if (!isOpen) return null;

  return (
    <div className="absolute bottom-4 left-4 w-96 max-h-[60vh] overflow-hidden bg-background/90 backdrop-blur-xl border border-border-subtle rounded-xl shadow-2xl z-50 flex flex-col animate-fade-in transition-all">
      <div className="p-4 border-b border-border-subtle font-brand font-bold text-text-primary flex justify-between items-center bg-card-bg">
        <span className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-neon-purple animate-pulse" />
          Consensus Engine (Debate)
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {logs.length === 0 && (
          <div className="text-center text-text-secondary text-sm italic">
            Initializing debate session...
          </div>
        )}
        {logs.map((log, idx) => (
          <div key={idx} className="bg-bg-void/50 p-3 rounded-lg border border-border-subtle hover:border-brand-primary/50 transition-colors">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-brand-primary">{log.agentName}</span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                log.status === 'CONSENSUS' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                log.status === 'RETHINKING' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                log.status === 'JUDGING' ? 'bg-neon-purple/20 text-neon-purple border border-neon-purple/30' :
                'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
              }`}>{log.status}</span>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">{log.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
};
