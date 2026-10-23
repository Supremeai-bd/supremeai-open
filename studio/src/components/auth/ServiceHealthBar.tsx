import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';

// বাংলা মন্তব্য: লগইন পেজের জন্য Public Service Health Bar — কোনো Authentication লাগবে না
// 5 Render Fleet Nodes: API Gateway, Scraper Relay, MCP Control Tower, Primary Node, Worker Node
import { apiClient } from '../../services/apiClient';

export interface HealthCheckResult {
  name?: string;
  status: string;
  message?: string;
  details?: Record<string, unknown>;
  response_time_ms?: number;
}

export interface HealthData {
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

export interface ServiceStatusProps {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown' | 'loading' | 'not_configured' | 'disabled';
  responseTime?: number;
}

export const FLEET_NODES = [
  { id: 'api', name: 'API Gateway', short: 'Gateway' },
  { id: 'scraper', name: 'Scraper Relay', short: 'Scraper' },
  { id: 'tower', name: 'MCP Control Tower', short: 'Tower' },
  { id: 'primary', name: 'Primary Core Node', short: 'Core' },
  { id: 'worker', name: 'Worker Node', short: 'Worker' },
] as const;

export const SERVICE_LABEL_MAP: Record<string, string> = {
  api: 'API Gateway',
  scraper: 'Scraper Relay',
  tower: 'MCP Control Tower',
  primary: 'Primary Core Node',
  worker: 'Worker Node',
  application: 'Backend Core',
  database: 'Data Store (Postgres)',
  redis: 'Cache Cluster (Redis)',
  ollama: 'Local Ollama Node',
  memory: 'Compute Memory',
  disk: 'Storage Node',
  external_services: 'External AI Gateways',
  integrations: 'Integrations Bus',
};

export const getServiceLabel = (key: string): string => {
  if (SERVICE_LABEL_MAP[key]) return SERVICE_LABEL_MAP[key];
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const StatusDot: React.FC<{ status: ServiceStatusProps['status'] }> = ({ status }) => {
  const colors: Record<ServiceStatusProps['status'], string> = {
    healthy: 'bg-emerald-400 shadow-emerald-400/50',
    degraded: 'bg-amber-400 shadow-amber-400/50',
    unhealthy: 'bg-rose-500 shadow-rose-500/50',
    unknown: 'bg-gray-500 shadow-gray-500/50',
    loading: 'bg-blue-400 animate-pulse shadow-blue-400/50',
    not_configured: 'bg-slate-500 shadow-slate-500/30',
    disabled: 'bg-slate-600 shadow-slate-600/30',
  };

  return (
    <div className={`w-2 h-2 rounded-full ${colors[status] || colors.unknown} shadow-sm`} />
  );
};

const ServiceStatusItem: React.FC<ServiceStatusProps> = ({ name, status, responseTime }) => {
  const statusLabels: Record<ServiceStatusProps['status'], string> = {
    healthy: 'Online',
    degraded: 'Waking up',
    unhealthy: 'Down',
    unknown: 'Unknown',
    loading: 'Checking...',
    not_configured: 'Not Configured',
    disabled: 'Disabled',
  };

  const statusColors: Record<ServiceStatusProps['status'], string> = {
    healthy: 'text-emerald-400',
    degraded: 'text-amber-400',
    unhealthy: 'text-rose-400',
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
        <span className={`text-xs font-semibold ${statusColors[status] || 'text-gray-400'}`}>
          {statusLabels[status] || 'Unknown'}
        </span>
        {responseTime !== undefined && status === 'healthy' && (
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
  try {
    const res = await apiClient.stream('/api/health-aggregation', {
      method: 'GET',
      auth: false,
      headers: {
        'Content-Type': 'application/json',
      },
    });

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
    try {
      const payload = await apiClient.get<{ status?: string; database?: string }>('/api/v1/health', {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(4000),
      });
      const healthy = payload.status === 'healthy';
      return {
        status: healthy ? 'healthy' : 'degraded',
        timestamp: Date.now(),
        total_response_time_ms: 0,
        checks: {
          application: { status: healthy ? 'healthy' : 'degraded', message: 'Canonical health endpoint' },
          ...(payload.database ? { database: { status: payload.database, message: 'Canonical health endpoint' } } : {}),
        },
        summary: {
          total_checks: payload.database ? 2 : 1,
          healthy: healthy ? (payload.database === 'healthy' ? 2 : 1) : 0,
          degraded: healthy ? (payload.database === 'healthy' ? 0 : 1) : 1,
          unhealthy: 0,
          unknown: 0,
        },
      };
    } catch (fallbackError) {
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

  const getServiceStatus = (check?: HealthCheckResult): ServiceStatusProps['status'] => {
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

  const avgLatency = data?.total_response_time_ms
    ? `${Math.round(data.total_response_time_ms)}ms`
    : isHealthy
      ? 'Synced'
      : '';

  // 5 mini circles mapping: check if fleet nodes exist, else fallback to received check keys
  const activeNodes = React.useMemo(() => {
    if (!data?.checks) {
      return FLEET_NODES.map((n) => ({
        id: n.id,
        name: n.name,
        short: n.short,
        status: (isLoading ? 'loading' : isError ? 'unhealthy' : 'unknown') as ServiceStatusProps['status'],
        latency: undefined as number | undefined,
      }));
    }

    const hasFleet = FLEET_NODES.some((n) => data.checks[n.id]);
    if (hasFleet) {
      return FLEET_NODES.map((n) => {
        const check = data.checks[n.id];
        return {
          id: n.id,
          name: n.name,
          short: n.short,
          status: getServiceStatus(check),
          latency: check?.response_time_ms,
        };
      });
    }

    // Dynamic keys if different schema
    return Object.entries(data.checks).map(([key, check]) => ({
      id: key,
      name: getServiceLabel(key),
      short: key.toUpperCase(),
      status: getServiceStatus(check),
      latency: check?.response_time_ms,
    }));
  }, [data, isLoading, isError]);

  const getNodeColor = (status: ServiceStatusProps['status']) => {
    switch (status) {
      case 'healthy':
        return 'bg-emerald-400 shadow-emerald-400/50';
      case 'degraded':
        return 'bg-amber-400 shadow-amber-400/50';
      case 'unhealthy':
        return 'bg-rose-500 shadow-rose-500/50';
      case 'loading':
        return 'bg-blue-400 animate-pulse shadow-blue-400/50';
      default:
        return 'bg-gray-500 shadow-gray-500/30';
    }
  };

  return (
    <div className="relative flex flex-col items-center select-none" data-testid="fleet-health-bar">
      {/* 🚀 5-Node Fleet Health Pill */}
      <motion.button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="group relative flex items-center gap-3 rounded-full border border-white/10 bg-black/40 px-3.5 py-1.5 shadow-sm backdrop-blur-md transition-all hover:border-emerald-500/40 hover:bg-black/60 cursor-pointer"
        title="Diagnostic Matrix (Click to toggle)"
      >
        {/* 5 mini status circles */}
        <div className="flex items-center gap-1.5" aria-label="Render fleet node health">
          {activeNodes.map((node) => (
            <span
              key={node.id}
              className={`relative inline-flex rounded-full h-2 w-2 transition-colors ${getNodeColor(node.status)}`}
              title={`${node.name}: ${node.status}${node.latency !== undefined ? ` (${node.latency}ms)` : ''}`}
            />
          ))}
        </div>

        <span className="text-[11px] font-mono tracking-wide text-slate-300 group-hover:text-white transition-colors">
          {publicStatusLabel}
        </span>

        {(data?.summary || avgLatency) && (
          <span className="border-l border-white/10 pl-2.5 text-[10px] font-mono text-slate-400 transition-colors group-hover:text-emerald-400">
            {data?.summary ? `${data.summary.healthy}/${data.summary.total_checks}` : avgLatency}
          </span>
        )}
      </motion.button>

      {/* 🔍 Diagnostics Modal / Fleet Matrix Drawer */}
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
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1">
                  {activeNodes.map((node) => (
                    <div key={node.id} className={`w-1.5 h-1.5 rounded-full ${getNodeColor(node.status)}`} />
                  ))}
                </div>
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
            ) : isLoading && !data ? (
              <div className="py-3 text-center text-xs font-mono text-gray-400 animate-pulse">
                Probing clusters...
              </div>
            ) : (
              <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                {activeNodes.map((node) => (
                  <ServiceStatusItem
                    key={node.id}
                    name={node.name}
                    status={node.status}
                    responseTime={node.latency}
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
