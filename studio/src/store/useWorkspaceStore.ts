// apps/studio-client/src/store/useWorkspaceStore.ts
// Zustand Orchestrator for Living Workspace
// বাংলা মন্তব্য: গ্লোবাল স্টেট ম্যানেজমেন্ট, যা dnd-kit ড্র্যাগ-অ্যান্ড-ড্রপ এবং ডাইনামিক ইন্টিগ্রেশন কন্ট্রোল করবে।

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Notification {
  id: string;
  type: 'info' | 'error' | 'success';
  message: string;
  correlationId?: string;
}

interface WorkspaceState {
  activeIntegrations: string[];
  notifications: Notification[];
  isSimulatorActive: boolean;

  // Actions
  toggleIntegration: (toolId: string) => void;
  addNotification: (notif: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  setSimulatorState: (isActive: boolean) => void;
  logout: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      activeIntegrations: ['github', 'slack'], // Defaults
      notifications: [],
      isSimulatorActive: false,

      toggleIntegration: (toolId) =>
        set((state) => ({
          activeIntegrations: state.activeIntegrations.includes(toolId)
            ? state.activeIntegrations.filter((id) => id !== toolId)
            : [...state.activeIntegrations, toolId],
        })),

      addNotification: (notif) =>
        set((state) => ({
          notifications: [
            ...state.notifications,
            { ...notif, id: crypto.randomUUID() },
          ].slice(-5), // Keep only latest 5
        })),

      removeNotification: (id) =>
        set((state) => ({
          notifications: state.notifications.filter((n) => n.id !== id),
        })),

      setSimulatorState: (isActive) => set({ isSimulatorActive: isActive }),

      logout: () => {
        for (const key of ['supreme_auth_token', 'supreme_admin_jwt', 'adminToken']) {
          localStorage.removeItem(key);
        }
        set({ activeIntegrations: [], notifications: [], isSimulatorActive: false });
      },
    }),
    {
      name: 'supreme-workspace-storage',
      // Only persist activeIntegrations, ignore transient states like notifications
      partialize: (state) => ({ activeIntegrations: state.activeIntegrations }),
    }
  )
);
