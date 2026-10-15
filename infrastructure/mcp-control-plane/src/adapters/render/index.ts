import { buildAccountRegistry } from "../../registry/account.registry.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";
import { maskSecretValue, redactSecretsInText } from "../../lib/masking.js";

const BASE_URL = "https://api.render.com/v1";

// ── Logs API defaults (free-plan friendly) ────────────────────────────────
// GET /v1/logs is Render's official REST endpoint for application/build logs.
// Docs: https://api-docs.render.com/reference/logs
// - Default window: last 15 minutes when no explicit startTime/endTime is
//   given (debugging-first default, keeps responses small).
// - Default limit: 50 entries. Render's API hard cap is 100 per request;
//   larger values are clamped (never silently dropped).
// - `type=request` (public HTTP request logs) requires a Pro workspace or
//   higher on Render. We do not default to it; when explicitly requested on
//   a free plan the API error is surfaced verbatim (fail-honest).
const DEFAULT_LOG_WINDOW_MS = 15 * 60 * 1000;
const DEFAULT_LOG_LIMIT = 50;
const MAX_LOG_LIMIT = 100;
const DEPLOY_LOG_WINDOW_MS = 30 * 60 * 1000;

export type RenderLogLevel = "debug" | "info" | "warning" | "error";
export type RenderLogType = "app" | "build" | "request";

export interface RenderLogFilters {
  /** ISO 8601 — window start (default: 15 minutes ago) */
  startTime?: string;
  /** ISO 8601 — window end (default: now) */
  endTime?: string;
  /** Severity filter */
  level?: RenderLogLevel;
  /** Log type filter (app = runtime, build = deploys, request = Pro only) */
  type?: RenderLogType;
  /** Substring search inside log messages */
  text?: string;
  /** Max entries per page (1..100, clamped to API cap) */
  limit?: number;
  /** Pagination cursor from a previous response */
  cursor?: string;
}

export interface RenderLogEntry {
  timestamp: string | null;
  level: string | null;
  type: string | null;
  resource: string | null;
  /** Secret-redacted message (redactSecretsInText) */
  message: string;
}

export interface RenderLogsResult {
  serviceId: string;
  ownerId: string;
  window: { startTime: string; endTime: string };
  filters: { level: string | null; type: string | null; text: string | null };
  count: number;
  /** Cursor for the next page, when the API provides one */
  nextCursor: string | null;
  logs: RenderLogEntry[];
}

/**
 * Resolve the Render API key for an account, following the account's
 * fallback chain (apiKeyRef first, then apiKeyRefs). Throws explicit,
 * actionable errors — never returns an empty string silently:
 * - unknown account id  → "Render account not found: …"
 * - no key configured   → "… is not configured/available (checked: …)"
 */
export function resolveRenderApiKey(accountId: string): string {
  const accounts = buildAccountRegistry();
  const account = accounts.find((a) => a.id === accountId && a.provider === "render");
  if (!account) throw new Error(`Render account not found: ${accountId}`);
  if (!account.available) {
    const refs = [account.apiKeyRef, ...(account.apiKeyRefs ?? [])].join(", ");
    throw new Error(`Render account is not configured/available: ${accountId} (checked env vars: ${refs})`);
  }

  const refs = [account.apiKeyRef, ...(account.apiKeyRefs ?? [])];
  for (const ref of refs) {
    const apiKey = process.env[ref];
    if (apiKey) return apiKey;
  }
  // available=true but key vanished between checks — still fail honestly.
  throw new Error(`Missing Render API Key in env for: ${refs.join(", ")}`);
}

function getApiKey(accountId: string): string {
  return resolveRenderApiKey(accountId);
}

async function resolveOwnerId(apiKey: string, serviceId: string): Promise<string> {
  const res = await httpRequest(`${BASE_URL}/services/${encodeURIComponent(serviceId)}`, {
    headers: bearerAuth(apiKey),
  });
  const body = res.data as Record<string, unknown> | null;

  if (!res.ok) {
    const msg =
      body && typeof body === "object" && "message" in body
        ? String(body.message)
        : `HTTP ${res.status}`;
    throw new Error(`Render API error while resolving owner for ${serviceId}: ${msg}`);
  }

  // GET /v1/services/:id returns the service object directly; be defensive
  // and also accept the wrapped shape used by list endpoints.
  const owner =
    body && typeof body === "object"
      ? body.ownerId ??
        (typeof (body as Record<string, unknown>).service === "object"
          ? ((body as Record<string, unknown>).service as Record<string, unknown>).ownerId
          : undefined)
      : undefined;

  if (!owner || typeof owner !== "string") {
    throw new Error(
      `Render service ${serviceId} did not expose ownerId — cannot query logs (owner mapping missing).`
    );
  }
  return owner;
}

