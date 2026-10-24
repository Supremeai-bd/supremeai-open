import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { InfraTopology } from './InfraTopology';

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children, nodes, edges }: any) => (
    <div data-testid="mock-react-flow">
      <div data-testid="nodes-count">{nodes.length}</div>
      <div data-testid="edges-count">{edges.length}</div>
      {children}
    </div>
  ),
  Background: () => <div data-testid="mock-bg" />,
  Controls: () => <div data-testid="mock-controls" />,
  MiniMap: () => <div data-testid="mock-minimap" />,
  useNodesState: (initial: any) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: any) => [initial, vi.fn(), vi.fn()],
  MarkerType: { ArrowClosed: 'arrowclosed' },
  // RESTORE-AND-WIRE (2026-09-14): InfraTopology now uses the @xyflow v12
  // Position enum for handle positions (type-correct); the mock must expose it.
  Position: { Right: 'right', Left: 'left', Top: 'top', Bottom: 'bottom' },
}));

describe('InfraTopology component', () => {
  it('renders loading placeholder when no health and providers are supplied', () => {
    render(
      <InfraTopology
        health={undefined}
        providers={undefined}
        onNavigate={vi.fn()}
      />
    );
    expect(screen.getByText('লোড করা হচ্ছে — অপেক্ষা করুন...')).toBeInTheDocument();
  });

  it('builds topology nodes and edges with health data', () => {
    const health = {
      overall_health_percent: 95,
      gcp: { status: 'healthy', region: 'us-east1', latency: 30, uptime: 99.9 },
      railway: { status: 'healthy', region: 'us-west1', latency: 45, uptime: 99.8 },
      render: { status: 'healthy', region: 'eu-central', latency: 60, uptime: 99.5 },
      core_services: {
        database: { status: 'healthy', region: 'us', latency: 15, uptime: 100 },
        redis: { status: 'healthy', region: 'us', latency: 5, uptime: 100 },
      },
    };

    const providers = [
      { id: 'p1', name: 'OpenAI', status: 'healthy', mode: 'prod', models: ['gpt-4'] },
    ];

    render(
      <InfraTopology
        health={health as any}
        providers={providers as any}
        onNavigate={vi.fn()}
      />
    );

    expect(screen.getByTestId('mock-react-flow')).toBeInTheDocument();
    expect(Number(screen.getByTestId('nodes-count').textContent)).toBeGreaterThan(3);
    expect(Number(screen.getByTestId('edges-count').textContent)).toBeGreaterThan(0);
  });
});
