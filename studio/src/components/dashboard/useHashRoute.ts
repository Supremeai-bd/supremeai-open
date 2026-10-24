// বাংলা মন্তব্য: react-router ছাড়া হালকা hash-ভিত্তিক রাউটিং হুক — Devin-স্টাইল ড্যাশবোর্ডের পেজ নেভিগেশনের জন্য
import { useEffect, useState, useCallback } from 'react';

export type DashboardRoute =
  | 'sessions'
  | 'session'
  | 'workspace'
  | 'vault'
  | 'automation'
  | 'site-actions'
  | 'llm-gateway'
  | 'knowledge'
  | 'secrets'
  | 'usage'
  | 'settings'
  | 'admin'
  | 'guardrails'
  | 'healing-log'
  | 'swarm-health';

export interface ParsedRoute {
  page: DashboardRoute;
  param?: string;
}

// বাংলা মন্তব্য: hash থেকে পেজ ও প্যারামিটার (যেমন session id) পার্স করা হয়
export function parseHash(hash: string): ParsedRoute {
  const clean = hash.replace(/^#\/?/, '');
  const [page, param] = clean.split('/');
  const known: DashboardRoute[] = ['sessions', 'session', 'workspace', 'vault', 'automation', 'site-actions', 'llm-gateway', 'knowledge', 'secrets', 'usage', 'settings', 'admin', 'guardrails', 'healing-log', 'swarm-health'];
  if (known.includes(page as DashboardRoute)) {
    return { page: page as DashboardRoute, param };
  }
  return { page: 'sessions' };
}

export function useHashRoute(): [ParsedRoute, (page: DashboardRoute, param?: string) => void] {
  const [route, setRoute] = useState<ParsedRoute>(() =>
    parseHash(typeof window !== 'undefined' ? window.location.hash : '')
  );

  useEffect(() => {
    const onHashChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = useCallback((page: DashboardRoute, param?: string) => {
    window.location.hash = param ? `#/${page}/${param}` : `#/${page}`;
  }, []);

  return [route, navigate];
}
