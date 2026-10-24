/**
 * ✅ ENHANCED BROWSER PREVIEW - Master Plan Pillar 1 Complete
 * Features: Device viewport switcher, CORS proxy, landscape mode
 *
 * ERR-A03 FIX (2026-09-16): external URLs are no longer rendered in a raw
 * <iframe> (X-Frame-Options / CSP frame-ancestors made modern sites show a
 * blank frame). The component now proxies through the REAL browser-automation
 * backend: session → navigate → Playwright screenshot → <img>. The direct
 * iframe remains only for same-origin generated content (the `html` prop)
 * and as an explicit opt-in fallback, because the proxy path needs a
 * reachable backend session.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Monitor, Tablet, Smartphone, RotateCcw, ExternalLink, RefreshCw, Pause, Play, ImageOff } from 'lucide-react';
import { browserService } from '../../services/browserService';

type DevicePreset = 'desktop' | 'tablet' | 'mobile';

interface DeviceConfig {
  name: string;
  width: number;
  height: number;
  icon: React.ReactNode;
  scale: number;
  devicePixelRatio?: number;
}

const DEVICE_PRESETS: Record<DevicePreset, DeviceConfig> = {
  desktop: {
    name: 'Desktop (1920×1080)',
    width: 1920,
    height: 1080,
    icon: <Monitor size={16} />,
    scale: 0.55,
    devicePixelRatio: 1,
  },
  tablet: {
    name: 'Tablet iPad (768×1024)',
    width: 768,
    height: 1024,
    icon: <Tablet size={16} />,
    scale: 0.75,
    devicePixelRatio: 2,
  },
  mobile: {
    name: 'Mobile iPhone (390×844)',
    width: 390,
    height: 844,
    icon: <Smartphone size={16} />,
    scale: 1,
    devicePixelRatio: 3,
  },
};

interface BrowserPreviewProps {
  url?: string;
  html?: string;
  showDeviceToolbar?: boolean;
  onUrlChange?: (url: string) => void;
  agentPaused?: boolean;
  onAgentPauseToggle?: () => void;
}

const isExternalHttpUrl = (value: string) => /^https?:\/\//i.test(value.trim());

export function BrowserPreview({
  url = '',
  html,
  showDeviceToolbar = true,
  onUrlChange,
  agentPaused = false,
  onAgentPauseToggle,
}: BrowserPreviewProps) {
  const [currentUrl, setCurrentUrl] = useState(url);
  const [reloadKey, setReloadKey] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [device, setDevice] = useState<DevicePreset>('desktop');
  const [isLandscape, setIsLandscape] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [automationError, setAutomationError] = useState<string | null>(null);
  const [automationStatus, setAutomationStatus] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<string | null>(null);
  // ERR-A03: server-side screenshot proxy state.
  const [liveScreenshot, setLiveScreenshot] = useState<string | null>(null);
  const [allowDirectEmbed, setAllowDirectEmbed] = useState(false);
  const sessionRef = useRef<string | null>(null);
  // dedupe guard for the auto-proxy effect below
  const lastAutoNavRef = useRef<string | null>(null);

  // react-compiler lint: refs must not be written during render.
  useEffect(() => {
    sessionRef.current = sessionId;
  }, [sessionId]);

  const captureLiveScreenshot = useCallback(async (id: string): Promise<string | null> => {
    const result = await browserService.execute(id, { action: 'screenshot', full_page: false });
    return result.screenshot ?? null;
  }, []);

  const runBrowserAction = async (action: 'content' | 'screenshot') => {
    if (!sessionId) {
      setAutomationError('Start a browser session by navigating to a URL first.');
      return;
    }

    setIsLoading(true);
    setAutomationError(null);
    setAutomationStatus(null);
    try {
      const result = await browserService.execute(sessionId, {
        action,
        ...(action === 'screenshot' ? { full_page: true } : {}),
      });
      if (action === 'content') {
        setPageContent(result.content ?? 'No readable page content was returned.');
      } else if (result.screenshot) {
        // ERR-A03: the captured image is actually shown now (it used to be
        // discarded with a success toast).
        setLiveScreenshot(result.screenshot);
        setAutomationStatus('Full-page screenshot captured and displayed.');
      } else {
        setAutomationError('The backend did not return a screenshot image.');
      }
    } catch (error) {
      setAutomationError(error instanceof Error ? error.message : 'Browser action failed');
    } finally {
      setIsLoading(false);
    }
  };

  const closeBrowserSession = async () => {
    if (!sessionId) return;
    setIsLoading(true);
    try {
      await browserService.closeSession(sessionId);
      setSessionId(null);
      setPageContent(null);
      setLiveScreenshot(null);
      setAutomationStatus('Browser session closed.');
    } catch (error) {
      setAutomationError(error instanceof Error ? error.message : 'Could not close browser session');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    return () => {
      if (sessionRef.current) {
        Promise.resolve(browserService.closeSession(sessionRef.current)).catch(() => undefined);
      }
    };
  }, []);

  useEffect(() => {
    setCurrentUrl(url);
  }, [url]);

  const navigateAndRender = useCallback(
    async (targetUrl: string) => {
      setAutomationError(null);
      setAutomationStatus(null);
      setLiveScreenshot(null);

      if (!isExternalHttpUrl(targetUrl)) {
        // Relative / non-HTTP targets keep the plain iframe path (same-origin
        // content cannot be screenshotted by the automation backend anyway).
        return;
      }

      setIsLoading(true);
      try {
        const session = sessionId ? { session_id: sessionId } : await browserService.createSession();
        setSessionId(session.session_id);
        await browserService.execute(session.session_id, { action: 'navigate', url: targetUrl });
        const shot = await captureLiveScreenshot(session.session_id);
        if (shot) {
          setLiveScreenshot(shot);
          setAutomationStatus('Rendered via server-side browser session (screenshot proxy).');
        } else {
          setAutomationError('The automation session navigated but returned no screenshot.');
        }
      } catch (error) {
        // Honest failure: show the verbatim backend reason instead of a blank iframe.
        setAutomationError(
          error instanceof Error ? error.message : 'Browser session unavailable for screenshot proxy',
        );
      } finally {
        setIsLoading(false);
      }
    },
    [captureLiveScreenshot, sessionId],
  );

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setReloadKey(value => value + 1);
    lastAutoNavRef.current = currentUrl;
    await navigateAndRender(currentUrl);
  };

  // ERR-A03: the old component auto-loaded the url prop in a raw iframe on
  // mount — preserve that auto-preview behavior, but through the proxy now.
  useEffect(() => {
    if (!html && isExternalHttpUrl(url) && lastAutoNavRef.current !== url) {
      lastAutoNavRef.current = url;
      void navigateAndRender(url);
    }
  }, [url, html, navigateAndRender]);

  const frameWidth = isLandscape ? DEVICE_PRESETS[device].height : DEVICE_PRESETS[device].width;
  const frameHeight = isLandscape ? DEVICE_PRESETS[device].width : DEVICE_PRESETS[device].height;

  const renderViewport = () => {
    if (html) {
      return (
        <iframe
          key={reloadKey}
          srcDoc={html}
          title="Preview"
          className="w-full h-full border-none"
          sandbox="allow-scripts allow-forms allow-popups"
          onLoad={() => setIsLoading(false)}
        />
      );
    }

    // ERR-A03: external URLs render through the screenshot proxy…
    if (liveScreenshot) {
      return (
        <img
          src={`data:image/png;base64,${liveScreenshot}`}
          alt={`Screenshot of ${currentUrl}`}
          className="h-full w-full border-none object-cover object-top"
          data-testid="screenshot-proxy-view"
        />
      );
    }

    // …with an explicit opt-in direct embed as fallback (many sites block it).
    if (isExternalHttpUrl(currentUrl) && allowDirectEmbed) {
      return (
        <iframe
          key={reloadKey}
          src={currentUrl}
          title="Preview"
          className="w-full h-full border-none"
          sandbox="allow-scripts allow-forms allow-popups"
          onLoad={() => setIsLoading(false)}
        />
      );
    }

    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-slate-950 px-6 text-center">
        <ImageOff size={22} className="text-slate-600" aria-hidden />
        <p className="text-[11px] leading-relaxed text-slate-400">
          {automationError ? (
            <>
              <span className="text-red-300">Screenshot proxy failed: </span>
              {automationError}
            </>
          ) : (
            'Enter an http(s) URL to render this page through the server-side browser session. Direct embedding is blocked by most sites (X-Frame-Options / CSP).'
          )}
        </p>
        <div className="flex items-center gap-2">
          <a
            href={currentUrl || undefined}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:border-cyan-500/60 hover:text-cyan-300"
          >
            <span className="inline-flex items-center gap-1">
              <ExternalLink size={11} /> Open directly
            </span>
          </a>
          <button
            type="button"
            onClick={() => setAllowDirectEmbed(true)}
            className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:border-cyan-500/60 hover:text-cyan-300"
          >
            Try direct embed anyway
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-[#030508] border border-slate-800 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between p-3 border-b border-[#00f3ff]/15 bg-[#06080b]">
        <h2 className="text-sm font-bold font-['Space_Grotesk'] tracking-widest text-[#00f3ff] uppercase">
          🌐 Browser Preview
        </h2>
        <div className="flex items-center gap-2">
          {showDeviceToolbar && <div className="flex bg-slate-900 rounded border border-slate-700/50 p-1">
            {(Object.keys(DEVICE_PRESETS) as DevicePreset[]).map((key) => (
              <button
                key={key}
                onClick={() => setDevice(key)}
                className={`p-1.5 rounded transition-colors ${device === key ? 'bg-cyan-500/20 text-cyan-400' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
                title={DEVICE_PRESETS[key].name}
              >
                {DEVICE_PRESETS[key].icon}
              </button>
            ))}
            <div className="w-px h-6 bg-slate-700 mx-1 self-center" />
            <button
              onClick={() => setIsLandscape(!isLandscape)}
              className={`p-1.5 rounded transition-colors ${isLandscape ? 'bg-cyan-500/20 text-cyan-400' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
              title="Toggle Landscape/Portrait"
            >
              <RotateCcw size={14} />
            </button>
          </div>}
        </div>
      </div>

      <div className="p-3 border-b border-slate-800">
        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 bg-[#06080b] border border-slate-800 rounded-lg px-3 py-1.5">
            <ExternalLink size={12} className="text-slate-400" />
            <input
              type="text"
              value={currentUrl}
              onChange={e => {
                setCurrentUrl(e.target.value);
                onUrlChange?.(e.target.value);
              }}
              className="flex-1 bg-transparent text-xs text-white outline-none font-mono"
            />
          </div>
          <button
            type="submit"
            className="p-1.5 rounded border border-slate-800 text-slate-400 hover:text-white hover:border-slate-700 transition-colors"
          >
            <RefreshCw size={12} />
          </button>
        </form>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void runBrowserAction('content')}
            disabled={!sessionId || isLoading}
            className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:border-cyan-500/60 hover:text-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Read page
          </button>
          <button
            type="button"
            onClick={() => void runBrowserAction('screenshot')}
            disabled={!sessionId || isLoading}
            className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition-colors hover:border-cyan-500/60 hover:text-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Capture full-page screenshot
          </button>
          <button
            type="button"
            onClick={() => void closeBrowserSession()}
            disabled={!sessionId || isLoading}
            className="rounded border border-red-900/70 px-2 py-1 text-[11px] text-red-300 transition-colors hover:border-red-500/70 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Close session
          </button>
          {onAgentPauseToggle && <button type="button" onClick={onAgentPauseToggle} className="flex items-center gap-1 rounded border border-amber-500/40 px-2 py-1 text-[11px] text-amber-200 transition-colors hover:bg-amber-500/10" aria-pressed={agentPaused}>{agentPaused ? <Play size={11} /> : <Pause size={11} />} {agentPaused ? 'Resume automation' : 'Pause for manual input'}</button>}
          {agentPaused && <span role="status" className="text-[11px] text-amber-200">Manual control active. You can type secrets directly in the browser.</span>}
          {automationStatus && <span role="status" className="text-[11px] text-emerald-300">{automationStatus}</span>}
        </div>
        {pageContent && (
          <pre className="mt-2 max-h-24 overflow-auto rounded border border-slate-800 bg-slate-950 px-2 py-1 text-[10px] leading-relaxed text-slate-400">
            {pageContent}
          </pre>
        )}
      </div>

      <div className="flex-1 relative bg-slate-950 overflow-auto flex justify-center items-start pt-8 pb-8">
        {automationError && liveScreenshot && (
          <div role="alert" className="absolute top-3 left-3 right-3 z-20 rounded border border-red-500/40 bg-red-950/80 px-3 py-2 text-xs text-red-200">
            {automationError}
          </div>
        )}
        {isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-cyan-500"></div>
          </div>
        )}
        <div
          className="transition-all duration-300 ease-in-out shadow-2xl"
          style={{
            width: frameWidth,
            height: frameHeight,
            transform: `scale(${DEVICE_PRESETS[device].scale})`,
            transformOrigin: 'top center',
            border: '2px solid #1e293b',
            borderRadius: device === 'desktop' ? '8px' : '32px',
            overflow: 'hidden',
            backgroundColor: '#ffffff'
          }}
        >
          {renderViewport()}
        </div>
      </div>
    </div>
  );
}
