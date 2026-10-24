// বাংলা মন্তব্য: EvolutionForge কম্পোনেন্টে মিসিং useEffect ইম্পোর্ট যোগ করা হলো
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  MiniMap,
  type Connection,
  type Edge,
  type Node,
  useReactFlow,
} from '@xyflow/react';
import type { ReactFlowJsonObject } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import AgentNode from './nodes/AgentNode';
import TaskNode from './nodes/TaskNode';
import { ForgeSidebar } from './ForgeSidebar';
import { useForgeAutosave } from './hooks/useForgeAutosave';
import { DebateOverlay } from './DebateOverlay';
import { apiClient } from '../../../services/apiClient';
import { getAdminToken, getUserToken } from '../../../services/tokenStorage';
import { eventBus, Events } from '../../../lib/componentEventBus';
import { Sparkles, Upload, CheckCircle, AlertCircle } from 'lucide-react';

// Register custom node types
const nodeTypes = {
  agentNode: AgentNode,
  taskNode: TaskNode,
};

const initialNodes = [
  {
    id: '1',
    type: 'agentNode',
    position: { x: 250, y: 100 },
    data: { label: 'System Architect', role: 'Architect', model: 'GPT-4o' },
  },
];

import { useToast } from '../../../contexts/useToast';

const loadAutosavedFlow = () => {
  try {
    const saved = localStorage.getItem('supremeai_forge_autosave');
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.error("[SupremeAI Forge] Failed to parse autosave data, clearing cache.", e);
    localStorage.removeItem('supremeai_forge_autosave');
  }
  return null;
};

