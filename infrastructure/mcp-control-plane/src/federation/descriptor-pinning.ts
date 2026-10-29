import { createHash } from "node:crypto";

/**
 * Remote-MCP tool-descriptor pinning (#1712 — rug-pull detection, fail-closed).
 *
 * Trust model before this module: approval-time only — a remote server approved
 * once under trustLevel X could silently mutate tool descriptors (descriptions,
 * input schemas) at call time. In the federation that is a cross-tenant
 * injection surface (Invariant Labs "tool poisoning", MCP discussion #348;
 * 2025–2026 rug-pull incident record).
 *
 * Model after this module: every discovery pins the SHA-256 of each tool
 * descriptor over the canonical tuple (name, description, inputSchema).
 * `remote.call` re-verifies the live tool surface against the approved pins
 * (TTL-bounded re-fetch) and FAILS CLOSED on any drift: typed error
 * `tool_descriptor_mutated`, server quarantined, slot-audit entry recorded.
 * Adopting changed descriptors requires an explicit, audited re-approval —
 * never silent, never automatic.
 *
 * PRIVACY (never-do): mutation events and status surfaces carry HASHES and
 * versions only — never full tool descriptions.
 */

export interface PinInputTool { name: string; description?: string; inputSchema: Record<string, unknown>; }

export interface DescriptorPin {
  toolName: string;
  /** Hash the operator approved. Undefined only for unapproved additions. */
  approvedHash?: string;
  /** Observed-but-not-approved hash (changed or added tool). */
  pendingHash?: string;
  version: number;
  pinnedAt: string;
  updatedAt: string;
  removedAt?: string;
}

export type DescriptorMutationKind = "changed" | "removed" | "added" | "reappeared" | "reapproved";

export interface DescriptorMutationEvent {
  ts: string;
  serverId: string;
  toolName: string;
  kind: DescriptorMutationKind;
  /** Hashes only — never descriptions. */
  approvedHash?: string;
  observedHash?: string;
  version: number;
}

export interface DescriptorDiff {
  toolName: string;
  kind: Exclude<DescriptorMutationKind, "reapproved">;
  approvedHash?: string;
  observedHash?: string;
}

interface ServerPinState {
  serverId: string;
  pins: Map<string, DescriptorPin>;
  events: DescriptorMutationEvent[];
  lastVerifiedAt?: string;
}

const pinStore = new Map<string, ServerPinState>();
const verifiedAt = new Map<string, string>();
const MAX_EVENTS_PER_SERVER = 50;

/** Deterministic JSON: object keys sorted recursively — stable across runs. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value ?? null);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v !== undefined).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
}

/** SHA-256 over the canonical tuple (name, description, inputSchema). */
export function descriptorHash(tool: PinInputTool): string {
  return createHash("sha256").update(canonicalJson([tool.name, tool.description ?? null, tool.inputSchema])).digest("hex");
}

function stateFor(serverId: string): ServerPinState {
  let state = pinStore.get(serverId);
  if (!state) { state = { serverId, pins: new Map(), events: [] }; pinStore.set(serverId, state); }
  return state;
}

function record(state: ServerPinState, event: Omit<DescriptorMutationEvent, "ts" | "serverId">): void {
  state.events.push({ ts: new Date().toISOString(), serverId: state.serverId, ...event });
  while (state.events.length > MAX_EVENTS_PER_SERVER) state.events.shift();
}

/**
 * Pin the observed tool surface at discovery time. First observation of a
 * server = approved baseline. Later observations NEVER auto-adopt changes:
 * changed/added tools become pending, removed tools keep a tombstone — every
 * one is a recorded drift event (hashes only). Call-time verification uses
 * these pins, so drift blocks execution until explicit re-approval.
 */
