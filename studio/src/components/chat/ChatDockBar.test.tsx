/**
 * ChatDockBar tests — RC-3 root fix (report §6.4/Table 8 P1).
 *
 * Contract under test:
 *  - in-flow docked bar (no fixed positioning in the class string — the RC-3
 *    defect class was a fixed z-40 floating dock),
 *  - 44px touch targets on every interactive element (§7.2),
 *  - Apps menu is user-published only (closed by default; opens on trigger;
 *    closes on outside click and Escape),
 *  - menu hidden entirely when no apps are passed (contextual by design).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { ChatDockBar, type DockAction } from './ChatDockBar';

const noop = () => {};

const actions: DockAction[] = [
  { id: 'preview', label: 'Preview', icon: () => null, onClick: noop },
];

const apps = [
  { id: 'tools', label: 'Dev Tools', to: '/tools', description: 'Free tools' },
  { id: 'jarvis', label: 'Jarvis HUD', to: '/jarvis', description: 'Voice cockpit' },
];

const renderDock = (props?: React.ComponentProps<typeof ChatDockBar>) =>
  render(
    <MemoryRouter>
      <ChatDockBar left={<span data-testid="orb-slot">orb</span>} {...props} />
    </MemoryRouter>,
  );

describe('ChatDockBar (RC-3, report §6.4)', () => {
  it('renders in flow — no fixed/floating positioning classes (RC-3 defect class)', () => {
    const { getByTestId } = renderDock({ actions, apps });
    const bar = getByTestId('chat-dock-bar');
    expect(bar.className).not.toMatch(/\bfixed\b/);
    expect(bar.className).not.toMatch(/\bz-40\b/);
    expect(bar.className).toContain('max-w-[46rem]');
  });

  it('renders the left slot and contextual actions', () => {
    renderDock({ actions, apps });
    expect(screen.getByTestId('orb-slot')).toBeTruthy();
    expect(screen.getByTestId('dock-action-preview')).toBeTruthy();
  });

  it('Apps menu is closed by default and opens on trigger (user-published only)', () => {
    renderDock({ actions, apps });
    expect(screen.queryByTestId('dock-apps-menu')).toBeNull();
    fireEvent.click(screen.getByTestId('dock-apps-button'));
    expect(screen.getByTestId('dock-apps-menu')).toBeTruthy();
    expect(screen.getByRole('menuitem', { name: /Dev Tools/ })).toBeTruthy();
  });

  it('closes the menu on Escape', () => {
    renderDock({ actions, apps });
    fireEvent.click(screen.getByTestId('dock-apps-button'));
    expect(screen.getByTestId('dock-apps-menu')).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('dock-apps-menu')).toBeNull();
  });

  it('closes the menu on outside click', () => {
    renderDock({ actions, apps });
    fireEvent.click(screen.getByTestId('dock-apps-button'));
    expect(screen.getByTestId('dock-apps-menu')).toBeTruthy();
    // the transparent click-catcher covers the viewport while open
    fireEvent.click(document.querySelector('.fixed.inset-0') ?? document.body);
    expect(screen.queryByTestId('dock-apps-menu')).toBeNull();
  });

  it('hides the Apps menu entirely when no apps are passed', () => {
    renderDock({ actions });
    expect(screen.queryByTestId('dock-apps-button')).toBeNull();
    expect(screen.queryByTestId('dock-apps-menu')).toBeNull();
  });

  it('keeps 44px (h-11) touch targets on interactive elements (§7.2)', () => {
    renderDock({ actions, apps });
    for (const el of [
      screen.getByTestId('dock-action-preview'),
      screen.getByTestId('dock-apps-button'),
    ]) {
      expect(el.className).toContain('h-11');
      expect(el.className).toContain('min-w-[44px]');
    }
  });
});
