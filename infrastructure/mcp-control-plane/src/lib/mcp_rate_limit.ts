// Rate-limit helpers extracted from index.ts (domain: rate-limit).
// Cross-cutting governance primitives: MCP per-IP sliding window + per-(identity,tool)
// rate limit, input payload validation, output truncation, execution timeout sentinel.

import { env } from "./env.js";
import { RequestContextStore } from "../policy/auth.context.js";

export const mcpRateBuckets = new Map<string, number[]>();
export const toolIdentityRateBuckets = new Map<string, number[]>();

export function mcpRateLimitConfig(): { max: number; windowMs: number } {
  return { max: env.runtime.mcpRateLimitMax, windowMs: env.runtime.mcpRateLimitWindowMs };
}

export function consumeSlidingWindow(
  buckets: Map<string, number[]>,
  key: string,
  max: number,
  windowMs: number,
): { allowed: boolean; retryAfterMs: number } {
  return consumeSlidingWindowAt(buckets, key, max, windowMs, Date.now());
}

/** Injectable-clock variant (offline test battery); behavior identical. */
export function consumeSlidingWindowAt(
  buckets: Map<string, number[]>,
  key: string,
  max: number,
  windowMs: number,
  nowMs: number,
): { allowed: boolean; retryAfterMs: number } {
  const now = nowMs;
  const cutoff = now - windowMs;
  let stamps = buckets.get(key);
  if (!stamps) { stamps = []; buckets.set(key, stamps); }
  while (stamps.length > 0 && stamps[0] <= cutoff) stamps.shift();
  if (buckets.size > 10_000) {
    for (const [bucketKey, bucketStamps] of buckets) {
      if (bucketStamps.length === 0 || bucketStamps[bucketStamps.length - 1] <= cutoff) {
        buckets.delete(bucketKey);
      }
    }
  }
  if (stamps.length >= max) {
    const retryAfterMs = stamps.length > 0 ? Math.max(1, (stamps[0] ?? now) + windowMs - now) : windowMs;
    return { allowed: false, retryAfterMs };
  }
  stamps.push(now);
  return { allowed: true, retryAfterMs: 0 };
}

export function consumeMcpRateLimit(key: string): { allowed: boolean; retryAfterMs: number } {
  const { max, windowMs } = mcpRateLimitConfig();
  return consumeSlidingWindow(mcpRateBuckets, key, max, windowMs);
}

export function toolRateLimitIdentity(): string {
  const store = RequestContextStore.get();
  if (!store) return "uncontexted";
  const principal = store.clientId ?? store.role ?? "anon";
  return `${store.tenantId ?? "default"}|${principal}`;
}

export function consumeToolRateLimit(toolName: string): { allowed: boolean; retryAfterMs: number } {
  const { max, windowMs } = { max: env.runtime.toolRateLimitMax, windowMs: env.runtime.toolRateLimitWindowMs };
  return consumeSlidingWindow(toolIdentityRateBuckets, `${toolRateLimitIdentity()}||${toolName}`, max, windowMs);
}

// ── Anonymous-mutation plane bound (#2363 Option A) ─────────────────────────
// The zero-credential protocol is the federation's BY-DESIGN front door
// (#2082 standing doctrine); this bound keeps it OPEN but BOUNDED. The
// existing per-(identity, tool) limit collapses every anonymous caller into
// the shared "default|anon" bucket — one abusive tenant can exhaust it (a
// DoS against the other anonymous agents) and nothing bounds novel-content
// spam at writes-per-hour scale from a single IP. The audit (#2363 F-1)
// observed zero 429s across 27 dispatch cycles on 4 side-effect-capable
// tools. This plane adds a per-(caller IP, tool) HOURLY window on exactly
// the anonymous-reachable mutation tools; the read plane and authenticated
// identity limits are untouched. Fail-open on unparseable payloads —
// malformed bodies must not widen the blast radius they already have.
export const MUTATION_TOOLS: ReadonlySet<string> = new Set([
  "github_create_issue",
  "memory_remember_fact",
  "work_claim",
  "bridge_submit_patch",
]);

export const mutationRateBuckets = new Map<string, number[]>();