export function pinDescriptors(serverId: string, tools: PinInputTool[]): { pinned: number; mutations: DescriptorMutationEvent[] } {
  const state = stateFor(serverId);
  const firstPin = state.pins.size === 0;
  const observed = new Map(tools.map((tool) => [tool.name, tool]));
  const mutations: DescriptorMutationEvent[] = [];
  const now = new Date().toISOString();

  for (const tool of tools) {
    const hash = descriptorHash(tool);
    const pin = state.pins.get(tool.name);
    if (!pin) {
      state.pins.set(tool.name, firstPin
        ? { toolName: tool.name, approvedHash: hash, version: 1, pinnedAt: now, updatedAt: now }
        : { toolName: tool.name, pendingHash: hash, version: 1, pinnedAt: now, updatedAt: now });
      const event: DescriptorMutationEvent = { ts: now, serverId, toolName: tool.name, kind: "added", observedHash: hash, version: 1 };
      if (!firstPin) { record(state, event); mutations.push(event); }
      continue;
    }
    pin.updatedAt = now;
    if (pin.approvedHash && hash === pin.approvedHash) {
      if (pin.removedAt) {
        // Re-observed after removal: stays fail-closed until explicit re-approval.
        // pendingHash marks "present again, identical content" so re-approval
        // can distinguish consent-to-return from consent-to-absence.
        pin.pendingHash = hash;
        pin.version += 1;
        const event: DescriptorMutationEvent = { ts: now, serverId, toolName: tool.name, kind: "reappeared", approvedHash: pin.approvedHash, observedHash: hash, version: pin.version };
        record(state, event); mutations.push(event);
      } else {
        pin.pendingHash = undefined;
      }
      continue;
    }
    pin.pendingHash = hash;
    pin.version += 1;
    const event: DescriptorMutationEvent = { ts: now, serverId, toolName: tool.name, kind: "changed", approvedHash: pin.approvedHash, observedHash: hash, version: pin.version };
    record(state, event); mutations.push(event);
  }

  for (const pin of state.pins.values()) {
    if (observed.has(pin.toolName) || pin.removedAt) continue;
    pin.removedAt = now;
    pin.version += 1;
    const event: DescriptorMutationEvent = { ts: now, serverId, toolName: pin.toolName, kind: "removed", approvedHash: pin.approvedHash, version: pin.version };
    record(state, event); mutations.push(event);
  }

  return { pinned: state.pins.size, mutations };
}

/**
 * Call-time verification: compare a freshly fetched tool surface against the
 * approved pins. ANY drift (changed / removed / unapproved addition /
 * reappeared) fails the whole server — one mutated descriptor is a
 * cross-tenant injection surface, not a per-tool concern.
 */
export function verifyDescriptorsForCall(serverId: string, observedTools: PinInputTool[]): { ok: true } | { ok: false; reason: string; diffs: DescriptorDiff[] } {
  const state = pinStore.get(serverId);
  if (!state || state.pins.size === 0) return { ok: false, reason: "no_approved_pins", diffs: [] };
  const observed = new Map(observedTools.map((tool) => [tool.name, tool]));
  const diffs: DescriptorDiff[] = [];

  for (const pin of state.pins.values()) {
    if (pin.removedAt) { diffs.push({ toolName: pin.toolName, kind: "removed", approvedHash: pin.approvedHash }); continue; }
    const tool = observed.get(pin.toolName);
    if (!tool) { diffs.push({ toolName: pin.toolName, kind: "removed", approvedHash: pin.approvedHash }); continue; }
    const hash = descriptorHash(tool);
    if (!pin.approvedHash) { diffs.push({ toolName: pin.toolName, kind: "added", observedHash: hash }); continue; }
    if (hash !== pin.approvedHash) diffs.push({ toolName: pin.toolName, kind: "changed", approvedHash: pin.approvedHash, observedHash: hash });
  }
  for (const tool of observedTools) {
    if (!state.pins.has(tool.name)) diffs.push({ toolName: tool.name, kind: "added", observedHash: descriptorHash(tool) });
  }

  if (diffs.length > 0) return { ok: false, reason: "tool_descriptor_mutated", diffs };
  return { ok: true };
}

