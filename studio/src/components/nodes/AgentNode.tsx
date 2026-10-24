import { Handle, Position, type Node } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { Bot, Activity } from 'lucide-react';
import { motion } from 'framer-motion';

/** Shape of the data payload attached to every agent node in the SwarmMap (#1597). */
export interface AgentNodeData {
  label: string;
  health?: {
    status?: string;
    latency?: number;
  };
  [key: string]: unknown;
}

export type AgentFlowNode = Node<AgentNodeData, 'agent'>;

export const AgentNode = ({ data }: NodeProps<AgentFlowNode>) => {
  // হেলথ স্ট্যাটাস এক্সট্র্যাক্ট করা
  const isAlive = data.health?.status === 'active';
  const latency = data.health?.latency || 0;

  // ডাইনামিক স্টাইলিং
  const borderColor = isAlive ? 'border-green-500' : 'border-red-500/50';
  const shadowColor = isAlive ? 'shadow-[0_0_15px_rgba(34,197,94,0.3)]' : 'shadow-none';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className={`p-4 rounded-lg bg-slate-900 border-2 ${borderColor} ${shadowColor} min-w-[160px] transition-colors duration-500`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-cyan-400">
          <Bot size={20} />
          <span className="font-bold">{data.label}</span>
        </div>

        {/* 🟢 Pulsing Status Dot */}
        <div className="relative flex h-3 w-3">
          {isAlive && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          )}
          <span className={`relative inline-flex rounded-full h-3 w-3 ${isAlive ? 'bg-green-500' : 'bg-red-500'}`}></span>
        </div>
      </div>

      {/* ⚡ Latency / Status Text */}
      <div className={`flex items-center gap-2 mt-3 text-xs font-medium ${isAlive ? 'text-green-400' : 'text-slate-500'}`}>
        <Activity size={14} />
        <span>{isAlive ? `${latency}ms` : 'Offline / Dead'}</span>
      </div>

      <Handle type="target" position={Position.Top} />
      <Handle type="source" position={Position.Bottom} />
    </motion.div>
  );
};
