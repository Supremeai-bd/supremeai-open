import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders eyebrow, title, and subtitle', () => {
    render(
      <PageHeader eyebrow="Admin Dashboard" title="Welcome back, Alex" subtitle="All systems operational" />,
    );
    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Welcome back, Alex' })).toBeInTheDocument();
    expect(screen.getByText('All systems operational')).toBeInTheDocument();
  });

  it('renders breadcrumb items when provided', () => {
    render(
      <PageHeader
        title="User Management"
        crumbItems={[{ label: 'Dashboard', href: '/workspace' }, { label: 'Accounts' }]}
      />,
    );
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Accounts')).toBeInTheDocument();
  });
});