/** Explicit, audited adoption of the pending surface — the ONLY path back. */
export function reapproveDescriptors(serverId: string): { approved: number; events: DescriptorMutationEvent[] } {
  const state = pinStore.get(serverId);
  if (!state) return { approved: 0, events: [] };
  const now = new Date().toISOString();
  const events: DescriptorMutationEvent[] = [];
  for (const [name, pin] of [...state.pins.entries()]) {
    if (pin.removedAt && !pin.pendingHash) { state.pins.delete(name); continue; } // consent to absence
    if (pin.removedAt) pin.removedAt = undefined; // consent to return (content adopted below)
    if (!pin.pendingHash && pin.approvedHash) continue;
    pin.approvedHash = pin.pendingHash ?? pin.approvedHash;
    pin.pendingHash = undefined;
    pin.version += 1;
    pin.updatedAt = now;
    const event: DescriptorMutationEvent = { ts: now, serverId, toolName: name, kind: "reapproved", approvedHash: pin.approvedHash, version: pin.version };
    record(state, event); events.push(event);
  }
  verifiedAt.delete(serverId); // force a fresh re-verification on the next call
  return { approved: events.length, events };
}

/** Observable drift for client_list_mcp_servers — hashes + versions only. */
export function getDescriptorStatus(serverId: string): {
  serverId: string; pinnedTools: number; pendingReapproval: boolean; lastVerifiedAt?: string;
  pins: Array<{ tool: string; hash?: string; version: number; pending?: string; removed?: boolean }>;
  recentEvents: DescriptorMutationEvent[];
} {
  const state = pinStore.get(serverId);
  if (!state) return { serverId, pinnedTools: 0, pendingReapproval: false, pins: [], recentEvents: [] };
  return {
    serverId,
    pinnedTools: state.pins.size,
    pendingReapproval: [...state.pins.values()].some((pin) => Boolean(pin.pendingHash || pin.removedAt || !pin.approvedHash)),
    lastVerifiedAt: state.lastVerifiedAt,
    pins: [...state.pins.values()].map((pin) => ({
      tool: pin.toolName,
      hash: pin.approvedHash?.slice(0, 12),
      version: pin.version,
      pending: pin.pendingHash?.slice(0, 12),
      removed: pin.removedAt ? true : undefined,
    })),
    recentEvents: state.events.slice(-5),
  };
}

/** TTL-bounded re-verification clock for remote.call (default 5 minutes). */
export function defaultReverifyTtlMs(): number {
  const raw = Number(process.env.SUPREMEAI_DESCRIPTOR_REVERIFY_TTL_MS ?? "");
  return Number.isFinite(raw) && raw > 0 ? raw : 300_000;
}

export function markVerified(serverId: string): void {
  const now = new Date().toISOString();
  verifiedAt.set(serverId, now);
  const state = pinStore.get(serverId);
  if (state) state.lastVerifiedAt = now;
}

export function isVerificationFresh(serverId: string, ttlMs: number): boolean {
  const at = verifiedAt.get(serverId);
  if (!at) return false;
  return Date.now() - new Date(at).getTime() < ttlMs;
}

/** Typed, fail-closed call-gate error (code: tool_descriptor_mutated). */
export class ToolDescriptorMutatedError extends Error {
  readonly code = "tool_descriptor_mutated";
  readonly serverId: string;
  readonly diffs: DescriptorDiff[];
  constructor(serverId: string, diffs: DescriptorDiff[]) {
    const summary = diffs.map((diff) => `${diff.toolName}:${diff.kind}`).join(", ") || "unknown";
    super(`tool_descriptor_mutated: ${diffs.length} descriptor change(s) detected on server ${serverId} (${summary}) — execution blocked, re-approval required`);
    this.name = "ToolDescriptorMutatedError";
    this.serverId = serverId;
    this.diffs = diffs;
  }
}

/** Test-only: wipe all pin state. */
export function clearDescriptorPins(): void {
  pinStore.clear();
  verifiedAt.clear();
}
