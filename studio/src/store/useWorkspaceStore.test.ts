import { describe, it, expect, beforeEach } from 'vitest';

const { useWorkspaceStore } = await import('./useWorkspaceStore');

const reset = () =>
  useWorkspaceStore.setState({
    activeIntegrations: ['github', 'slack'],
    notifications: [],
    isSimulatorActive: false,
  });

describe('useWorkspaceStore', () => {
  beforeEach(() => {
    localStorage.clear();
    reset();
  });

  it('toggles integrations on and off', () => {
    useWorkspaceStore.getState().toggleIntegration('slack');
    expect(useWorkspaceStore.getState().activeIntegrations).toEqual(['github']);

    useWorkspaceStore.getState().toggleIntegration('slack');
    expect(useWorkspaceStore.getState().activeIntegrations).toEqual(['github', 'slack']);
  });

  it('adds a notification with a generated id, keeping only the latest 5', () => {
    for (let i = 0; i < 7; i++) {
      useWorkspaceStore.getState().addNotification({ type: 'info', message: `n${i}` });
    }
    const notifications = useWorkspaceStore.getState().notifications;
    expect(notifications).toHaveLength(5);
    notifications.forEach((n) => expect(n.id).toBeTruthy());
    expect(notifications[notifications.length - 1].message).toBe('n6');
  });

  it('removes a notification by id', () => {
    useWorkspaceStore.getState().addNotification({ type: 'error', message: 'e' });
    const id = useWorkspaceStore.getState().notifications[0].id;
    useWorkspaceStore.getState().removeNotification(id);
    expect(useWorkspaceStore.getState().notifications).toHaveLength(0);
  });

  it('sets the simulator state', () => {
    useWorkspaceStore.getState().setSimulatorState(true);
    expect(useWorkspaceStore.getState().isSimulatorActive).toBe(true);
  });

  it('logout clears state and the auth token', () => {
    localStorage.setItem('supreme_auth_token', 'abc');
    useWorkspaceStore.getState().logout();
    const state = useWorkspaceStore.getState();
    expect(state.activeIntegrations).toEqual([]);
    expect(state.notifications).toEqual([]);
    expect(state.isSimulatorActive).toBe(false);
    expect(localStorage.getItem('supreme_auth_token')).toBeNull();
  });
});
