// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Data Contracts (P0)
// বাংলা মন্তব্য: সব ডোমেইন টাইপ — সার্ভার থেকে আসা ডেটার একক সত্য
// ═══════════════════════════════════════════════════════════════════════════

// ─── Module IDs ─────────────────────────────────────────────────────────────
export type CommandModuleId =
  | 'deck'
  | 'agents'
  | 'swarm'
  | 'tasks'
  | 'sessions'
  | 'tenants'
  | 'router'
  | 'providers'
  | 'skills'
  | 'memory'
  | 'metrics'
  | 'logs'
  | 'events'
  | 'ci'
  | 'health'
  | 'traffic'
  | 'evolution'
  | 'threats'
  | 'audit'
  | 'approvals'
  | 'rules'
  | 'secrets'
  | 'ratelimits'
  | 'cost'
  | 'usage'
  | 'budget'
  | 'roi'
  | 'config'
  | 'flags'
  | 'workspaces'
  | 'backups'
  | 'deploy';

// ─── Metrics ────────────────────────────────────────────────────────────────
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
  active_tasks?: number;
}

// ─── Health Map ─────────────────────────────────────────────────────────────
export interface HealthNode {
  region: string;
  status: 'healthy' | 'degraded' | 'down' | 'unknown';
  latency?: number;
  uptime?: number;
}

export interface HealthMapData {
  gcp: HealthNode;
  railway: HealthNode;
  render: HealthNode;
  core_services?: Record<string, HealthNode>;
  overall_health_percent?: number;
}

// ─── CI/CD ──────────────────────────────────────────────────────────────────
export type CIStatus = 'success' | 'failure' | 'failed' | 'running' | 'pending' | 'cancelled';

export interface CIReport {
  id: string;
  status: CIStatus;
  message: string;
  commit_message?: string;
  branch?: string;
  created_at?: number;
  duration_sec?: number;
  steps?: CIStep[];
}

export interface CIStep {
  name: string;
  status: CIStatus;
  started_at?: number;
  completed_at?: number;
}

// ─── Events ─────────────────────────────────────────────────────────────────
export type EventSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface DashboardEvent {
  timestamp: string;
  level: EventSeverity;
  message: string;
  source: string;
  metadata?: Record<string, unknown>;
}

// ─── Tenants ────────────────────────────────────────────────────────────────
export type TenantTier = 'free' | 'starter' | 'pro' | 'enterprise';

export interface Tenant {
  tenant_id: string;
  org: string;
  tier: TenantTier;
  rpm_limit: number;
  tokens_per_day: number;
  concurrent_sessions: number;
  usage_today?: {
    requests: number;
    tokens: number;
    cost: number;
  };
  quota_percent?: number;
  status: 'active' | 'suspended' | 'pending';
}

// ─── Users ──────────────────────────────────────────────────────────────────
export type UserRole = 'god' | 'operator' | 'viewer';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  tenant_id?: string;
  status: 'active' | 'disabled';
  last_login?: number;
  created_at?: number;
}

// ─── Providers & Router ─────────────────────────────────────────────────────
export type ProviderStatus = 'healthy' | 'degraded' | 'down' | 'disabled';

export interface Provider {
  id: string;
  name: string;
  status: ProviderStatus;
  latency_ms?: number;
  latency_history?: number[];
  rate_limit_remaining?: number;
  rate_limit_max?: number;
  models: string[];
  mode: 'primary' | 'fallback' | 'disabled';
  cost_per_1k_tokens?: number;
}

export interface RouterConfig {
  current_override?: {
    provider: string;
    model: string;
    remaining_requests?: number;
  };
  a_b_split?: Record<string, number>;
  cost_quality_preference?: number; // 0 = cost, 1 = quality
  provider_order: string[];
}

// ─── Cost & Usage ───────────────────────────────────────────────────────────
export interface CostReport {
  report: string;
  generated_at?: string;
}

