import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { env } from "../lib/env.js";
import type { UserRole } from "./auth.context.js";
import { roleRank } from "./auth.context.js";
import { isValidToolProfile, type ToolProfile } from "./tool-visibility.js";
import { createClientRegistryStore, type ClientRegistryStore, type PersistedClientRecord } from "./client-registry.store.js";

export type ClientRole = UserRole;
// #3663 (P0, root-cause): the guest default was "admin" (a pre-production
// shortcut) — every tokenless connect auto-registered a GLOBAL-ADMIN record
// with `scopes: ["*"]`, and the fail-open `?? "admin"` defaults in
// http_server.ts / viewerFallback amplified it into an unauthenticated
// global-admin context (46/88 registry rows admin, 20 carrying visitor-IP
// PII, kill-switch class tools reachable anonymously). Fail-closed now: the
// zero-credential front door keeps its documented public surface via the
// public_viewer mode + the public-safe bridge lane; privilege is granted
// ONLY by verified credential (env admin key, registry token, verified slot)
// or an explicit dashboard promotion.
export const DEFAULT_GUEST_ROLE: ClientRole = "viewer";
export type ClientProtocol = "streamable-http" | "sse" | "stdio" | "custom";
/**
 * #48: `suspended` is a first-class status — the fail-closed revocation state.
 * A suspended slot loses access on the immediate-next authorization check
 * (see policy/slot-verification.ts) without requiring a client reconnect.
 */
export type ClientStatus = "pending" | "active" | "suspended" | "revoked" | "expired";

export interface ExternalClient {
  id: string;
  /** Owner tenant. Каждый admin/customer видит только своих клиентов. */
  tenantId: string;
  name: string;
  provider: string;
  protocol: ClientProtocol;
  role: ClientRole;
  scopes: string[];
  /**
   * Tool Exposure Policy: curated discovery surface for this client.
   * Undefined = full RBAC surface (no profile-based list filtering).
   */
  toolProfile?: ToolProfile;
  createdAt: string;
  updatedAt: string;
  expiresAt?: string;
  lastSeenAt?: string;
  status: ClientStatus;
  /** #48: why the slot was suspended (revocation audit context). */
  suspendedReason?: string;
  /** #48: when the slot credential was last rotated (rotation audit). */
  rotatedAt?: string;
}

interface StoredClient extends ExternalClient { tokenHash: string; }

const clients = new Map<string, StoredClient>();
let registryStore = createClientRegistryStore(process.env.MCP_CLIENT_REGISTRY_FILE);
for (const record of registryStore.load()) clients.set(record.id, record as StoredClient);
const digest = (value: string) => createHash("sha256").update(value).digest("hex");

/**
 * Boot-time hydration (#1421). Runs AFTER the Infisical secrets pull so the
 * Upstash chain env (service env + vault imports) is fully populated, then:
 *  1. hydrates the in-memory map from the store (network-backed stores fetch
 *     the authoritative copy here),
 *  2. optionally seeds well-known infrastructure clients from
 *     `MCP_CLIENT_SEEDS_JSON` (declarative re-creation without manual
 *     register+approve round-trips) — array of
 *     `{id, name, role, token, provider?, protocol?, scopes?, tenantId?, status?, expiresAt?}`,
 *  3. logs which backend is active — LOUD warning when memory-only in
 *     production, because registrations would be lost on restart/redeploy.
 */
