import { useQuery } from '@tanstack/react-query';
import { useCallback, useState, useEffect } from 'react';
import { applyNodeChanges, applyEdgeChanges } from '@xyflow/react';
import type { Edge, EdgeChange, Node, NodeChange } from '@xyflow/react';
import { getApiBaseUrl } from '../utils/api';
import { getAuthHeaders } from '../services/apiClient';

interface SwarmGraphDelta {
  added: { nodes: Node[]; edges: Edge[] };
  removed: { nodes: Pick<Node, 'id'>[]; edges: Pick<Edge, 'source' | 'target'>[] };
}

type AgentHealthMap = Record<string, unknown>;

export const useSwarmGraph = () => {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  const { data: delta } = useQuery<SwarmGraphDelta>({
    queryKey: ['swarm-graph'],
    queryFn: async () => {
      const res = await fetch(`${getApiBaseUrl()}/api/v1/evolution/swarm-graph`, {
        method: 'GET',
        headers: await getAuthHeaders(),
      });
      return res.json(); // ব্যাকএন্ড থেকে {added: {nodes:[], edges:[]}, removed: {nodes:[], edges:[]}}
    },
    refetchInterval: 2000, // ২ সেকেন্ড পর পর পোলিং
  });

  // 🧠 Delta Merging Logic
  useEffect(() => {
    if (!delta) return;
    const removedNodes = delta.removed?.nodes ?? [];
    const removedEdges = delta.removed?.edges ?? [];
    const addedNodes = delta.added?.nodes ?? [];
    const addedEdges = delta.added?.edges ?? [];

    setNodes((nds) => [
      ...nds.filter((n) => !removedNodes.some((rn) => rn.id === n.id)),
      ...addedNodes.filter((an) => !nds.some((n) => n.id === an.id)),
    ]);
    setEdges((eds) => [
      ...eds.filter((e) => !removedEdges.some((re) => re.source === e.source && re.target === e.target)),
      ...addedEdges.filter((ae) => !eds.some((e) => e.source === ae.source && e.target === ae.target)),
    ]);
  }, [delta]);

  // 🧬 Agent Health Polling
  const agentIds = nodes.filter((n) => n.type === 'agent').map((n) => n.id);

  const { data: healthData } = useQuery<AgentHealthMap>({
    queryKey: ['agent-health', agentIds],
    queryFn: async () => {
      if (agentIds.length === 0) return {};
      const res = await fetch(`${getApiBaseUrl()}/api/v1/health/agents`, {
        method: 'GET',
        headers: await getAuthHeaders(),
      });
      return res.json();
    },
    refetchInterval: 2000, // ২ সেকেন্ড পর পর হার্টবিট চেক
    enabled: agentIds.length > 0, // এজেন্ট থাকলেই কেবল পোলিং হবে
  });

  // Health Data নোডের সাথে মার্জ করা
  useEffect(() => {
    if (!healthData) return;
    setNodes((nds) => nds.map((node) => {
      if (node.type === 'agent' && healthData[node.id]) {
        return { ...node, data: { ...node.data, health: healthData[node.id] } };
      }
      return node;
    }));
  }, [healthData]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [],
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  return { nodes, edges, onNodesChange, onEdgesChange };
};
