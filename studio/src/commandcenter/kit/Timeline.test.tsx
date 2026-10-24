import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Timeline } from './Timeline';
import type { DashboardEvent } from '../data/types';

describe('Timeline', () => {
  const events: DashboardEvent[] = [
    { timestamp: '2026-08-28T10:00:00Z', level: 'info', message: 'Started', source: 'core' },
    { timestamp: '2026-08-28T10:01:00Z', level: 'critical', message: 'Failure', source: 'api' },
  ];

  it('renders event messages and sources', () => {
    render(<Timeline events={events} />);
    expect(screen.getByText('Started')).toBeInTheDocument();
    expect(screen.getByText('Failure')).toBeInTheDocument();
    expect(screen.getByText('core')).toBeInTheDocument();
    expect(screen.getByText('api')).toBeInTheDocument();
  });

  it('renders loading skeleton', () => {
    const { container } = render(<Timeline events={events} loading />);
    expect(container.querySelectorAll('.animate-pulse').length).toBe(4);
  });

  it('renders empty message for no events', () => {
    render(<Timeline events={[]} />);
    expect(screen.getByText(/NO EVENTS/i)).toBeInTheDocument();
  });

  it('handles null events', () => {
    render(<Timeline events={null as unknown as DashboardEvent[]} />);
    expect(screen.getByText(/NO EVENTS/i)).toBeInTheDocument();
  });

  it('respects the limit prop', () => {
    const many = Array.from({ length: 10 }, (_, i) => ({
      timestamp: '2026-08-28T10:00:00Z',
      level: 'info' as const,
      message: `Event ${i}`,
      source: 'core',
    }));
    render(<Timeline events={many} limit={3} />);
    expect(screen.getByText('Event 0')).toBeInTheDocument();
    expect(screen.queryByText('Event 9')).not.toBeInTheDocument();
  });

  it('applies critical severity color', () => {
    const { container } = render(<Timeline events={events} />);
    expect(container.querySelector('.bg-\\[\\#ef4444\\]')).toBeTruthy();
  });
});