export async function initClientRegistry(): Promise<{ backend: string; loaded: number; seeded: number }> {
  let loaded = 0;
  try {
    const records = typeof registryStore.loadAsync === "function" ? await registryStore.loadAsync() : registryStore.load();
    clients.clear();
    for (const record of records) clients.set(record.id, record as StoredClient);
    loaded = records.length;
  } catch (err) {
    console.error(`[client-registry] hydration FAILED (${err instanceof Error ? err.message : String(err)}) — continuing with current snapshot`);
  }

  let seeded = 0;
  const seedsRaw = process.env.MCP_CLIENT_SEEDS_JSON;
  if (seedsRaw) {
    try {
      const seeds = JSON.parse(seedsRaw) as Array<Record<string, unknown>>;
      if (!Array.isArray(seeds)) throw new Error("MCP_CLIENT_SEEDS_JSON must be an array");
      for (const seed of seeds) {
        const id = typeof seed.id === "string" ? seed.id.trim() : "";
        const name = typeof seed.name === "string" ? seed.name : "";
        const token = typeof seed.token === "string" ? seed.token : "";
        const role = (typeof seed.role === "string" ? seed.role : "viewer") as ClientRole;
        if (!id || !name || !token || clients.has(id)) continue;
        const now = new Date().toISOString();
        clients.set(id, {
          id,
          tenantId: typeof seed.tenantId === "string" ? seed.tenantId : "tenant_default",
          name,
          provider: typeof seed.provider === "string" ? seed.provider : "generic",
          protocol: (typeof seed.protocol === "string" ? seed.protocol : "streamable-http") as ClientProtocol,
          role,
          scopes: Array.isArray(seed.scopes) ? (seed.scopes as string[]) : defaultClientScopes(role),
          toolProfile: isValidToolProfile(seed.toolProfile) ? seed.toolProfile : undefined,
          createdAt: now,
          updatedAt: now,
          expiresAt: typeof seed.expiresAt === "string" ? seed.expiresAt : undefined,
          status: (typeof seed.status === "string" ? seed.status : "active") as ClientStatus,
          tokenHash: digest(token),
        });
        seeded += 1;
      }
    } catch (err) {
      console.error(`[client-registry] seed parsing FAILED (${err instanceof Error ? err.message : String(err)})`);
    }
    if (seeded > 0) persist();
  }

  const backend = registryStore.backend || "memory";
  if (backend === "memory" && process.env.NODE_ENV === "production") {
    console.error("[client-registry] ⚠️  MEMORY-BACKED registry in production — client registrations WILL BE LOST on restart/redeploy. Provide Upstash chain env or set MCP_CLIENT_REGISTRY_FILE.");
  } else {
    console.error(`[client-registry] backend=${backend} clients=${clients.size}${seeded > 0 ? ` seeded=${seeded}` : ""}`);
  }
  return { backend, loaded, seeded };
}

/**
 * Timing-safe equality for token-hash comparison (#698). Both sides are
 * fixed-length sha256 hex digests; the length guard keeps timingSafeEqual from
 * throwing if a stored hash were ever corrupt/short.
 */
function digestEquals(a: string, b: string): boolean {
  const ab = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

const persist = () => registryStore.save([...clients.values()].map((client) => ({ ...client })) as PersistedClientRecord[]);

export function registerClient(
  name: string,
  role: ClientRole = "viewer",
  scopes: string[] = [],
  expiresAt?: string,
  provider = "generic",
  protocol: ClientProtocol = "streamable-http",
  tenantId = "tenant_default",
  customId?: string,
  toolProfile?: ToolProfile,
  /** #48: credential prefix — "slot_" marks server-issued slot credentials. */
  tokenPrefix = "mcp_"
) {
  if (toolProfile !== undefined && !isValidToolProfile(toolProfile)) {
    throw new Error("toolProfile must be 'chatgpt' or 'readonly'");
  }
  const token = `${tokenPrefix}${randomBytes(32).toString("base64url")}`;
  const now = new Date().toISOString();
  let id = customId?.trim();
  if (id) {
    if (clients.has(id)) {
      throw new Error(`Client ID '${id}' is already registered`);
    }
  } else {
    id = `client_${randomBytes(10).toString("hex")}`;
  }
  const client: StoredClient = { id, tenantId, name, provider, protocol, role, scopes, toolProfile, createdAt: now, updatedAt: now, expiresAt, status: "pending", tokenHash: digest(token) };
  clients.set(client.id, client);
  persist();
  return { client: sanitize(client), token };
}

export function deleteClient(id: string, tenantId?: string): boolean {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client) return false;
  const removed = clients.delete(id);
  persist();
  return removed;
}


