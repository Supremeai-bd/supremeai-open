import { ReactFlow, Background, Controls } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useSwarmGraph } from '../hooks/useSwarmGraph';
import { AgentNode } from './nodes/AgentNode';
import { SkillNode } from './nodes/SkillNode';

const nodeTypes = {
  agent: AgentNode,
  skill: SkillNode,
};

const defaultEdgeOptions = {
  animated: true,
  style: { stroke: 'var(--supremeai-color-brand-primary-light, #10b981)', strokeWidth: 2 },
};

export default function SwarmMap() {
  const { nodes, edges, onNodesChange, onEdgesChange } = useSwarmGraph();

  return (
    <div className="w-full h-[calc(100vh-60px)] flex flex-col bg-[var(--supremeai-color-bg-void-light)] dark:bg-[var(--supremeai-color-bg-void-dark)] rounded-xl overflow-hidden border border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] shadow-sm">
      <div className="p-4 border-b border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-light)] dark:bg-[var(--supremeai-color-bg-elevated-dark)]">
        <h2 className="text-xl font-bold">Swarm Map</h2>
        <p className="text-sm text-[var(--supremeai-color-neutral-500)]">Real-time visualization of autonomous agent interactions</p>
      </div>
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          fitView
          snapToGrid
          colorMode="system"
        >
          <Background color="var(--supremeai-color-neutral-500)" gap={16} />
          <Controls className="bg-[var(--supremeai-color-bg-elevated-light)] dark:bg-[var(--supremeai-color-bg-elevated-dark)] border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)]" />
        </ReactFlow>
      </div>
    </div>
  );
}
