import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
// বাংলা মন্তব্য: বাহিরের মডেল নামের বদলে SupremeAI ব্র্যান্ডেড নাম দেখানোর ইউটিলিটি
import { getSupremeModelLabel } from '../../../../lib/modelBranding';

// Custom data type for our Agent Node
export type AgentNodeData = {
  label: string;
  role: 'Architect' | 'Coder' | 'Reviewer' | 'Deployer';
  model: string;
};

export type AgentFlowNode = Node<AgentNodeData, 'agentNode'>;

const AgentNode = ({ data, selected }: NodeProps<AgentFlowNode>) => {
  return (
    <div className={`
      relative min-w-[200px] p-4 rounded-xl border-2 backdrop-blur-md transition-all duration-fast
      ${selected
        ? 'border-neon-blue shadow-[0_0_20px_var(--color-neon-blue)] bg-card-bg/90'
        : 'border-border-subtle bg-card-bg/50 hover:border-text-secondary'}
    `}>
      {/* Incoming Data/Task Handle */}
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-neon-purple border-2 border-background"
      />

      {/* Node Content */}
      <div className="flex flex-col gap-2">
        <div className="flex justify-between items-center">
          <span className="font-brand font-bold text-text-primary text-lg">
            {data.label}
          </span>
          <span className="text-xs px-2 py-1 rounded-full bg-background border border-border-accent text-brand-primary">
            {getSupremeModelLabel(data.model)}
          </span>
        </div>
        <p className="text-sm text-text-muted">{data.role}</p>
      </div>

      {/* Outgoing Result Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-neon-blue border-2 border-background"
      />
    </div>
  );
};

export default memo(AgentNode);