export function resolveClient(token: string): ExternalClient | undefined {
  // #698: timing-safe token-hash comparison (no early-exit string equality).
  const tokenDigest = digest(token);
  const match = [...clients.values()].find((client) => digestEquals(client.tokenHash, tokenDigest));
  if (!match || match.status !== "active") return undefined;
  if (match.expiresAt && Date.parse(match.expiresAt) <= Date.now()) { match.status = "expired"; persist(); return undefined; }
  match.lastSeenAt = new Date().toISOString();
  match.updatedAt = match.lastSeenAt;
  persist();
  return sanitize(match);
}

/** Tenant isolation: global admin видит всех, tenant admin — только своих. */
export function listClients(tenantId?: string, includeRevoked = false) {
  const scope = tenantId ?? "*";
  return [...clients.values()]
    .filter((client) => (scope === "*" || client.tenantId === scope) && (includeRevoked || client.status !== "revoked"))
    .map(sanitize);
}

export function countClientsByTenant(tenantId: string): number {
  return [...clients.values()].filter((client) => client.tenantId === tenantId && client.status !== "revoked").length;
}

function assertTenantScope(client: StoredClient | undefined, tenantId?: string): void {
  if (!tenantId || tenantId === "*") return; // global admin
  if (!client) return;
  if (client.tenantId !== tenantId) throw new Error("Forbidden: client belongs to another tenant");
}

export function approveClient(id: string, tenantId?: string) {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client || client.status !== "pending") return undefined;
  client.status = "active";
  client.updatedAt = new Date().toISOString();
  persist();
  return sanitize(client);
}

export function changeClientRole(id: string, role: ClientRole, tenantId?: string) {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client || client.status === "revoked" || client.status === "expired") return undefined;
  client.role = role;
  client.scopes = defaultClientScopes(role);
  client.updatedAt = new Date().toISOString();
  persist();
  return sanitize(client);
}

export function changeClientProvider(id: string, provider: string, tenantId?: string) {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client) return undefined;
  client.provider = provider;
  client.updatedAt = new Date().toISOString();
  persist();
  return sanitize(client);
}

/**
 * Tool Exposure Policy: set (or clear with `null`) a client's curated
 * discovery profile. Visibility-only — the call path stays RBAC-gated.
 */
export function changeClientProfile(id: string, toolProfile: ToolProfile | null, tenantId?: string) {
  if (toolProfile !== null && !isValidToolProfile(toolProfile)) {
    throw new Error("toolProfile must be 'chatgpt', 'readonly', or null");
  }
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client || client.status === "revoked" || client.status === "expired") return undefined;
  client.toolProfile = toolProfile ?? undefined;
  client.updatedAt = new Date().toISOString();
  persist();
  return sanitize(client);
}

export function revokeClient(id: string, tenantId?: string) {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client) return false;
  client.status = "revoked";
  client.updatedAt = new Date().toISOString();
  persist();
  return true;
}

export function rotateClient(id: string, tenantId?: string) {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  // #48: rotation is allowed for active AND suspended slots — rotating a
  // suspended slot's credential is part of the incident-recovery workflow.
  if (!client || (client.status !== "active" && client.status !== "suspended")) return undefined;
  const token = `mcp_${randomBytes(32).toString("base64url")}`;
  client.tokenHash = digest(token);
  client.rotatedAt = new Date().toISOString();
  client.updatedAt = client.rotatedAt;
  persist();
  return { client: sanitize(client), token };
}

// ── #48 Verified Slot Architecture: server-side slot primitives ─────────────
// The registry IS the operational RBAC store. Slots are ordinary registry
// clients under the `slot_` id namespace (see policy/slot-verification.ts),
// but their lifecycle primitives are expressed here so every mutation keeps
// the single-writer + persist invariant.

