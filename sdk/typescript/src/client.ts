/**
 * @supremeai/sdk — SupremeAI Unified Gateway client.
 *
 * Zero-dependency HTTP layer built on native fetch (Node 20+, Bun, Deno,
 * Edge runtimes). Requests are signed with a bearer API key resolved from
 * the caller-supplied option or the SUPREMEAI_API_KEY environment value.
 * Transient gateway failures (502/503/504) are retried with exponential
 * backoff and jitter before surfacing a GatewayError.
 */

import type {
  GatewayErrorShape,
  HealthResponse,
  ModelInfo,
  StreamEvent,
  TaskRunRequest,
  TaskRunResponse,
} from './types/generated.ts';
import { SSEParser, streamRunEvents } from './streaming.ts';

export * from './types/generated.ts';
export { SSEParser, streamRunEvents } from './streaming.ts';

/** Status codes considered transient and safe to retry. */
const RETRYABLE_STATUSES = new Set([502, 503, 504]);

export class GatewayError extends Error {
  readonly status: number;
  readonly code: string;
  readonly provider?: string;
  readonly retryable: boolean;
  readonly body?: unknown;

  constructor(status: number, shape: Partial<GatewayErrorShape>, body?: unknown) {
    super(shape.message || 'gateway request failed');
    this.name = 'GatewayError';
    this.status = status;
    this.code = shape.code || 'GATEWAY_ERROR';
    this.provider = shape.provider;
    this.retryable = shape.retryable ?? RETRYABLE_STATUSES.has(status);
    this.body = body;
  }
}

export interface ClientOptions {
  /** Gateway base, e.g. an env-driven value; falsy means same-origin paths. */
  baseUrl?: string;
  /** Bearer credential; falls back to the SUPREMEAI_API_KEY env value. */
  apiKey?: string;
  /** Max attempts per request (first call + retries). Default 3. */
  maxRetries?: number;
  /** Per-attempt fetch timeout in milliseconds. Default 30000. */
  timeoutMs?: number;
  /** Base backoff floor in milliseconds. Default 150. */
  backoffMs?: number;
  /** Extra headers merged into every request (after signing). */
  defaultHeaders?: Record<string, string>;
}

export interface RequestOptions {
  /** Abort signal propagated to the underlying fetch. */
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

interface ResolvedConfig {
  baseUrl: string;
  apiKey: string;
  maxRetries: number;
  timeoutMs: number;
  backoffMs: number;
}

function resolveConfig(options: ClientOptions = {}): ResolvedConfig {
  const env =
    typeof globalThis !== 'undefined'
      ? (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
      : undefined;
  const baseUrl = (options.baseUrl ?? env?.SUPREMEAI_GATEWAY_URL ?? '').replace(/\/+$/, '');
  const apiKey = options.apiKey ?? env?.SUPREMEAI_API_KEY ?? '';
  return {
    baseUrl,
    apiKey,
    maxRetries: options.maxRetries ?? 3,
    timeoutMs: options.timeoutMs ?? 30000,
    backoffMs: options.backoffMs ?? 150,
  };
}

/** Exponential backoff with full jitter: floor + random(0 .. backoff * 2^attempt). */
export function backoffDelay(attempt: number, backoffMs: number): number {
  const ceiling = backoffMs * Math.pow(2, attempt);
  return backoffMs + Math.floor(Math.random() * ceiling);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new Error('aborted'));
      },
      { once: true },
    );
  });
}

/**
 * Unified client for the SupremeAI gateway. One instance per process is
 * sufficient; the class is stateless beyond configuration.
 */
export class SupremeAIClient {
  private readonly config: ResolvedConfig;
  private readonly defaultHeaders: Record<string, string>;

  constructor(options: ClientOptions = {}) {
    this.config = resolveConfig(options);
    this.defaultHeaders = { ...(options.defaultHeaders ?? {}) };
  }

  /** Build signed headers; overrides win over defaults. */
  private signedHeaders(extra?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = {
      'content-type': 'application/json',
      accept: 'application/json',
      'x-client': 'supremeai-sdk-ts/0.1.0',
      ...this.defaultHeaders,
      ...(extra ?? {}),
    };
    if (this.config.apiKey) {
      headers.authorization = 'Bearer ' + this.config.apiKey;
    }
    return headers;
  }

  private url(path: string): string {
    return this.config.baseUrl + path;
  }

  /**
   * Perform a signed JSON request with retry + exponential backoff on
   * 502/503/504. Throws GatewayError for terminal failures.
   */
  async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    let lastError: GatewayError | undefined;
    for (let attempt = 0; attempt < this.config.maxRetries; attempt++) {
      if (attempt > 0) {
        await sleep(backoffDelay(attempt - 1, this.config.backoffMs), options.signal);
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.config.timeoutMs);
      const onOuterAbort = () => controller.abort();
      options.signal?.addEventListener('abort', onOuterAbort, { once: true });
      try {
        const response = await fetch(this.url(path), {
          method,
          headers: this.signedHeaders(options.headers),
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: controller.signal,
        });
        if (response.ok) {
          if (response.status === 204) {
            return undefined as T;
          }
          return (await response.json()) as T;
        }
        let shape: Partial<GatewayErrorShape> = {};
        let raw: unknown;
        try {
          raw = await response.json();
          if (raw && typeof raw === 'object') {
            const obj = raw as Record<string, unknown>;
            const inner = obj['error'];
            shape = (inner && typeof inner === 'object' ? inner : obj) as Partial<GatewayErrorShape>;
          }
        } catch {
          raw = undefined;
        }
        const error = new GatewayError(response.status, shape, raw);
        if (RETRYABLE_STATUSES.has(response.status) && attempt < this.config.maxRetries - 1) {
          lastError = error;
          continue;
        }
        throw error;
      } catch (err) {
        if (err instanceof GatewayError) {
          if (attempt >= this.config.maxRetries - 1) throw err;
          lastError = err;
          continue;
        }
        throw err;
      } finally {
        clearTimeout(timer);
        options.signal?.removeEventListener('abort', onOuterAbort);
      }
    }
    throw lastError ?? new GatewayError(0, { code: 'UNREACHABLE', message: 'gateway unreachable' });
  }

  /** List models available to the failover cascade. */
  listModels(options?: RequestOptions): Promise<ModelInfo[]> {
    return this.request<ModelInfo[]>('GET', '/v1/models', undefined, options);
  }

  /** Gateway health probe. */
  health(options?: RequestOptions): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/v1/health', undefined, options);
  }

  /** OpenAI-compatible chat completion via /v1/chat/completions. */
  chat<T = unknown>(body: Record<string, unknown>, options?: RequestOptions): Promise<T> {
    return this.request<T>('POST', '/v1/chat/completions', body, options);
  }

  /** Parallel multi-model consensus via /v1/consensus. */
  consensus<T = unknown>(body: Record<string, unknown>, options?: RequestOptions): Promise<T> {
    return this.request<T>('POST', '/v1/consensus', body, options);
  }
}
