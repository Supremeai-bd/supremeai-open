import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatCard } from './StatCard';

describe('StatCard component', () => {
  it('renders label, tabular value and sparkline properly', () => {
    render(<StatCard label="Active Swarm" value="128" delta="+12%" deltaTone="positive" />);
    expect(screen.getByText('Active Swarm')).toBeInTheDocument();
    expect(screen.getByText('128')).toBeInTheDocument();
    expect(screen.getByText('+12%')).toBeInTheDocument();
    expect(screen.getByTestId('stat-sparkline')).toBeInTheDocument();
  });

  it('renders with custom sparkline data and negative delta tone', () => {
    render(
      <StatCard
        label="Latency"
        value="42ms"
        delta="-4ms"
        deltaTone="negative"
        sparklineData={[40, 38, 42, 35, 30]}
      />
    );
    expect(screen.getByText('Latency')).toBeInTheDocument();
    expect(screen.getByText('42ms')).toBeInTheDocument();
    expect(screen.getByText('-4ms')).toBeInTheDocument();
  });
});
