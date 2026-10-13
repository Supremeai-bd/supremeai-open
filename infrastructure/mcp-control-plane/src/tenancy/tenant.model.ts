import type { UserRole } from "../policy/auth.context.js";

/** Tenant identity: каждый tenant руководит своим отдельным MCP setup. */
export type TenantType = "admin" | "customer";
export type TenantStatus = "active" | "suspended" | "deleted";
export type TenantPlan = "admin" | "free" | "pro" | "enterprise";

export interface TenantLimits {
  /** Максимально подключенных AI-клиентов. */
  maxClients: number;
  /** Вызовов инструментов за минуту (rate limit). */
  maxToolsPerMinute: number;
  /** Максимально дней жизни токена клиента (0 = без срока). */
  maxTokenDays: number;
}

export interface TenantSettings {
  allowedCategories: string[];
  allowPublicSignup: boolean;
  notifyOnNewClient: boolean;
}

export interface TenantRecord {
  id: string;
  type: TenantType;
  name: string;
  ownerEmail: string;
  description?: string;
  status: TenantStatus;
  plan: TenantPlan;
  limits: TenantLimits;
  settings: TenantSettings;
  /** SHA-256 хеш ТОЛЬКО админ-токена владельца (сырой токен никогда не хранится). */
  adminTokenHash: string;
  createdAt: string;
  updatedAt: string;
  updatedBy?: string;
}

export interface PersistedTenantRecord {
  id: string;
  type: TenantType;
  name: string;
  ownerEmail: string;
  description?: string;
  status: TenantStatus;
  plan: TenantPlan;
  limits: TenantLimits;
  settings: TenantSettings;
  adminTokenHash: string;
  createdAt: string;
  updatedAt: string;
  updatedBy?: string;
}

/** Публичный (безопасный) вид записи — без хешей токенов. */
export interface PublicTenant {
  id: string;
  type: TenantType;
  name: string;
  ownerEmail: string;
  description?: string;
  status: TenantStatus;
  plan: TenantPlan;
  limits: TenantLimits;
  settings: TenantSettings;
  clientCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface TenantAccess {
  tenantId: string;
  role: UserRole;
  type: TenantType;
  isGlobalAdmin: boolean;
}

export const GLOBAL_TENANT_ID = "tenant_supremeai_hq";
export const MAX_TENANTS = 50;

export const DEFAULT_ADMIN_LIMITS: TenantLimits = {
  maxClients: 200,
  maxToolsPerMinute: 1200,
  maxTokenDays: 0,
};

export const DEFAULT_CUSTOMER_LIMITS: TenantLimits = {
  maxClients: 10,
  maxToolsPerMinute: 120,
  maxTokenDays: 30,
};

export function defaultTenantLimits(type: TenantType): TenantLimits {
  return type === "admin" ? { ...DEFAULT_ADMIN_LIMITS } : { ...DEFAULT_CUSTOMER_LIMITS };
}

export function defaultTenantSettings(type: TenantType): TenantSettings {
  return {
    allowedCategories: type === "admin" ? ["*"] : ["github", "ai", "docs", "notify", "knowledge"],
    allowPublicSignup: true,
    notifyOnNewClient: true,
  };
}