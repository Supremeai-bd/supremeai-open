// ══════════════════════════════════════════════════════════════════════════════
// CI Dashboard — WebSocket real-time connection hook
// (extracted verbatim from CIDashboard.tsx — mechanical split, no behavior change)
// ══════════════════════════════════════════════════════════════════════════════

import { useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { CISummaryData, ConnectionStatus } from './types';
import { getAdminToken, getUserToken } from '../../../../services/tokenStorage';

interface UseDashboardWebSocketOptions {
  wsUrl?: string;
  fetchData: () => Promise<void>;
  setConnectionStatus: Dispatch<SetStateAction<ConnectionStatus>>;
  setData: Dispatch<SetStateAction<CISummaryData | null>>;
  setLastUpdated: Dispatch<SetStateAction<Date | null>>;
}

export function useDashboardWebSocket({
  wsUrl,
  fetchData,
  setConnectionStatus,
  setData,
  setLastUpdated,
}: UseDashboardWebSocketOptions) {
  // WebSocket connection for real-time updates
  useEffect(() => {
    const wsEndpoint = wsUrl || import.meta.env.VITE_DASHBOARD_WS_URL;

    if (!wsEndpoint) {
      // Fallback to polling
      fetchData();
      return;
    }

    let reconnectAttempt = 0;
    const MAX_RECONNECT = 8;
    let destroyed = false;
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      if (destroyed) return;
      setConnectionStatus('connecting');

      try {
        // SECURITY FIX (audit S-2): token must NOT be in the URL.
        // Strip any ?token= that the caller might have embedded in wsEndpoint.
        const cleanWsEndpoint = wsEndpoint.replace(/([?&])token=[^&]*/g, '$1').replace(/[?&]$/, '');
        const socket = new WebSocket(cleanWsEndpoint);
        ws = socket;

        socket.onopen = () => {
          // First-message auth frame — token never appears in URL or logs.
          // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
          const token = getUserToken() || getAdminToken();
          if (token) socket.send(JSON.stringify({ type: 'auth', token }));
          reconnectAttempt = 0;
          setConnectionStatus('connected');
        };

        socket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);

            if (message.channel === 'ci.summary' || message.type === 'ci_update') {
              setData(message.data);
              setLastUpdated(new Date());
            }
          } catch (err) {
            console.error('WebSocket parse error:', err);
          }
        };

        socket.onclose = () => {
          setConnectionStatus('disconnected');
          if (destroyed || reconnectAttempt >= MAX_RECONNECT) return;
          // Exponential backoff with jitter
          const delay = Math.min(1_000 * Math.pow(2, reconnectAttempt) + Math.random() * 1_000, 30_000);
          reconnectAttempt++;
          reconnectTimeout = setTimeout(connect, delay);
        };

        socket.onerror = () => {
          setConnectionStatus('error');
          socket.close();
        };

      } catch (err) {
        console.error('WebSocket connection failed:', err);
        setConnectionStatus('error');
        // Fall back to polling
        fetchData();
      }
    };

    connect();

    return () => {
      destroyed = true;
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, [wsUrl, fetchData, setConnectionStatus, setData, setLastUpdated]);
}
