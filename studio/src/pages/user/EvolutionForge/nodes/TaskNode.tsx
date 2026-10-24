import React, { memo } from 'react';
import { Handle, Position, type Node, type NodeProps, useReactFlow } from '@xyflow/react';

export type TaskNodeData = {
  label: string;
  prompt: string;
};

export type TaskFlowNode = Node<TaskNodeData, 'taskNode'>;

const TaskNode = ({ id, data, selected }: NodeProps<TaskFlowNode>) => {
  const { updateNodeData } = useReactFlow();

  const handlePromptChange = (evt: React.ChangeEvent<HTMLTextAreaElement>) => {
    // Update the React Flow internal state so it saves correctly later
    updateNodeData(id, { prompt: evt.target.value });
  };

  return (
    <div className={`
      relative min-w-[280px] p-5 rounded-xl border-2 border-dashed backdrop-blur-md transition-all duration-fast
      ${selected
        ? 'border-brand-primary shadow-[0_0_20px_var(--color-brand-primary)] bg-card-bg/90'
        : 'border-text-muted bg-card-bg/40 hover:border-text-secondary'}
    `}>
      {/* Task Node Header */}
      <div className="flex items-center gap-2 mb-3 border-b border-border-subtle pb-2">
        <div className="w-2 h-2 rounded-full bg-brand-primary animate-pulse" />
        <span className="font-brand font-bold text-text-primary text-sm uppercase tracking-wider">
          {data.label || 'Input Trigger'}
        </span>
      </div>

      {/* Input Field for User Prompt */}
      <div className="flex flex-col gap-2">
        <label className="text-xs text-text-muted">Task Description</label>
        <textarea
          // 🔥 'nodrag' and 'nowheel' are critical for React Flow inputs
          className="nodrag nowheel w-full bg-background/60 border border-border-subtle rounded-md p-3 text-sm text-text-primary focus:border-brand-primary focus:ring-1 focus:ring-brand-primary outline-none resize-y min-h-[80px]"
          placeholder="e.g., Analyze this codebase and generate a Python script..."
          value={data.prompt || ''}
          onChange={handlePromptChange}
        />
      </div>

      {/* Outgoing Handle ONLY (No incoming handle for the starting node) */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-4 h-4 bg-brand-primary border-2 border-background"
      />
    </div>
  );
};

export default memo(TaskNode);
