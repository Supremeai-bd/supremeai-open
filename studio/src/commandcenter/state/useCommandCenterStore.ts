import { create } from 'zustand';
import type { CommandModuleId } from '../data/types';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — UI State Store (zustand)
// বাংলা মন্তব্য: শুধুমাত্র UI-transient state — server ডেটা সব React Query-তে
// ═══════════════════════════════════════════════════════════════════════════

type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

interface CommandCenterState {
    // Active module
    activeModule: CommandModuleId;
    setActiveModule: (module: CommandModuleId) => void;

    // Command palette
    isPaletteOpen: boolean;
    setPaletteOpen: (open: boolean) => void;

    // Realtime status
    wsStatus: WsStatus;
    setWsStatus: (status: WsStatus) => void;
    lastSyncAt: number | null;
    setLastSyncAt: (ts: number) => void;

    // Theme
    theme: 'dark' | 'light' | 'sunset' | 'matrix';
    setTheme: (theme: 'dark' | 'light' | 'sunset' | 'matrix') => void;

    // Drawer state (per-module detail drawer)
    drawerOpen: boolean;
    setDrawerOpen: (open: boolean) => void;
}

export const useCommandCenterStore = create<CommandCenterState>((set) => ({
    activeModule: 'deck',
    setActiveModule: (module) => set({ activeModule: module }),

    isPaletteOpen: false,
    setPaletteOpen: (open) => set({ isPaletteOpen: open }),

    wsStatus: 'closed',
    setWsStatus: (status) => set({ wsStatus: status }),
    lastSyncAt: null,
    setLastSyncAt: (ts) => set({ lastSyncAt: ts }),

    theme: 'dark',
    setTheme: (theme) => set({ theme }),

    drawerOpen: false,
    setDrawerOpen: (open) => set({ drawerOpen: open }),
}));