export function mutationRateLimitConfig(): { max: number; windowMs: number } {
  return { max: env.runtime.mutationRateLimitMax, windowMs: env.runtime.mutationRateLimitWindowMs };
}

export function consumeMutationRateLimit(
  callerIp: string, toolName: string, nowMs: number = Date.now(),
): { allowed: boolean; retryAfterMs: number } {
  const { max, windowMs } = mutationRateLimitConfig();
  return consumeSlidingWindowAt(mutationRateBuckets, `${callerIp}||${toolName}`, max, windowMs, nowMs);
}

/**
 * Pure gate for the /mcp POST entry: returns the retry-after payload when
 * the request invokes a mutation tool and the (ip, tool) hourly bucket is
 * exhausted, else null. Handles JSON-RPC single objects and batch arrays;
 * anything unparseable/non-tools-call/non-mutation returns null (read plane
 * untouched, malformed bodies fail open into the downstream RBAC/limits).
 */
export function mutationToolGateError(
  parsedBody: unknown, callerIp: string, nowMs: number = Date.now(),
): { retryAfterMs: number; tool: string } | null {
  const calls: string[] = [];
  if (Array.isArray(parsedBody)) {
    for (const item of parsedBody) {
      const name = toolCallName(item);
      if (name) calls.push(name);
    }
  } else {
    const name = toolCallName(parsedBody);
    if (name) calls.push(name);
  }
  let worst: { retryAfterMs: number; tool: string } | null = null;
  for (const tool of calls) {
    if (!MUTATION_TOOLS.has(tool)) continue;
    const verdict = consumeMutationRateLimit(callerIp, tool, nowMs);
    if (!verdict.allowed) {
      // deterministic worst reply: the longest wait among exhausted tools
      if (worst === null || verdict.retryAfterMs > worst.retryAfterMs) {
        worst = { retryAfterMs: verdict.retryAfterMs, tool };
      }
    }
  }
  return worst;
}

function toolCallName(item: unknown): string | null {
  if (item === null || typeof item !== "object") return null;
  const method = (item as { method?: unknown }).method;
  if (method !== "tools/call") return null;
  const params = (item as { params?: unknown }).params;
  if (params === null || typeof params !== "object") return null;
  const name = (params as { name?: unknown }).name;
  return typeof name === "string" ? name : null;
}

export function toolPayloadError(toolName: string, toolArgs: unknown): string | null {
  if (toolArgs === undefined || toolArgs === null) return null;
  if (typeof toolArgs !== "object" || Array.isArray(toolArgs)) {
    return `Invalid arguments for tool '${toolName}': arguments must be a JSON object.`;
  }
  let serialized: string;
  try {
    serialized = JSON.stringify(toolArgs) ?? "";
  } catch {
    return `Invalid arguments for tool '${toolName}': arguments are not JSON-serializable.`;
  }
  const maxBytes = env.runtime.toolPayloadMaxBytes;
  const byteLength = Buffer.byteLength(serialized, "utf8");
  if (byteLength > maxBytes) {
    return `Payload too large for tool '${toolName}': ${byteLength} bytes exceeds the ${maxBytes}-byte limit (MCP_TOOL_PAYLOAD_MAX_BYTES).`;
  }
  return null;
}

export class ToolExecutionTimeoutError extends Error {
  constructor(toolName: string, timeoutMs: number) {
    super(`Tool '${toolName}' execution timed out after ${timeoutMs}ms`);
    this.name = "ToolExecutionTimeoutError";
  }
}

/** Minimum surviving byte length for a pruned string leaf — below this we stop cutting. */
const PRUNE_MIN_KEEP_BYTES = 256;
/** Max nesting depth we recurse into string values that parse as JSON (tower github tools double-encode). */
const PRUNE_MAX_NEST_DEPTH = 2;
/** A string value must exceed this to be worth parsing as nested JSON. */
const PRUNE_NESTED_THRESHOLD_BYTES = 4096;
/** Hard pass cap for the prune loop; exhaustion falls back to the wholesale summary. */
const PRUNE_MAX_PASSES = 200;

