import type { IncomingMessage } from "node:http";
import {
  approveClient,
  clientCredentialId,
  clientMatchesToken,
  defaultClientScopes,
  DEFAULT_GUEST_ROLE,
  getClient,
  isRegistryNetworkBacked,
  lastStoreVerificationAt,
  refreshRegistryFromStore,
  registerClient,
  reinstateClient,
  revokeClient,
  rotateClient,
  suspendClient,
  SLOT_ID_PREFIX,
  type ClientProtocol,
  type ExternalClient,
} from "./client-registry.js";
import type { UserRole } from "./auth.context.js";
import { roleRank } from "./auth.context.js";
import { autoRegisterGuestClient, isValidClientName, namedClientFromUrl } from "./auto-register.js";
import { recordSlotAudit } from "./slot-audit.js";

/**
 * Verified Slot Architecture (issue #48).
 *
 * Core tenet: **Stable Identity + Verified Authentication + Live Authorization
 * + Immediate-Next-Check Revocation.**
 *
 *   • Slot      — pre-provisioned, persistent, unique identity in the database
 *                 (`slot_<name>` registry records). No auto-promotion: a slot
 *                 starts `pending` and an administrator must approve it.
 *   • Credential— server-issued secret bound to the slot. The URL alone is
 *                 NEVER authentication: an anonymous caller presenting a slot
 *                 URL gets the strict `viewer` fallback, not the slot's role.
 *   • Live AuthZ— every privileged re-check reads the operational registry
 *                 (role, status, scopes) and verifies the store is reachable.
 *   • Revocation— `suspended` / demotion terminates access on the immediate-
 *                 next authorization check — no client reconnect required.
 *   • Fail-     — if the operational store cannot be verified during a
 *     Closed       privileged operation, execution is strictly DENIED.
 */

/** URL path that carries the slot name (`/agents/<slot>/sse|mcp`). */
const AGENTS_PATH_RE = /^\/agents\/([^/]+)\/(sse|mcp)$/;

export type SlotStatus = ExternalClient["status"];

export type SlotDenialReason =
  | "slot-unknown"
  | "slot-not-approved"
  | "slot-suspended"
  | "slot-revoked"
  | "slot-expired"
  | "slot-credential-missing"
  | "slot-credential-mismatch"
  | "slot-credential-rotated"
  | "slot-store-unreachable";

export interface SlotAuthorizationResult {
  allowed: boolean;
  reason?: SlotDenialReason;
  role?: UserRole;
  scopes?: string[];
  slot?: ExternalClient;
  /** "local" = file/memory store is authoritative; "store" = fresh store read. */
  source?: "local" | "store";
}

export interface SlotSession {
  /** Observability record (guest) or the verified slot record. */
  client?: ExternalClient;
  role: UserRole;
  authenticated: boolean;
  scopes: string[];
  /** Set when a slot identity is in play (verified OR attempted). */
  slotId?: string;
  /** True ONLY when the slot credential verified against the live registry. */
  slotVerified: boolean;
  /** Audit-safe fingerprint of the presented credential (never the raw one). */
  credentialId?: string;
  /** Why an unauthenticated fallback was applied (audit context). */
  fallbackReason?: SlotDenialReason | "anonymous";
  tenantId: string;
}

/** Canonical slot id for a name: `slot_<name>`. */
export function slotIdFor(name: string): string {
  return `${SLOT_ID_PREFIX}${name}`;
}

export function isSlotId(id: string): boolean {
  return id.startsWith(SLOT_ID_PREFIX);
}

/**
 * Extract the slot name from the request URL — `?client=<name>` (the #110
 * named-client surface) or the `/agents/<name>/sse|mcp` path form. The value
 * is sanitized exactly like `?client=` so it can never smuggle path
 * separators or registry-key collisions.
 */
export function slotNameFromRequest(rawUrl: string | undefined | null): string | null {
  if (!rawUrl) return null;
  const path = rawUrl.split("?")[0] ?? "";
  const agentsMatch = AGENTS_PATH_RE.exec(path);
  if (agentsMatch && isValidClientName(agentsMatch[1] ?? "")) {
    return agentsMatch[1] as string;
  }
  const named = namedClientFromUrl(rawUrl);
  return named ? named.name : null;
}

/**
 * Resolve the registry id for a presented slot name: the credential-bound
 * `slot_<name>` record wins; otherwise the legacy `named_<name>` observability
 * record (kept for the dashboard — never grants privilege by itself).
 */
