import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { CustomerState } from '../types/customer';

const STORAGE_KEY = 'supremeai_customer_state';

const plainStorage = {
  getItem: (name: string): string | null => {
    return localStorage.getItem(name);
  },
  setItem: (name: string, value: string): void => {
    localStorage.setItem(name, value);
  },
  removeItem: (name: string): void => {
    localStorage.removeItem(name);
  }
};

interface CustomerStoreState extends CustomerState {
  hydrated: boolean;
  setHydrated: (val: boolean) => void;
  /** SECURITY FIX (audit P-7): Clears all user data on logout to prevent
   *  data leakage between users on shared devices. */
  clearSession: () => void;
}

export const useCustomerStore = create<CustomerStoreState>()(
  persist(
    (set) => ({
      user: null,
      projects: [],
      activeProjectId: null,
      chatHistory: [],
      widgets: [],
      sidebarCollapsed: false,
      isLoading: false,
      hydrated: false,

      setUser: (user) => set({ user }),
      setProjects: (projects) => set({ projects }),
      setActiveProject: (id) => set({ activeProjectId: id }),
      addMessage: (message) =>
        set((state) => ({
          chatHistory: [...state.chatHistory, message],
        })),
      clearChat: () => set({ chatHistory: [] }),
      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      reorderWidgets: (widgets) => set({ widgets }),
      setHydrated: (val) => set({ hydrated: val }),
      // SECURITY FIX (audit P-7): Wipe all PII / session data on logout.
      clearSession: () => {
        set({
          user: null,
          projects: [],
          activeProjectId: null,
          chatHistory: [],
          widgets: [],
        });
        // Remove the persisted localStorage entry so next user gets a clean state.
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) { console.debug('customerStore: failed to clear storage', e); }
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => plainStorage),
      partialize: (state) => ({
        user: state.user,
        projects: state.projects,
        activeProjectId: state.activeProjectId,
        widgets: state.widgets,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    }
  )
);

export function useHydrated() {
  return useCustomerStore((s) => s.hydrated);
}
