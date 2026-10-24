import React from 'react';
import { useServerStream } from '../../hooks/useServerStream';

/**
 * Headless runtime mount for {@link useServerStream}.
 *
 * ROOT-CAUSE FIX (honesty fix for #972 / #1028 regression class): the
 * useServerStream hook — the ONLY runtime writer of `isServerOnline` /
 * `isServerStatusChecking` via `setServerStatus` — existed for months but was
 * never mounted anywhere (consumers were tests and comments only). As a result
 * the GlobalHeader could never leave its store defaults and showed a
 * permanently stale status label.
 *
 * Mounted ONCE at the App root (inside AppContent, above <Routes>) so the
 * health probe + SSE connection lifecycle cover every route, guest or authed.
 * Renders nothing.
 */
const ServerHealthWatcher: React.FC = () => {
  useServerStream();
  return null;
};

export default ServerHealthWatcher;
