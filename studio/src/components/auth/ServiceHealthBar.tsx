import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';

// বাংলা মন্তব্য: লগইন পেজের জন্য Public Service Health Bar — কোনো Authentication লাগবে না
import { getApiBaseUrl } from '../../utils/api';

interface HealthCheckResult {
  status: string;
  message: string;
  details?: Record<string, unknown>;
  response_time_ms?: number;
}

interface HealthData {
  status: string;
  timestamp: number;
  total_response_time_ms: number;
  checks: Record<string, HealthCheckResult>;
  summary: {
    total_checks: number;
    healthy: number;
    degraded: number;
    unhealthy: number;
    unknown: number;
  };
}

interface ServiceStatusProps {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown' | 'loading' | 'not_configured' | 'disabled';
  responseTime?: number;
}

const SERVICE_LABEL_MAP: Record<string, string> = {
  application: 'Backend Core',
  database: 'Data Store (Postgres)',
  redis: 'Cache Cluster (Redis)',
  scraper: 'Scraper Service',
  ollama: 'Local Ollama Node',
  memory: 'Compute Memory',
  disk: 'Storage Node',
  external_services: 'External AI Gateways',
  integrations: 'Integrations Bus',
};

const getServiceLabel = (key: string): string => {
  if (SERVICE_LABEL_MAP[key]) return SERVICE_LABEL_MAP[key];
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const StatusDot: React.FC<{ status: ServiceStatusProps['status'] }> = ({ status }) => {
  const colors: Record<ServiceStatusProps['status'], string> = {
    healthy: 'bg-emerald-500 shadow-emerald-500/50',
    degraded: 'bg-amber-500 shadow-amber-500/50',
    unhealthy: 'bg-red-500 shadow-red-500/50',
    unknown: 'bg-gray-500 shadow-gray-500/50',
    loading: 'bg-blue-500 animate-pulse shadow-blue-500/50',
    not_configured: 'bg-slate-500 shadow-slate-500/30',
    disabled: 'bg-slate-600 shadow-slate-600/30',
  };

  return (
    <div className={`w-2 h-2 rounded-full ${colors[status]} shadow-sm`} />
  );
};

const ServiceStatusItem: React.FC<ServiceStatusProps> = ({ name, status, responseTime }) => {
  const statusLabels: Record<ServiceStatusProps['status'], string> = {
    healthy: 'Online',
    degraded: 'Slow',
    unhealthy: 'Down',
    unknown: 'Unknown',
    loading: 'Checking...',
    not_configured: 'Not Configured',
    disabled: 'Disabled',
  };

  const statusColors: Record<ServiceStatusProps['status'], string> = {
    healthy: 'text-emerald-400',
    degraded: 'text-amber-400',
    unhealthy: 'text-red-400',
    unknown: 'text-gray-400',
    loading: 'text-blue-400',
    not_configured: 'text-slate-400',
    disabled: 'text-slate-500',
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-black/20 backdrop-blur-sm"
    >
      <div className="flex items-center gap-2">
        <StatusDot status={status} />
        <span className="text-xs font-medium text-gray-300">{name}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-semibold ${statusColors[status]}`}>
          {statusLabels[status]}
        </span>
        {responseTime && status === 'healthy' && (
          <span className="text-[10px] text-gray-500 font-mono">
            {responseTime.toFixed(0)}ms
          </span>
        )}
      </div>
    </motion.div>
  );
};

// বাংলা মন্তব্য: Public Health Check Function — কোনো Auth Header ছাড়াই কল হবে
const fetchPublicHealth = async (): Promise<HealthData> => {
  const apiBaseUrl = getApiBaseUrl();
  
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000); // 8s timeout for health check

  try {
    const res = await fetch(`${apiBaseUrl}/api/health-aggregation`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        // বাংলা: কোনো Authorization header নেই — public endpoint
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const contentType = res.headers.get('content-type') || '';
    const body = await res.text();

    if (!res.ok) {
      throw new Error(`Health check failed with status ${res.status} from ${res.url}`);
    }

    if (!contentType.toLowerCase().includes('application/json')) {
      const preview = body.replace(/\s+/g, ' ').trim().slice(0, 120);
      throw new Error(
        `Health check returned ${contentType || 'non-JSON'} from ${res.url}${preview ? `: ${preview}` : ''}`,
      );
    }

    try {
      return JSON.parse(body) as HealthData;
    } catch {
      throw new Error(`Health check returned invalid JSON from ${res.url}`);
    }
  } catch (error) {
    clearTimeout(timeoutId);

    // The aggregate endpoint may be unavailable while the canonical liveness
    // endpoint is healthy. Keep the status chip truthful instead of reporting
    // individual services as down from a stale/degraded aggregate response.
    try {
      const fallback = await fetch(`${apiBaseUrl}/api/v1/health`, {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(4000),
      });
      if (fallback.ok) {
        const payload = await fallback.json() as { status?: string; database?: string };
        const healthy = payload.status === 'healthy';
        return {
          status: healthy ? 'healthy' : 'degraded',
          timestamp: Date.now(),
          total_response_time_ms: 0,
          checks: {
            application: { status: healthy ? 'healthy' : 'degraded', message: 'Canonical health endpoint' },
            ...(payload.database ? { database: { status: payload.database, message: 'Canonical health endpoint' } } : {}),
          },
          summary: { total_checks: payload.database ? 2 : 1, healthy: healthy ? (payload.database === 'healthy' ? 2 : 1) : 0, degraded: healthy ? (payload.database === 'healthy' ? 0 : 1) : 1, unhealthy: 0, unknown: 0 },
        };
      }
    } catch (fallbackError) {
      // Fall through to the user-facing connection state below.
      console.warn('Fallback health check skipped:', fallbackError);
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Backend health check timed out');
    }
    throw error;
  }
};

export const ServiceHealthBar: React.FC = () => {
  const [isOpen, setIsOpen] = React.useState(false);
  const { data, error, isLoading, isError } = useQuery<HealthData>({
    queryKey: ['public-health-status'],
    queryFn: fetchPublicHealth,
    refetchInterval: (query) => (query.state.status === 'error' ? false : 20000), // 20 seconds refresh
    staleTime: 12_000,
    enabled: true,

  });


  const getServiceStatus = (check: HealthCheckResult): ServiceStatusProps['status'] => {
    if (!check || !check.status) return 'unknown';
    return check.status as ServiceStatusProps['status'];
  };

  const overallStatus = data?.status || (isError ? 'unhealthy' : 'loading');
  const isHealthy = overallStatus === 'healthy';
  const isDegraded = overallStatus === 'degraded';
  // Subtle label for public users
  const publicStatusLabel = isLoading
    ? 'Connecting to Node...'
    : isError
      ? 'Sync Pending'
      : isHealthy
        ? 'Network Optimal'
        : isDegraded
          ? 'High Concurrency'
          : 'Connecting...';

  // Subtle accent dot colors
  const dotColor = isLoading
    ? 'bg-blue-400 animate-pulse shadow-blue-400/40'
    : isError
      ? 'bg-amber-500/80 shadow-amber-500/30'
      : isHealthy
        ? 'bg-emerald-400 shadow-emerald-400/50'
        : isDegraded
          ? 'bg-amber-400 shadow-amber-400/40'
          : 'bg-rose-500 shadow-rose-500/40';

  // Issue #1463: the detail slot once fell back to 'Synced' in unknown/error
  // states, so the chip could read "Connecting... · Synced" at the same time.
  // Now: measured latency when we have it, 'Synced' only when healthy, and an
  // empty string (nothing rendered) in every transitional/degraded state.
  // The '<50ms' fallback was also a fabricated number — removed.
  const avgLatency = data?.total_response_time_ms
    ? `${Math.round(data.total_response_time_ms)}ms`
    : isHealthy
      ? 'Synced'
      : '';

  return (
    <div className="relative flex flex-col items-center select-none">
      {/* 🚀 Stealth Ambient Chip: Looks like a sleek tech design pill to normal users */}
      <motion.button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="group relative flex items-center gap-2.5 rounded-full border border-[var(--sa-border)] bg-[var(--sa-surface)] px-3.5 py-1.5 shadow-sm transition-colors hover:border-[var(--sa-primary)] cursor-pointer"
        title="Diagnostic Matrix (Click to toggle)"
      >
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${dotColor}`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${dotColor}`} />
        </span>

        <span className="text-[11px] font-mono tracking-wide text-[var(--sa-ink-muted)] group-hover:text-[var(--sa-ink)] transition-colors">
          {publicStatusLabel}
        </span>

        {(data?.summary || avgLatency) && (
          <span className="border-l border-[var(--sa-border)] pl-2 text-[10px] font-mono text-[var(--sa-ink-muted)] transition-colors group-hover:text-[var(--sa-primary)]">
            {data?.summary ? `${data.summary.healthy}/${data.summary.total_checks}` : avgLatency}
          </span>
        )}
      </motion.button>

      {/* 🔍 Secret Diagnostics Modal/Dropdown for those who know */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.16 }}
            className="absolute top-10 z-50 w-80 p-3.5 rounded-2xl bg-black/85 border border-white/10 backdrop-blur-xl shadow-2xl shadow-black/80 text-left"
          >
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10">
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${dotColor}`} />
                <span className="text-xs font-mono font-semibold text-gray-200">System Telemetry</span>
              </div>
              <span className="text-[10px] font-mono text-gray-500" title="Time of the latest backend health check">
                {data?.timestamp
                  ? `Last check ${new Date(data.timestamp < 10_000_000_000 ? data.timestamp * 1000 : data.timestamp).toLocaleTimeString()}`
                  : 'Live'}
              </span>
            </div>

            {isError ? (
              <div className="py-2 text-[11px] font-mono text-rose-400">
                Connection check: {error?.message || 'Server unreachable'}
              </div>
            ) : isLoading || !data ? (
              <div className="py-3 text-center text-xs font-mono text-gray-400 animate-pulse">
                Probing clusters...
              </div>
            ) : (
              <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                {Object.entries(data.checks || {}).map(([key, check]) => (
                  <ServiceStatusItem
                    key={key}
                    name={getServiceLabel(key)}
                    status={getServiceStatus(check)}
                    responseTime={check?.response_time_ms}
                  />
                ))}
              </div>
            )}

            <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between text-[9px] font-mono text-gray-500">
              <span>Status: {overallStatus.toUpperCase()}</span>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="hover:text-cyan-400 text-gray-400 underline cursor-pointer"
              >
                Close
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ServiceHealthBar;
