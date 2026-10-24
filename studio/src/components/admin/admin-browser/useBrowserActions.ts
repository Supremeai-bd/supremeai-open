import type { Dispatch, RefObject, SetStateAction } from 'react';

import { componentEventBus } from '../../../lib/componentEventBus';
import { useUnifiedStore } from '../../../store/unifiedStore';

import { getPageContent, formatLinksFromData, formatIssuesFromData } from './formatHelpers';
import type { AIBrowserAction, BrowserTab, ConsoleMessage, DeviceMode, SecurityScanResult } from './types';

// ════════════════════════════════════════════════════════════════════
// BROWSER ACTIONS HOOK
// Hosts the AI-assistant, devtools security-scan and screenshot logic
// extracted verbatim from the CrownJewelBrowser component. Plain
// (non-memoized) functions exactly like before — no behavior change.
// ════════════════════════════════════════════════════════════════════

interface UseBrowserActionsParams {
  activeTab?: BrowserTab;
  deviceMode: DeviceMode;
  userId?: string;
  iframeRef: RefObject<HTMLIFrameElement | null>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setAiResponse: Dispatch<SetStateAction<string>>;
  setIsAIProcessing: Dispatch<SetStateAction<boolean>>;
  setSecurityScanResult: Dispatch<SetStateAction<SecurityScanResult | null>>;
  setConsoleMessages: Dispatch<SetStateAction<ConsoleMessage[]>>;
  addConsoleMessage: (type: ConsoleMessage['type'], content: string, source?: string) => void;
}

export function useBrowserActions({
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
}: UseBrowserActionsParams) {
  const addAlert = useUnifiedStore(s => s.addAlert);
  const setLastSecurityScan = useUnifiedStore(s => s.setLastSecurityScan);

  // ════════════════════════════════════════════════════════════════════
  // AI ASSISTANT FUNCTIONS
  // ════════════════════════════════════════════════════════════════════

  const handleAIAction = async (action: AIBrowserAction) => {
    setIsAIProcessing(true);
    setAiResponse('');

    try {
      addConsoleMessage('info', `🤖 Running AI action: ${action.type}...`);

      const response = await fetch('/api/browser/ai-action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: action.type,
          url: activeTab?.url,
          payload: action.payload,
          // FINAL-TEST FIX: pass the preview iframe so getPageContent() can
          // extract the visible page text (same-origin) or at least URL/title
          // (cross-origin). Previously this was a stub returning '' and every
          // AI action ran with zero page context.
          context: await getPageContent(iframeRef)
        })
      });

      if (!response.ok) {
        throw new Error(`AI service error: ${response.status}`);
      }

      const data = await response.json();

      switch (action.type) {
        case 'summarize':
          setAiResponse(data.response || data.summary || 'Summary generated');
          break;
        case 'explain':
          setAiResponse(data.response || data.analysis || 'Analysis complete');
          break;
        case 'extract_links':
          setAiResponse(formatLinksFromData(data.links));
          break;
        case 'find_issues':
          setAiResponse(formatIssuesFromData(data.issues));

          // ✅ Auto-create alert for critical issues
          if (data.criticalIssues?.length > 0) {
            data.criticalIssues.forEach((issue: string) => {
              addAlert({ severity: 'error', source: 'Browser-AI', message: issue });
            });
          }
          break;
        case 'interact':
          setAiResponse(data.response || 'AI response received');
          break;
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      setAiResponse(`❌ AI processing failed: ${errorMsg}\n\nThe AI service may be temporarily unavailable. Please check:\n- Service health monitor\n- Network connection\n- Backend logs`);

      addAlert({
        severity: 'warning',
        source: 'CrownJewelBrowser-AI',
        message: `AI action '${action.type}' failed: ${errorMsg}`
      });
    } finally {
      setIsAIProcessing(false);
    }
  };

  // ════════════════════════════════════════════════════════════════════
  // DEVTOOLS FUNCTIONS
  // ════════════════════════════════════════════════════════════════════

  const clearConsole = () => setConsoleMessages([]);

  const runSecurityScan = async () => {
    setIsAIProcessing(true);

    try {
      // ✅ REAL SECURITY SCAN VIA BACKEND
      addConsoleMessage('info', '🔒 Initiating security scan...');

      const response = await fetch('/api/browser/security-scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: activeTab?.url })
      });

      if (!response.ok) {
        throw new Error(`Security scan service error: ${response.status}`);
      }

      const result = await response.json();

      const scanResult = {
        score: result.score || 0,
        issues: result.issues || []
      };

      setSecurityScanResult(scanResult);

      // ✅ UPDATE UNIFIED STORE
      setLastSecurityScan({
        url: activeTab?.url || '',
        score: scanResult.score,
        issues: scanResult.issues,
        timestamp: Date.now()
      });

      addConsoleMessage('info', `✅ Security scan complete. Score: ${scanResult.score}/100`);

      // ✅ TRIGGER SECURITY DASHBOARD UPDATE via event bus
      componentEventBus.emit('security:scan-complete', result);

      // ✅ AUTO-ALERT FOR LOW SCORES
      if (scanResult.score < 70) {
        addAlert({
          severity: scanResult.score < 50 ? 'critical' : 'error',
          source: 'CrownJewelBrowser-Security',
          message: `Low security score (${scanResult.score}/100) for ${activeTab?.url}`
        });
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      setAiResponse(`❌ Security scan failed: ${errorMsg}`);
      addConsoleMessage('error', `Security scan error: ${errorMsg}`);

      addAlert({
        severity: 'warning',
        source: 'CrownJewelBrowser-Security',
        message: `Security scan failed: ${errorMsg}`
      });
    } finally {
      setIsAIProcessing(false);
    }
  };

  // ════════════════════════════════════════════════════════════════════
  // SCREENSHOT & CAPTURE
  // ════════════════════════════════════════════════════════════════════

  const takeScreenshot = async () => {
    if (!iframeRef.current) return;

    try {
      // ✅ REAL SCREENSHOT CAPTURE VIA BACKEND
      addConsoleMessage('log', '📸 Capturing screenshot...');
      setIsLoading(true);

      const response = await fetch('/api/browser/screenshot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: activeTab?.url,
          width: deviceMode === 'mobile' ? 375 : deviceMode === 'tablet' ? 768 : 1280,
          height: 800,
          fullPage: false
        })
      });

      if (!response.ok) {
        throw new Error(`Screenshot service error: ${response.status}`);
      }

      // Get screenshot as blob and open in new tab
      const blob = await response.blob();
      const screenshotUrl = URL.createObjectURL(blob);
      window.open(screenshotUrl, '_blank');

      addConsoleMessage('log', '✅ Screenshot captured successfully');

      // ✅ OPTIONAL: Save to gallery (non-blocking)
      if (userId) {
        fetch('/api/browser/screenshots', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ url: activeTab?.url, timestamp: Date.now() })
  }).catch((error) => {
    console.warn('[browser] screenshot persistence failed', error);
  });
      }
    } catch (err) {
      addConsoleMessage('error', `Screenshot failed: ${err}`);
      addAlert({
        severity: 'warning',
        source: 'CrownJewelBrowser-Screenshot',
        message: `Screenshot capture failed: ${err instanceof Error ? err.message : err}`
      });
    } finally {
      setIsLoading(false);
    }
  };

  return {
    handleAIAction,
    clearConsole,
    runSecurityScan,
    takeScreenshot,
  };
}