/** #48: timing-safe check that a presented credential belongs to THIS client. */
export function clientMatchesToken(id: string, token: string): boolean {
  const client = clients.get(id);
  if (!client || !token) return false;
  return digestEquals(client.tokenHash, digest(token));
}

/**
 * #48: audit-safe credential fingerprint (first 12 hex chars of the stored
 * sha256 digest). NEVER log or transport the raw credential — the fingerprint
 * is enough to correlate audit rows and to detect rotation mid-session.
 */
export function clientCredentialId(id: string): string | undefined {
  const client = clients.get(id);
  return client ? client.tokenHash.slice(0, 12) : undefined;
}

/** #48: suspend a slot — fail-closed revocation state (distinct from revoke). */
export function suspendClient(id: string, reason = "suspended by administrator", tenantId?: string): ExternalClient | undefined {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client || client.status === "revoked") return undefined;
  client.status = "suspended";
  client.suspendedReason = reason;
  client.updatedAt = new Date().toISOString();
  persist();
  return sanitize(client);
}

/** #48: reinstate a suspended slot. */
export function reinstateClient(id: string, tenantId?: string): ExternalClient | undefined {
  const client = clients.get(id);
  assertTenantScope(client, tenantId);
  if (!client || client.status !== "suspended") return undefined;
  client.status = "active";
  client.suspendedReason = undefined;
  client.updatedAt = new Date().toISOString();
  persist();
  return sanitize(client);
}

/** #48 slot id namespace — declared here so the registry owns the prefix. */
export const SLOT_ID_PREFIX = "slot_";

/** #48: list slot records (`slot_` id namespace) for the dashboard/bridge. */
export function listSlotClients(tenantId?: string): ExternalClient[] {
  return listClients(tenantId, true).filter((client) => client.id.startsWith(SLOT_ID_PREFIX));
}

// ── #48: live operational-store verification (fail-closed) ──────────────────
// The in-memory map is kept current by this process (single writer, debounced
// flush). For network-backed stores every privileged authorization check may
// additionally require a FRESH read of the operational store; if that read
// fails, callers MUST deny (Invariant 5). Local (file/memory) stores are
// authoritative by construction — no freshness window applies.

let lastStoreVerificationAtMs = 0;

/** True when the registry is network-backed (staleness + fail-closed apply). */
export function isRegistryNetworkBacked(): boolean {
  return typeof registryStore.loadAsync === "function";
}

/** Epoch ms of the last SUCCESSFUL operational-store verification (0 = never). */
export function lastStoreVerificationAt(): number {
  return lastStoreVerificationAtMs;
}

/**
 * Re-read the registry from the operational store, merging by `updatedAt`
 * (local writes win ties so an unflushed local mutation is never clobbered
 * by a stale remote snapshot). Returns ok=false when the store could not be
 * verified — callers must treat that as fail-closed denial.
 */
export async function refreshRegistryFromStore(): Promise<{ ok: boolean; source: "local" | "store"; error?: string; clients: number }> {
  if (typeof registryStore.loadAsync !== "function") {
    return { ok: true, source: "local", clients: clients.size };
  }
  try {
    const records = await registryStore.loadAsync();
    for (const record of records) {
      const local = clients.get(record.id);
      if (!local || Date.parse(local.updatedAt) <= Date.parse(record.updatedAt)) {
        clients.set(record.id, record as StoredClient);
      }
    }
    lastStoreVerificationAtMs = Date.now();
    return { ok: true, source: "store", clients: records.length };
  } catch (err) {
    return { ok: false, source: "store", error: err instanceof Error ? err.message : String(err), clients: clients.size };
  }
}

export function hasClientRegistry() { return Boolean(env.mcpAdminKey); }
function sanitize(client: StoredClient): ExternalClient { const { tokenHash: _tokenHash, ...safe } = client; return safe; }

/**
 * Test-only: swap the registry store (Verified Slot fail-closed suite, #48).
 * Used to simulate an unreachable operational store without network calls
 * against real infrastructure. Never call from production paths.
 */
