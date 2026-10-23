/**
 * Shared HTTP client with retry, timeout, and exponential backoff.
 * Used by all provider adapters.
 */

export interface HttpOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  headers?: Record<string, string>;
  body?: unknown;
  timeoutMs?: number;
  retries?: number;
}

export interface HttpResponse<T = unknown> {
  ok: boolean;
  status: number;
  data: T;
  latencyMs: number;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function httpRequest<T = unknown>(
  url: string,
  opts: HttpOptions = {}
): Promise<HttpResponse<T>> {
  const {
    method = "GET",
    headers = {},
    body,
    timeoutMs = 10_000,
    retries = 2,
  } = opts;

  const start = Date.now();

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    // Fresh AbortController PER ATTEMPT (defect-class fix): the previous
    // implementation created ONE controller before the loop, so a timeout
    // on attempt N left the shared signal permanently aborted — every
    // later retry then failed instantly with AbortError, making retries
    // dead code for the most common retry cause (timeout / cold-start
    // spin-up of sleeping Render instances). Each attempt now owns its
    // timeout and is aborted only by its own deadline.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const requestBody =
        body === undefined || body === null
          ? undefined
          : typeof body === "string"
            ? body
            : JSON.stringify(body);

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...headers,
        },
        body: requestBody,
        signal: controller.signal,
      });

      clearTimeout(timeout);
      const latencyMs = Date.now() - start;

      let data: T;
      const contentType = res.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        data = await res.json() as T;
      } else {
        data = (await res.text()) as unknown as T;
      }

      return { ok: res.ok, status: res.status, data, latencyMs };
    } catch (err) {
      clearTimeout(timeout);
      lastError = err as Error;
      if (attempt < retries) {
        await sleep(500 * Math.pow(2, attempt)); // 500ms, 1000ms...
      }
    }
  }

  throw lastError ?? new Error(`HTTP request failed: ${url}`);
}

export function bearerAuth(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}
