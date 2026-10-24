import { Handle, Position, type Node } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { Zap } from 'lucide-react';
import { motion } from 'framer-motion';

/** Shape of the data payload attached to every skill node in the SwarmMap (#1597). */
export interface SkillNodeData {
  label: string;
  [key: string]: unknown;
}

export type SkillFlowNode = Node<SkillNodeData, 'skill'>;

export const SkillNode = ({ data }: NodeProps<SkillFlowNode>) => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className="p-3 rounded-full bg-slate-800 border border-orange-500 flex items-center gap-2 shadow-[0_0_10px_rgba(249,115,22,0.3)]"
    >
      <Zap size={16} className="text-orange-400" />
      <span className="text-sm font-medium text-white">{data.label}</span>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </motion.div>
  );
};
