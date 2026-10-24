import { describe, it, expect, vi } from 'vitest';
import {
  COMMAND_REGISTRY,
  getCommandsForPortal,
  getCurrentPortal,
} from './commandRegistry';

describe('commandRegistry', () => {
  it('has unique command ids', () => {
    const ids = COMMAND_REGISTRY.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('every route command uses an absolute path and every command has route or action', () => {
    for (const cmd of COMMAND_REGISTRY) {
      if (cmd.route) expect(cmd.route.startsWith('/')).toBe(true);
      expect(cmd.route || cmd.action).toBeTruthy();
    }
  });

  it('user portal excludes admin-only commands', () => {
    const userCommands = getCommandsForPortal('user');
    expect(userCommands.find((c) => c.id === 'nav-admin')).toBeUndefined();
    expect(userCommands.find((c) => c.id === 'action-gap')).toBeUndefined();
  });

  it('admin portal includes admin commands and shared workspace nav', () => {
    const adminCommands = getCommandsForPortal('admin');
    expect(adminCommands.find((c) => c.id === 'nav-admin')).toBeTruthy();
    expect(adminCommands.find((c) => c.id === 'nav-workspace')).toBeTruthy();
    expect(adminCommands.find((c) => c.id === 'action-gap')).toBeTruthy();
  });

  it('every command declares at least one portal', () => {
    for (const cmd of COMMAND_REGISTRY) {
      expect(cmd.portals.length).toBeGreaterThan(0);
    }
  });

  it('getCurrentPortal defaults to user outside /admin routes', () => {
    // বাংলা মন্তব্য (single-frontend migration): portal এখন runtime route context —
    // test env (jsdom pathname='/') হলে default 'user' হওয়া উচিত
    expect(getCurrentPortal()).toBe('user');
  });

  it('admin subtab commands dispatch shared event with correct tab id', () => {
    const spy = vi.spyOn(window, 'dispatchEvent');
    const cmd = COMMAND_REGISTRY.find((c) => c.id === 'admin-nav-costs');
    expect(cmd).toBeTruthy();
    cmd!.action!();
    const dispatched = spy.mock.calls.find(
      ([e]) => e.type === 'supremeai-admin-subtab',
    ) as unknown as [CustomEvent<string>];
    expect(dispatched).toBeTruthy();
    expect(dispatched[0].detail).toBe('costs');
    spy.mockRestore();
  });
});
