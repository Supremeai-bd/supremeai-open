import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface DockIntegration {
  id: string;
  icon: string;
  label: string;
  enabled: boolean;
}

interface WorkspaceSettingsState {
  integrations: DockIntegration[];
  toggleIntegration: (id: string) => void;
  reorderIntegrations: (ids: string[]) => void;
}

const DEFAULT_INTEGRATIONS: DockIntegration[] = [
  { id: 'github', icon: 'Github', label: 'GitHub', enabled: true },
  { id: 'slack', icon: 'MessagesSquare', label: 'Slack', enabled: true },
  { id: 'linear', icon: 'NotebookText', label: 'Linear', enabled: false },
  { id: 'jira', icon: 'HardDrive', label: 'Jira', enabled: false },
  { id: 'email', icon: 'Mail', label: 'Email', enabled: false },
  { id: 'facebook', icon: 'Facebook', label: 'Facebook', enabled: false },
];

export const useWorkspaceSettingsStore = create<WorkspaceSettingsState>()(
  persist(
    (set) => ({
      integrations: DEFAULT_INTEGRATIONS,

      toggleIntegration: (id) =>
        set((state) => ({
          integrations: state.integrations.map((i) =>
            i.id === id ? { ...i, enabled: !i.enabled } : i
          ),
        })),

      reorderIntegrations: (ids) =>
        set((state) => {
          const newIntegrations = [...state.integrations].sort((a, b) => {
            const indexA = ids.indexOf(a.id);
            const indexB = ids.indexOf(b.id);
            if (indexA === -1 && indexB === -1) return 0;
            if (indexA === -1) return 1;
            if (indexB === -1) return -1;
            return indexA - indexB;
          });
          return { integrations: newIntegrations };
        }),
    }),
    {
      name: 'supreme-workspace-settings-storage',
    }
  )
);
