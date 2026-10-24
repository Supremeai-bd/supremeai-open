import React from 'react';
import { type SujonState } from '../../store/sessionCockpitStore';

interface AgentStatePillProps {
  state: SujonState;
}

const stateConfig: Record<SujonState, { color: string; label: string; animation: string }> = {
  idle: { color: 'bg-gray-500', label: 'Idle', animation: '' },
  scanning: { color: 'bg-blue-500', label: 'Scanning Target', animation: 'animate-pulse' },
  executing: { color: 'bg-emerald-500', label: 'Executing Workflow', animation: 'animate-pulse' },
  circuit_open: { color: 'bg-red-700', label: 'Circuit Open', animation: '' },
  self_healing: { color: 'bg-amber-500', label: 'Self Healing', animation: 'animate-bounce' },
  awaiting_human: { color: 'bg-purple-500', label: 'Awaiting Input', animation: 'animate-ping' },
  success: { color: 'bg-emerald-400', label: 'Success', animation: '' },
  failed: { color: 'bg-red-500', label: 'Failed', animation: '' },
  // বাংলা মন্তব্য: SujonState enum এর processing স্টেটের জন্য কালার ও লেবেল ম্যাপিং যোগ করা হলো
  processing: { color: 'bg-indigo-500', label: 'Processing', animation: 'animate-pulse' },
};

export const AgentStatePill: React.FC<AgentStatePillProps> = ({ state }) => {
  const config = stateConfig[state];

  return (
    <div
      className="flex items-center space-x-2 px-3 py-1 bg-gray-800 rounded-full border border-gray-700 shadow-sm"
      aria-label={`Agent is currently ${config.label}`}
    >
      <div className="relative flex h-3 w-3">
        {config.animation === 'animate-ping' && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${config.color}`}></span>
        )}
        <span className={`relative inline-flex rounded-full h-3 w-3 ${config.color} ${config.animation !== 'animate-ping' ? config.animation : ''}`}></span>
      </div>
      <span className="text-xs font-medium text-gray-200 uppercase tracking-wider">
        {config.label}
      </span>
    </div>
  );
};
