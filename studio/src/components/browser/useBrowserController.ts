import { useCallback, useEffect, useRef, useState } from 'react';

export type ViewMode = 'desktop' | 'mobile';
export type DeviceProfile = 'iphone16pro' | 'galaxy-s24' | 'ipad' | 'desktop';
export type Orientation = 'portrait' | 'landscape';

export interface DeviceSpec {
  id: DeviceProfile;
  label: string;
  width: number;
  height: number;
  bezel: string;
  hasDynamicIsland: boolean;
}

export const DEVICE_SPECS: Record<DeviceProfile, DeviceSpec> = {
  desktop: { id: 'desktop', label: 'Desktop', width: 1280, height: 800, bezel: '', hasDynamicIsland: false },
  iphone16pro: { id: 'iphone16pro', label: 'iPhone 16 Pro', width: 393, height: 852, bezel: 'black', hasDynamicIsland: true },
  'galaxy-s24': { id: 'galaxy-s24', label: 'Galaxy S24', width: 360, height: 780, bezel: 'black', hasDynamicIsland: false },
  ipad: { id: 'ipad', label: 'iPad', width: 820, height: 1180, bezel: 'black', hasDynamicIsland: false },
};

export interface BrowserControllerState {
  url: string;
  inputUrl: string;
  history: string[];
  historyIndex: number;
  viewMode: ViewMode;
  device: DeviceProfile;
  orientation: Orientation;
  keyboardVisible: boolean;
  inspectMode: boolean;
  isLoading: boolean;
  proxyEnabled: boolean;
  lastError: string | null;
}

export interface BrowserController {
  state: BrowserControllerState;
  navigate: (raw: string) => void;
  goBack: () => void;
  goForward: () => void;
  reload: () => void;
  home: () => void;
  setViewMode: (mode: ViewMode) => void;
  toggleViewMode: () => void;
  setDevice: (device: DeviceProfile) => void;
  toggleOrientation: () => void;
  toggleKeyboard: () => void;
  setKeyboardVisible: (v: boolean) => void;
  toggleInspect: () => void;
  setInspectMode: (v: boolean) => void;
  setInputUrl: (v: string) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  canGoBack: boolean;
  canGoForward: boolean;
  effectiveUrl: string;
  viewportHeight: number;
}

const HOME_URL = 'https://supremeai.dev';
const PROXY_PREFIX = '/api/proxy?url=';

export function normalizeUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return HOME_URL;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.includes('.') && !trimmed.includes(' ')) return `https://${trimmed}`;
  return `https://www.google.com/search?q=${encodeURIComponent(trimmed)}`;
}

export function needsProxy(url: string): boolean {
  try {
    const u = new URL(url);
    if (typeof window !== 'undefined' && u.origin === window.location.origin) return false;
    return true;
  } catch {
    return false;
  }
}

export function useBrowserController(initialUrl: string = HOME_URL): BrowserController {
  const [url, setUrl] = useState<string>(initialUrl);
  const [inputUrl, setInputUrl] = useState<string>(initialUrl);
  const [history, setHistory] = useState<string[]>([initialUrl]);
  const [historyIndex, setHistoryIndex] = useState<number>(0);
  const [viewMode, setViewModeState] = useState<ViewMode>('desktop');
  const [device, setDeviceState] = useState<DeviceProfile>('iphone16pro');
  const [orientation, setOrientation] = useState<Orientation>('portrait');
  const [keyboardVisible, setKeyboardVisible] = useState<boolean>(false);
  const [inspectMode, setInspectMode] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const historyRef = useRef(history);
  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  const navigate = useCallback((raw: string) => {
    const next = normalizeUrl(raw);
    setUrl(next);
    setInputUrl(next);
    setHistory((prev) => {
      const base = prev.slice(0, historyIndex + 1);
      const updated = [...base, next];
      return updated;
    });
    setHistoryIndex((i) => i + 1);
    setIsLoading(true);
    setLastError(null);
  }, [historyIndex]);

  const goBack = useCallback(() => {
    setHistoryIndex((i) => {
      if (i <= 0) return i;
      const next = i - 1;
      const target = historyRef.current[next];
      if (target) {
        setUrl(target);
        setInputUrl(target);
        setIsLoading(true);
      }
      return next;
    });
  }, []);

  const goForward = useCallback(() => {
    setHistoryIndex((i) => {
      const arr = historyRef.current;
      if (i >= arr.length - 1) return i;
      const next = i + 1;
      const target = arr[next];
      if (target) {
        setUrl(target);
        setInputUrl(target);
        setIsLoading(true);
      }
      return next;
    });
  }, []);

  const reload = useCallback(() => {
    setIsLoading(true);
    setUrl((u) => u);
  }, []);

  const home = useCallback(() => navigate(HOME_URL), [navigate]);

  const setViewMode = useCallback((mode: ViewMode) => {
    setViewModeState(mode);
    if (mode === 'mobile' && device === 'desktop') setDeviceState('iphone16pro');
    if (mode === 'desktop') setDeviceState('desktop');
  }, [device]);

  const toggleViewMode = useCallback(() => {
    setViewModeState((m) => (m === 'desktop' ? 'mobile' : 'desktop'));
  }, []);

  const setDevice = useCallback((d: DeviceProfile) => {
    setDeviceState(d);
    setViewModeState(d === 'desktop' ? 'desktop' : 'mobile');
  }, []);

  const toggleOrientation = useCallback(() => {
    setOrientation((o) => (o === 'portrait' ? 'landscape' : 'portrait'));
  }, []);

  const toggleKeyboard = useCallback(() => setKeyboardVisible((v) => !v), []);
  const toggleInspect = useCallback(() => setInspectMode((v) => !v), []);

  const spec = DEVICE_SPECS[device];
  const portrait = orientation === 'portrait';
  const baseHeight = portrait ? spec.height : spec.width;
  const keyboardOffset = keyboardVisible ? (viewMode === 'mobile' ? 260 : 0) : 0;
  const viewportHeight = Math.max(200, baseHeight - keyboardOffset);

  const proxyEnabled = needsProxy(url);
  const effectiveUrl = proxyEnabled ? `${PROXY_PREFIX}${encodeURIComponent(url)}` : url;

  const state: BrowserControllerState = {
    url,
    inputUrl,
    history,
    historyIndex,
    viewMode,
    device,
    orientation,
    keyboardVisible,
    inspectMode,
    isLoading,
    proxyEnabled,
    lastError,
  };

  return {
    ...state,
    state,
    navigate,
    goBack,
    goForward,
    reload,
    home,
    setViewMode,
    toggleViewMode,
    setDevice,
    toggleOrientation,
    toggleKeyboard,
    setKeyboardVisible,
    toggleInspect,
    setInspectMode,
    setInputUrl,
    setLoading: setIsLoading,
    setError: setLastError,
    canGoBack: historyIndex > 0,
    canGoForward: historyIndex < history.length - 1,
    effectiveUrl,
    viewportHeight,
  };
}