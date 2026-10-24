import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { WorkspaceViewport } from '../WorkspaceViewport';
import { useCommandCenterStore } from '../../state/useCommandCenterStore';

describe('WorkspaceViewport', () => {
  beforeEach(() => {
    useCommandCenterStore.setState({
      activeModule: 'deck',
      isPaletteOpen: false,
      wsStatus: 'open',
      theme: 'dark',
      drawerOpen: false,
    });
  });

  it('renders loading spinner in Suspense fallback or resolves module container', () => {
    const { container } = render(<WorkspaceViewport />);
    expect(container.querySelector('main')).toBeInTheDocument();
  });

  it('renders fallback EmptyState when activeModule is unknown', () => {
     
    useCommandCenterStore.setState({ activeModule: 'non_existent_module' as any });
    render(<WorkspaceViewport />);
    expect(screen.getByText('মডিউল পাওয়া যায়নি')).toBeInTheDocument();
    expect(screen.getByText('এই মডিউলটি এখনো তৈরি হয়নি।')).toBeInTheDocument();
  });
});