/**
 * Build the GET /v1/logs query string. Pure helper (unit-tested): applies
 * the 15-minute default window, clamps limit to the API cap and forwards
 * optional level/type/text/cursor filters.
 */
export function buildRenderLogQuery(
  ownerId: string,
  serviceId: string,
  filters: RenderLogFilters = {},
  now: Date = new Date()
): URLSearchParams {
  const params = new URLSearchParams();
  params.set("ownerId", ownerId);
  params.set("resource", serviceId);

  const endTime = filters.endTime ?? now.toISOString();
  const startTime = filters.startTime ?? new Date(now.getTime() - DEFAULT_LOG_WINDOW_MS).toISOString();
  params.set("startTime", startTime);
  params.set("endTime", endTime);

  if (filters.limit !== undefined) {
    if (!Number.isInteger(filters.limit) || filters.limit < 1) {
      throw new Error(`Invalid log limit: ${filters.limit} (must be an integer >= 1)`);
    }
    params.set("limit", String(Math.min(filters.limit, MAX_LOG_LIMIT)));
  } else {
    params.set("limit", String(DEFAULT_LOG_LIMIT));
  }

  if (filters.level) params.set("level", filters.level);
  if (filters.type) params.set("type", filters.type);
  if (filters.text) params.set("text", filters.text);
  if (filters.cursor) params.set("cursor", filters.cursor);
  return params;
}

/**
 * Normalize one /v1/logs entry and redact credentials from its message.
 * The endpoint wraps entries as { log: { … } } (same convention as
 * /deploys' { deploy: { … } }); the flat shape is accepted defensively.
 */
export function normalizeLogEntry(raw: unknown): RenderLogEntry {
  const entry =
    raw && typeof raw === "object" && "log" in (raw as Record<string, unknown>)
      ? ((raw as Record<string, unknown>).log as Record<string, unknown> | null)
      : (raw as Record<string, unknown> | null);

  const message = entry && typeof entry.message === "string" ? redactSecretsInText(entry.message) : "";
  return {
    timestamp: entry && typeof entry.timestamp === "string" ? entry.timestamp : null,
    level: entry && typeof entry.level === "string" ? entry.level : null,
    type: entry && typeof entry.type === "string" ? entry.type : null,
    resource: entry && typeof entry.resource === "string" ? entry.resource : null,
    message,
  };
}

function apiErrorMessage(data: unknown, fallback: string): string {
  return data && typeof data === "object" && "message" in (data as Record<string, unknown>)
    ? String((data as Record<string, unknown>).message)
    : fallback;
}

/**
 * Query real Render application/build logs (GET /v1/logs).
 *
 * Replaces the old getDeployLogs() stub that returned deploy metadata only.
 * Read-only: no deploy, restart or environment mutation is possible here.
 */
export async function listLogs(
  accountId: string,
  serviceId: string,
  filters: RenderLogFilters = {}
): Promise<RenderLogsResult> {
  const apiKey = getApiKey(accountId);
  const ownerId = await resolveOwnerId(apiKey, serviceId);

  const params = buildRenderLogQuery(ownerId, serviceId, filters);
  const res = await httpRequest(`${BASE_URL}/logs?${params.toString()}`, {
    headers: bearerAuth(apiKey),
  });

  if (!res.ok) {
    // Surface the API error verbatim (e.g. Pro-plan requirement for
    // type=request) instead of returning an empty result silently.
    throw new Error(`Render Logs API error: ${apiErrorMessage(res.data, `HTTP ${res.status}`)}`);
  }

  const body = res.data as unknown;
  const entries = Array.isArray(body)
    ? body
    : body && typeof body === "object" && Array.isArray((body as Record<string, unknown>).logs)
      ? ((body as Record<string, unknown>).logs as unknown[])
      : [];

  const nextCursor =
    body && !Array.isArray(body) && typeof body === "object"
      ? ((body as Record<string, unknown>).nextCursor as string | undefined) ?? null
      : null;

  const logs = entries.map(normalizeLogEntry);
  const windowStart = params.get("startTime") as string;
  const windowEnd = params.get("endTime") as string;

  return {
    serviceId,
    ownerId,
    window: { startTime: windowStart, endTime: windowEnd },
    filters: {
      level: params.get("level"),
      type: params.get("type"),
      text: params.get("text"),
    },
    count: logs.length,
    nextCursor,
    logs,
  };
}

