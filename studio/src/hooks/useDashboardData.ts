import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { adminTokenStore } from '../services/adminTokenStore';
import { useErrorHandler } from './useErrorHandler';

// বাংলা মন্তব্য: MetricsData ফিল্ডগুলোতে active_agents, cpu_percent, memory_percent যোগ করা হলো
export interface MetricsData {
  latency_p50_ms: number;
  latency_p95_ms: number;
  latency_p99_ms: number;
  error_rate: number;
  requests_per_second: number;
  total_requests_24h: number;
  cost_per_hour: number;
  cost_projected_monthly: number;
  active_providers: string[];
  model_call_distribution: Record<string, number>;
  cpu_usage_percent?: number;
  gpu_usage_percent?: number;
  memory_usage_percent?: number;
  cpu_percent?: number;
  memory_percent?: number;
  active_agents?: number;
}

export interface CostReport {
  report: string;
}

export interface HealthMapData {
  gcp: { region: string; status: string; latency?: number; uptime_sla?: string };
  railway: { region: string; status: string; latency?: number; uptime_sla?: string };
  render: { region: string; status: string; latency?: number; uptime_sla?: string; live_uptime_seconds?: number };
  frontend?: { region: string; status: string; latency?: number; uptime_sla?: string; live_uptime_seconds?: number };
}

export interface CIReport {
  id: string;
  status: 'success' | 'failure' | 'failed' | 'running';
  message: string;
  commit_message?: string;
  branch?: string;
  created_at?: number;
}

export interface ThreatScanResult {
  scan_time: string;
  findings: Array<{
    id: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    title: string;
    description: string;
  }>;
  total_findings: number;
}

// 🛡️ অডিটর ফিক্স: টোকেন চেক হেল্পার এবং useErrorHandler integrate করা হয়েছে
const hasToken = (): boolean => !!adminTokenStore.getDecodedToken();

// 🛡️ অডিটর ফিক্স: আপনার exact useDashboardData implementation
export const useDashboardData = () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const { handleError } = useErrorHandler();

  const loadMetrics = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiClient.get<MetricsData>('/admin-api/metrics');
      setMetrics(data);
    } catch (err) {
      handleError(err, 'Failed to load metrics data');
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    if (hasToken()) {
      loadMetrics();
    }
  }, [loadMetrics]);

  return { metrics, loading, refetch: loadMetrics };
};

// বাংলা মন্তব্য: পোলিং বন্ধ করে SSE-এর মাধ্যমে ডেটা আপডেট করা হবে, তবে optional interval প্যারামিটার সাপোর্ট করা হলো
export function useMetrics(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: ['dashboard', 'metrics'],
    queryFn: () => apiClient.get<MetricsData>('/admin-api/metrics'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    // SSE (useDashboardSSE) is the primary update path, but staleTime must be
    // finite: with Infinity a dead SSE connection left metrics frozen for the
    // whole session — never refetched on remount, focus or reconnect.
    staleTime: 30_000,
  });
}

export function useCostReport() {
  return useQuery({
    queryKey: ['dashboard', 'costs'],
    queryFn: () => apiClient.get<CostReport>('/admin-api/costs'),
    refetchInterval: false,
    enabled: hasToken(),
    // Slow-moving data — generous but finite (was Infinity).
    staleTime: 300_000,
  });
}

export function useHealthMap(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: ['dashboard', 'health'],
    queryFn: () => apiClient.get<HealthMapData>('/admin-api/health-map'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    // Volatile provider health — finite (was Infinity, froze on SSE loss).
    staleTime: 60_000,
  });
}

export function useCIReports(limit = 5, refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: ['dashboard', 'ci-logs', limit],
    queryFn: () => apiClient.get<CIReport[]>(`/admin-api/ci-logs?limit=${limit}`),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    // New CI runs land continuously — finite (was Infinity).
    staleTime: 60_000,
  });
}

export function useThreatScan() {
  return useQuery({
    queryKey: ['dashboard', 'security-scan'],
    queryFn: () => apiClient.get<ThreatScanResult>('/admin-api/security-scan'),
    // বাংলা মন্তব্য: পোলিং বন্ধ করে SSE-এর মাধ্যমে ডেটা আপডেট করা হবে
    refetchInterval: false,
    enabled: hasToken(),
    // Scans run periodically, not per-request — finite (was Infinity).
    staleTime: 600_000,
  });
}

export function useDeploy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<{ message: string }>('/admin-api/deploy', {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });
}

export function useUpdateRules() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rules: Record<string, unknown>) =>
      apiClient.post<{ message: string }>('/admin-api/rules', rules),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard'] }),
  });
}

export interface DashboardEvent {
  timestamp: string;
  level: string;
  message: string;
  source: string;
}

export interface ReportsResponse {
  reports: string[];
}

export interface ReportDetail {
  name: string;
  content: string;
}

// বাংলা মন্তব্য: রিয়েল-টাইম ইভেন্ট ডেটা ফেচ করার জন্য রিয়্যাক্ট কোয়েরি হুক
export function useDashboardEvents(limit = 50, refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: ['dashboard', 'events', limit],
    queryFn: () => apiClient.get<DashboardEvent[]>(`/admin-api/events?limit=${limit}`),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    // Live event feed — finite (was Infinity, froze on SSE loss).
    staleTime: 30_000,
  });
}

// বাংলা মন্তব্য: দৈনিক রিপোর্ট ও তার কন্টেন্ট রিট্রিভ করার জন্য রিয়্যাক্ট কোয়েরি হুক
export function useDashboardReports(reportName?: string) {
  return useQuery({
    queryKey: ['dashboard', 'reports', reportName],
    queryFn: () => {
      const url = reportName ? `/admin-api/reports?report_name=${reportName}` : '/admin-api/reports';
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return apiClient.get<any>(url);
    },
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

// SSE Listener Hook
import { getApiBaseUrl } from '../utils/api';
import { createSecureEventSource } from '../lib/secureSse';

export function useDashboardSSE() {
  const qc = useQueryClient();

  useEffect(() => {
    if (!hasToken()) return;
    const backendUrl = getApiBaseUrl();
    const rawToken = adminTokenStore.getRawToken();
    
    const sse = createSecureEventSource(`${backendUrl}/api/dashboard/stream`, rawToken, {
      onMessage: (e) => {
        if (e.type === 'dashboard_events') {
          try {
            const data = JSON.parse(e.data);
            qc.setQueryData(['dashboard', 'events', 50], data); // update cache directly
          } catch (err) {
            console.error('Failed to parse dashboard_events:', err);
          }
        } else if (e.type === 'metrics_events') {
          try {
            const data = JSON.parse(e.data);
            qc.setQueryData(['dashboard', 'metrics'], data);
          } catch (err) {
            console.error('Failed to parse metrics_events:', err);
          }
        }
      },
      onError: (err) => {
        console.error('Dashboard SSE error:', err);
      }
    });

    return () => {
      sse.close();
    };
  }, [qc]);
}
