import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { env } from "../lib/env.js";
import { RequestContextStore } from "../policy/auth.context.js";
import {
  GLOBAL_TENANT_ID,
  MAX_TENANTS,
  defaultTenantLimits,
  defaultTenantSettings,
  type PublicTenant,
  type TenantLimits,
  type TenantRecord,
  type TenantSettings,
  type TenantType,
  type TenantPlan,
  type TenantStatus,
  type TenantAccess,
} from "./tenant.model.js";

/**
 * Tenant Registry — центральный реестр изолированных окружений.
 *
 * Каждый admin/customer владеет отдельным MCP setup:
 *   - собственным tenant record (лимиты, настройки);
 *   - собственным списком AI-клиентов (client registry, поле tenantId);
 *   - собственным админ-токеном для управления своим окружением.
 *
 * Хранилище: JSON-файл с атомарной записью. Это даёт полную изоляцию
 * данных по tenants без внешней БД и может быть заменено на
 * Supabase/Postgres позже (реализация за интерфейсом).
 */

interface TenantStoreFile {
  version: 1;
  tenants: TenantRecord[];
}

const DEFAULT_FILE = process.env.MCP_TENANT_DIR
  ? `${process.env.MCP_TENANT_DIR}/registry.json`
  : "";

const digest = (value: string) => createHash("sha256").update(value).digest("hex");

/**
 * Timing-safe equality for admin-token-hash comparison (#698). Both sides are
 * fixed-length sha256 hex digests; the length guard keeps timingSafeEqual from
 * throwing if a stored hash were ever corrupt/short.
 */
function hashEquals(a: string, b: string): boolean {
  const ab = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

function atomicWrite(filePath: string, data: unknown): void {
  mkdirSync(dirname(filePath), { recursive: true });
  const tmp = `${filePath}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`, { mode: 0o600 });
  renameSync(tmp, filePath);
}

function loadFile(): TenantRecord[] {
  if (!DEFAULT_FILE || !existsSync(DEFAULT_FILE)) return [];
  try {
    const parsed: unknown = JSON.parse(readFileSync(DEFAULT_FILE, "utf8"));
    if (!parsed || typeof parsed !== "object" || !Array.isArray((parsed as TenantStoreFile).tenants)) {
      return [];
    }
    return (parsed as TenantStoreFile).tenants;
  } catch {
    return [];
  }
}

function persistFile(tenants: TenantRecord[]): void {
  if (!DEFAULT_FILE) return;
  atomicWrite(DEFAULT_FILE, { version: 1, tenants } satisfies TenantStoreFile);
}

const memoryStore = new Map<string, TenantRecord>();
for (const record of loadFile()) memoryStore.set(record.id, record);

function all(): TenantRecord[] {
  return [...memoryStore.values()];
}

function save(record: TenantRecord): void {
  memoryStore.set(record.id, record);
  persistFile([...memoryStore.values()]);
}

