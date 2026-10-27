// 🔧 DYNAMIC CONFIG: No fallback hardcoded URLs - Fail-Fast in production

// 🔬 Evolution v3.0: Enhanced API client with Retry + Circuit Breaker
// বাংলা মন্ত্য: Portal-ভিত্তিক একক backend নির্ধারণ — কোনো cross-portal failover নয়।

// DRY Phase 1-B5: the private FrontendCircuitBreaker copy lived here while the
// identical implementation was single-sourced into @supremeai/core-infrastructure
// (CircuitBreaker, Phase 1-B3). Frontend now consumes the shared primitive —
// exports below keep the same shapes (`circuits`, `CircuitState`) so every
// consumer stays source-compatible.
import { CircuitBreaker, type CircuitState } from '@supremeai/core-infrastructure';

// Pre-configured circuits
const apiCircuit = new CircuitBreaker({
  name: 'api_backend',
  failureThreshold: parseInt(import.meta.env.VITE_CIRCUIT_FAILURE_THRESHOLD || '5'),
  recoveryTimeoutMs: parseInt(import.meta.env.VITE_CIRCUIT_RECOVERY_MS || '30000'),
});

const wsCircuit = new CircuitBreaker({
  name: 'websocket',
  failureThreshold: 3,
  recoveryTimeoutMs: 15000,
});

/**
 * 🔬 Retry Configuration
 */
interface RetryConfig {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  retryableStatuses: number[];
}

const DEFAULT_RETRY: RetryConfig = {
  maxRetries: parseInt(import.meta.env.VITE_MAX_RETRIES || '3'),
  baseDelayMs: 500,
  maxDelayMs: 5000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
};

async function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function calculateBackoff(attempt: number, config: RetryConfig): number {
  // Exponential backoff with jitter
  const delay = Math.min(config.baseDelayMs * Math.pow(2, attempt), config.maxDelayMs);
  return delay + Math.random() * 200; // Jitter
}

/**
 * 🔬 Enhanced fetchWithRetry with Circuit Breaker integration
 */
// Justified raw fetch (Issue #2522): এটি নিচের প্রিমিটিভ লেয়ার — apiClient
// নিজেই এই মডিউলের getApiBaseUrl import করে, তাই উল্টোদিকে apiClient
// ব্যবহার করলে circular dependency হতো। কেবল এই ফাইলে bare fetch অনুমোদিত।
export async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  retryConfig: Partial<RetryConfig> = {}
): Promise<Response> {
  const config = { ...DEFAULT_RETRY, ...retryConfig };
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      // Circuit breaker protection
      const response = await apiCircuit.execute(() => fetch(url, options));

      // Don't retry on success or non-retryable codes
      if (!config.retryableStatuses.includes(response.status)) {
        return response;
      }

      // Retry on rate-limit or server errors
      console.warn(`⚠️ Attempt ${attempt + 1}/${config.maxRetries + 1}: ${response.status} ${url}`);
      lastError = new Error(`HTTP ${response.status}`);

    } catch (error) {
      // supremeai-studio#1 (CORS residual): network-layer failures surface as
      // TypeError per the fetch spec (CORS origin-policy rejection, DNS, refused
      // connection). An origin-policy rejection is DETERMINISTIC — re-firing the
      // same request up to 3 more times cannot succeed and only multiplies the
      // browser's un-suppressable console errors. Retry remains reserved for
      // retryable HTTP statuses (handled above) and constructed errors (timeouts,
      // cold-start 50x wrappers) thrown by higher layers.
      if (error instanceof TypeError) throw error;
      lastError = error as Error;
      console.warn(`⚠️ Attempt ${attempt + 1}/${config.maxRetries + 1}:`, error);
    }

    // Wait before retry (except after last attempt)
    if (attempt < config.maxRetries) {
      const delay = calculateBackoff(attempt, config);
      await sleep(delay);
    }
  }

  throw lastError || new Error('All retries exhausted');
}// বাংলা (single-frontend migration, roadmap Phase 1/7): VITE_PORTAL_TYPE সরানো হয়েছে।
// Environment managers occasionally inject values as `KEY=value`; normalize that shape
// before constructing requests so malformed configuration cannot produce invalid hosts.
export function normalizeBackendUrl(value: unknown): string {
  if (typeof value !== 'string') return '';
  const normalized = value.trim().replace(/^VITE_[A-Z0-9_]+=\s*/i, '').replace(/\/$/, '');
  if (!normalized) return '';
  try {
    const parsed = new URL(normalized);
    if (!['http:', 'https:'].includes(parsed.protocol)) return '';
    return parsed.toString().replace(/\/$/, '');
  } catch (err) {
    // অবৈধ URL → খালি স্ট্রিং fallback, তবে কারণটা লগে থাকবে।
    console.warn('[api] backend URL normalization failed, using empty fallback:', err);
    return '';
  }
}

