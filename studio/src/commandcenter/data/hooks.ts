import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';
import { adminTokenStore } from '../../services/adminTokenStore';
import type {
  Agent,
  ApprovalItem,
  AuditEntry,
  Backup,
  BudgetCap,
  CIReport,
  ConfigEntry,
  CostReport,
  DashboardEvent,
  DeployGateStatus,
  FeatureFlag,
  HealthMapData,
  KnowledgeStats,
  MemoryStats,
  MetricsData,
  Provider,
  RateLimitInfo,
  ROIData,
  RouterConfig,
  SecurityFinding,
  Session,
  Skill,
  SwarmEdge,
  SwarmNode,
  Tenant,
  ThreatScanResult,
  TrafficData,
  UsageData,
  User,
  Workspace,
} from './types';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — React Query Hooks (P0)
// বাংলা মন্তব্য: সব ডেটা ফেচ এখান থেকে — কম্পোনেন্ট সরাসরি fetch() করবে না
// ═══════════════════════════════════════════════════════════════════════════

const hasToken = (): boolean => !!adminTokenStore.getDecodedToken();

// ─── Query Keys Registry ────────────────────────────────────────────────────
export const cmdKeys = {
  metrics: ['cmd', 'metrics'] as const,
  traffic: ['cmd', 'traffic'] as const,
  providers: ['cmd', 'providers'] as const,
  router: ['cmd', 'router'] as const,
  ci: ['cmd', 'ci'] as const,
  health: ['cmd', 'health'] as const,
  events: ['cmd', 'events'] as const,
  audit: ['cmd', 'audit'] as const,
  tenants: ['cmd', 'tenants'] as const,
  users: ['cmd', 'users'] as const,
  sessions: ['cmd', 'sessions'] as const,
  workspaces: ['cmd', 'workspaces'] as const,
  cost: ['cmd', 'cost'] as const,
  usage: ['cmd', 'usage'] as const,
  roi: ['cmd', 'roi'] as const,
  budget: ['cmd', 'budget'] as const,
  flags: ['cmd', 'flags'] as const,
  settings: ['cmd', 'settings'] as const,
  backups: ['cmd', 'backups'] as const,
  security: ['cmd', 'security'] as const,
  skills: ['cmd', 'skills'] as const,
  memory: ['cmd', 'memory'] as const,
  knowledge: ['cmd', 'knowledge'] as const,
  agents: ['cmd', 'agents'] as const,
  swarm: ['cmd', 'swarm'] as const,
  approvals: ['cmd', 'approvals'] as const,
  rules: ['cmd', 'rules'] as const,
  secrets: ['cmd', 'secrets'] as const,
  ratelimits: ['cmd', 'ratelimits'] as const,
  deploy: ['cmd', 'deploy'] as const,
  evolution: ['cmd', 'evolution'] as const,
};

// ─── Metrics ────────────────────────────────────────────────────────────────
export function useMetrics(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.metrics,
    queryFn: () => apiClient.get<MetricsData>('/admin-api/metrics'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 15_000,
  });
}

// ─── Traffic ────────────────────────────────────────────────────────────────
export function useTraffic(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.traffic,
    queryFn: () => apiClient.get<TrafficData>('/api/admin/traffic/live'),
    refetchInterval: refetchIntervalMs ?? 30_000,
    enabled: hasToken(),
    staleTime: 15_000,
  });
}