export function slotIdFromName(name: string): string {
  const slotId = slotIdFor(name);
  return getClient(slotId) ? slotId : `named_${name}`;
}

/**
 * Provision a pre-registered, credential-bound slot (#48 Invariant 1).
 * The slot is created `pending` — an administrator must explicitly approve
 * it before any credential can authenticate (no auto-elevation, guardrail 1).
 */
export function provisionSlot(input: {
  name: string;
  role: UserRole;
  tenantId?: string;
  scopes?: string[];
  provider?: string;
  protocol?: ClientProtocol;
}): { slot: ExternalClient; credential: string } {
  if (!isValidClientName(input.name)) {
    throw new Error("slot name must match ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$");
  }
  const result = registerClient(
    input.name,
    input.role,
    input.scopes ?? defaultClientScopes(input.role),
    undefined,
    input.provider ?? "slot",
    input.protocol ?? "streamable-http",
    input.tenantId ?? "tenant_default",
    slotIdFor(input.name),
    undefined,
    "slot_",
  );
  return { slot: result.client, credential: result.token };
}

/** Approve a pending slot (administrator action — no auto-elevation). */
export function approveSlot(id: string, tenantId?: string): ExternalClient | undefined {
  return approveClient(id, tenantId);
}

/** Suspend a slot — fails closed on the immediate-next authorization check. */
export function suspendSlot(id: string, reason?: string, tenantId?: string): ExternalClient | undefined {
  return suspendClient(id, reason, tenantId);
}

/** Reinstate a suspended slot. */
export function reinstateSlot(id: string, tenantId?: string): ExternalClient | undefined {
  return reinstateClient(id, tenantId);
}

/** Revoke a slot permanently (terminal state). */
export function revokeSlot(id: string, tenantId?: string): boolean {
  return revokeClient(id, tenantId);
}

/**
 * Rotate a slot credential — the old credential is invalidated IMMEDIATELY
 * (hash replaced in-place), the new one is returned exactly once.
 */
export function rotateSlotCredential(id: string, tenantId?: string): { slot: ExternalClient; credential: string } | undefined {
  const result = rotateClient(id, tenantId);
  return result ? { slot: result.client, credential: result.token } : undefined;
}

/** Live slot record (sanitized — never carries the credential or its hash). */
export function getSlot(id: string): ExternalClient | undefined {
  return getClient(id);
}

/** Rank helper for status surfaces. Returns -1 for unknown slots (fail-closed). */
export function slotRank(id: string): number {
  const slot = getClient(id);
  return slot ? roleRank(slot.role) : -1;
}

function deny(reason: SlotDenialReason, slot?: ExternalClient): SlotAuthorizationResult {
  return { allowed: false, reason, slot };
}

/**
 * Freshness window for network-backed store re-verification (#48 Invariants
 * 3/5). A privileged check trusts the in-process registry only while the last
 * successful operational-store read is younger than this window; otherwise it
 * re-reads the store and fails CLOSED when the read fails.
 */
export function slotStoreMaxStalenessMs(): number {
  const raw = Number(process.env.MCP_SLOT_STORE_MAX_STALENESS_MS ?? "");
  return Number.isFinite(raw) && raw > 0 ? raw : 15_000;
}

/**
 * LIVE authorization check for a slot (#48 Invariants 3, 4, 5).
 *
 * Called on every privileged re-check (tool-call gate, /messages and session
 * refresh). Never throws: store outages surface as `slot-store-unreachable`
 * denials (fail-closed) and every decision is written to the immutable audit
 * trail (#48 Invariant 6).
 */