// এক বিল্ডে User + Admin দুই context-ই থাকে, তাই backend নির্বাচন এখন RUNTIME সিদ্ধান্ত:
//  - '/admin-api' path অথবা /admin/* route context → admin backend (থাকলে)
//  - বাকি সব → user backend
// Firebase hosting external rewrite proxy সাপোর্ট করে না, তাই Firebase-এ সরাসরি backend URL ব্যবহার হয় (CORS allow)।
// Vercel-এ relative path ('') রাখা হয় কারণ Vercel external rewrite proxy সাপোর্ট করে।

/** User-context API calls-এর canonical backend URL (build-time resolved, runtime-picked) */
export const USER_BACKEND_URL: string = normalizeBackendUrl(
  import.meta.env.VITE_USER_BACKEND ||
    import.meta.env.VITE_API_BASE ||
    import.meta.env.VITE_API_URL ||
    import.meta.env.VITE_BACKEND_URL,
);

/** Admin-context API calls-এর canonical backend URL (build-time resolved, runtime-picked) */
export const ADMIN_BACKEND_URL: string =
  normalizeBackendUrl(import.meta.env.VITE_ADMIN_BACKEND) || USER_BACKEND_URL;

/** Optional Scraper backend URL (returns empty string if unset) */
export const SCRAPER_BACKEND_URL: string = normalizeBackendUrl(
  import.meta.env.VITE_SCRAPER_BACKEND ||
    import.meta.env.VITE_SCRAPER_URL ||
    import.meta.env.VITE_SCRAPER_SERVICE_URL,
);

export function isScraperConfigured(): boolean {
  return Boolean(SCRAPER_BACKEND_URL);
}

// 🔬 Export circuits for monitoring
export const circuits = { api: apiCircuit, websocket: wsCircuit };
export type { CircuitState };

// 🔒 RUNTIME VALIDATION - Missing backend = degraded viewer mode, NOT a white screen.
// FIX (P0, review 2026-09-12): আগে এখানে module-scope `throw` ছিল — import টাইমেই
// পুরো React অ্যাপ white-screen হয়ে যেত (Error Boundary-ও মাউন্ট হওয়ার আগেই)।
// vite.config.ts নিজেই "public viewer mode" সাপোর্ট করে; তাই এখন শুধু একটি
// `backendMissing` ফ্ল্যাগ export করা হয় — অ্যাপ চাইলে কনফিগ-এরর ব্যানার দেখাতে পারে।
export const backendMissing: boolean = import.meta.env.PROD && !USER_BACKEND_URL;
if (backendMissing) {
  console.error(
    '❌ VITE_API_URL or VITE_BACKEND_URL is required in production. ' +
      'App will run in degraded viewer mode until the backend URL is configured.',
  );
}

/**
 * বাংলা: এই call টি admin-context কিনা — path prefix (per-call) অথবা
 * current route context (/admin/*) দেখে নির্ধারিত হয়। Env var দিয়ে নয়।
 */
export function isAdminContextPath(path?: string): boolean {
  if (path && (path.startsWith('/admin-api') || path.startsWith('/api/admin'))) return true;
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')) return true;
  return false;
}

/**
 * বাংলা: runtime backend URL নির্বাচন — কোনো build-time portal identity নেই।
 * @param path API call-এর path (যেমন '/admin-api/deploy') — থাকলে per-call precision
 */
export function getBackendUrl(path?: string): string {
  if (isAdminContextPath(path) && ADMIN_BACKEND_URL) return ADMIN_BACKEND_URL;
  return USER_BACKEND_URL || ADMIN_BACKEND_URL;
}

/**
 * @deprecated বাংলা: পুরোনো portal-pinned constant — শুধু backward compatibility।
 * নতুন কোডে getBackendUrl(path) / getApiBaseUrl(path) ব্যবহার করুন।
 */
