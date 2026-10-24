import React, { useState, useRef, useCallback, useMemo } from 'react';

import { componentEventBus } from '../../../lib/componentEventBus';
import { eventBus, Events } from '../../../lib/componentEventBus';
import { useUnifiedStore } from '../../../store/unifiedStore';

import { DEFAULT_BOOKMARKS } from './defaultBookmarks';
import { useBrowserActions } from './useBrowserActions';
import { BrowserToolbar } from './BrowserToolbar';
import { BookmarksPanel } from './BookmarksPanel';
import { BrowserViewport } from './BrowserViewport';
import { AIAssistantPanel } from './AIAssistantPanel';
import { DevToolsPanel } from './DevToolsPanel';
import { StatusBar } from './StatusBar';
import { HistoryPanel } from './HistoryPanel';
import type {
  Bookmark,
  BrowserTab,
  ConsoleMessage,
  CrownJewelBrowserProps,
  DeviceMode,
  HistoryEntry,
  SecurityScanResult,
} from './types';

// ════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// (Extracted verbatim from AdminBrowserPanel.tsx — mechanical refactor;
//  render sections moved into the sibling sub-panel components)
// ════════════════════════════════════════════════════════════════════

export const CrownJewelBrowser: React.FC<CrownJewelBrowserProps> = ({
  initialUrl = import.meta.env.VITE_ADMIN_FRONTEND_URL || '',
  showAIAssistant = true,
  showDevTools = false,
  height = 'full',
  onUrlChange,
  onPageDetect,
  serviceHealthStatus = {},
  enableMemorySave = true,
  userId,
}) => {
  // ── Core State ──
  const [tabs, setTabs] = useState<BrowserTab[]>(() => [
    {
      id: 'tab-1',
      url: initialUrl,
      title: 'New Tab',
      isLoading: false,
      lastVisited: Date.now(),
      bookmarked: false,
    }
  ]);
  const [activeTabId, setActiveTabId] = useState<string>('tab-1');
  const [bookmarks, setBookmarks] = useState<Bookmark[]>(DEFAULT_BOOKMARKS);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // ── UI State ──
  const [showBookmarks, setShowBookmarks] = useState(false);
  const [showDevToolsPanel, setShowDevToolsPanel] = useState(showDevTools);
  const [showAIPanel, setShowAIPanel] = useState(showAIAssistant);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [deviceMode, setDeviceMode] = useState<DeviceMode>('desktop');
  const [isLoading, setIsLoading] = useState(false);
  const [consoleMessages, setConsoleMessages] = useState<ConsoleMessage[]>([]);
  const [aiInput, setAiInput] = useState('');
  const [aiResponse, setAiResponse] = useState('');
  const [isAIProcessing, setIsAIProcessing] = useState(false);
  const [urlInputValue, setUrlInputValue] = useState(initialUrl);
  const [showHistory, setShowHistory] = useState(false);
  const [securityScanResult, setSecurityScanResult] = useState<SecurityScanResult | null>(null);

  const iframeRef = useRef<HTMLIFrameElement>(null);

  // ── Computed Values ──
  const activeTab = useMemo(() => tabs.find(t => t.id === activeTabId) || tabs[0], [tabs, activeTabId]);
  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;

  const addAlert = useUnifiedStore(s => s.addAlert);
  const addBrowseSession = useUnifiedStore(s => s.addBrowseSession);

  // ════════════════════════════════════════════════════════════════════
  // UTILITY FUNCTIONS (defined early so hooks below can reference them)
  // ════════════════════════════════════════════════════════════════════

  const normalizeUrl = (url: string): string => {
    if (!url) return 'about:blank';
    if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('about:')) {
      return url;
    }
    // Default to https
    return `https://${url}`;
  };

  const updateTabUrl = useCallback((url: string) => {
    setTabs(prev => prev.map(tab =>
      tab.id === activeTabId ? { ...tab, url } : tab
    ));
  }, [activeTabId]);

  const addConsoleMessage = useCallback((
    type: ConsoleMessage['type'],
    content: string,
    source?: string
  ) => {
    setConsoleMessages(prev => [
      ...prev.slice(-99), // Keep last 100 messages
      { type, content, timestamp: Date.now(), source }
    ]);
  }, []);

  // ════════════════════════════════════════════════════════════════════
  // AI / DEVTOOLS / SCREENSHOT ACTIONS (see useBrowserActions.ts)
  // ════════════════════════════════════════════════════════════════════

  const { handleAIAction, clearConsole, runSecurityScan, takeScreenshot } = useBrowserActions({
    activeTab,
    deviceMode,
    userId,
    iframeRef,
    setIsLoading,
    setAiResponse,
    setIsAIProcessing,
    setSecurityScanResult,
    setConsoleMessages,
    addConsoleMessage,
  });

  // ════════════════════════════════════════════════════════════════════
  // NAVIGATION FUNCTIONS
  // ════════════════════════════════════════════════════════════════════

  const navigateTo = useCallback((url: string, tabId?: string) => {
    const targetTabId = tabId || activeTabId;
    const normalizedUrl = normalizeUrl(url);

    try {
      const domain = new URL(normalizedUrl).hostname;
      const isServiceDown = Object.entries(serviceHealthStatus).some(
        ([service, status]) => domain.includes(service) && status === 'down'
      );

      if (isServiceDown) {
        addAlert({
          severity: 'warning',
          source: 'CrownJewelBrowser',
          message: `⚠️ Navigating to potentially down service: ${domain}`
        });
      }
    } catch (err) {
      console.warn("Invalid URL parse attempt:", err);
    }

    setIsLoading(true);
    setUrlInputValue(normalizedUrl);

    updateTabUrl(normalizedUrl);

    // Update local history
    setHistory(prev => {
      const newHistory = prev.slice(0, historyIndex + 1);
      newHistory.push({
        url: normalizedUrl,
        title: '',
        timestamp: Date.now(),
        tabId: targetTabId,
      });
      return newHistory;
    });
    setHistoryIndex(prev => prev + 1);

    onUrlChange?.(normalizedUrl);
    componentEventBus.emitBrowserUrlChange(normalizedUrl);

    if (enableMemorySave && userId) {
      addBrowseSession({
        url: normalizedUrl,
        title: `Browsing: ${normalizedUrl.substring(0, 50)}`,
        timestamp: Date.now(),
        tabId: targetTabId
      });

      fetch('/api/browser/browse-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: normalizedUrl, timestamp: Date.now(), tabId: targetTabId })
  }).catch((error) => {
    console.warn('[browser] browse-session persistence failed', error);
  });
  }
}, [activeTabId, historyIndex, onUrlChange, serviceHealthStatus, addAlert, updateTabUrl, enableMemorySave, userId, addBrowseSession]);

  const goBack = useCallback(() => {
    if (canGoBack && history[historyIndex - 1]) {
      const entry = history[historyIndex - 1];
      setUrlInputValue(entry.url);
      setHistoryIndex(prev => prev - 1);
      updateTabUrl(entry.url);
    }
  }, [canGoBack, history, historyIndex, updateTabUrl]);

  const goForward = useCallback(() => {
    if (canGoForward && history[historyIndex + 1]) {
      const entry = history[historyIndex + 1];
      setUrlInputValue(entry.url);
      setHistoryIndex(prev => prev + 1);
      updateTabUrl(entry.url);
    }
  }, [canGoForward, history, historyIndex, updateTabUrl]);

  const refresh = useCallback(() => {
    setIsLoading(true);
    if (iframeRef.current) {
      const currentSrc = iframeRef.current.src;
      iframeRef.current.src = 'about:blank';
      // Force the iframe to reload by resetting src on the next tick
      setTimeout(() => {
        if (iframeRef.current) {
          iframeRef.current.src = currentSrc;
        }
      }, 0);
    }
    addConsoleMessage('info', 'Page refreshed');
  }, [addConsoleMessage]);

  // ════════════════════════════════════════════════════════════════════
  // TAB MANAGEMENT
  // ════════════════════════════════════════════════════════════════════

  const createNewTab = useCallback(() => {
    const newTab: BrowserTab = {
      id: `tab-${Date.now()}`,
      url: 'about:blank',
      title: 'New Tab',
      isLoading: false,
      lastVisited: Date.now(),
      bookmarked: false,
    };
    setTabs(prev => [...prev, newTab]);
    setActiveTabId(newTab.id);
  }, []);

  const closeTab = useCallback((tabId: string) => {
    if (tabs.length <= 1) return; // Don't close last tab

    setTabs(prev => {
      const newTabs = prev.filter(t => t.id !== tabId);
      if (activeTabId === tabId) {
        const closedIndex = prev.findIndex(t => t.id === tabId);
        const nextActive = newTabs[Math.min(closedIndex, newTabs.length - 1)];
        setActiveTabId(nextActive?.id || newTabs[0].id);
      }
      return newTabs;
    });
  }, [tabs, activeTabId]);

  // ════════════════════════════════════════════════════════════════════
  // BOOKMARK MANAGEMENT
  // ════════════════════════════════════════════════════════════════════

  const toggleBookmark = useCallback((tabId?: string) => {
    const targetId = tabId || activeTabId;
    const tab = tabs.find(t => t.id === targetId);
    if (!tab) return;

    if (tab.bookmarked) {
      setBookmarks(prev => prev.filter(b => b.url !== tab.url));
    } else {
      const newBookmark: Bookmark = {
        id: `bm-${Date.now()}`,
        url: tab.url,
        title: tab.title || tab.url,
        category: 'frequent',
      };
      setBookmarks(prev => [...prev, newBookmark]);
    }

    setTabs(prev => prev.map(t =>
      t.id === targetId ? { ...t, bookmarked: !t.bookmarked } : t
    ));
  }, [activeTabId, tabs]);

  // ════════════════════════════════════════════════════════════════════
  // UTILITY FUNCTIONS
  // ════════════════════════════════════════════════════════════════════

  const handleIframeLoad = () => {
    setIsLoading(false);
    setTabs(prev => prev.map(tab =>
      tab.id === activeTabId ? { ...tab, isLoading: false } : tab
    ));
    addConsoleMessage('log', `Page loaded: ${activeTab?.url}`);

    eventBus.emit(Events.BROWSER_PAGE_LOADED, {
      url: activeTab?.url,
      timestamp: Date.now(),
      source: 'crown_jewel_browser',
    });

    // Try to detect page info
    try {
      const iframe = iframeRef.current;
      if (iframe?.contentDocument?.title) {
        const title = iframe.contentDocument.title;
        setTabs(prev => prev.map(tab =>
          tab.id === activeTabId ? { ...tab, title: title || 'Loading...' } : tab
        ));
        onPageDetect?.({ title, url: activeTab?.url || '', type: 'page' });
      }
    } catch (err) {
      console.warn("Cross-origin restriction:", err);
    }
  };

  const handleIframeError = () => {
    setIsLoading(false);
    setTabs(prev => prev.map(tab =>
      tab.id === activeTabId
        ? { ...tab, isLoading: false, error: 'Failed to load' }
        : tab
    ));
    addConsoleMessage('error', `Failed to load: ${activeTab?.url}`);
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(activeTab?.url || '');
    addConsoleMessage('log', 'URL copied to clipboard');
  };

  // ════════════════════════════════════════════════════════════════════
  // RENDER (composition — sections live in the sub-panel components)
  // ════════════════════════════════════════════════════════════════════

  return (
    <div className={`flex flex-col bg-[#0a0e1a] border border-cyan-500/20 rounded-xl overflow-hidden shadow-2xl shadow-cyan-500/5 ${
      height === 'full' ? 'h-full' : height
    }`}>

      {/* ═══ BROWSER TOOLBAR ═══ */}
      <BrowserToolbar
        goBack={goBack}
        canGoBack={canGoBack}
        goForward={goForward}
        canGoForward={canGoForward}
        refresh={refresh}
        isLoading={isLoading}
        showHistory={showHistory}
        setShowHistory={setShowHistory}
        urlInputValue={urlInputValue}
        setUrlInputValue={setUrlInputValue}
        navigateTo={navigateTo}
        activeTab={activeTab}
        copyUrl={copyUrl}
        showBookmarks={showBookmarks}
        setShowBookmarks={setShowBookmarks}
        toggleBookmark={toggleBookmark}
        takeScreenshot={takeScreenshot}
        runSecurityScan={runSecurityScan}
        showDevToolsPanel={showDevToolsPanel}
        setShowDevToolsPanel={setShowDevToolsPanel}
        showAIPanel={showAIPanel}
        setShowAIPanel={setShowAIPanel}
        tabs={tabs}
        activeTabId={activeTabId}
        setActiveTabId={setActiveTabId}
        closeTab={closeTab}
        createNewTab={createNewTab}
      />

      {/* ═══ MAIN CONTENT AREA ═══ */}
      <div className="flex-1 flex overflow-hidden">

        {/* Bookmarks Panel (Dropdown) */}
        <BookmarksPanel
          show={showBookmarks}
          bookmarks={bookmarks}
          navigateTo={navigateTo}
          setShowBookmarks={setShowBookmarks}
        />

        {/* Browser Viewport */}
        <BrowserViewport
          isLoading={isLoading}
          deviceMode={deviceMode}
          zoomLevel={zoomLevel}
          activeTab={activeTab}
          iframeRef={iframeRef}
          handleIframeLoad={handleIframeLoad}
          handleIframeError={handleIframeError}
          refresh={refresh}
          securityScanResult={securityScanResult}
          setSecurityScanResult={setSecurityScanResult}
        />

        {/* AI Assistant Panel */}
        <AIAssistantPanel
          show={showAIPanel}
          setShowAIPanel={setShowAIPanel}
          handleAIAction={handleAIAction}
          aiResponse={aiResponse}
          isAIProcessing={isAIProcessing}
          aiInput={aiInput}
          setAiInput={setAiInput}
        />

        {/* DevTools Panel (Bottom) */}
        <DevToolsPanel
          show={showDevToolsPanel}
          setShowDevToolsPanel={setShowDevToolsPanel}
          clearConsole={clearConsole}
          consoleMessages={consoleMessages}
        />
      </div>

      {/* ═══ STATUS BAR ═══ */}
      <StatusBar
        isLoading={isLoading}
        activeTab={activeTab}
        deviceMode={deviceMode}
        setDeviceMode={setDeviceMode}
        zoomLevel={zoomLevel}
        setZoomLevel={setZoomLevel}
        securityScanResult={securityScanResult}
      />

      {/* History Panel (Overlay) */}
      <HistoryPanel
        show={showHistory}
        setShowHistory={setShowHistory}
        history={history}
        navigateTo={navigateTo}
      />
    </div>
  );
};