/**
 * Clip a string to at most maxBytes WITHOUT splitting a multi-byte UTF-8
 * sequence (a raw Buffer.subarray cut emits U+FFFD mojibake for Bengali/CJK
 * payloads, which dominate this federation).
 */
function utf8SafeClip(text: string, maxBytes: number): string {
  if (maxBytes <= 0) return "";
  const buf = Buffer.from(text, "utf8");
  if (buf.length <= maxBytes) return text;
  let cut = maxBytes;
  // step back over UTF-8 continuation bytes (0b10xxxxxx) to keep the glyph whole
  while (cut > 0 && (buf[cut] & 0xc0) === 0x80) cut--;
  return buf.subarray(0, cut).toString("utf8");
}

function getChildValue(parent: unknown, key: string | number): unknown {
  return Array.isArray(parent)
    ? (parent as unknown[])[key as number]
    : (parent as Record<string, unknown>)[key as string];
}

function setChildValue(parent: unknown, key: string | number, value: unknown): void {
  if (Array.isArray(parent)) (parent as unknown[])[key as number] = value;
  else (parent as Record<string, unknown>)[key as string] = value;
}

/** An editable string leaf, addressed through its parent so mutation stays in place. */
interface EditableString {
  parent: unknown;
  key: string | number;
  bytes: number; // current utf8 byte length; 0 = demoted from the prune set
}

/** A string value that parsed as nested JSON; re-serialized into its parent on every measurement. */
interface NestedJsonRoot {
  parent: unknown;
  key: string | number;
  parsed: unknown;
}

/**
 * Collect editable string leaves of `node`. String values that themselves
 * parse as a JSON object/array above the size threshold are recursed into so
 * the prune operates at the innermost useful granularity (the tower's github
 * tools double- and triple-encode payloads).
 */
function collectLeaves(node: unknown, depth: number, leaves: EditableString[], roots: NestedJsonRoot[]): void {
  if (depth > PRUNE_MAX_NEST_DEPTH || node === null || typeof node !== "object") return;
  const keys: (string | number)[] = Array.isArray(node)
    ? (node as unknown[]).map((_, i) => i)
    : Object.keys(node as Record<string, unknown>);
  for (const key of keys) {
    // never touch prototype-chain keys (JSON.parse can produce own "__proto__" props)
    if (key === "__proto__" || key === "constructor" || key === "prototype") continue;
    const value = getChildValue(node, key);
    if (typeof value === "string") {
      const bytes = Buffer.byteLength(value, "utf8");
      if (bytes > PRUNE_NESTED_THRESHOLD_BYTES && depth < PRUNE_MAX_NEST_DEPTH) {
        try {
          const nested: unknown = JSON.parse(value);
          if (nested !== null && typeof nested === "object") {
            const before = leaves.length + roots.length;
            collectLeaves(nested, depth + 1, leaves, roots);
            if (leaves.length + roots.length > before) {
              roots.push({ parent: node, key, parsed: nested });
              continue; // inner granularity registered; outer string not editable directly
            }
          }
        } catch {
          /* not nested JSON — treat as an ordinary string leaf */
        }
      }
      if (bytes > PRUNE_MIN_KEEP_BYTES) leaves.push({ parent: node, key, bytes });
    } else if (value !== null && typeof value === "object") {
      collectLeaves(value, depth, leaves, roots);
    }
  }
}

/**
 * Iteratively halve the largest string leaf (UTF-8-safe) until the
 * re-stringified document fits `budgetBytes`. Deterministic: largest-first,
 * ties broken by discovery order. Returns total bytes removed, or null when
 * the prune floor / pass cap is reached before fitting.
 */
