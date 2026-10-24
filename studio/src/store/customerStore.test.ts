import { describe, it, expect, beforeEach } from 'vitest';
import { useCustomerStore } from './customerStore';

describe('customerStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useCustomerStore.setState({
      user: null,
      projects: [],
      activeProjectId: null,
      chatHistory: [],
      widgets: [],
      sidebarCollapsed: false,
      isLoading: false,
      hydrated: false,
    });
  });

  it('sets the user', () => {
    useCustomerStore.getState().setUser({ id: '1', name: 'A' } as never);
    expect(useCustomerStore.getState().user).toEqual({ id: '1', name: 'A' });
  });

  it('sets projects and the active project', () => {
    useCustomerStore.getState().setProjects([{ id: 'p1' } as never]);
    useCustomerStore.getState().setActiveProject('p1');
    expect(useCustomerStore.getState().activeProjectId).toBe('p1');
    expect(useCustomerStore.getState().projects).toHaveLength(1);
  });

  it('appends and clears chat messages', () => {
    useCustomerStore.getState().addMessage({ id: 1, text: 'hi' } as never);
    expect(useCustomerStore.getState().chatHistory).toHaveLength(1);
    useCustomerStore.getState().clearChat();
    expect(useCustomerStore.getState().chatHistory).toHaveLength(0);
  });

  it('toggles the sidebar collapsed flag', () => {
    const before = useCustomerStore.getState().sidebarCollapsed;
    useCustomerStore.getState().toggleSidebar();
    expect(useCustomerStore.getState().sidebarCollapsed).toBe(!before);
  });

  it('reorders widgets and marks hydration state', () => {
    useCustomerStore.getState().reorderWidgets([{ id: 'w' } as never]);
    expect(useCustomerStore.getState().widgets).toHaveLength(1);
    useCustomerStore.getState().setHydrated(true);
    expect(useCustomerStore.getState().hydrated).toBe(true);
  });
});
