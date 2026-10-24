import type React from 'react';

// ════════════════════════════════════════════════════════════════════
// TYPES
// (Extracted verbatim from AdminBrowserPanel.tsx — mechanical refactor)
// ════════════════════════════════════════════════════════════════════

export interface BrowserTab {
  id: string;
  url: string;
  title: string;
  favicon?: string;
  isLoading: boolean;
  error?: string;
  lastVisited: number;
  bookmarked: boolean;
}

export interface Bookmark {
  id: string;
  url: string;
  title: string;
  category: 'service' | 'tool' | 'doc' | 'frequent';
  icon?: React.ReactNode;
}

export interface HistoryEntry {
  url: string;
  title: string;
  timestamp: number;
  tabId: string;
}

export interface ConsoleMessage {
  type: 'log' | 'error' | 'warn' | 'info';
  content: string;
  timestamp: number;
  source?: string;
}

export interface AIBrowserAction {
  type: 'summarize' | 'explain' | 'extract_links' | 'find_issues' | 'interact';
  payload?: unknown;
}

// Inlined state type of the former `securityScanResult` useState
export interface SecurityScanResult {
  score: number;
  issues: string[];
}

export type DeviceMode = 'desktop' | 'tablet' | 'mobile';

export interface CrownJewelBrowserProps {
  initialUrl?: string;
  showAIAssistant?: boolean;
  showDevTools?: boolean;
  height?: string | 'full';
  onUrlChange?: (url: string) => void;
  onPageDetect?: (data: { title: string; url: string; type: string }) => void;
  serviceHealthStatus?: Record<string, 'healthy' | 'degraded' | 'down'>;
  enableMemorySave?: boolean;
  userId?: string;
}
