/**
 * Unified Store - Single Source of Truth for Cross-Component State
 * 
 * This store connects your 20+ crown jewel components!
 * 
 * @file frontend/src/store/unifiedStore.ts
 * @description Centralized state management for SupremeAI integration
 * @version 1.0.0
 * 
 * REPLACES: Fragmented state across 10+ separate stores
 * ENABLES: Real-time cross-component communication
 */

import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import type { UnifiedChatMessage } from '../types/chat';

// ════════════════════════════════════════════════════════════════════
// TYPES
// ════════════════════════════════════════════════════════════════════

export interface ServiceHealthEntry {
  status: 'healthy' | 'degraded' | 'down';
  latency?: number;
  lastCheck: number;
  error?: string;
  uptimePercent?: number;
}

export interface BrowseSession {
  url: string;
  title: string;
  timestamp: number;
  tabId: string;
  userId?: string;
  duration?: number;
}

export interface SecurityScanResult {
  url: string;
  score: number;
  issues: SecurityIssue[];
  timestamp: number;
  scanId?: string;
}

export interface SecurityIssue {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  category: string;
  message: string;
  remediation?: string;
}

export interface AlertItem {
  id: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  source: string;
  message: string;
  timestamp: number;
  acknowledged: boolean;
  actionUrl?: string;
  resolvedAt?: number;
}

export interface DeploymentItem {
  id: string;
  environment: 'production' | 'staging' | 'development';
  status: 'pending' | 'running' | 'success' | 'failed' | 'rolled_back';
  commitSha: string;
  commitMessage?: string;
  triggeredBy: string;
  startedAt: number;
  completedAt?: number;
  duration?: number;
  logsUrl?: string;
}

export interface MemoryItem {
  id: string;
  type: 'conversation' | 'browse-session' | 'agent-task' | 'user-action';
  summary: string;
  content: unknown;
  tags: string[];
  importanceScore: number;
  createdAt: number;
  sessionId?: string;
}

// ════════════════════════════════════════════════════════════════════
// UNIFIED STATE INTERFACE
// ════════════════════════════════════════════════════════════════════

export interface UnifiedState {
  // ── CHAT STATE (shared by ChatInterface + CommandCenter + AI) ──
  chat: {
    unreadCount: number;
    activeConversationId: string | null;
    cachedMessages: UnifiedChatMessage[];
    chatPanelExpanded: boolean;
  };
  setChatUnreadCount: (count: number) => void;
  setActiveConversation: (conversationId: string | null) => void;
  appendChatMessage: (message: UnifiedChatMessage) => void;
  toggleChatPanel: () => void;
  
  // ── SERVICE HEALTH (shared by HealthMonitor + Browser + Dashboard) ──
  serviceHealth: Record<string, ServiceHealthEntry>;
  setServiceHealth: (service: string, health: Partial<ServiceHealthEntry>) => void;
  batchUpdateServiceHealth: (updates: Record<string, ServiceHealthEntry>) => void;
  
  // ── BROWSER STATE (shared by CommandCenter + MemoryBrowser + AI) ──
  activeBrowseSessions: BrowseSession[];
  addBrowseSession: (session: BrowseSession) => void;
  clearBrowseSessions: () => void;
  currentBrowserUrl: string | null;
  setCurrentBrowserUrl: (url: string | null) => void;
  
  // ── SECURITY STATE (shared by SecurityDashboard + Browser + ThreatDetection) ──
  lastSecurityScan: SecurityScanResult | null;
  setLastSecurityScan: (scan: SecurityScanResult) => void;
  securityScanHistory: SecurityScanResult[];
  addToSecurityHistory: (scan: SecurityScanResult) => void;
  
  // ── ALERTS (shared by AdminAlertsTab + all components) ──
  alerts: AlertItem[];
  addAlert: (alert: Omit<AlertItem, 'id' | 'timestamp' | 'acknowledged'>) => string; // Returns alert ID
  acknowledgeAlert: (id: string) => void;
  resolveAlert: (id: string) => void;
  clearAcknowledgedAlerts: () => void;
  getUnresolvedCount: () => number;
  
  // ── DEPLOYMENT STATE (shared by CICDVisualizer + CloudOrchestrator) ──
  deployments: DeploymentItem[];
  setDeployments: (deployments: DeploymentItem[]) => void;
  updateDeploymentStatus: (id: string, status: DeploymentItem['status'], updates?: Partial<DeploymentItem>) => void;
  activeDeployments: () => DeploymentItem[];
  