export interface DailyUsage {
  date: string;
  total_cost: number;
  total_tokens: number;
  unique_users: number;
}

export interface UsageData {
  daily: DailyUsage[];
  cost_projected_monthly: number;
  cost_per_hour: number;
}

export interface BudgetCap {
  default_cap: number;
  per_tenant: Record<string, number>;
}

export interface ROIData {
  semantic_cache_hits: number;
  estimated_usd_saved: number;
  duplicate_executions_prevented: number;
  api_cost_reduction_ratio: number;
}

// ─── Security ───────────────────────────────────────────────────────────────
export type FindingSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface SecurityFinding {
  id: string;
  severity: FindingSeverity;
  title: string;
  description: string;
}

export interface ThreatScanResult {
  scan_time: string;
  findings: SecurityFinding[];
  total_findings: number;
}

export interface AuditEntry {
  timestamp: string;
  admin: string;
  role: UserRole;
  action: string;
  target: string;
  result: 'success' | 'failure' | 'pending';
  ip?: string;
  otp_verified?: boolean;
}

export interface ApprovalItem {
  id: string;
  action: string;
  target: string;
  requested_by: string;
  requested_at: string;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
}

export interface RateLimitInfo {
  current_429_events: number;
  per_ip: Record<string, { limit: number; used: number }>;
  per_tenant: Record<string, { limit: number; used: number }>;
}

// ─── Traffic ────────────────────────────────────────────────────────────────
export interface TrafficData {
  current_rps: number;
  window_30min: number[];
  distribution: Record<string, number>;
}

// ─── Backups ────────────────────────────────────────────────────────────────
export type BackupStatus = 'completed' | 'running' | 'failed' | 'pending';

export interface Backup {
  id: string;
  timestamp: string;
  size_mb: number;
  type: 'full' | 'incremental';
  status: BackupStatus;
  retention_tag?: string;
}

// ─── Feature Flags & Config ─────────────────────────────────────────────────
export interface FeatureFlag {
  key: string;
  enabled: boolean;
  rollout_percent: number;
  environment: 'prod' | 'staging' | 'dev';
  updated_at?: string;
}

export interface ConfigEntry {
  key: string;
  value: string;
  masked: boolean;
  last_modified?: string;
}

// ─── Skills & Memory ────────────────────────────────────────────────────────
export interface Skill {
  id: string;
  name: string;
  version: string;
  installed: boolean;
  enabled: boolean;
  source: 'registry' | 'byoc' | 'builtin';
}

export interface MemoryStats {
  banks: Array<{
    name: string;
    entry_count: number;
    recent_writes: number;
  }>;
  semantic_cache_hit_rate: number;
  tokens_saved: number;
}

export interface KnowledgeStats {
  docs_count: number;
  rag_index_status: 'indexed' | 'indexing' | 'failed';
}

// ─── Sessions & Workspaces ──────────────────────────────────────────────────
export interface Session {
  id: string;
  user_id: string;
  started_at: string;
  last_active: string;
  status: 'active' | 'idle' | 'expired';
  ip?: string;
}

export interface Workspace {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
  member_count: number;
}

// ─── Deploy Gate ────────────────────────────────────────────────────────────
export interface DeployGateStatus {
  status: 'LOCKED' | 'UNLOCKED';
  reason?: string;
  updated_by?: string;
  updated_at?: string;
}

// ─── Agents & Swarm ─────────────────────────────────────────────────────────
export type AgentStatus = 'healthy' | 'busy' | 'stalled' | 'dead';

export interface Agent {
  id: string;
  name: string;
  role: string;
  status: AgentStatus;
  current_task?: string;
  queue_depth: number;
  last_heartbeat: string;
  memory_load_percent: number;
  rpm_limit?: number;
}

export interface SwarmNode {
  id: string;
  type: 'agent' | 'provider' | 'service';
  name: string;
  status: AgentStatus | ProviderStatus;
  load?: number;
}

export interface SwarmEdge {
  source: string;
  target: string;
  load: number;
}