function sanitize(record: TenantRecord): PublicTenant {
  const { adminTokenHash: _hash, ...safe } = record;
  return { ...safe } as PublicTenant;
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function hasTenantRegistry(): boolean {
  return Boolean(env.mcpAdminKey) || Boolean(process.env.MCP_ADMIN_KEY);
}

export function isGlobalAdmin(): boolean {
  const ctx = RequestContextStore.get();
  return ctx?.role === "admin" && Boolean(ctx.isGlobalAdmin);
}

export function canManageTenants(): boolean {
  return hasTenantRegistry() && isGlobalAdmin();
}
export function createTenant(
  input: {
    name: string;
    ownerEmail: string;
    type: TenantType;
    plan?: TenantPlan;
    limits?: Partial<TenantLimits>;
    settings?: Partial<TenantSettings>;
    description?: string;
  }
): { tenant: PublicTenant; adminToken: string } {
  if (!canManageTenants()) {
    throw new Error("Forbidden: only the global SupremeAI admin can create tenants");
  }
  if (all().length >= MAX_TENANTS) {
    throw new Error(`Tenant limit reached (max ${MAX_TENANTS})`);
  }
  const trimmedName = (input.name ?? "").trim();
  const email = (input.ownerEmail ?? "").trim().toLowerCase();
  if (!trimmedName || !email || !/[^@\s]+@[^@\s]+\.[^@\s]+/.test(email)) {
    throw new Error("name and a valid ownerEmail are required");
  }
  if (all().some((t) => t.ownerEmail === email && t.status !== "deleted")) {
    throw new Error(`A tenant already exists for owner email: ${email}`);
  }

  const adminToken = `tenant_admin_${randomBytes(32).toString("base64url")}`;
  const defaults = defaultTenantLimits(input.type);
  const record: TenantRecord = {
    id: `tenant_${randomBytes(8).toString("hex")}`,
    type: input.type,
    name: trimmedName,
    ownerEmail: email,
    description: input.description?.trim(),
    status: "active",
    plan: input.plan ?? (input.type === "admin" ? "admin" : "free"),
    limits: { ...defaults, ...(input.limits ?? {}) },
    settings: { ...defaultTenantSettings(input.type), ...(input.settings ?? {}) },
    adminTokenHash: digest(adminToken),
    createdAt: nowIso(),
    updatedAt: nowIso(),
    updatedBy: "global-admin",
  };

  save(record);
  return { tenant: sanitize(record), adminToken };
}

export function listTenants(): PublicTenant[] {
  return all()
    .filter((t) => t.status !== "deleted")
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    .map(sanitize);
}

export function getTenant(id: string): TenantRecord | undefined {
  return all().find((t) => t.id === id && t.status !== "deleted");
}

export function getTenantByEmail(email: string): TenantRecord | undefined {
  const normalized = (email ?? "").trim().toLowerCase();
  return all().find((t) => t.ownerEmail === normalized && t.status === "active");
}
export function updateTenant(
  id: string,
  patch: Partial<Omit<TenantRecord, "id" | "adminTokenHash" | "createdAt" | "updatedAt" | "limits">> & {
    limits?: Partial<TenantLimits>;
  }
): PublicTenant {

  if (!canManageTenants()) {
    throw new Error("Forbidden: only the global SupremeAI admin can update tenants");
  }
  const record = getTenant(id);
  if (!record) throw new Error(`Tenant not found: ${id}`);

  if (patch.name !== undefined) record.name = patch.name.trim();
  if (patch.description !== undefined) record.description = patch.description?.trim();
  if (patch.status !== undefined) record.status = patch.status;
  if (patch.plan !== undefined) record.plan = patch.plan;
  if (patch.limits !== undefined) record.limits = { ...record.limits, ...patch.limits };
  if (patch.settings !== undefined) record.settings = { ...record.settings, ...patch.settings };
  record.updatedAt = nowIso();
  record.updatedBy = "global-admin";

  save(record);
  return sanitize(record);
}

export function suspendTenant(id: string): PublicTenant | undefined {
  if (!canManageTenants()) throw new Error("Forbidden: only the global SupremeAI admin can suspend tenants");
  const record = getTenant(id);
  if (!record) return undefined;
  record.status = "suspended";
  record.updatedAt = nowIso();
  record.updatedBy = "global-admin";
  save(record);
  return sanitize(record);
}

export function activateTenant(id: string): PublicTenant | undefined {
  if (!canManageTenants()) throw new Error("Forbidden: only the global SupremeAI admin can activate tenants");
  const record = getTenant(id);
  if (!record) return undefined;
  record.status = "active";
  record.updatedAt = nowIso();
  record.updatedBy = "global-admin";
  save(record);
  return sanitize(record);
}

export function verifyTenantAdminToken(
  tenantId: string,
  adminToken: string
): TenantRecord | undefined {
  const record = getTenant(tenantId);
  if (!record || record.status !== "active") return undefined;
  if (!adminToken) return undefined;
  // #698: timing-safe token-hash comparison (no early-exit string equality).
  return hashEquals(digest(adminToken), record.adminTokenHash) ? record : undefined;
}

export function rotateTenantAdminToken(id: string): { tenant: PublicTenant; adminToken: string } {
  if (!canManageTenants()) throw new Error("Forbidden: only the global SupremeAI admin can rotate tenant tokens");
  const record = getTenant(id);
  if (!record) throw new Error(`Tenant not found: ${id}`);
  const adminToken = `tenant_admin_${randomBytes(32).toString("base64url")}`;
  record.adminTokenHash = digest(adminToken);
  record.updatedAt = nowIso();
  record.updatedBy = "global-admin";
  save(record);
  return { tenant: sanitize(record), adminToken };
}

export function resolveTenantAccess(
  tenant: TenantRecord | undefined,
  clientRole: "viewer" | "agent" | "admin",
  isGlobalAdmin: boolean
): TenantAccess {
  if (!tenant || tenant.status !== "active") {
    return { tenantId: GLOBAL_TENANT_ID, role: "viewer", type: "customer", isGlobalAdmin };
  }
  return {
    tenantId: tenant.id,
    role: isGlobalAdmin ? "admin" : clientRole,
    type: tenant.type,
    isGlobalAdmin,
  };
}