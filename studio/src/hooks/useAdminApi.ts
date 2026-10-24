import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { adminTokenStore } from '../services/adminTokenStore';

// বাংলা মন্তব্য: টোকেন চেক — টোকেন ছাড়া কোনো admin-api কল হবে না
const hasToken = (): boolean => !!adminTokenStore.getDecodedToken();

export function useAdminRules() {
  return useQuery({
    queryKey: ['admin', 'rules'],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    queryFn: () => apiClient.get<any>('/api/admin/rules'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useSaveRules() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rules: unknown) => apiClient.post('/api/admin/rules', { rules }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'rules'] }),
  });
}

export function useSkills(query = '') {
  return useQuery({
    queryKey: ['skills', query],
    queryFn: () => apiClient.post<import('../types').Skill[]>('/api/skills/search', { query, installed_only: false }),
    staleTime: 30_000,
  });
}

export function useInstallSkill() {
  const qc = useQueryClient();
  return useMutation({
    // ERR-H02 FIX: backend contract is POST /api/skills/install?skill=<id> —
    // the backend reads `skill` as a query param, a JSON body was ignored.
    mutationFn: (skill: string) =>
      apiClient.post(`/api/skills/install?skill=${encodeURIComponent(skill)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skills'] }),
  });
}

export function useCheckpoints() {
  return useQuery({
    queryKey: ['checkpoints'],
    queryFn: () => apiClient.get<import('../types').Checkpoint[]>('/api/memory/checkpoints'),
    staleTime: 30_000,
  });
}

export function useDeleteCheckpoint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => apiClient.delete(`/api/memory/checkpoint/${taskId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['checkpoints'] }),
  });
}

// বাংলা মন্তব্য: useDashboardData.ts এ একই ডেটার জন্য হুক আছে — queryKey ম্যাচ করানো হয়েছে ডুপ্লিকেট ফেচ ঠেকাতে
export function useCostReport() {
  return useQuery({
    queryKey: ['dashboard', 'costs'],
    queryFn: () => apiClient.get<{ report: string }>('/admin-api/costs'),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    refetchInterval: (query: any) => query.state.error ? false : 60000,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export interface ProviderCost {
  name: string;
  spent: number;
  quota: number;
  color: string;
}

export interface RecentCharge {
  time: string;
  user: string;
  model: string;
  tokens: number;
  cost: number;
}

export interface CostBreakdownData {
  spent: number;
  limit: number;
  percentage: number;
  providerCosts: ProviderCost[];
  recentCharges: RecentCharge[];
}

export function useCostBreakdown() {
  return useQuery({
    queryKey: ['dashboard', 'costs', 'breakdown'],
    queryFn: () => apiClient.get<CostBreakdownData>('/admin-api/costs/breakdown'),
    refetchInterval: 30000,
    enabled: hasToken(),
    staleTime: 20000,
  });
}

export function useHealthMap() {
  return useQuery({
    queryKey: ['dashboard', 'health'],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    queryFn: () => apiClient.get<any>('/admin-api/health-map'),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    refetchInterval: (query: any) => query.state.error ? false : 45000,
    enabled: hasToken(),
    staleTime: 20_000,
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ['admin', 'users'],
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    queryFn: () => apiClient.get<any[]>('/admin-api/users'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useSaveUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (user: { username: string; role: string; permissions: string[] }) =>
      apiClient.post('/admin-api/users', user),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (username: string) => apiClient.delete(`/admin-api/users/${username}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useEnvConfig() {
  return useQuery({
    queryKey: ['admin', 'config'],
    queryFn: () => apiClient.get<Record<string, string>>('/admin-api/config'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

export function useSaveConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (env_vars: Record<string, string>) => apiClient.post('/admin-api/config', { env_vars }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'config'] }),
  });
}

export function useTriggerDeploy() {
  return useMutation({
    mutationFn: () => apiClient.post<{ message: string }>('/admin-api/deploy', {}),
  });
}

export function useGcpHealth() {
  return useQuery({
    queryKey: ['gcp', 'health'],
    queryFn: () => apiClient.get<import('../types').GcpHealth>('/gcp/health'),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    refetchInterval: (query: any) => query.state.error ? false : 45000,
    staleTime: 20_000,
  });
}

export function useCloudStats() {
  return useQuery({
    queryKey: ['cloud', 'distribution'],
    queryFn: () => apiClient.get<import('../types').CloudStats>('/admin/cloud-distribution'),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    refetchInterval: (query: any) => query.state.error ? false : 45000,
    staleTime: 20_000,
  });
}

export function useCIReports(limit = 20) {
  // বাংলা মন্তব্য: সাম্প্রতিক সিআই রিপোর্টগুলো — queryKey ম্যাচ করানো হয়েছে useDashboardData এর সাথে
  return useQuery({
    queryKey: ['dashboard', 'ci-logs', limit],
    queryFn: () => apiClient.get<import('../types').CIReport[]>(`/admin-api/ci-logs?limit=${limit}`),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    refetchInterval: (query: any) => query.state.error ? false : 30000,
    enabled: hasToken(),
    staleTime: 15_000,
  });
}
