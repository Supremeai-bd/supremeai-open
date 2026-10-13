import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

/**
 * Immutable slot audit trail (#48 Invariant 6).
 *
 * Captures which slot, with which credential fingerprint and role, executed
 * or attempted which operation/tool, when — append-only: there is no update
 * or delete API by design.
 *
 * Sinks (best-effort, never break the request path):
 *   1. In-process bounded ring buffer (always on) — powers slot.audit_trail.
 *   2. Optional append-only JSONL file (MCP_SLOT_AUDIT_FILE) — survives
 *      restarts for forensic review. Write failures are swallowed.
 *
 * SECURITY: never store the raw credential — `credentialId` is the 12-hex
 * fingerprint of the sha256 digest (client-registry.clientCredentialId).
 */

export type SlotAuditOutcome = "allowed" | "denied";
export type SlotAuditOperation = "connect" | "tool-call" | "message" | "admin";

export interface SlotAuditEvent {
  ts: string;
  /** Slot id (`slot_<name>` / `named_<name>`) or the acting client id. */
  slotId?: string;
  /** Credential fingerprint (never the raw credential). */
  credentialId?: string;
  role?: string;
  operation: SlotAuditOperation;
  tool?: string;
  outcome: SlotAuditOutcome;
  /** Machine-readable denial/allowance reason. */
  reason?: string;
  tenantId?: string;
  clientIp?: string;
}

const DEFAULT_RING_SIZE = 5_000;
const ring: SlotAuditEvent[] = [];
let ringSize = positiveIntEnv("MCP_SLOT_AUDIT_RING_SIZE", DEFAULT_RING_SIZE);

function positiveIntEnv(name: string, fallback: number): number {
  const raw = Number(process.env[name] ?? "");
  return Number.isFinite(raw) && raw > 0 ? raw : fallback;
}

function auditFilePath(): string | undefined {
  const path = process.env.MCP_SLOT_AUDIT_FILE?.trim();
  return path || undefined;
}

/**
 * Append an audit event. Synchronous + non-throwing: the ring buffer is the
 * in-process truth; the file sink is best-effort forensic persistence.
 */
export function recordSlotAudit(event: Omit<SlotAuditEvent, "ts"> & { ts?: string }): void {
  const entry: SlotAuditEvent = { ts: event.ts ?? new Date().toISOString(), ...event };
  ring.push(entry);
  while (ring.length > ringSize) ring.shift();

  const file = auditFilePath();
  if (!file) return;
  try {
    mkdirSync(dirname(file), { recursive: true });
    appendFileSync(file, `${JSON.stringify(entry)}\n`, { mode: 0o600 });
  } catch {
    // Forensic sink unavailable — the ring buffer keeps the session truth.
  }
}

/** Read recent audit events (newest last), optionally filtered by slot. */
export function readSlotAudit(filter?: { slotId?: string; limit?: number }): SlotAuditEvent[] {
  const events = filter?.slotId ? ring.filter((event) => event.slotId === filter.slotId) : ring;
  const limit = filter?.limit && filter.limit > 0 ? filter.limit : events.length;
  return events.slice(-limit);
}

/** Current ring buffer occupancy (diagnostics/health surfaces). */
export function slotAuditDepth(): number {
  return ring.length;
}

/** Test-only: clear the ring (used by the security suite between cases). */
export function __clearSlotAuditForTests(): void {
  ring.length = 0;
}