export function __setRegistryStoreForTests(store: ClientRegistryStore): void {
  registryStore = store;
}

// #110: 6-tier scope matrix. Viewer tiers get read-only scope sets; the
// repo tiers additionally carry repo-read scopes that the GitHub tools
// middleware (github.tools.ts assertRepoReadAccess) enforces against the
// satellite allowlist / full-repo boundary.
// বাংলা মন্তব্য: ৬-স্তর স্কোপ ম্যাট্রিক্স — রিড-অনলি স্তরগুলোতে repo-read স্কোপ, GitHub টুল মিডলওয়্যার সেগুলো স্যাটেলাইট allowlist-এর সাথে আচরণ করে।
export function defaultClientScopes(role: ClientRole): string[] {
  if (role === "viewer") return ["health:read", "system:read", "audit:read"];
  if (role === "restricted_viewer")
    return ["health:read", "system:read", "audit:read", "repos:satellite:read"];
  if (role === "repo_viewer")
    return ["health:read", "system:read", "audit:read", "repos:satellite:read", "repos:all:read"];
  if (role === "agent")
    return ["health:read", "system:read", "audit:read", "repos:satellite:read", "repos:all:read", "tools:execute", "approvals:request"];
  // admin ও supremeadmin: সম্পূর্ণ অ্যাক্সেস (omni scope)।
  return ["*"];
}

/**
 * #110: rank-ladder role check (replaces the flat 3-tier boolean chain).
 * Legacy required tiers map onto the rank scale (viewer=0, agent=3, admin=4)
 * so existing call sites keep identical semantics; the new read-only tiers
 * (restricted_viewer=1, repo_viewer=2) pass legacy-"viewer" requirements but
 * never legacy-"agent"/"admin" ones — read-only stays read-only.
 * বাংলা মন্তব্য: র‍্যাঙ্ক-ল্যাডার চেক — নতুন রিড-অনলি স্তরগুলো viewer-স্তরের কাজ পারে কিন্তু agent/admin-স্তরের নয়।
 */
export function roleAllows(role: ClientRole, required: "viewer" | "agent" | "admin") {
  const requiredRank = required === "viewer" ? 0 : required === "agent" ? 3 : 4;
  return roleRank(role) >= requiredRank;
}

export function scopeAllows(scopes: string[], required: string) { return scopes.includes("*") || scopes.includes(required); }

export function getClient(id: string): ExternalClient | undefined {
  const match = clients.get(id);
  return match ? sanitize(match) : undefined;
}

/**
 * Dynamic auto-registration for no-auth AI clients (#1767).
 * When an external AI connects via No Auth, this creates or reuses an active guest record
 * in the database registry so it can be viewed and upgraded dynamically by admins.
 *
 * AUDIT-FIX (#1787 Gap 3): আগে শুধু preferredId (IP-based `guest_<provider>_<ip>`)
 * দিয়ে duplicate check করা হতো। কিন্তু দুটো আলাদা IP থেকে একই name দিয়ে
 * দুটো guest client register হতে পারত — যা admin-এর জন্য বিভ্রান্তিকর। এখন
 * name-based duplicate check যোগ করা হয়েছে: যদি একই name-এ কোনো existing
 * client থাকে, সেটি reuse করা হয় (preferredId যাই হোক না কেন)।
 */
