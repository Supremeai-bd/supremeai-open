import React, { useMemo } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useHealthMap, useProviders } from '../../data/hooks';
import type { CommandModuleId, HealthNode, Provider } from '../../data/types';

// ─── Helpers ────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, { border: string; glow: string; bg: string }> = {
  healthy:   { border: '#00f3ff', glow: 'rgba(0,243,255,0.35)', bg: 'rgba(0,243,255,0.08)' },
  degraded:  { border: '#f59e0b', glow: 'rgba(245,158,11,0.35)', bg: 'rgba(245,158,11,0.08)' },
  down:      { border: '#ef4444', glow: 'rgba(239,68,68,0.4)',  bg: 'rgba(239,68,68,0.1)' },
  disabled:  { border: '#6b7280', glow: 'rgba(107,114,128,0.2)', bg: 'rgba(107,114,128,0.05)' },
  unknown:   { border: '#6b7280', glow: 'rgba(107,114,128,0.2)', bg: 'rgba(107,114,128,0.05)' },
};

function getStatusColor(status: string) {
  return STATUS_COLORS[status] ?? STATUS_COLORS.unknown;
}

function buildTopology(health: { gcp?: HealthNode; railway?: HealthNode; render?: HealthNode; core_services?: Record<string, HealthNode> } | undefined, providers: Provider[] | undefined) {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const addNode = (id: string, label: string, tier: 'cloud' | 'core' | 'provider', status: string, x: number, y: number) => {
    const colors = getStatusColor(status);
    nodes.push({
      id,
      type: 'default',
      position: { x, y },
      data: { label, tier, status, colors },
      style: {
        background: colors.bg,
        border: `2px solid ${colors.border}`,
        borderRadius: 12,
        padding: '8px 14px',
        color: '#e5e5e5',
        fontSize: '11px',
        fontFamily: 'monospace',
        minWidth: 120,
        boxShadow: `0 0 18px ${colors.glow}`,
        textAlign: 'center',
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
  };

  const addEdge = (source: string, target: string, animated = false) => {
    edges.push({
      id: `e-${source}-${target}`,
      source,
      target,
      type: 'smoothstep',
      animated,
      style: { stroke: '#3a3a3a', strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#3a3a3a', width: 14, height: 14 },
    });
  };

  // Tier 1 — Cloud providers
  const cloudY = 40;
  const cloudSpacing = 220;
  const cloudStartX = 60;
  if (health?.gcp)   addNode('gcp',   'GCP',      'cloud', health.gcp.status,   cloudStartX,            cloudY);
  if (health?.railway) addNode('railway', 'RAILWAY', 'cloud', health.railway.status, cloudStartX + cloudSpacing, cloudY);
  if (health?.render)  addNode('render',  'RENDER',  'cloud', health.render.status,  cloudStartX + cloudSpacing * 2, cloudY);

  // Tier 2 — Core services (generic placeholders if core_services missing)
  const coreY = 220;
  const coreServices = health?.core_services ?? {
    'api-gateway': { status: 'unknown', region: 'us', latency: 0, uptime: 0 },
    'ws-server':   { status: 'unknown', region: 'us', latency: 0, uptime: 0 },
    'postgres':    { status: 'unknown', region: 'us', latency: 0, uptime: 0 },
    'redis':       { status: 'unknown', region: 'us', latency: 0, uptime: 0 },
    'firestore':   { status: 'unknown', region: 'us', latency: 0, uptime: 0 },
  };

  const coreEntries = Object.entries(coreServices);
  const coreTotalWidth = coreEntries.length * 160;
  const coreStartX = Math.max(60, (600 - coreTotalWidth) / 2);

  coreEntries.forEach(([name, node], idx) => {
    const x = coreStartX + idx * 160;
    addNode(`core-${name}`, name.toUpperCase(), 'core', node.status, x, coreY);
    // Connect cloud → core
    ['gcp', 'railway', 'render'].forEach(cloud => {
      if (nodes.some(n => n.id === cloud)) {
        addEdge(cloud, `core-${name}`);
      }
    });
  });

  // Tier 3 — AI Providers
  const providerY = 420;
  const providerEntries = providers ?? [];
  const providerTotalWidth = Math.max(providerEntries.length * 150, 600);
  const providerStartX = Math.max(60, (600 - providerTotalWidth) / 2);

  providerEntries.forEach((provider, idx) => {
    const x = providerStartX + idx * 150;
    addNode(`provider-${provider.id}`, provider.name.toUpperCase(), 'provider', provider.status, x, providerY);
    // Connect each core to each provider
    coreEntries.forEach(([coreName]) => {
      addEdge(`core-${coreName}`, `provider-${provider.id}`);
    });
  });

  return { nodes, edges };
}

// ─── Component ──────────────────────────────────────────────────────────────

export function InfraTopology({
  health,
  providers,
  onNavigate,
}: {
  health: ReturnType<typeof useHealthMap>['data'];
  providers: ReturnType<typeof useProviders>['data'];
  onNavigate: (module: CommandModuleId) => void;
}) {
  const initial = useMemo(() => buildTopology(health, providers), [health, providers]);
  const [nodes, , onNodesChange] = useNodesState(initial.nodes);
  const [edges, , onEdgesChange] = useEdgesState(initial.edges);

  const handleNodeClick = (_: React.MouseEvent, node: Node) => {
    const tier = node.data?.tier;
    if (tier === 'cloud' || tier === 'core') {
      onNavigate('health');
    } else if (tier === 'provider') {
      onNavigate('providers');
    }
  };

  if (!health && !providers) {
    return (
      <div className="text-[10px] font-mono text-[var(--sa-text-2)] text-center py-8">
        লোড করা হচ্ছে — অপেক্ষা করুন...
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: 520 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2a2a2a" gap={20} size={1} />
        <Controls className="!bg-[var(--sa-bg-1)] !border !border-[var(--sa-line)]" />
        <MiniMap
          nodeColor={(n) => (n.data as { colors?: { border?: string } } | undefined)?.colors?.border ?? '#6b7280'}
          maskColor="rgba(0,0,0,0.6)"
          className="!bg-[var(--sa-bg-0)] !border !border-[var(--sa-line)]"
        />
      </ReactFlow>
    </div>
  );
}
