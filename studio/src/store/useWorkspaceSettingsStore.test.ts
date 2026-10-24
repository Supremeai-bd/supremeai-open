import { describe, it, expect, beforeEach } from 'vitest';
import { useWorkspaceSettingsStore } from './useWorkspaceSettingsStore';

describe('useWorkspaceSettingsStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useWorkspaceSettingsStore.setState({
      integrations: [
        { id: 'github', icon: 'Github', label: 'GitHub', enabled: true },
        { id: 'slack', icon: 'MessagesSquare', label: 'Slack', enabled: true },
        { id: 'linear', icon: 'NotebookText', label: 'Linear', enabled: false },
      ],
    });
  });

  it('toggles an integration enabled flag by id', () => {
    useWorkspaceSettingsStore.getState().toggleIntegration('linear');
    const linear = useWorkspaceSettingsStore.getState().integrations.find((i) => i.id === 'linear');
    expect(linear?.enabled).toBe(true);

    useWorkspaceSettingsStore.getState().toggleIntegration('github');
    const github = useWorkspaceSettingsStore.getState().integrations.find((i) => i.id === 'github');
    expect(github?.enabled).toBe(false);
  });

  it('reorders integrations according to the provided id list', () => {
    useWorkspaceSettingsStore.getState().reorderIntegrations(['linear', 'slack', 'github']);
    const ids = useWorkspaceSettingsStore.getState().integrations.map((i) => i.id);
    expect(ids).toEqual(['linear', 'slack', 'github']);
  });
});