export function getOrCreateGuestClient(
  preferredId: string,
  name: string,
  provider = "generic",
  protocol: ClientProtocol = "sse",
  tenantId = "tenant_default",
  toolProfile?: ToolProfile
): ExternalClient {
  // AUDIT-FIX (#1787 Gap 3): name-based duplicate check.
  // প্রথমে preferredId দিয়ে দেখি (fast path)। না থাকলে name দিয়ে দেখি —
  // যদি name match করে, সেই existing client reuse করি (id যাই হোক)।
  const existingById = clients.get(preferredId);
  if (existingById) {
    const now = new Date().toISOString();
    existingById.lastSeenAt = now;
    existingById.updatedAt = now;
    // #2588: the same AI often reconnects over a DIFFERENT transport (e.g. an
    // /sse guest later handshaking /mcp, or vice versa). The registry is the
    // operational truth for the admin dashboard, so the stored protocol (and
    // a now-known provider label) must follow the LATEST connection instead
    // of staying frozen at the first one.
    if (existingById.protocol !== protocol) existingById.protocol = protocol;
    if (provider !== "generic" && existingById.provider !== provider) existingById.provider = provider;
    // Pre-production: refresh existing unprivileged guest clients to current defaultGuestRole
    if (existingById.id.startsWith("guest_") && existingById.role !== DEFAULT_GUEST_ROLE) {
      existingById.role = DEFAULT_GUEST_ROLE;
      existingById.scopes = defaultClientScopes(DEFAULT_GUEST_ROLE);
    }
    // Tool Exposure Policy: derive the default profile once, never clobber an
    // explicit admin-set profile on reconnects.
    if (toolProfile && !existingById.toolProfile) existingById.toolProfile = toolProfile;
    persist();
    return sanitize(existingById);
  }

  // AUDIT-FIX (#1787): name-based lookup — একই name-এ আরেকটা client থাকলে
  // সেটি reuse করি, নতুন entry তৈরি করি না। এতে admin dashboard-এ একই
  // AI এর জন্য duplicate rows দেখা যাবে না।
  const existingByName = [...clients.values()].find(
    (c) => c.name === name && c.tenantId === tenantId
  );
  if (existingByName) {
    const now = new Date().toISOString();
    existingByName.lastSeenAt = now;
    existingByName.updatedAt = now;
    // #2588: keep protocol/provider current on the name-reuse path too.
    if (existingByName.protocol !== protocol) existingByName.protocol = protocol;
    if (provider !== "generic" && existingByName.provider !== provider) existingByName.provider = provider;
    // Pre-production: refresh existing unprivileged guest clients to current defaultGuestRole
    if (existingByName.id.startsWith("guest_") && existingByName.role !== DEFAULT_GUEST_ROLE) {
      existingByName.role = DEFAULT_GUEST_ROLE;
      existingByName.scopes = defaultClientScopes(DEFAULT_GUEST_ROLE);
    }
    // Tool Exposure Policy: same derive-once rule on the name-reuse path.
    if (toolProfile && !existingByName.toolProfile) existingByName.toolProfile = toolProfile;
    persist();
    return sanitize(existingByName);
  }

  // AUDIT-FIX (#2030): Name auto-increment — if "z.ai" is taken, try "z.ai-2", "z.ai-3", etc.
  // This lets agents connect with a simple base name and get a unique identity automatically.
  let finalName = name;
  let counter = 2;
  while ([...clients.values()].some((c) => c.name === finalName && c.tenantId === tenantId)) {
    finalName = `${name}-${counter}`;
    counter++;
  }

  // #3663 (P0 root-cause): single SSOT for the guest default — the local
  // "admin" duplicate here drifted against the reconnect-refresh paths that
  // read DEFAULT_GUEST_ROLE. Guests are born viewer; privilege requires a
  // verified credential or an explicit dashboard promotion.
  const defaultGuestRole: ClientRole = DEFAULT_GUEST_ROLE;

  const token = `mcp_${randomBytes(32).toString("base64url")}`;
  const now = new Date().toISOString();
  const client: StoredClient = {
    id: preferredId,
    tenantId,
    name: finalName,  // AUDIT-FIX (#2030): use auto-incremented name
    provider,
    protocol,
    role: defaultGuestRole,
    scopes: defaultClientScopes(defaultGuestRole),
    toolProfile, // Tool Exposure Policy: provider-derived default (chatgpt → curated surface)
    createdAt: now,
    updatedAt: now,
    status: "active",
    tokenHash: digest(token),
  };
  clients.set(client.id, client);
  persist();
  return sanitize(client);
}
