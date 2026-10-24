import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import EvolutionForge from './EvolutionForge';

// Mock dependencies
vi.mock('../../../contexts/useToast', () => ({
  useToast: () => ({ addToast: vi.fn() }),
}));

vi.mock('../../../utils/api', () => ({
  getApiBaseUrl: vi.fn(() => 'http://localhost:8080'),
}));

vi.mock('../../../services/apiClient', () => ({
  apiClient: {
    post: vi.fn().mockResolvedValue({ success: true }),
  },
}));

// Mock @xyflow/react components so Canvas renders without DOM measurement errors
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: any) => <div data-testid="react-flow-canvas">{children}</div>,
  ReactFlowProvider: ({ children }: any) => <div>{children}</div>,
  Controls: () => <div>Controls</div>,
  Background: () => <div>Background</div>,
  MiniMap: () => <div>MiniMap</div>,
  addEdge: vi.fn(),
  useNodesState: (initial: any) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: any) => [initial, vi.fn(), vi.fn()],
  useReactFlow: () => ({
    project: vi.fn(({ x, y }: any) => ({ x, y })),
  }),
}));

describe('EvolutionForge page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders the canvas and sidebar components', () => {
    render(<EvolutionForge />);
    expect(screen.getByTestId('react-flow-canvas')).toBeInTheDocument();
    expect(screen.getByText('Evolution Forge')).toBeInTheDocument();
  });
});
