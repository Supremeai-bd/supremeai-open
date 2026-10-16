/**
 * Heartbeat task-ownership validator — fail-closed gate for `agent_heartbeat`
 * (#340 AC2 + AC3, aligned with api-schemas/heartbeat.schema.json).
 *
 * Problem (issue #340): the live `agent_heartbeat` MCP tool validates only
 * the slot regex and writes to Redis immediately. Task-ownership telemetry
 * (taskId / status / ttlSeconds per the landed heartbeat schema) is neither
 * accepted nor validated, so the orchestrator cannot trust heartbeat-derived
 * lease decisions.
 *
 * Contract (mirrors heartbeat.schema.json EXACTLY — patterns, enums, bounds):
 *   taskId      string, pattern ^$|^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$
 *   status      enum "alive" | "busy" | "idle"
 *   ttlSeconds  integer, 30..3600 (schema default 300)
 *
 * Modes:
 *   - LEGACY (AC3 backward compat): NONE of the three ownership fields is
 *     present → { ok: true, legacy: true }. The slot-only ping keeps working
 *     unchanged — zero breakage for every existing pinger.
 *   - STRICT (AC2): ANY ownership field present → ALL of taskId + status are
 *     REQUIRED and validated; ttlSeconds is optional with the schema default
 *     300 but must be an integer in [30, 3600] when present. Partial
 *     ownership (e.g. status without taskId) is REJECTED — a validator that
 *     guesses is a validator that lies (U2: UNKNOWN is never PASS).
 *   - idle may carry an empty taskId (schema pattern allows ^$); alive/busy
 *     MUST name a non-empty taskId — an agent claiming to work without a
 *     task id is exactly the ghost-state this validator exists to kill.
 *
 * বাংলা মন্তব্য: যেকোনো state-modification (Redis write) ঘটার আগে এই validator
 * চালানো বাধ্যতামূলক (#340: "validators run fail-closed BEFORE any write")।
 * প্রত্যাখ্যান field-ভিত্তিক কারণসহ ফেরত যায় — integration সেটাই সৎভাবে
 * isError হিসেবে দেখাবে। এই মডিউল pure TypeScript — কোনো import নেই, তাই
 * hermetic selftest-এ নেটওয়ার্ক/credential/dotenv কিছুইই লাগে না।
 */

// ── Public types ────────────────────────────────────────────────────────────

export type HeartbeatStatus = "alive" | "busy" | "idle";

export type HeartbeatOwnershipInput = {
  taskId?: unknown;
  status?: unknown;
  ttlSeconds?: unknown;
};

export type ValidatedHeartbeatOwnership =
  | {
      ok: true;
      /** true when the ping carried no ownership fields at all (AC3 legacy). */
      legacy: true;
    }
  | {
      ok: true;
      legacy: false;
      taskId: string;
      status: HeartbeatStatus;
      ttlSeconds: number;
      /** True when the caller omitted ttlSeconds and the schema default applied. */
      ttlDefaulted: boolean;
    };

export type HeartbeatOwnershipRejection = {
  ok: false;
  field: "taskId" | "status" | "ttlSeconds" | "ownership";
  reason: string;
};

// ── Constants (SSOT: api-schemas/heartbeat.schema.json) ─────────────────────

export const HEARTBEAT_TASK_ID_PATTERN = /^$|^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/;
export const HEARTBEAT_STATUSES: readonly HeartbeatStatus[] = ["alive", "busy", "idle"] as const;
export const HEARTBEAT_TTL_MIN_SECONDS = 30;
export const HEARTBEAT_TTL_MAX_SECONDS = 3600;
export const HEARTBEAT_TTL_DEFAULT_SECONDS = 300;

// ── Validator ───────────────────────────────────────────────────────────────

/**
 * Only `undefined` means "field not sent". An explicit JSON `null` is a
 * deliberate value — it counts as PRESENT and fails the type checks below
 * (fail-closed: a client nulling fields must not sneak into legacy mode).
 */
function isPresent(value: unknown): boolean {
  return value !== undefined;
}

