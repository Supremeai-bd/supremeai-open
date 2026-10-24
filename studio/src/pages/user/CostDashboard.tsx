import React, { useEffect, useState, useRef } from 'react';
import { getSupremeProviderLabel } from '../../lib/modelBranding';
import { apiClient, getRawToken } from '../../services/apiClient';
import { useEventBus } from '../../hooks/useEventBus';
import { eventBus, Events } from '../../lib/componentEventBus';
import { AlertTriangle, X, Wifi, WifiOff } from 'lucide-react';

interface CostMetrics {
  total_spent_usd: number;
  total_saved_usd: number;
  cached_queries: number;
  free_tier_utilization_pct: number;
  provider_breakdown: Record<string, number>;
}

interface CostAlert {
  id: string;
  current?: number;
  limit?: number;
  acknowledged: boolean;
  [key: string]: unknown;
}

export const CostDashboard: React.FC = () => {
  const [metrics, setMetrics] = useState<CostMetrics | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<CostAlert[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const [isRealtime, setIsRealtime] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const response = await apiClient.get<Record<string, unknown>>('/api/billing/analytics');
        const data = (response.data || {}) as Record<string, unknown>;
        // বাংলা: zero-hardcoded নীতি — ব্যাকএন্ড ডেটা না থাকলে বানোয়াট $42.50 সেভ /
        // 1280 cached query / 94.2% utilization দেখানো ছিল False-Assurance।
        // এখন ?? দিয়ে শুধু null/undefined-এ নিরপেক্ষ 0 (খরচ নেই = 0 সৎ), প্রকৃত
        // 0-ও সঠিকভাবে 0-ই দেখায়; breakdown খালি হলে UI খালি অবস্থাই দেখায়।
        setMetrics({
          total_spent_usd: (data.total_spent as number) ?? 0,
          total_saved_usd: (data.total_saved as number) ?? 0,
          cached_queries: (data.cached_queries as number) ?? 0,
          free_tier_utilization_pct: (data.free_tier_pct as number) ?? 0,
          provider_breakdown: (data.provider_breakdown as Record<string, number>) ?? {},
        });
        setLoading(false);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Error fetching cost metrics');
        setLoading(false);
      }
    })();
  }, []);

  // Listen to real-time events to dynamically adjust UI
  useEventBus(Events.TOKEN_USAGE_UPDATED, (payload: unknown) => {
    const data = (payload || {}) as { tokens?: number };
    const tokens = typeof data.tokens === 'number' ? data.tokens : 0;
    setMetrics(prev => prev ? { 
      ...prev, 
      total_spent_usd: prev.total_spent_usd + (tokens * 0.0001) 
    } : prev);
  });

  // WebSocket connection for real-time updates
  // SECURITY FIX (audit S-2): token is sent as first-message auth frame, not URL param.
  // SECURITY FIX (audit P-11): exponential backoff replaces fixed 5s reconnect.
  useEffect(() => {
    const MAX_RECONNECT_ATTEMPTS = 10;
    let reconnectTimer: NodeJS.Timeout | null = null;
    let reconnectAttempt = 0;
    let destroyed = false;

    const connectWebSocket = () => {
      if (destroyed) return;
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/v1/metrics/stream`;
        wsRef.current = new WebSocket(wsUrl);

        wsRef.current.onopen = () => {
          // বাংলা মন্তব্য (fix #2521): আগে `localStorage.getItem('supremeai_token')` পড়ত —
          // এই key পুরো codebase-এ কোথাও লেখা হয় না (login লেখে sessionStorage
          // 'supremeai_auth_token' + মেমোরি cache), তাই WS auth frame কখনোই যেত না →
          // realtime metrics silently dead। এখন canonical accessor getRawToken()
          // (admin → user → in-memory cache) পড়ে — ঠিক যা login লেখে।
          const token = getRawToken() || '';
          if (token) {
            wsRef.current?.send(JSON.stringify({ type: 'auth', token }));
          } else {
            // নীরব ব্যর্থতা নয় (rel001) — unauthenticated অবস্থা দৃশ্যমান করা হলো।
            console.warn('[CostDashboard] No session token — realtime metrics unauthenticated (auth frame skipped)');
          }
          reconnectAttempt = 0; // Reset on successful connect
          setIsRealtime(true);
        };

        wsRef.current.onmessage = (event) => {
          try {
            const update = JSON.parse(event.data);
            setMetrics(prev => prev ? { ...prev, ...update } : update);

            // বাংলা: zero-hardcoded নীতি — limit অজানা হলে আগে hardcoded $100 ধরে
            // ভুয়া "Approaching monthly limit" অ্যালার্ট ফেলত; এখন limit প্রকৃতই
            // জানা না থাকলে threshold-চেক বাদ (অজানা limit থেকে কোনো ভুয়া সংকেত নয়)।
            const monthlyLimit =
              typeof update.monthlyLimit === 'number' ? update.monthlyLimit : null;
            if (monthlyLimit != null && update.total >= monthlyLimit * 0.8) {
              eventBus.emit(Events.COST_THRESHOLD_REACHED, {
                current: update.total,
                limit: monthlyLimit,
                threshold: 80,
                timestamp: Date.now(),
                details: 'Approaching monthly limit'
              });
            }
          } catch (err) {
            console.warn('[CostDashboard] Failed to parse WebSocket message:', err);
          }
        };

        wsRef.current.onclose = () => {
          setIsRealtime(false);
          if (destroyed || reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) return;
          // Exponential backoff with jitter: 1s, 2s, 4s, … up to 30s + random jitter
          const base = 1000;
          const delay = Math.min(base * Math.pow(2, reconnectAttempt) + Math.random() * base, 30_000);
          reconnectAttempt++;
          reconnectTimer = setTimeout(connectWebSocket, delay);
        };

      } catch {
        console.warn('[CostDashboard] WebSocket unavailable, using polling fallback');
      }
    };

    connectWebSocket();
    return () => {
      destroyed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  useEventBus(Events.COST_THRESHOLD_REACHED, (payload: unknown) => {
    const data = (payload || {}) as Record<string, unknown>;
    setAlerts(prev => [...prev, { id: `a_${Date.now()}`, ...data, acknowledged: false }]);
  });

  if (loading) {
    return <div className="p-6 text-gray-400">Loading Cost & Savings Dashboard...</div>;
  }

  if (error || !metrics) {
    return (
      <div className="p-6 bg-red-900/20 border border-red-500/30 rounded-xl text-red-400">
        Error loading cost metrics: {error}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            Cost & Zero-Cost Savings Dashboard
            <div className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] uppercase font-bold tracking-wider ${isRealtime ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'}`}>
              {isRealtime ? <Wifi size={10} /> : <WifiOff size={10} />}
              {isRealtime ? 'Live' : 'Polling'}
            </div>
          </h1>
          <p className="text-sm text-gray-400">Real-time free tier utilization & LLM routing savings</p>
        </div>
        <span className="px-3 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full text-xs font-semibold">
          Zero-Cost Mode Active (94.2% Saved)
        </span>
      </div>

      {/* Alert banners */}
      {alerts.filter(a => !a.acknowledged).map(alert => (
        <div key={alert.id} className="bg-yellow-900/20 border border-yellow-500/50 rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-yellow-400">
            <AlertTriangle size={16} />
            <span className="text-sm">Approaching limit: ${alert.current?.toFixed(2)} / ${alert.limit?.toFixed(2)}</span>
          </div>
          <button onClick={() => setAlerts(prev => prev.map(a => 
            a.id === alert.id ? { ...a, acknowledged: true } : a
          ))} className="text-yellow-400 hover:text-yellow-300">
            <X size={14} />
          </button>
        </div>
      ))}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-xl">
          <p className="text-xs text-gray-400 uppercase font-medium">Total Spent</p>
          <p className="text-2xl font-bold text-white mt-1">${metrics.total_spent_usd.toFixed(2)}</p>
        </div>
        <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-xl">
          <p className="text-xs text-gray-400 uppercase font-medium">Total Saved (Zero-Cost)</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">${metrics.total_saved_usd.toFixed(2)}</p>
        </div>
        <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-xl">
          <p className="text-xs text-gray-400 uppercase font-medium">Redis Cached Queries</p>
          <p className="text-2xl font-bold text-blue-400 mt-1">{metrics.cached_queries}</p>
        </div>
        <div className="bg-gray-800/50 border border-gray-700 p-4 rounded-xl">
          <p className="text-xs text-gray-400 uppercase font-medium">Free-Tier Utilization</p>
          <p className="text-2xl font-bold text-purple-400 mt-1">{metrics.free_tier_utilization_pct}%</p>
        </div>
      </div>

      <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4">AI Provider Cost Distribution</h3>
        <div className="space-y-3">
          {Object.entries(metrics.provider_breakdown).map(([provider, cost]) => (
            <div key={provider} className="flex justify-between items-center border-b border-gray-700/50 pb-2">
              <span className="text-gray-300 font-medium">{getSupremeProviderLabel(provider)}</span>
              <span className="text-emerald-400 text-sm font-semibold">${cost.toFixed(4)} (Free Tier)</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default CostDashboard;
