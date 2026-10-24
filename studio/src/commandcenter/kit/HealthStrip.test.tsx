import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HealthStrip } from './HealthStrip';
import type { HealthNode } from '../data/types';

describe('HealthStrip', () => {
  const nodes: Record<string, HealthNode> = {
    gcp: { region: 'us', status: 'healthy', latency: 20 },
    railway: { region: 'eu', status: 'degraded' },
    render: { region: 'us', status: 'down' },
  };

  it('renders a node per entry with name and latency', () => {
    render(<HealthStrip nodes={nodes} />);
    expect(screen.getByText('gcp')).toBeInTheDocument();
    expect(screen.getByText('railway')).toBeInTheDocument();
    expect(screen.getByText('render')).toBeInTheDocument();
    expect(screen.getByText('20ms')).toBeInTheDocument();
  });

  it('renders loading placeholder', () => {
    const { container } = render(<HealthStrip nodes={nodes} loading />);
    expect(container.querySelectorAll('.animate-pulse').length).toBe(3);
  });

  it('renders empty message when no nodes', () => {
    render(<HealthStrip nodes={{}} />);
    expect(screen.getByText(/NO HEALTH DATA/i)).toBeInTheDocument();
  });

  it('handles null nodes gracefully', () => {
    render(<HealthStrip nodes={null as unknown as Record<string, HealthNode>} />);
    expect(screen.getByText(/NO HEALTH DATA/i)).toBeInTheDocument();
  });

  it('applies down status color', () => {
    const { container } = render(<HealthStrip nodes={nodes} />);
    expect(container.querySelector('.bg-\\[\\#ef4444\\]')).toBeTruthy();
  });
});