// ─── Providers & Router ─────────────────────────────────────────────────────
export function useProviders(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.providers,
    queryFn: () => apiClient.get<Provider[]>('/admin-api/providers'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useRouterConfig() {
  return useQuery({
    queryKey: cmdKeys.router,
    queryFn: () => apiClient.get<RouterConfig>('/admin-api/model-router'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

// ─── CI/CD ──────────────────────────────────────────────────────────────────
export function useCIReports(limit = 20, refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: [...cmdKeys.ci, limit],
    queryFn: () => apiClient.get<CIReport[]>(`/admin-api/ci-logs?limit=${limit}`),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

// ─── Health Map ─────────────────────────────────────────────────────────────
export function useHealthMap(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.health,
    queryFn: () => apiClient.get<HealthMapData>('/admin-api/health-map'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 45_000,
  });
}

// ─── Events ─────────────────────────────────────────────────────────────────
export function useDashboardEvents(limit = 50, refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: [...cmdKeys.events, limit],
    queryFn: () => apiClient.get<DashboardEvent[]>(`/admin-api/events?limit=${limit}`),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 15_000,
  });
}

// ─── Tenants & Users ────────────────────────────────────────────────────────
export function useTenants() {
  return useQuery({
    queryKey: cmdKeys.tenants,
    queryFn: () => apiClient.get<Tenant[]>('/admin-api/tenant-limits'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

export function useUsers() {
  return useQuery({
    queryKey: cmdKeys.users,
    queryFn: () => apiClient.get<User[]>('/admin-api/users'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

// ─── Sessions & Workspaces ──────────────────────────────────────────────────
export function useSessions() {
  return useQuery({
    queryKey: cmdKeys.sessions,
    queryFn: () => apiClient.get<Session[]>('/admin-api/sessions'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

export function useWorkspaces() {
  return useQuery({
    queryKey: cmdKeys.workspaces,
    queryFn: () => apiClient.get<Workspace[]>('/admin-api/workspaces'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

// ─── Cost & Usage ───────────────────────────────────────────────────────────
export function useCostReport() {
  return useQuery({
    queryKey: cmdKeys.cost,
    queryFn: () => apiClient.get<CostReport>('/admin-api/costs'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

export function useUsage(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.usage,
    queryFn: () => apiClient.get<UsageData>('/metrics/usage/'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

export function useROI(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.roi,
    queryFn: () => apiClient.get<ROIData>('/admin-api/metrics/dashboard'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

export function useBudgetCaps() {
  return useQuery({
    queryKey: cmdKeys.budget,
    queryFn: () => apiClient.get<BudgetCap>('/admin-api/budget-caps'),
    enabled: hasToken(),
    staleTime: 60_000,
  });
}

// ─── Security ───────────────────────────────────────────────────────────────
export function useThreatScan(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.security,
    queryFn: () => apiClient.get<ThreatScanResult>('/admin-api/security-scan'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useAuditLogs(limit = 100) {
  return useQuery({
    queryKey: [...cmdKeys.audit, limit],
    queryFn: () => apiClient.get<AuditEntry[]>(`/admin-api/audit?limit=${limit}`),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useApprovalQueue() {
  return useQuery({
    queryKey: cmdKeys.approvals,
    queryFn: () => apiClient.get<ApprovalItem[]>('/admin-api/approvals'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useRateLimits(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.ratelimits,
    queryFn: () => apiClient.get<RateLimitInfo>('/admin-api/rate-limits'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

// ─── Skills & Memory ────────────────────────────────────────────────────────
export function useSkills() {
  return useQuery({
    queryKey: cmdKeys.skills,
    queryFn: () => apiClient.get<Skill[]>('/admin-api/skills'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useMemoryStats(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.memory,
    queryFn: () => apiClient.get<MemoryStats>('/admin-api/memory'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

export function useKnowledgeStats(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.knowledge,
    queryFn: () => apiClient.get<KnowledgeStats>('/admin-api/knowledge'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

// ─── Agents & Swarm ─────────────────────────────────────────────────────────
export function useAgents(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.agents,
    queryFn: () => apiClient.get<Agent[]>('/admin-api/agents'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 15_000,
  });
}

export function useSwarm() {
  return useQuery({
    queryKey: cmdKeys.swarm,
    queryFn: () => apiClient.get<{ nodes: SwarmNode[]; edges: SwarmEdge[] }>('/admin-api/swarm'),
    enabled: hasToken(),
    staleTime: 15_000,
  });
}

// ─── Config & Flags ─────────────────────────────────────────────────────────
export function useFeatureFlags(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.flags,
    queryFn: () => apiClient.get<FeatureFlag[]>('/admin-api/feature-flags'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 120_000,
  });
}

export function useConfigEntries(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.settings,
    queryFn: () => apiClient.get<ConfigEntry[]>('/admin-api/settings'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 120_000,
  });
}

// ─── Backups ────────────────────────────────────────────────────────────────
export function useBackups() {
  return useQuery({
    queryKey: cmdKeys.backups,
    queryFn: () => apiClient.get<Backup[]>('/admin-api/backups'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

// ─── Deploy Gate ────────────────────────────────────────────────────────────
export function useDeployGate() {
  return useQuery({
    queryKey: cmdKeys.deploy,
    queryFn: () => apiClient.get<DeployGateStatus>('/admin-api/deploy-gate'),
    enabled: hasToken(),
    staleTime: 15_000,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────
export function useDeploy(payload?: Record<string, unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mutationPayload?: Record<string, unknown>) =>
      apiClient.post<{ message: string }>('/admin-api/deploy', mutationPayload ?? payload ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cmd'] });
    },
  });
}

export function useCreateBackup(payload?: Record<string, unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mutationPayload?: Record<string, unknown>) =>
      apiClient.post<{ message: string }>('/admin-api/backups', mutationPayload ?? payload ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.backups });
    },
  });
}

export function useSecurityRescan(payload?: Record<string, unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mutationPayload?: Record<string, unknown>) =>
      apiClient.post<{ message: string }>('/admin-api/security-scan', mutationPayload ?? payload ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.security });
    },
  });
}

export function useToggleDeployGate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { status: 'LOCKED' | 'UNLOCKED'; reason: string }) =>
      apiClient.post<{ message: string }>('/admin-api/deploy-gate', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.deploy });
    },
  });
}

export function useUpdateRules() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rules: Record<string, unknown>) =>
      apiClient.post<{ message: string }>('/admin-api/rules', rules),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cmd'] });
    },
  });
}

export function useApproveAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { id: string; approve: boolean; reason: string; otp: string }) =>
      apiClient.post<{ message: string }>('/admin-api/approvals', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.approvals });
    },
  });
}

export function useUpdateBudgetCap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { default_cap?: number; per_tenant?: Record<string, number>; otp: string }) =>
      apiClient.post<{ message: string }>('/admin-api/budget-caps', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.budget });
    },
  });
}

export function useUpdateFeatureFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { key: string; enabled: boolean; rollout_percent: number; otp: string }) =>
      apiClient.post<{ message: string }>('/admin-api/feature-flags', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.flags });
    },
  });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { key: string; value: string; otp: string }) =>
      apiClient.post<{ message: string }>('/admin-api/settings', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.settings });
    },
  });
}

export function useRestoreBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { id: string; otp: string }) =>
      apiClient.post<{ message: string }>(`/admin-api/backups/${payload.id}/restore`, { otp: payload.otp }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.backups });
    },
  });
}