export async function assertSlotAuthorization(
  slotId: string,
  presentedCredentialId?: string,
  context?: { tool?: string; operation?: "tool-call" | "message" | "connect"; clientIp?: string; tenantId?: string },
): Promise<SlotAuthorizationResult> {
  const operation = context?.operation ?? "tool-call";
  let slot = getClient(slotId);
  if (!slot) {
    recordSlotAudit({ slotId, credentialId: presentedCredentialId, operation, tool: context?.tool, outcome: "denied", reason: "slot-unknown", clientIp: context?.clientIp, tenantId: context?.tenantId });
    return deny("slot-unknown");
  }

  // Invariant 5 — the operational store must be verifiable for privileged
  // checks. Network-backed registries enforce a freshness window; local
  // (file/memory) stores are authoritative by construction.
  let source: "local" | "store" = "local";
  if (isSlotId(slotId) && isRegistryNetworkBacked()) {
    source = "store";
    if (Date.now() - lastStoreVerificationAt() > slotStoreMaxStalenessMs()) {
      const refresh = await refreshRegistryFromStore();
      if (!refresh.ok) {
        recordSlotAudit({ slotId, credentialId: presentedCredentialId, role: slot.role, operation, tool: context?.tool, outcome: "denied", reason: "slot-store-unreachable", clientIp: context?.clientIp, tenantId: slot.tenantId });
        return deny("slot-store-unreachable", slot);
      }
      // refreshRegistryFromStore merges by updatedAt — re-read the possibly
      // remote-updated record before evaluating status.
      slot = getClient(slotId) ?? slot;
      if (!slot) {
        recordSlotAudit({ slotId, credentialId: presentedCredentialId, operation, tool: context?.tool, outcome: "denied", reason: "slot-unknown", clientIp: context?.clientIp, tenantId: context?.tenantId });
        return deny("slot-unknown");
      }
    }
  }

  // Invariant 4 — suspension/demotion terminates on the immediate-next check.
  const statusReason: SlotDenialReason | null =
    slot.status === "suspended" ? "slot-suspended"
    : slot.status === "revoked" ? "slot-revoked"
    : slot.status === "pending" ? "slot-not-approved"
    : slot.status === "expired" ? "slot-expired"
    : null;
  const expired = Boolean(slot.expiresAt && Date.parse(slot.expiresAt) <= Date.now());
  const denialReason = statusReason ?? (expired ? "slot-expired" : null);
  if (denialReason) {
    recordSlotAudit({ slotId, credentialId: presentedCredentialId, role: slot.role, operation, tool: context?.tool, outcome: "denied", reason: denialReason, clientIp: context?.clientIp, tenantId: slot.tenantId });
    return deny(denialReason, slot);
  }

  // Invariant 2 — the presented credential must still be the slot's CURRENT
  // credential. Rotation replaces the hash, so a rotated-away credential is
  // rejected on the very next check (no reconnect needed).
  if (presentedCredentialId) {
    const liveCredentialId = clientCredentialId(slotId);
    if (liveCredentialId !== presentedCredentialId) {
      recordSlotAudit({ slotId, credentialId: presentedCredentialId, role: slot.role, operation, tool: context?.tool, outcome: "denied", reason: "slot-credential-rotated", clientIp: context?.clientIp, tenantId: slot.tenantId });
      return deny("slot-credential-rotated", slot);
    }
  }

  recordSlotAudit({ slotId, credentialId: clientCredentialId(slotId), role: slot.role, operation, tool: context?.tool, outcome: "allowed", clientIp: context?.clientIp, tenantId: slot.tenantId });
  return { allowed: true, role: slot.role, scopes: slot.scopes, slot, source };
}

/**
 * Slot-bound session resolution for a transport request (#48 Invariants 1+2).
 *
 *  • A resolved Bearer credential (env key or registry client token) keeps
 *    full existing behavior — it IS a verified credential.
 *  • A slot URL WITHOUT a verified credential degrades to the strict
 *    `viewer` fallback (never the slot's stored role): the URL is identity,
 *    never authentication (security correction #2 in the issue).
 *  • Anonymous callers still get an observability record (dashboard
 *    visibility, #1767/#2588 behavior) — with `viewer` role only.
 */
