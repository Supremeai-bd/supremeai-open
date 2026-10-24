import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Activity } from 'lucide-react';
import { KpiTile } from './KpiTile';

describe('KpiTile', () => {
  it('renders label and value', () => {
    render(<KpiTile label="Swarm" value={128} />);
    expect(screen.getByText('Swarm')).toBeInTheDocument();
    expect(screen.getByText('128')).toBeInTheDocument();
  });

  it('renders unit when provided', () => {
    render(<KpiTile label="Latency" value={42} unit="ms" />);
    expect(screen.getByText('ms')).toBeInTheDocument();
  });

  it('renders placeholder for null value', () => {
    render(<KpiTile label="Latency" value={null} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders loading skeleton when loading', () => {
    render(<KpiTile label="Swarm" value={128} loading />);
    expect(screen.getByText('Swarm')).toBeInTheDocument();
    expect(screen.queryByText('128')).not.toBeInTheDocument();
  });

  it('renders hint', () => {
    render(<KpiTile label="Swarm" value={128} hint="live" />);
    expect(screen.getByText('live')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(<KpiTile label="Swarm" value={128} icon={Activity} />);
    expect(document.querySelector('svg')).toBeTruthy();
  });

  it('is a button that fires onClick and is disabled without handler', () => {
    const onClick = vi.fn();
    const { rerender } = render(<KpiTile label="Swarm" value={128} onClick={onClick} />);
    const btn = screen.getByRole('button');
    btn.click();
    expect(onClick).toHaveBeenCalledTimes(1);
    rerender(<KpiTile label="Swarm" value={128} />);
    expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
  });

  it('applies tone class', () => {
    const { container } = render(<KpiTile label="Swarm" value={128} tone="emerald" />);
    expect(container.querySelector('.text-\\[\\#10b981\\]')).toBeTruthy();
  });
});
