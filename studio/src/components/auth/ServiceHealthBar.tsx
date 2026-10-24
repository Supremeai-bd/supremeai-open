import React from 'react';
import { useQuery } from '@tanstack/react-query';

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

// Public Health Check Function — called without any auth headers.
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
    <div className="flex items-center justify-center select-none" data-testid="fleet-health-bar">
      {/* OWNER DECISION (2026-10-24): keep ONLY the 5 signal lights — no text label,
          no healthy/total count, no diagnostics drawer. Public visitors just see
          quiet dots changing colour; only admins know the mapping
          (Gateway / Scraper / Tower / Core / Worker) via the title tooltip. */}
      <div
        className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/40 px-3 py-1.5 backdrop-blur-md"
        aria-label="Render fleet node health"
        role="status"
      >
        {activeNodes.map((node) => (
          <span
            key={node.id}
            className={`inline-flex h-2 w-2 rounded-full transition-colors ${getNodeColor(node.status)}`}
            title={`${node.name}: ${node.status}`}
          />
        ))}
      </div>
    </div>
  );
};

export default ServiceHealthBar;
