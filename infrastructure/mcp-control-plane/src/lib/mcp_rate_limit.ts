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
  const now = Date.now();
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
  const clipped = Buffer.from(serialized, "utf8").subarray(0, maxBytes).toString("utf8");
  const truncatedBytes = originalBytes - maxBytes;
  const wasError = (result as { isError?: unknown }).isError === true;
  return {
    content: [{ type: "text", text: `${clipped}\n...[truncated ${truncatedBytes} bytes]` }],
    isError: wasError,
    metadata: {
      truncated: true,
      tool: toolName,
      originalBytes,
      maxBytes,
      truncatedBytes,
    },
  };
}