  // ── MEMORY/KNOWLEDGE (shared by MemoryBrowser + Chat + AI) ──
  memoryItems: MemoryItem[];
  addMemoryItem: (item: Omit<MemoryItem, 'id' | 'createdAt'>) => void;
  searchMemory: (query: string) => MemoryItem[];
  
  // ── UI STATE (shared across components) ──
  globalLoading: boolean;
  setGlobalLoading: (loading: boolean) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  activeModule: string | null;
  setActiveModule: (module: string | null) => void;
  
  // ── USER CONTEXT (shared for personalization) ──
  currentUserId: string | null;
  setCurrentUserId: (userId: string | null) => void;
  userPreferences: Record<string, unknown>;
  setUserPreference: (key: string, value: unknown) => void;
  
  // ── DASHBOARD UI (migrated from dashboardStore — Wave 3.7, issue #1263) ──
  systemStatus: 'healthy' | 'degraded' | 'critical';
  updateSystemStatus: (status: 'healthy' | 'degraded' | 'critical') => void;
  activePanel: string | null;
  setActivePanel: (panel: string | null) => void;
  dashboardMode: 'simple' | 'advanced';
  chatTabTerminalOpen: boolean;
  chatTabBrowserOpen: boolean;
  chatTabMobileOpen: boolean;
  toggleDashboardMode: () => void;
  setDashboardMode: (mode: 'simple' | 'advanced') => void;
  toggleTerminal: () => void;
  toggleBrowser: () => void;
  toggleMobile: () => void;
  setChatTabTerminalOpen: (open: boolean) => void;
  setChatTabBrowserOpen: (open: boolean) => void;
  setChatTabMobileOpen: (open: boolean) => void;
  isDeploymentModalOpen: boolean;
  setDeploymentModal: (open: boolean) => void;

  
  // ── UTILITIES ──
  resetState: () => void;
  getStateSnapshot: () => unknown;
}

// ════════════════════════════════════════════════════════════════════
// INITIAL STATE
// ════════════════════════════════════════════════════════════════════

const initialState = {
  // ── CHAT STATE ──
  chat: {
    unreadCount: 0,
    activeConversationId: null as string | null,
    cachedMessages: [] as UnifiedChatMessage[],
    chatPanelExpanded: true,
  },
  serviceHealth: {} as Record<string, ServiceHealthEntry>,
  activeBrowseSessions: [] as BrowseSession[],
  currentBrowserUrl: null as string | null,
  lastSecurityScan: null as SecurityScanResult | null,
  securityScanHistory: [] as SecurityScanResult[],
  alerts: [] as AlertItem[],
  deployments: [] as DeploymentItem[],
  memoryItems: [] as MemoryItem[],
  globalLoading: false,
  sidebarCollapsed: false,
  activeModule: null as string | null,
  // ── DASHBOARD UI (dashboardStore migration) ──
  systemStatus: 'healthy' as 'healthy' | 'degraded' | 'critical',
  activePanel: null as string | null,
  dashboardMode: 'simple' as 'simple' | 'advanced',
  chatTabTerminalOpen: true,
  chatTabBrowserOpen: true,
  chatTabMobileOpen: false,
  isDeploymentModalOpen: false,
  currentUserId: null as string | null,
  userPreferences: {} as Record<string, unknown>,
};

// ════════════════════════════════════════════════════════════════════
// STORE CREATION
// ════════════════════════════════════════════════════════════════════

