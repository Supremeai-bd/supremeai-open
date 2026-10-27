import { useEffect, useState } from 'react';

const QUERIES = {
  sm: '(min-width: 640px)',
  md: '(min-width: 768px)',
  lg: '(min-width: 1024px)',
  xl: '(min-width: 1280px)',
} as const;

type Breakpoint = keyof typeof QUERIES;

function matches(query: string): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(query).matches;
}

export function useBreakpoint(bp: Breakpoint): boolean {
  const [value, setValue] = useState<boolean>(() => matches(QUERIES[bp]));

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(QUERIES[bp]);
    const handler = (event: MediaQueryListEvent) => setValue(event.matches);
    setValue(mql.matches);
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', handler);
      return () => mql.removeEventListener('change', handler);
    }
    // Safari < 14 fallback
    mql.addListener(handler);
    return () => mql.removeListener(handler);
  }, [bp]);

  return value;
}

export function useIsMobile(): boolean {
  return !useBreakpoint('md');
}

export function useIsDesktop(): boolean {
  return useBreakpoint('lg');
}