export function useImpersonateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { user_id: string; otp: string }) =>
      apiClient.post<{ token: string }>('/admin-api/impersonate', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.users });
    },
  });
}

export function useResetTenantUsage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { tenant_id: string; otp: string }) =>
      apiClient.post<{ message: string }>(`/admin-api/tenants/${payload.tenant_id}/reset`, { otp: payload.otp }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.tenants });
    },
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { alert_id: string }) =>
      apiClient.post<{ message: string }>('/admin-api/alerts/acknowledge', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cmdKeys.events });
    },
  });
}

// ─── Security Findings (for Threats module) ─────────────────────────────────
export function useSecurityFindings() {
  return useQuery({
    queryKey: [...cmdKeys.security, 'findings'],
    queryFn: () => apiClient.get<SecurityFinding[]>('/admin-api/security-scan/findings'),
    enabled: hasToken(),
    staleTime: 30_000,
  });
}

// ─── Evolution Observability (Self-Evolution plan §20) ──────────────────────
export interface EvolutionProviderRow {
  provider: string | null;
  model: string | null;
  requests: number | null;
  success_rate: number | null;
  rate_limited: number | null;
  latency_p95_ms: number | null;
  estimated_cost: number | null;
  actual_cost: number | null;
}

export interface EvolutionMetrics {
  available: boolean;
  error?: string;
  window_hours?: number;
  learning_events_24h?: number;
  successful_tasks?: number;
  failed_tasks?: number;
  cache_hit_rate_24h?: number | null;
  feedback_events_24h?: number;
  estimated_cost_24h?: number;
  actual_cost_24h?: number;
  token_estimation_error?: number | null;
  providers_24h?: EvolutionProviderRow[];
  autonomous_changes?: {
    proposals_by_status: Record<string, number>;
    total_proposals: number;
    rejected: number;
    promoted: number;
    rolled_back: number;
  };
  learning_store?: {
    queued: number;
    dropped: number;
    flushed: number;
    last_flush_at: string | null;
    db_ok: boolean;
    fallback: number;
  };
}

export function useEvolutionMetrics(refetchIntervalMs?: number | false) {
  return useQuery({
    queryKey: cmdKeys.evolution,
    queryFn: () => apiClient.get<EvolutionMetrics>('/api/v1/evolution/metrics'),
    refetchInterval: refetchIntervalMs ?? false,
    enabled: hasToken(),
    staleTime: 30_000,
  });
}