export const useUnifiedStore = create<UnifiedState>()(
  subscribeWithSelector((set, get) => ({
    ...initialState,

    // ════════════════════════════════════════════════════════════════════
    // SERVICE HEALTH METHODS
    // ════════════════════════════════════════════════════════════════════
    
    setServiceHealth: (service, health) => set((state) => ({
      serviceHealth: {
        ...state.serviceHealth,
        [service]: {
          ...state.serviceHealth[service],
          ...health,
          lastCheck: Date.now()
        }
      }
    })),
    
    batchUpdateServiceHealth: (updates) => set((state) => ({
      serviceHealth: {
        ...state.serviceHealth,
        ...Object.fromEntries(
          Object.entries(updates).map(([service, health]) => [
            service,
            { ...health, lastCheck: Date.now() }
          ])
        )
      }
    })),

    // ════════════════════════════════════════════════════════════════════
    // BROWSER METHODS
    // ════════════════════════════════════════════════════════════════════
    
    addBrowseSession: (session) => set((state) => ({
      activeBrowseSessions: [session, ...state.activeBrowseSessions].slice(0, 100), // Keep last 100
      currentBrowserUrl: session.url
    })),
    
    clearBrowseSessions: () => set({ activeBrowseSessions: [] }),
    
    setCurrentBrowserUrl: (url) => set({ currentBrowserUrl: url }),

    // ════════════════════════════════════════════════════════════════════
    // SECURITY METHODS
    // ════════════════════════════════════════════════════════════════════
    
    setLastSecurityScan: (scan) => set((state) => ({
      lastSecurityScan: scan,
      securityScanHistory: [scan, ...state.securityScanHistory].slice(0, 50)
    })),
    
    addToSecurityHistory: (scan) => set((state) => ({
      securityScanHistory: [scan, ...state.securityScanHistory].slice(0, 50)
    })),

    // ════════════════════════════════════════════════════════════════════
    // ALERTS METHODS
    // ════════════════════════════════════════════════════════════════════
    
    addAlert: (alert) => {
      const id = `alert-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const newAlert: AlertItem = {
        id,
        ...alert,
        timestamp: Date.now(),
        acknowledged: false
      };
      
      set((state) => ({
        alerts: [newAlert, ...state.alerts].slice(0, 500) // Keep last 500
      }));
      
      return id; // Return ID so caller can reference it
    },
    
    acknowledgeAlert: (id) => set((state) => ({
      alerts: state.alerts.map(a => a.id === id ? { ...a, acknowledged: true } : a)
    })),
    
    resolveAlert: (id) => set((state) => ({
      alerts: state.alerts.map(a => 
        a.id === id ? { ...a, acknowledged: true, resolvedAt: Date.now() } : a
      )
    })),
    
    clearAcknowledgedAlerts: () => set((state) => ({
      alerts: state.alerts.filter(a => !a.acknowledged)
    })),
    
    getUnresolvedCount: () => {
      return get().alerts.filter(a => !a.acknowledged).length;
    },

    // ════════════════════════════════════════════════════════════════════
    // DEPLOYMENT METHODS
    // ════════════════════════════════════════════════════════════════════
    
    setDeployments: (deployments) => set({ deployments }),
    
    updateDeploymentStatus: (id, status, updates = {}) => set((state) => ({
      deployments: state.deployments.map(d =>
        d.id === id
          ? { 
              ...d, 
              status, 
              ...updates,
              completedAt: ['success', 'failed', 'rolled_back'].includes(status) ? Date.now() : d.completedAt,
              duration: ['success', 'failed', 'rolled_back'].includes(status) ? Date.now() - d.startedAt : d.duration
            }
          : d
      )
    })),
    
    activeDeployments: () => {
      return get().deployments.filter(d => ['pending', 'running'].includes(d.status));
    },

    // ════════════════════════════════════════════════════════════════════
    // MEMORY METHODS
    // ════════════════════════════════════════════════════════════════════
    
    addMemoryItem: (item) => {
      const id = `memory-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      set((state) => ({
        memoryItems: [{
          id,
          ...item,
          createdAt: Date.now()
        }, ...state.memoryItems].slice(0, 1000)
      }));
    },
    
    searchMemory: (query) => {
      const items = get().memoryItems;
      const lowerQuery = query.toLowerCase();
      
      return items.filter(item =>
        item.summary.toLowerCase().includes(lowerQuery) ||
        item.tags.some(tag => tag.toLowerCase().includes(lowerQuery)) ||
        JSON.stringify(item.content).toLowerCase().includes(lowerQuery)
      ).slice(0, 50); // Return max 50 results
    },

    // ════════════════════════════════════════════════════════════════════
    // CHAT METHODS
    // ════════════════════════════════════════════════════════════════════

    setChatUnreadCount: (count: number) =>
      set((state) => ({
        ...state,
        chat: { ...state.chat, unreadCount: count },
      })),

    setActiveConversation: (conversationId: string | null) =>
      set((state) => ({
        ...state,
        chat: {
          ...state.chat,
          activeConversationId: conversationId,
          cachedMessages: conversationId === null ? [] : state.chat.cachedMessages,
        },
      })),

    appendChatMessage: (message: UnifiedChatMessage) =>
      set((state) => ({
        ...state,
        chat: {
          ...state.chat,
          cachedMessages: [...state.chat.cachedMessages, message].slice(-200),
        },
      })),

    toggleChatPanel: () =>
      set((state) => ({
        ...state,
        chat: { ...state.chat, chatPanelExpanded: !state.chat.chatPanelExpanded },
      })),

    // ════════════════════════════════════════════════════════════════════
    // UI STATE METHODS
    // ════════════════════════════════════════════════════════════════════
    
    setGlobalLoading: (loading) => set({ globalLoading: loading }),
    
    toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    
    setActiveModule: (module) => set({ activeModule: module }),

    // ════════════════════════════════════════════════════════════════════
    // USER CONTEXT METHODS
    // ════════════════════════════════════════════════════════════════════
    
    setCurrentUserId: (userId) => set({ currentUserId: userId }),
    
    setUserPreference: (key, value) => set((state) => ({
      userPreferences: { ...state.userPreferences, [key]: value }
    })),

    // ════════════════════════════════════════════════════════════════════
    // UTILITY METHODS
    // ════════════════════════════════════════════════════════════════════
    
    // ════════════════════════════════════════════════════════════════════
    // DASHBOARD UI METHODS (migrated from dashboardStore — issue #1263)
    // ════════════════════════════════════════════════════════════════════

    updateSystemStatus: (status) => set({ systemStatus: status }),
    setActivePanel: (panel) => set({ activePanel: panel }),
    toggleDashboardMode: () =>
      set((state) => ({ dashboardMode: state.dashboardMode === 'simple' ? 'advanced' : 'simple' })),
    setDashboardMode: (mode) => set({ dashboardMode: mode }),
    toggleTerminal: () => set((state) => ({ chatTabTerminalOpen: !state.chatTabTerminalOpen })),
    toggleBrowser: () => set((state) => ({ chatTabBrowserOpen: !state.chatTabBrowserOpen })),
    toggleMobile: () => set((state) => ({ chatTabMobileOpen: !state.chatTabMobileOpen })),
    setChatTabTerminalOpen: (open) => set({ chatTabTerminalOpen: open }),
    setChatTabBrowserOpen: (open) => set({ chatTabBrowserOpen: open }),
    setChatTabMobileOpen: (open) => set({ chatTabMobileOpen: open }),
    setDeploymentModal: (open) => set({ isDeploymentModalOpen: open }),

    resetState: () => set(initialState),
    
    getStateSnapshot: () => {
      const state = get();
      return {
        timestamp: Date.now(),
        alertsCount: state.alerts.length,
        unresolvedAlerts: state.alerts.filter(a => !a.acknowledged).length,
        servicesDown: Object.values(state.serviceHealth).filter(s => s.status === 'down').length,
        servicesHealthy: Object.values(state.serviceHealth).filter(s => s.status === 'healthy').length,
        activeDeployments: state.activeDeployments().length,
        recentMemoryItems: state.memoryItems.length,
        browserSessions: state.activeBrowseSessions.length,
        lastSecurityScore: state.lastSecurityScan?.score || null,
        chatUnread: state.chat.unreadCount,
        activeChatConversation: state.chat.activeConversationId,
      };
    }
  }))
);

