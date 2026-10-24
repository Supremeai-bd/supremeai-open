import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QuickActionsPanel } from './QuickActionsPanel';

describe('QuickActionsPanel', () => {
  it('renders all 4 quick action items properly', () => {
    render(
      <MemoryRouter>
        <QuickActionsPanel />
      </MemoryRouter>
    );

    expect(screen.getByText('Trigger Self-Healer')).toBeInTheDocument();
    expect(screen.getByText('Evolve New Skill')).toBeInTheDocument();
    expect(screen.getByText('Browser Live Preview')).toBeInTheDocument();
    expect(screen.getByText('Deep Codebase Audit')).toBeInTheDocument();
  });

  it('triggers custom event on Self-Healer click', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    render(
      <MemoryRouter>
        <QuickActionsPanel />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText('Trigger Self-Healer'));
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'supremeai-notification' })
    );
    dispatchSpy.mockRestore();
  });
});