export async function resolveSlotSession(
  req: IncomingMessage,
  base: { client?: ExternalClient; role: UserRole | null; tenantId: string; protocol?: ClientProtocol },
): Promise<SlotSession> {
  const clientIp = clientIpOf(req);
  const protocol = base.protocol ?? "sse";

  // Path A — a Bearer credential already resolved a principal (env key or
  // registry token). resolveClient already ran the timing-safe hash + live
  // status/expiry check, so this request is credential-verified.
  if (base.client || base.role !== null) {
    const credentialId = base.client ? clientCredentialId(base.client.id) : undefined;
    recordSlotAudit({
      slotId: base.client?.id,
      credentialId,
      role: base.role ?? "viewer",
      operation: "connect",
      outcome: "allowed",
      clientIp,
      tenantId: base.tenantId,
    });
    return {
      client: base.client,
      role: base.role ?? "viewer",
      authenticated: true,
      // Env-key callers (no registry record) get the role's default scopes —
      // registry clients carry their live scopes from the operational store.
      scopes: base.client?.scopes ?? defaultClientScopes(base.role ?? "viewer"),
      slotId: base.client?.id,
      slotVerified: Boolean(base.client),
      credentialId,
      tenantId: base.tenantId,
    };
  }

  // Path B — anonymous: a slot name may still be presented in the URL.
  const name = slotNameFromRequest(req.url);
  if (name) {
    const slotId = slotIdFromName(name);
    const credential = slotCredentialFromRequest(req);
    const slot = getClient(slotId);

    if (slot && credential && clientMatchesToken(slotId, credential)) {
      // Credential matches — evaluate live status too (pending/suspended/
      // revoked/expired all deny; the URL alone never authenticates).
      const verdict = await assertSlotAuthorization(slotId, clientCredentialId(slotId), { operation: "connect", clientIp });
      if (verdict.allowed && verdict.slot) {
        return {
          client: verdict.slot,
          role: verdict.role ?? "viewer",
          authenticated: true,
          scopes: verdict.scopes ?? [],
          slotId,
          slotVerified: true,
          credentialId: clientCredentialId(slotId),
          tenantId: verdict.slot.tenantId,
        };
      }
      return viewerFallback(req, base.tenantId, protocol, verdict.reason ?? "slot-credential-mismatch", clientIp, slotId);
    }

    // No / invalid credential: strict fallback. The named observability
    // record is preserved for the dashboard, but its stored role is NEVER
    // adopted for an unverified caller (this was the URL-hijack hole).
    const reason: SlotDenialReason = !credential ? "slot-credential-missing" : slot ? "slot-credential-mismatch" : "slot-unknown";
    return viewerFallback(req, base.tenantId, protocol, reason, clientIp, slotId);
  }

  // Fully anonymous, no slot name — read-only observability guest (#1767).
  return viewerFallback(req, base.tenantId, protocol, "anonymous", clientIp);
}

/**
 * The credential a slot presents at the transport layer. Query-string
 * credentials are deliberately NOT accepted (they leak into proxy logs,
 * browser history and Referer headers — see index.ts resolveRole). Header
 * only: `x-mcp-slot-token` or `Authorization: Bearer <slot credential>`.
 */
export function slotCredentialFromRequest(req: IncomingMessage): string | undefined {
  const header = req.headers["x-mcp-slot-token"];
  if (typeof header === "string" && header.trim()) return header.trim();
  const auth = req.headers.authorization ?? "";
  const match = /^Bearer\s+(.+)$/i.exec(auth);
  if (match) return match[1]?.trim();
  return undefined;
}

function clientIpOf(req: IncomingMessage): string {
  const forwarded = req.headers["x-forwarded-for"];
  if (typeof forwarded === "string" && forwarded.trim()) return forwarded.split(",")[0].trim();
  return req.socket?.remoteAddress ?? "unknown";
}

/**
 * URL connection fallback.
 * TEMPORARY (PRE-PRODUCTION): Until the system is fully ready for production,
 * URL connections default to "admin" role so AI agents connecting via URL
 * (Claude, Cursor, Antigravity, etc.) can execute tasks immediately.
 * প্রোডাকশনের জন্য সম্পূর্ণ প্রস্তুত হওয়ার পূর্ব পর্যন্ত এটি "admin" রোলে থাকবে;
 * প্রোডাকশন রেডি হলে পুনরায় কঠোর "viewer" রোলে রোলব্যাক করা হবে।
 */
function viewerFallback(
  req: IncomingMessage,
  tenantId: string,
  protocol: ClientProtocol,
  reason: SlotDenialReason | "anonymous",
  clientIp: string,
  slotId?: string,
): SlotSession {
  const guest = autoRegisterGuestClient(req, protocol, tenantId);
  recordSlotAudit({ slotId, operation: "connect", outcome: "denied", reason, clientIp, tenantId });
  // #3663 (P0 root-cause): this fallback previously returned role "admin"
  // with authenticated:true and ["*"] scopes — the literal opposite of its
  // own name and of the #48 law it implements ("the URL alone is NEVER
  // authentication"). The session now carries the DEFAULT_GUEST_ROLE
  // (viewer) with authenticated:false, so an unverified caller lands in the
  // public_viewer surface: the zero-credential bridge lane stays open, and
  // every privileged tool/registry path denies by default.
  const fallbackRole: UserRole = DEFAULT_GUEST_ROLE;
  return {
    client: guest,
    role: fallbackRole,
    authenticated: false,
    scopes: defaultClientScopes(fallbackRole),
    slotId,
    slotVerified: false,
    fallbackReason: reason,
    tenantId,
  };
}
