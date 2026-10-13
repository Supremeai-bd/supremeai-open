import { AsyncLocalStorage } from "node:async_hooks";
import type { ToolProfile } from "./tool-visibility.js";

// #110: flat 3-tier → 6-tier operational RBAC ladder (viewer → supremeadmin).
// বাংলা মন্তব্য: সমতল ৩-স্তর মডেল থেকে ৬-স্তর ক্রমোচ্চ RBAC শ্রেণিবিন্যাসে উন্নীত।
export type UserRole =
  | "supremeadmin"
  | "admin"
  | "agent"
  | "repo_viewer"
  | "restricted_viewer"
  | "viewer";

/**
 * #110: explicit privilege rank per role. Higher rank ⇒ strictly more access
 * (monotonic). repo_viewer (2) reads ALL private repos but cannot execute
 * tools; restricted_viewer (1) reads only satellite repos; supremeadmin (5)
 * is the omni-role super administrator (deploys, secret rotation, overrides).
 * বাংলা মন্তব্য: প্রতিটি রোলের সুস্পষ্ট প্রাইভিলেজ র‍্যাঙ্ক — উচ্চতর র‍্যাঙ্ক মানে কঠোরভাবে বেশি অ্যাক্সেস।
 */
export const ROLE_RANK: Readonly<Record<UserRole, number>> = {
  viewer: 0,
  restricted_viewer: 1,
  repo_viewer: 2,
  agent: 3,
  admin: 4,
  supremeadmin: 5,
} as const;

/** #110: rank accessor with fail-closed viewer default. */
export function roleRank(role: UserRole | undefined | null): number {
  return role ? (ROLE_RANK[role] ?? 0) : 0;
}

export type AccessMode = "public_viewer" | UserRole;

export interface RequestContext {
  role: UserRole;
  accessMode?: AccessMode;
  authenticated?: boolean;
  tenantBound?: boolean;
  requestId?: string;
  clientId?: string;
  scopes?: string[];
  /** Owner tenant of the current caller (client/tenant-admin). */
  tenantId?: string;
  /** True only for the global SupremeAI admin (MCP_ADMIN_KEY). */
  isGlobalAdmin?: boolean;
  /** Tenant type (admin vs customer). */
  tenantType?: "admin" | "customer";
  /**
   * Verified Slot Architecture (#48): slot / registry-client identity bound
   * to this request. Set for credential-verified sessions only.
   */
  slotId?: string;
  /** True only when the slot credential verified against the live registry. */
  slotVerified?: boolean;
  /** Audit-safe credential fingerprint (never the raw credential). */
  credentialId?: string;
  /**
   * Tool Exposure Policy: the client's curated tool-surface profile. Absent
   * or undefined = full RBAC surface (no discovery filtering beyond RBAC).
   * Derived from the registry client record at every transport entry point.
   */
  toolProfile?: ToolProfile;
}

const asyncLocalStorage = new AsyncLocalStorage<RequestContext>();

/**
 * Options for RequestContextStore.getRole().
 */
export interface GetRoleOptions {
  /**
   * Explicit opt-in for genuinely trusted, transport-internal call paths
   * (stdio). HTTP request paths must NEVER pass this — they always run inside
   * a RequestContextStore carrying the caller's real role (#698). The stdio
   * entry point (index.ts startStdioServer) establishes an explicit admin
   * context per inbound message instead of relying on this flag.
   */
  trustedInternal?: boolean;
}

export const RequestContextStore = {
  run<T>(context: RequestContext, fn: () => T): T {
    return asyncLocalStorage.run(context, fn);
  },

  get(): RequestContext | undefined {
    return asyncLocalStorage.getStore();
  },

  /**
   * SECURITY (#698): fail-CLOSED. When no RequestContextStore exists the
   * caller is NOT a known, trusted transport — return "viewer" (which denies
   * privileged operations: action execution, tenant management, approvals)
   * instead of the old fail-open "admin" default. Genuinely trusted internal
   * paths must opt in explicitly via { trustedInternal: true }.
   */
  getRole(options?: GetRoleOptions): UserRole {
    const store = asyncLocalStorage.getStore();
    if (store) return store.role;
    return options?.trustedInternal === true ? "admin" : "viewer";
  },

  getTenantId(): string | undefined {
    return asyncLocalStorage.getStore()?.tenantId;
  },

  isGlobalAdmin(): boolean {
    return asyncLocalStorage.getStore()?.isGlobalAdmin === true;
  },
};
