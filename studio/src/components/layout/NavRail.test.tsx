import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NavRail } from './NavRail';

const renderRail = () =>
  render(
    <MemoryRouter>
      <NavRail />
    </MemoryRouter>,
  );

const expandRail = () => {
  fireEvent.click(screen.getByRole('button', { name: 'Toggle Sidebar' }));
};

describe('NavRail', () => {
  it('renders grouped navigation with group labels when expanded', () => {
    renderRail();
    expandRail();
    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('Discover')).toBeInTheDocument();
  });

  it('renders all nav item labels when expanded', () => {
    renderRail();
    expandRail();
    for (const label of ['Agent Studio', 'Cloud IDE', 'Swarm Map', 'Architect Tower', 'Skill Catalog', 'Evolution Forge']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('renders bottom system actions when expanded', () => {
    renderRail();
    expandRail();
    expect(screen.getByText('Integrations')).toBeInTheDocument();
    expect(screen.getByText('Documentation')).toBeInTheDocument();
  });

  it('keeps labels hidden in collapsed rail by default', () => {
    renderRail();
    expect(screen.queryByText('Agent Studio')).not.toBeInTheDocument();
    expect(screen.queryByText('Workspace')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Toggle Sidebar' })).toHaveAttribute('aria-expanded', 'false');
  });
});
