/**
 * Canonical HTTP client for the SupremeAI monorepo (DRY Phase 1-B2).
 *
 * WHY: the audit found 10+ parallel transport implementations (~3,200 LOC)
 * with divergent timeout / retry / error semantics, 58 inline `!res.ok`
 * throws and 13 hand-rolled AbortController boilerplates. This module is the
 * SINGLE transport primitive everything should converge on.
 *
 * Design constraints:
 * - Platform-agnostic: plain `fetch`, works in browser / Node 18+ / Edge /
 *   Bun. No axios, no window monkey-patching (the old apiInterceptor habit).
 * - No hardcoded URLs: the base URL is injected by the host app — URL
 *   resolution stays the app's single point of policy (B4).
 * - Auth is injected via `getAuthHeaders()` per request — the client never
 *   reads env/storage itself, so one implementation serves web, extension
 *   and server callers.
 * - Deterministic retry: exponential backoff + full jitter, honoring
 *   `Retry-After` when present; never retries 4xx (except 408/429).
 */

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface HttpError extends Error {
  name: "HttpError";
  status: number;
  url: string;
  method: HttpMethod;
  /** Parsed response body when possible, else raw text. */
  body: unknown;
  correlationId?: string | null;
}

export interface HttpRequestOptions {
  method?: HttpMethod;
  headers?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  /** ms until the request aborts (default: client config, else 15_000). */
  timeoutMs?: number;
  /** Override the client-level retry policy for this request. */
  retries?: number;
  signal?: AbortSignal;
}

export interface HttpClientConfig {
  /** Injected by the host app — NEVER hardcode a URL here. */
  baseUrl: string;
  /** Per-request auth headers (token lookups stay app-side). */
  getAuthHeaders?: () => Record<string, string> | Promise<Record<string, string>>;
  /** Default timeout per attempt (ms). */
  timeoutMs?: number;
  /** Default retry count for retryable failures (default 2). */
  retries?: number;
  /** Extra static headers (User-Agent, tenant id, …). */
  defaultHeaders?: Record<string, string>;
  /** Fetch implementation override (tests / streaming proxies). */
  fetchImpl?: typeof fetch;
}

const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504]);
const DEFAULT_TIMEOUT_MS = 15_000;
const DEFAULT_RETRIES = 2;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(signal.reason ?? new Error("Aborted"));
      },
      { once: true },
    );
  });
}

/**
 * Join a base URL and a path with slash normalization (Wave 3.6, issue #1262).
 * Exported so host-app clients (e.g. frontend apiClient) resolve URLs through
 * the SAME single-point policy as this primitive — no per-client join bugs.
 */
export function buildUrl(baseUrl: string, path: string, query?: HttpRequestOptions["query"]): string {
  let url =
    path.startsWith("http://") || path.startsWith("https://")
      ? path
      : `${baseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  return url;
}

function retryAfterMs(headers: Headers): number | null {
  const ra = headers.get("retry-after");
  if (!ra) return null;
  const secs = Number(ra);
  return Number.isFinite(secs) ? secs * 1000 : null;
}

export function createHttpClient(config: HttpClientConfig) {
  const doFetch = config.fetchImpl ?? fetch;

  async function attempt<T>(
    path: string,
    opts: HttpRequestOptions,
    correlationId?: string,
  ): Promise<
    | { ok: true; data: T }
    | { ok: false; error: HttpError; retryable: boolean; retryInMs: number | null }
  > {
    const controller = new AbortController();
    const timeoutMs = opts.timeoutMs ?? config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const timer = setTimeout(() => controller.abort(new Error(`Timeout after ${timeoutMs}ms`)), timeoutMs);
    const onOuterAbort = () => controller.abort(opts.signal?.reason);
    opts.signal?.addEventListener("abort", onOuterAbort, { once: true });

    const url = buildUrl(config.baseUrl, path, opts.query);
    const method = opts.method ?? "GET";
    try {
      const auth = config.getAuthHeaders ? await config.getAuthHeaders() : {};
      const headers: Record<string, string> = {
        Accept: "application/json",
        ...config.defaultHeaders,
        ...auth,
        ...opts.headers,
      };
      const init: RequestInit = { method, headers, signal: controller.signal };
      if (opts.body !== undefined) {
        headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
        init.body = typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body);
      }

      const res = await doFetch(url, init);
      const text = await res.text();
      let parsed: unknown = text;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch (err) {
        // Non-JSON body is a legitimate outcome — keep raw text, but record why.
        console.warn('[canonical-http] response body is not JSON, keeping raw text:', err);
      }

      if (!res.ok) {
        const error = Object.assign(new Error(`HTTP ${res.status} ${method} ${path}`), {
          name: "HttpError",
          status: res.status,
          url,
          method,
          body: parsed,
          correlationId: res.headers.get("x-correlation-id") ?? correlationId,
        }) as HttpError;
        return {
          ok: false,
          error,
          retryable: RETRYABLE_STATUS.has(res.status),
          retryInMs: retryAfterMs(res.headers),
        };
      }
      return { ok: true, data: parsed as T };
    } catch (err) {
      const error = Object.assign(err instanceof Error ? err : new Error(String(err)), {
        name: "HttpError",
        status: 0,
        url,
        method,
        body: undefined,
        correlationId,
      }) as HttpError;
      // Network failures / timeouts are retryable; caller aborts are not.
      const callerAborted = opts.signal?.aborted === true;
      return { ok: false, error, retryable: !callerAborted, retryInMs: null };
    } finally {
      clearTimeout(timer);
      opts.signal?.removeEventListener("abort", onOuterAbort);
    }
  }

  async function request<T>(path: string, opts: HttpRequestOptions = {}): Promise<T> {
    const maxRetries = opts.retries ?? config.retries ?? DEFAULT_RETRIES;
    let lastError: HttpError | null = null;

    for (let attemptNo = 0; attemptNo <= maxRetries; attemptNo++) {
      const correlationId = `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
      const result = await attempt<T>(path, opts, correlationId);
      if (result.ok) return result.data;

      lastError = result.error;
      const isLast = attemptNo === maxRetries;
      if (!result.retryable || isLast) break;

      const backoff = Math.min(30_000, 250 * 2 ** attemptNo);
      const jittered = result.retryInMs ?? Math.round(backoff * (0.5 + Math.random() * 0.5));
      await sleep(jittered, opts.signal);
    }
    throw lastError;
  }

  return {
    request,
    get: <T>(path: string, opts: Omit<HttpRequestOptions, "method" | "body"> = {}) =>
      request<T>(path, { ...opts, method: "GET" }),
    post: <T>(path: string, body?: unknown, opts: Omit<HttpRequestOptions, "method" | "body"> = {}) =>
      request<T>(path, { ...opts, method: "POST", body }),
    put: <T>(path: string, body?: unknown, opts: Omit<HttpRequestOptions, "method" | "body"> = {}) =>
      request<T>(path, { ...opts, method: "PUT", body }),
    patch: <T>(path: string, body?: unknown, opts: Omit<HttpRequestOptions, "method" | "body"> = {}) =>
      request<T>(path, { ...opts, method: "PATCH", body }),
    delete: <T>(path: string, opts: Omit<HttpRequestOptions, "method" | "body"> = {}) =>
      request<T>(path, { ...opts, method: "DELETE" }),
  };
}

export type HttpClient = ReturnType<typeof createHttpClient>;
