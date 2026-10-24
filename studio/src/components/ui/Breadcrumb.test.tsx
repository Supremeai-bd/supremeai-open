import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Breadcrumb } from './Breadcrumb';

describe('Breadcrumb', () => {
  it('renders all crumb labels', () => {
    render(<Breadcrumb items={[{ label: 'Dashboard', href: '/' }, { label: 'Overview' }]} />);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Overview')).toBeInTheDocument();
  });

  it('marks the last crumb as current page', () => {
    render(<Breadcrumb items={[{ label: 'Home' }, { label: 'Analytics' }]} />);
    expect(screen.getByText('Analytics')).toHaveAttribute('aria-current', 'page');
  });
});