function pruneToBudget(root: unknown, budgetBytes: number): number | null {
  const leaves: EditableString[] = [];
  const roots: NestedJsonRoot[] = [];
  collectLeaves(root, 0, leaves, roots);
  let removedTotal = 0;
  for (let pass = 0; pass < PRUNE_MAX_PASSES; pass++) {
    roots.forEach((r) => setChildValue(r.parent, r.key, JSON.stringify(r.parsed)));
    const serialized = JSON.stringify(root);
    if (Buffer.byteLength(serialized, "utf8") <= budgetBytes) return removedTotal;
    let biggest: EditableString | null = null;
    for (const leaf of leaves) {
      if (leaf.bytes > PRUNE_MIN_KEEP_BYTES && (biggest === null || leaf.bytes > biggest.bytes)) {
        biggest = leaf;
      }
    }
    if (biggest === null) return null; // prune floor reached
    const current = getChildValue(biggest.parent, biggest.key) as string;
    const target = Math.max(PRUNE_MIN_KEEP_BYTES, Math.floor(biggest.bytes / 2));
    const clipped = utf8SafeClip(current, target);
    const removed = biggest.bytes - Buffer.byteLength(clipped, "utf8");
    setChildValue(biggest.parent, biggest.key, clipped);
    biggest.bytes = removed > 0 ? Buffer.byteLength(clipped, "utf8") : 0; // 0 = demoted
    if (removed > 0) removedTotal += removed;
  }
  return null; // pass cap exhausted
}

/**
 * Output-truncation gate (MCP_TOOL_RESULT_MAX_BYTES).
 *
 * Superior replacement of the former byte-clip: the old behavior cut the
 * serialized JSON mid-structure and appended a prose marker, producing an
 * UNPARSEABLE text payload (every JSON-parsing client failed on the largest,
 * richest responses) and U+FFFD mojibake whenever the cut split a multi-byte
 * UTF-8 sequence. The replacement prunes the largest string leaves
 * (UTF-8-safe, nested-JSON-aware) so the emitted payload stays VALID JSON,
 * embeds truncation facts under a reserved `_truncation` key, and preserves
 * the original `metadata` contract. A wholesale-summary fallback covers the
 * pathological case where the prune floor is reached before fitting.
 * Signature and call sites unchanged.
 */
export function truncateToolResult(toolName: string, result: unknown): unknown {
  if (result === null || typeof result !== "object") return result;
  let serialized: string | undefined;
  try {
    serialized = JSON.stringify(result);
  } catch {
    return result;
  }
  if (serialized === undefined) return result;
  const originalBytes = Buffer.byteLength(serialized, "utf8");
  const maxBytes = env.runtime.toolResultMaxBytes;
  if (originalBytes <= maxBytes) return result;
  const wasError = (result as { isError?: unknown }).isError === true;

  // reserve room for the in-band `_truncation` note
  const budget = Math.max(1024 + 256, maxBytes - 256);

  let parsed: unknown = null;
  try {
    parsed = JSON.parse(serialized);
  } catch {
    parsed = null; // unreachable for stringify output; defensive
  }

  const removed = parsed !== null && typeof parsed === "object"
    ? pruneToBudget(parsed, budget)
    : null;

  if (removed !== null) {
    if (!Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      if (!("_truncation" in obj)) {
        obj._truncation = {
          truncated: true,
          tool: toolName,
          originalBytes,
          maxBytes,
          truncatedBytes: removed,
        };
      }
    }
    const prunedText = JSON.stringify(parsed);
    if (Buffer.byteLength(prunedText, "utf8") <= maxBytes) {
      return {
        content: [{ type: "text", text: prunedText }],
        isError: wasError,
        metadata: {
          truncated: true,
          tool: toolName,
          originalBytes,
          maxBytes,
          truncatedBytes: removed,
          mode: "json-prune",
        },
      };
    }
  }

  // wholesale fallback: prune floor / pass cap reached — emit a compact
  // VALID-JSON summary instead of a corrupt half-document.
  const summary = {
    truncated: true,
    tool: toolName,
    originalBytes,
    maxBytes,
    note: "Result exceeded MCP_TOOL_RESULT_MAX_BYTES and could not be pruned under budget; re-query with narrower arguments (lower limit / tighter filters).",
  };
  return {
    content: [{ type: "text", text: JSON.stringify(summary) }],
    isError: wasError,
    metadata: {
      truncated: true,
      tool: toolName,
      originalBytes,
      maxBytes,
      truncatedBytes: originalBytes - Buffer.byteLength(JSON.stringify(summary), "utf8"),
      mode: "wholesale",
    },
  };
}