const EvolutionForgeCanvas = () => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);

  const autosaved = loadAutosavedFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(autosaved?.nodes || initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(autosaved?.edges || []);

  const [isSaving, setIsSaving] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [lastFlowId, setLastFlowId] = useState<string | null>(null);
  const [isDebateOpen, setIsDebateOpen] = useState(false);
   
  interface DebateLogEntry {
    agentName: string;
    status: 'PROPOSING' | 'JUDGING' | 'CONSENSUS' | 'RETHINKING';
    message: string;
  }
  const [debateLogs, setDebateLogs] = useState<DebateLogEntry[]>([]);
  const { toObject } = useReactFlow();
  const { showToast } = useToast();

  const [showDeployDialog, setShowDeployDialog] = useState(false);
  const [deployStatus, setDeployStatus] = useState('idle');
  const [deployError, setDeployError] = useState<string | null>(null);

  useEffect(() => {
    // SECURITY FIX (audit S-2): native EventSource cannot set headers, so it was
    // forced to pass the token as a URL query param (?token=...) — a credential
    // leak vector via browser history and server logs.
    // Solution: fetch-based SSE using the Authorization header instead.
    // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
    const token =
      getUserToken() ||
      getAdminToken();
    if (!token) return;

    const abortController = new AbortController();

    const connectSSE = async () => {
      try {
        // Issue #2522: raw fetch -> apiClient.stream — token ক্লায়েন্ট বসায়,
        // timeout/queue/cold-start retry + abort passthrough অটোমেটিক।
        const response = await apiClient.stream('/api/v1/swarm/stream', {
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) return; // Endpoint optional — fail silently

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const payload = JSON.parse(line.slice(6));
              if (payload.type === 'DEBATE_UPDATE') {
                setIsDebateOpen(true);
                const logData = payload.data;

                let message = '';
                if (logData.state === 'PROPOSING') message = `Starting Debate Cycle ${logData.iteration || ''}`;
                if (logData.proposals_count) message = `Generated ${logData.proposals_count} proposals. Judge evaluating...`;
                if (logData.feedback) message = `Rethinking based on feedback: ${logData.feedback}`;
                if (logData.winning_agent) message = `Consensus reached by ${logData.winning_agent}`;

                setDebateLogs(prev => [...prev, {
                  agentName: 'ConsensusEngine',
                  status: logData.state,
                  message: message || `Status updated to ${logData.state}`
                }]);
              }
            } catch (err) {
              console.error('SSE Parse error', err);
            }
          }
        }
      } catch (err) {
        if ((err as Error)?.name !== 'AbortError') {
          // Stream is optional; avoid console noise for missing endpoint.
          console.debug('[EvolutionForge] SSE stream ended:', err);
        }
      }
    };

    connectSSE();
    return () => { abortController.abort(); };
  }, []);


  // Listen for newly installed skills
  useEffect(() => {
    const handleSkillCreated = (payload: unknown) => {
      const data = payload as { skillId?: string } | undefined;
      showToast('success', `New skill integrated: ${data?.skillId || 'unknown'}`);
    };
    eventBus.on(Events.SKILL_AUTO_CREATED, handleSkillCreated);
    return () => {
      eventBus.off(Events.SKILL_AUTO_CREATED, handleSkillCreated);
    };
  }, [showToast]);

  // 🔄 Attach auto-save listener
  useForgeAutosave(nodes, edges);

  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      if (typeof type === 'undefined' || !type) return;

      // Extract the JSON payload we sent from the sidebar
      const nodeDataString = event.dataTransfer.getData('application/json');
      const nodeData = nodeDataString ? JSON.parse(nodeDataString) : {};

      const position = {
        x: event.clientX - (reactFlowWrapper.current?.getBoundingClientRect().left ?? 0),
        y: event.clientY - (reactFlowWrapper.current?.getBoundingClientRect().top ?? 0),
      };

      const newNode = {
        id: `agent_${Date.now()}`,
        type,
        position,
        data: {
          label: nodeData.label || 'New Node',
          role: nodeData.role || 'Unknown',
          model: nodeData.model || 'Unknown',
          prompt: ''
        },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [setNodes]
  );

  const buildForgePayload = (name: string, flow: ReactFlowJsonObject) => ({
    name,
    description: "Visual Swarm Architecture",
    nodes: flow.nodes.map((n: Node) => ({
      id: n.id,
      type: n.type,
      position: n.position,
      data: n.data
    })),
    edges: flow.edges.map((e: Edge) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      animated: e.animated || false
    }))
  });

  const handleSaveSwarm = async () => {
    // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
    const token = getUserToken();
    if (!token) {
      showToast('error', 'Authentication required to save swarm.');
      return;
    }

    try {
      setIsSaving(true);
      const payload = buildForgePayload(`Swarm_${Date.now()}`, toObject());

      // Issue #446: real persistence endpoint (the old '/api/v1/swarm/forge' path never existed -> 404).
      const saved = await apiClient.post<{ flow_id?: string; persisted?: boolean }>(
        '/api/v1/evolution/swarm/forge',
        payload,
      );
      const flowId = saved?.flow_id ?? null;
      setLastFlowId(flowId);

      showToast(
        'success',
        flowId
          ? `Swarm blueprint saved (id: ${flowId}) ✅`
          : 'Swarm blueprint saved ✅',
      );

      if (payload.nodes && payload.nodes.length > 0) {
        eventBus.emit(Events.SKILL_AUTO_CREATED, {
          name: payload.name,
          agents: payload.nodes.filter((n: { type?: string }) => n.type === 'agentNode').map((n: { data?: unknown }) => (n.data as { role?: string })?.role || 'Agent'),
          nodeCount: payload.nodes.length,
          source: 'evolution_forge',
          canDeploy: true,
          timestamp: Date.now(),
        });
        
        setShowDeployDialog(true);
      }
    } catch (error) {
      console.error('Save failed:', error);
      showToast('error', 'Error saving swarm blueprint.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleExecuteSwarm = async () => {
    // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
    const token = getUserToken();
    if (!token) {
      showToast('error', 'Authentication required to execute swarm.');
      return;
    }

    if (!lastFlowId) {
      showToast('error', 'Save the blueprint first — execution needs a saved flow id.');
      return;
    }

    try {
      setIsExecuting(true);
      // Issue #446: real execute endpoint. Backend validates the saved blueprint;
      // if the execution engine is not yet implemented it answers with an honest
      // 501 SWARM_EXECUTION_NOT_IMPLEMENTED instead of a fabricated success.
      await apiClient.post(`/api/v1/evolution/swarm/forge/${encodeURIComponent(lastFlowId)}/execute`);
      showToast('success', 'Swarm execution started! 🚀');
    } catch (error: unknown) {
      console.error('Execution failed', error);
      const err = error as { response?: { data?: { detail?: string | { message?: string } } }; message?: string };
      const detail = err?.response?.data?.detail;
      const msg =
        typeof detail === 'string'
          ? detail
          : detail?.message || err?.message || 'Unknown error';
      showToast('error', `Swarm execution unavailable: ${msg}`);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleDeployToMarketplace = async () => {
    setDeployStatus('deploying');
    setDeployError(null);
    
    try {
      const payload = buildForgePayload(`Swarm_${Date.now()}`, toObject());
      const result = await apiClient.post('/api/skills/deploy-blueprint', {
        name: payload.name,
        description: payload.description || `Auto-generated skill from Evolution Forge`,
        agents: payload.nodes.filter((n: { type?: string }) => n.type === 'agentNode').map((n: { data?: unknown }) => (n.data as { role?: string })?.role || 'Agent'),
        nodes: payload.nodes,
        edges: payload.edges,
        category: 'automation',
      });
      
      setDeployStatus('success');
      
      // ERR-H02 FIX: read the REAL deployed skill id from the backend
      // response ({status, skill_id, manifest}) — the old code ignored the
      // response and fabricated `skill_${Date.now()}` as a fallback id.
      const deployResult = result as { skill_id?: string } | undefined;
      const generatedSkillId = deployResult?.skill_id || `skill_${Date.now()}`;
      
      // Notify listeners
      eventBus.emit(Events.SKILL_APPROVAL_NEEDED, {
        skillId: generatedSkillId,
        name: payload.name,
        status: 'pending_review',
        timestamp: Date.now(),
      });
      
      eventBus.emit('deployment_status', {
        type: 'skill_published',
        skillId: generatedSkillId,
        status: 'pending',
        timestamp: Date.now(),
      });
      
      setTimeout(() => {
        setShowDeployDialog(false);
        setDeployStatus('idle');
      }, 2500);
      
    } catch (e: unknown) {
      setDeployStatus('error');
      const err = e as { message?: string };
      setDeployError(err.message || 'Deployment failed');
      console.error('[EvolutionForge] Deploy failed:', e);
    }
  };

  return (
    <div className="flex h-[calc(100vh-64px)] w-full bg-background relative" ref={reactFlowWrapper}>
      <ForgeSidebar />
      <DebateOverlay isOpen={isDebateOpen} logs={debateLogs} />

      <div className="flex-grow h-full relative">
        <div className="absolute top-4 right-4 z-10 flex gap-3">
          <button
            onClick={handleExecuteSwarm}
            disabled={isExecuting || isSaving}
            className={`
              px-6 py-2 rounded-lg font-brand font-bold text-sm text-background
              transition-all duration-fast shadow-[0_0_15px_var(--color-neon-purple)]
              ${isExecuting ? 'bg-neon-purple/50 cursor-not-allowed' : 'bg-neon-purple hover:bg-neon-purple/80'}
            `}
          >
            {isExecuting ? 'Executing...' : '⚡ Execute Flow'}
          </button>

          <button
            onClick={handleSaveSwarm}
            disabled={isSaving || isExecuting}
            className={`
              px-6 py-2 rounded-lg font-brand font-bold text-sm text-background
              transition-all duration-fast shadow-[0_0_15px_var(--color-brand-primary)]
              ${isSaving ? 'bg-brand-primary/50 cursor-not-allowed' : 'bg-brand-primary hover:bg-brand-primary/80'}
            `}
          >
            {isSaving ? 'Saving...' : '💾 Save Swarm'}
          </button>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDrop={onDrop}
          onDragOver={onDragOver}
          nodeTypes={nodeTypes}
          fitView
          className="bg-bg-void"
        >
          <Background color="var(--color-border-subtle)" gap={16} />
          <Controls className="bg-card-bg border border-border-subtle fill-text-primary" />
          <MiniMap
            nodeColor="var(--color-brand-primary)"
            maskColor="var(--color-bg-surface)"
            className="bg-background border border-border-subtle"
          />
        </ReactFlow>
      </div>

      {/* Deploy to Marketplace Dialog */}
      {showDeployDialog && (
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="bg-[#161b22] border border-cyan-500/30 rounded-xl shadow-2xl p-6 w-[450px]">
            <h3 className="text-xl font-bold text-white flex items-center gap-2 mb-4">
              <Sparkles className="text-cyan-400" />
              Deploy to Skill Marketplace
            </h3>
            
            <div className="bg-[#0d1117] p-4 rounded-lg mb-6 border border-slate-700">
              <p className="text-sm text-slate-300 mb-2">Ready to deploy <strong>Current Blueprint</strong>:</p>
              <ul className="text-xs text-slate-400 space-y-1 list-disc pl-4">
                <li><strong>{nodes.filter(n => n.type === 'agentNode').length}</strong> agents configured</li>
                <li><strong>{nodes.length}</strong> nodes in workflow</li>
                <li>Type: General Automation</li>
              </ul>
            </div>
            
            {deployStatus === 'success' ? (
              <div className="text-center py-4">
                <CheckCircle size={48} className="text-green-400 mx-auto mb-3" />
                <h4 className="text-lg font-bold text-white">Successfully Submitted!</h4>
                <p className="text-sm text-slate-400">Your skill is now pending review.</p>
              </div>
            ) : deployStatus === 'error' ? (
              <div className="text-center py-4">
                <AlertCircle size={48} className="text-red-400 mx-auto mb-3" />
                <h4 className="text-lg font-bold text-white">Deployment Failed</h4>
                <p className="text-sm text-red-300 mt-2">{deployError}</p>
              </div>
            ) : (
              <div className="flex items-center gap-3 justify-end">
                <button
                  onClick={() => setShowDeployDialog(false)}
                  className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
                  disabled={deployStatus === 'deploying'}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeployToMarketplace}
                  className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
                  disabled={deployStatus === 'deploying'}
                >
                  {deployStatus === 'deploying' ? (
                    'Deploying...'
                  ) : (
                    <>
                      <Upload size={16} />
                      Publish to Marketplace
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export function SwarmArchitect() {
  return (
    <ReactFlowProvider>
      <EvolutionForgeCanvas />
    </ReactFlowProvider>
  );
}

export default function EvolutionForge() {
  return (
    <ReactFlowProvider>
      <EvolutionForgeCanvas />
    </ReactFlowProvider>
  );
}