// ════════════════════════════════════════════════════════════════════
// SELECTOR HOOKS (for optimized re-renders)
// ════════════════════════════════════════════════════════════════════

/**
 * Get service health for a specific service
 */
export function useServiceHealth(service: string) {
  return useUnifiedStore(s => s.serviceHealth[service]);
}

/**
 * Get all unresolved alerts
 */
export function useUnresolvedAlerts() {
  return useUnifiedStore(s => s.alerts.filter(a => !a.acknowledged));
}

/**
 * Get count of unresolved alerts by severity
 */
export function useAlertCounts() {
  return useUnifiedStore(s => ({
    critical: s.alerts.filter(a => !a.acknowledged && a.severity === 'critical').length,
    error: s.alerts.filter(a => !a.acknowledged && a.severity === 'error').length,
    warning: s.alerts.filter(a => !a.acknowledged && a.severity === 'warning').length,
    info: s.alerts.filter(a => !a.acknowledged && a.severity === 'info').length,
  }));
}

export function useAnyServicesDown() {
  return useUnifiedStore(s => 
    Object.values(s.serviceHealth).some(h => h.status === 'down')
  );
}

/**
 * Access the chat slice
 */
export function useChatSlice() {
  return useUnifiedStore(s => s.chat);
}

export default useUnifiedStore;


// ── R13 unified-store feature-flag helpers ──────────────────────────────────
// These used to live in store/index.ts (deleted as part of the dead-code
// cleanup — the barrel was unreachable from main.tsx). The tests and the
// migration helpers need them, so they now live beside the store itself.

export const isUnifiedStoreEnabled = (): boolean => {
  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage.getItem('UNIFIED_STORE') === 'true';
  }
  // Vite env fallback
  return import.meta?.env?.VITE_UNIFIED_STORE === 'true';
};

export const disableUnifiedStore = (): void => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('UNIFIED_STORE');
  }
};
