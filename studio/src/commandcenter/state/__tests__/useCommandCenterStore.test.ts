import { describe, it, expect, beforeEach } from 'vitest';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('useCommandCenterStore', () => {
  beforeEach(() => {
    useCommandCenterStore.setState({
      activeModule: 'deck',
      isPaletteOpen: false,
      wsStatus: 'closed',
      lastSyncAt: null,
      theme: 'dark',
      drawerOpen: false,
    });
  });

  it('initializes with default values', () => {
    const state = useCommandCenterStore.getState();
    expect(state.activeModule).toBe('deck');
    expect(state.isPaletteOpen).toBe(false);
    expect(state.wsStatus).toBe('closed');
    expect(state.theme).toBe('dark');
  });

  it('updates active module correctly', () => {
    useCommandCenterStore.getState().setActiveModule('metrics');
    expect(useCommandCenterStore.getState().activeModule).toBe('metrics');

    useCommandCenterStore.getState().setActiveModule('threats');
    expect(useCommandCenterStore.getState().activeModule).toBe('threats');
  });

  it('toggles command palette state', () => {
    useCommandCenterStore.getState().setPaletteOpen(true);
    expect(useCommandCenterStore.getState().isPaletteOpen).toBe(true);

    useCommandCenterStore.getState().setPaletteOpen(false);
    expect(useCommandCenterStore.getState().isPaletteOpen).toBe(false);
  });

  it('updates WebSocket status and sync timestamp', () => {
    const now = Date.now();
    useCommandCenterStore.getState().setWsStatus('open');
    useCommandCenterStore.getState().setLastSyncAt(now);

    const state = useCommandCenterStore.getState();
    expect(state.wsStatus).toBe('open');
    expect(state.lastSyncAt).toBe(now);
  });

  it('switches themes smoothly', () => {
    useCommandCenterStore.getState().setTheme('matrix');
    expect(useCommandCenterStore.getState().theme).toBe('matrix');

    useCommandCenterStore.getState().setTheme('sunset');
    expect(useCommandCenterStore.getState().theme).toBe('sunset');
  });

  it('controls detail drawer open/close', () => {
    useCommandCenterStore.getState().setDrawerOpen(true);
    expect(useCommandCenterStore.getState().drawerOpen).toBe(true);

    useCommandCenterStore.getState().setDrawerOpen(false);
    expect(useCommandCenterStore.getState().drawerOpen).toBe(false);
  });
});
