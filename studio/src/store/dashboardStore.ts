import { create } from 'zustand';

type DashboardMode = 'simple' | 'advanced';

interface DashboardState {
  dashboardMode: DashboardMode;
  setDashboardMode: (mode: DashboardMode) => void;
  chatTabTerminalOpen: boolean;
  chatTabBrowserOpen: boolean;
  chatTabMobileOpen: boolean;
  toggleTerminal: () => void;
  toggleBrowser: () => void;
  toggleMobile: () => void;
  setChatTabTerminalOpen: (open: boolean) => void;
  setChatTabBrowserOpen: (open: boolean) => void;
  setChatTabMobileOpen: (open: boolean) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  dashboardMode: 'advanced',
  setDashboardMode: (mode) => set({ dashboardMode: mode }),
  chatTabTerminalOpen: false,
  chatTabBrowserOpen: true,
  chatTabMobileOpen: false,
  toggleTerminal: () => set((s) => ({ chatTabTerminalOpen: !s.chatTabTerminalOpen })),
  toggleBrowser: () => set((s) => ({ chatTabBrowserOpen: !s.chatTabBrowserOpen })),
  toggleMobile: () => set((s) => ({ chatTabMobileOpen: !s.chatTabMobileOpen })),
  setChatTabTerminalOpen: (open) => set({ chatTabTerminalOpen: open }),
  setChatTabBrowserOpen: (open) => set({ chatTabBrowserOpen: open }),
  setChatTabMobileOpen: (open) => set({ chatTabMobileOpen: open }),
}));