export const BACKEND_URL: string = USER_BACKEND_URL;

export const getApiBaseUrl = (path?: string): string => {
  if (typeof window === 'undefined') {
    // বাংলা মন্তব্য: SSR/Node.js কনটেক্সটে সরাসরি backend URL
    const backend = getBackendUrl(path);
    if (!backend && import.meta.env.PROD) throw new Error('API URL missing in production');
    return backend;
  }

  // ���� DYNAMIC: Configure via explicit VITE_USE_RELATIVE_PATH boolean flag
  if (import.meta.env.VITE_USE_RELATIVE_PATH === 'true') {
    return '';
  }

  // Firebase, Vercel ও বাকি সব হোস্টে সরাসর��� backend URL — runtime context অনুযায়ী

  // Firebase ও বাকি হোস্টে (local dev ইত্যাদি) সরাসররি backend URL — runtime context অনুযায়ী
  return getBackendUrl(path);
};

/**
 * 🔬 Evolution v3.0: Health check for backend connectivity
 */
export async function checkBackendHealth(): Promise<{
  healthy: boolean;
  latency?: number;
  error?: string;
}> {
  const start = performance.now();
  try {
    const response = await fetchWithRetry(`${getApiBaseUrl()}/api/v1/health/live`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    });
    return {
      healthy: response.ok,
      latency: Math.round(performance.now() - start),
    };
  } catch (error) {
    return {
      healthy: false,
      latency: Math.round(performance.now() - start),
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

export interface WorkspaceCapabilityConnection {
  id: string;
  tenant_id: string;
  actor_id: string;
  url: string;
  name: string;
  connection_type: string;
  permission_level: string;
  status: string;
  capabilities: Array<Record<string, unknown>>;
  tool_permissions: Record<string, string>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

async function capabilityRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetchWithRetry(`${getApiBaseUrl('/api/v1/workspace')}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  });
  if (!response.ok) throw new Error(`Capability request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const workspaceCapabilitiesApi = {
  list: () => capabilityRequest<{ capabilities: WorkspaceCapabilityConnection[] }>('/api/v1/workspace/capabilities'),
  register: (payload: { url: string; name: string; connection_type?: string }) => capabilityRequest<{ connection: WorkspaceCapabilityConnection }>('/api/v1/workspace/capabilities', { method: 'POST', body: JSON.stringify(payload) }),
  health: (id: string) => capabilityRequest<{ connection: WorkspaceCapabilityConnection }>(`/api/v1/workspace/capabilities/${id}/health`, { method: 'POST' }),
  reactivate: (id: string) => capabilityRequest<{ connection: WorkspaceCapabilityConnection }>(`/api/v1/workspace/capabilities/${id}/reactivate`, { method: 'POST' }),
  revoke: (id: string) => capabilityRequest<{ connection: WorkspaceCapabilityConnection }>(`/api/v1/workspace/capabilities/${id}/revoke`, { method: 'POST' }),
};

export const getWsBaseUrl = (): string => getWebSocketBaseUrl();

export const getWebSocketBaseUrl = (): string => {
  // বাংলা মন্তব্য: এক্সপ্লিসিট override সবার আগে
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL;
  }

  // বাংলা (single-frontend migration): runtime context-aware backend
  const backendUrl = getBackendUrl();
  const apiBase = getApiBaseUrl();

  // 🔥 ফিক্স: Firebase hosting-এ apiBase === '' (relative path)।
  // WebSocket Firebase rewrite proxy দিয়ে যায় না — সরাসরি Render-এর wss:// URL ব্যবহার করতে হবে।
  if (apiBase === '') {
    return backendUrl.replace(/^https:\/\//, 'wss://');
  }

  if (apiBase.startsWith('https://')) {
    return apiBase.replace(/^https:\/\//, 'wss://');
  }
  if (apiBase.startsWith('http://')) {
    return apiBase.replace(/^http:\/\//, 'ws://');
  }

  const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';

  if (typeof window === 'undefined') {
    if (!backendUrl) {
      if (import.meta.env.PROD) {
        throw new Error('❌ Backend URL is required in production SSR.');
      }
      return '';
    }
    const backendProtocol = backendUrl.startsWith('https:') ? 'wss:' : 'ws:';
    return `${backendProtocol}//${backendUrl.replace(/^https?:\/\//, '')}`;
  }

  return `${protocol}//${window.location.host}`;
};
