import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LiveTelemetryChart } from './LiveTelemetryChart';

describe('LiveTelemetryChart', () => {
  it('renders telemetry title, metrics labels and container', () => {
    render(<LiveTelemetryChart />);
    expect(screen.getByText(/Swarm Throughput & Engine Latency/i)).toBeInTheDocument();
    expect(screen.getByText(/Throughput \(Req\/s\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Latency \(ms\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('live-telemetry-chart')).toBeInTheDocument();
  });
});
