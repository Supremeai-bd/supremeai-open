// SupremeAI Studio — shared type barrel (transit surface).
// Re-exports domain types and defines UI-facing types that were previously
// imported from '../../types' without a backing module.

export * from './domain';
export * from './federation';

export type AdminSubTab = string;

export interface HealthMap {
  [key: string]: {
    status?: string;
    region?: string;
    latency?: string | number;
    [k: string]: unknown;
  };
}

export interface ChatMessage {
  id: string;
  role?: string;
  content?: string;
  text?: string;
  sender?: string;
  timestamp?: number | string;
  [key: string]: unknown;
}

export interface Skill {
  id?: string;
  name?: string;
  description?: string;
  [key: string]: unknown;
}

export interface Checkpoint {
  id?: string;
  taskId?: string;
  [key: string]: unknown;
}

export interface AdminUser {
  username: string;
  role?: string;
  permissions?: string[];
  [key: string]: unknown;
}

export interface GcpHealth {
  [key: string]: unknown;
}

export interface CloudStats {
  [key: string]: unknown;
}

export interface SystemAlert {
  id: string;
  level?: string;
  message?: string;
  created_at?: string | number;
  resolved?: boolean;
  resolved_at?: string | number;
  [key: string]: unknown;
}
