import type { UnifiedChatMessage } from './types/chat';

export type ChatMessage = UnifiedChatMessage;

export const legacyToUnified = (legacy: { sender: string; text: string; timestamp: string }): UnifiedChatMessage => ({
  id: `migrated_${Date.now()}`,
  role: legacy.sender === 'ai' ? 'assistant' : 'user',
  content: legacy.text,
  timestamp: new Date(legacy.timestamp).getTime(),
});

export interface Skill {
  id: string;
  name: string;
  version: string;
  description: string;
  dependencies?: string;
  installed: boolean;
  source: string;
}

export interface Checkpoint {
  task_id: string;
  step_index: number;
  state: Record<string, unknown>;
}

export interface CloudStats {
  distribution: Record<string, unknown>;
  total_requests: number;
  active_providers: number;
  strategy: string;
}

export interface GcpHealth {
  status: string;
  cloud_run: Record<string, unknown>;
  firestore_mode: string;
  pubsub_mode: string;
  cloud_functions: Record<string, unknown>;
}

export interface HealthMap {
  /** Named known services — additional dynamic services use the index signature. */
  gcp: { status: string; latency: string; region: string };
  railway: { status: string; latency: string; region: string };
  render: { status: string; latency: string; region: string };
  /** Index signature required for compatibility with SubTabContentProps.healthMap */
  [key: string]: { status?: string; latency?: string | number; region?: string; [k: string]: unknown };
}

export interface AdminUser {
  username: string;
  role: string;
  permissions: string[];
  /** Index signature for assignability to SubTabContentProps.adminUsers */
  [key: string]: unknown;
}

export interface SystemAlert {
  id: string;
  level: 'info' | 'warning' | 'error' | 'critical';
  message: string;
  resolved: boolean;
  created_at: string;
  resolved_at: string | null;
}

// বাংলা মন্তব্য: অ্যাডমিন সাবট্যাব ইউনিয়নে 'interactive-chat', 'alerts', 'telemetry', 'automation-queue', 'platform-vault' ও 'llm-gateway' যোগ করা হলো
export type AdminSubTab = 'overview' | 'topology' | 'mesh-agents' | 'service-explorer' | 'agents-swarm' | 'security' | 'audit' | 'incidents' | 'approvals' | 'guardrails' | 'healing' | 'site-actions' | 'librarian' | 'deployments' | 'reliability' | 'recovery' | 'tenants-rbac' | 'finops' | 'rca-intelligence' | 'configuration' | 'command-center' | 'telemetry' | 'automation-queue' | 'platform-vault' | 'llm-gateway' | 'dashboard' | 'sandbox' | 'logs' | 'costs' | 'health' | 'users' | 'config' | 'model-router' | 'skills' | 'memory' | 'cloud' | 'observability' | 'threats' | 'rules' | 'cicd' | 'github' | 'backups' | 'rate-limits';

export interface CIReport {
  id: number;
  run_id: number;
  run_number: number;
  event_name: string;
  actor: string;
  workflow_name: string;
  status: string;
  runtime_seconds: number;
  commit_sha: string;
  branch: string;
  jobs_summary: Record<string, unknown> | null;
  error_logs: string | null;
  created_at: number;
}