export async function listServices(accountId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  const res = await httpRequest(`${BASE_URL}/services?limit=20`, {
    headers: bearerAuth(apiKey),
  });
  return res.data;
}

export async function getServiceHealth(accountId: string, serviceId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  const res = await httpRequest(`${BASE_URL}/services/${serviceId}`, {
    headers: bearerAuth(apiKey),
  });

  // Try to fetch last deploy
  let deployStatus = "unknown";
  try {
    const deploysRes = await httpRequest(`${BASE_URL}/services/${serviceId}/deploys?limit=1`, {
      headers: bearerAuth(apiKey),
    });
    const deploys = deploysRes.data;
    if (Array.isArray(deploys) && deploys.length > 0) {
      deployStatus = deploys[0]?.deploy?.status ?? "unknown";
    }
  } catch (err) {
    // Ignore error for deploys
  }

  return {
    service: res.data,
    lastDeployStatus: deployStatus
  };
}

/**
 * Latest deploy metadata + REAL build logs for that deploy window.
 *
 * Previously this stub returned deploy metadata only, with the (wrong)
 * assumption that Render's v1 REST API has no logs endpoint. It now calls
 * GET /v1/logs (type=build) over the deploy window (deploy createdAt, capped
 * at the last 30 minutes). The output shape is additive/backward compatible:
 * `message` and `latestDeploy` keep their meaning; `buildLogs` is new and
 * `buildLogsError` is set when the log query fails while deploy metadata
 * remains available (deploy status must never be hidden by a log failure).
 */
export async function getDeployLogs(accountId: string, serviceId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);

  // First, get the latest deploy
  const deploysRes = await httpRequest(`${BASE_URL}/services/${serviceId}/deploys?limit=1`, {
    headers: bearerAuth(apiKey),
  });
  const deploys = deploysRes.data;
  if (!Array.isArray(deploys) || deploys.length === 0) {
    throw new Error(apiErrorMessage(deploys, "No deploys found for this service"));
  }

  const deploy = deploys[0].deploy;

  // Real build logs via GET /v1/logs (type=build). Window: from the deploy's
  // createdAt (capped at the last 30 minutes so old deploys stay bounded) to now.
  let buildLogs: RenderLogEntry[] = [];
  let buildLogsError: string | null = null;
  try {
    const createdAt = typeof deploy?.createdAt === "string" ? Date.parse(deploy.createdAt) : NaN;
    const windowStart = Number.isFinite(createdAt)
      ? new Date(Math.max(createdAt, Date.now() - DEPLOY_LOG_WINDOW_MS)).toISOString()
      : new Date(Date.now() - DEPLOY_LOG_WINDOW_MS).toISOString();
    const result = await listLogs(accountId, serviceId, {
      type: "build",
      startTime: windowStart,
      limit: MAX_LOG_LIMIT,
    });
    buildLogs = result.logs;
  } catch (err) {
    buildLogsError = (err as Error).message;
  }

  return {
    message: "Latest deploy metadata + real build logs (GET /v1/logs, type=build).",
    latestDeploy: deploy,
    buildLogs,
    ...(buildLogsError ? { buildLogsError } : {}),
  };
}

export async function getServiceEnvVars(accountId: string, serviceId: string): Promise<unknown> {
  const apiKey = getApiKey(accountId);
  const res = await httpRequest(`${BASE_URL}/services/${serviceId}/env-vars?limit=50`, {
    headers: bearerAuth(apiKey),
  });
  // Read-Only: env var values are masked by KEY NAME *and* by VALUE SHAPE
  // (#695). URLs with embedded credentials, bcrypt/argon hashes, JWTs,
  // high-entropy hex/base64 tokens and connection strings are masked even when
  // the variable's key name does not contain key/secret/token.
  if (!res.ok || !Array.isArray(res.data)) {
    const errorMsg =
      res.data && typeof res.data === "object" && "message" in (res.data as Record<string, unknown>)
        ? String((res.data as Record<string, unknown>).message)
        : `Failed to fetch env vars (HTTP ${res.status})`;
    throw new Error(`Render API error: ${errorMsg}`);
  }
  const items = res.data as any[];
  return items.map((item: any) => ({
    key: item.envVar?.key,
    value: item.envVar?.value ? maskSecretValue(String(item.envVar.key ?? ""), String(item.envVar.value)) : "",
  }));
}
