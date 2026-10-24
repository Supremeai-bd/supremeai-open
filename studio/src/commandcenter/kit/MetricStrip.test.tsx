import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MetricStrip } from './MetricStrip';

describe('MetricStrip', () => {
  const items = [
    { label: 'RPS', value: 12, unit: '/s', tone: 'cyan' as const },
    { label: 'Err', value: 0, tone: 'rose' as const },
  ];

  it('renders all metric items', () => {
    render(<MetricStrip items={items} />);
    expect(screen.getByText('RPS')).toBeInTheDocument();
    expect(screen.getByText('Err')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('/s')).toBeInTheDocument();
  });

  it('renders placeholder for null value', () => {
    render(<MetricStrip items={[{ label: 'X', value: null }]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders loading skeletons', () => {
    const { container } = render(<MetricStrip items={items} loading />);
    expect(container.querySelectorAll('.animate-pulse').length).toBe(2);
    expect(screen.queryByText('12')).not.toBeInTheDocument();
  });

  it('applies tone text class', () => {
    const { container } = render(<MetricStrip items={[{ label: 'X', value: 1, tone: 'emerald' }]} />);
    expect(container.querySelector('.text-\\[\\#10b981\\]')).toBeTruthy();
  });
});