function validateTaskId(taskId: unknown): string | null {
  if (!isPresent(taskId)) return "taskId is required in strict ownership mode";
  if (typeof taskId !== "string") return `taskId must be a string, got ${typeof taskId}`;
  if (!HEARTBEAT_TASK_ID_PATTERN.test(taskId)) {
    return `taskId must match ^$|^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$ (≤128 chars, no whitespace/slashes); got ${JSON.stringify(taskId).slice(0, 140)}`;
  }
  return null;
}

function validateStatus(status: unknown): HeartbeatStatus | string {
  if (!isPresent(status)) return "status is required in strict ownership mode";
  if (typeof status !== "string") return `status must be a string, got ${typeof status}`;
  if (!(HEARTBEAT_STATUSES as readonly string[]).includes(status)) {
    return `status must be one of ${HEARTBEAT_STATUSES.map((s) => JSON.stringify(s)).join(" | ")}; got ${JSON.stringify(status)}`;
  }
  return status as HeartbeatStatus;
}

function validateTtlSeconds(ttl: unknown): { value: number; defaulted: boolean } | string {
  if (!isPresent(ttl)) return { value: HEARTBEAT_TTL_DEFAULT_SECONDS, defaulted: true };
  if (typeof ttl !== "number" || !Number.isInteger(ttl)) {
    return `ttlSeconds must be an integer (schema: ${HEARTBEAT_TTL_MIN_SECONDS}..${HEARTBEAT_TTL_MAX_SECONDS}), got ${JSON.stringify(ttl).slice(0, 60)}`;
  }
  if (ttl < HEARTBEAT_TTL_MIN_SECONDS || ttl > HEARTBEAT_TTL_MAX_SECONDS) {
    return `ttlSeconds must be within [${HEARTBEAT_TTL_MIN_SECONDS}, ${HEARTBEAT_TTL_MAX_SECONDS}] per heartbeat.schema.json, got ${ttl}`;
  }
  return { value: ttl, defaulted: false };
}

/**
 * Validates task-ownership fields BEFORE any state modification. Never
 * throws — rejections are values (the tool layer maps them to isError).
 */
export function validateHeartbeatOwnership(
  input: HeartbeatOwnershipInput,
): ValidatedHeartbeatOwnership | HeartbeatOwnershipRejection {
  const hasTaskId = isPresent(input?.taskId);
  const hasStatus = isPresent(input?.status);
  const hasTtl = isPresent(input?.ttlSeconds);

  // AC3 — legacy slot-only ping: no ownership fields anywhere → allow.
  if (!hasTaskId && !hasStatus && !hasTtl) return { ok: true, legacy: true };

  // AC2 — strict mode: partial ownership is rejected (never guess).
  if (!hasTaskId || !hasStatus) {
    return {
      ok: false,
      field: "ownership",
      reason: "partial task ownership: when any of taskId/status/ttlSeconds is sent, both taskId and status are REQUIRED (ttlSeconds optional, default 300)",
    };
  }

  const taskIdError = validateTaskId(input.taskId);
  if (taskIdError) return { ok: false, field: "taskId", reason: taskIdError };

  const status = validateStatus(input.status);
  if (typeof status === "string" && !(HEARTBEAT_STATUSES as readonly string[]).includes(status)) {
    return { ok: false, field: "status", reason: status as string };
  }

  const ttl = validateTtlSeconds(input.ttlSeconds);
  if (typeof ttl === "string") return { ok: false, field: "ttlSeconds", reason: ttl };

  const taskId = input.taskId as string;
  const effectiveStatus = status as HeartbeatStatus;
  if (effectiveStatus !== "idle" && taskId === "") {
    return {
      ok: false,
      field: "taskId",
      reason: `status ${JSON.stringify(effectiveStatus)} requires a non-empty taskId (empty taskId is legal only with status "idle")`,
    };
  }

  return {
    ok: true,
    legacy: false,
    taskId,
    status: effectiveStatus,
    ttlSeconds: ttl.value,
    ttlDefaulted: ttl.defaulted,
  };
}

/**
 * Boolean convenience wrapper for integrations that only need the gate
 * decision ("fail-closed BEFORE any write").
 */
export function isHeartbeatOwnershipValid(input: HeartbeatOwnershipInput): boolean {
  return validateHeartbeatOwnership(input).ok;
}
