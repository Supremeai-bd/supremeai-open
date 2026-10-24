// Centralized API Client for SupremeAI 2.0
// Viewer rule: keep ordinary page reads behind this boundary. The backend owns
// authorization and policy; do not duplicate backend orchestration in components.
// বাংলা মন্তব্য: এটি অ্যাপ্লিকেশনের সেন্ট্রাল এপিআই ক্লায়েন্ট যা হেডার, টোকেন এবং সিকিউর রেট লিমিট (429) / ভ্যালিডেশন এরর ইন্টারসেপ্ট করে।

import { getApiBaseUrl } from '../utils/api';
import { buildUrl } from '@supremeai/shared-services';
import { getDeviceFingerprint } from '../utils/deviceFingerprint';
import { clearAdminToken, clearUserToken, getAdminToken, getUserToken, setUserToken } from './tokenStorage';
import PQueue from 'p-queue';

// বাংলা মন্তব্য: কাস্টম এরর ক্লাস — status প্রপার্টি দিয়ে React Query retry ফাংশন সঠিকভাবে 401/403/429 চিহ্নিত করতে পারে
export class ApiError extends Error {
  status: number;
  // Issue #685 (Domain 15): backend-echoed request correlation id (X-Request-ID
  // response header, or the correlation_id field of the error payload) — lets
  // user-reported failures be matched to the backend's structured logs.
  requestId?: string;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// Dynamic concurrency queue — env-configurable (VITE_API_CONCURRENCY) with safe default of 3.
// বাংলা: কনকারেন্সি এখন env var দিয়ে কনফিগারযোগ্য — প্রোডাকশনে আরও বেশি রিকোয়েস্ট সমান্তরালে।
const DEFAULT_CONCURRENCY = Number(import.meta.env.VITE_API_CONCURRENCY ?? 3);
const _concurrency = Number.isFinite(DEFAULT_CONCURRENCY) && DEFAULT_CONCURRENCY > 0
  ? DEFAULT_CONCURRENCY
  : 3;
export const requestQueue = new PQueue({ concurrency: _concurrency });

export const setApiConcurrency = (concurrency: number) => {
  requestQueue.concurrency = concurrency;
};

let cachedToken: string | null = null;

// বাংলা: authStore/adminStore থেকে টোকেন সেট/ক্লিয়ার হলে এই event ফায়ার হয়,
// যাতে App root-এ mount থাকা ThemeSyncProvider token আসা/যাওয়ার সাথে সাথে
// reactively connect/disconnect করতে পারে, পুরো component tree remount না হয়েও।
// সততা নোট (honesty fix): SSE hook useServerStream এই event listen করে, কিন্তু
// তার কোনো runtime importer নেই — বর্তমানে unmounted/dead, global-mounted নয়।
export const AUTH_CHANGED_EVENT = 'supremeai:auth-changed';

export const updateTokenCache = (token: string | null) => {
  cachedToken = token;
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT, { detail: { hasToken: !!token } }));
  }
};

// বাংলা: লগআউট/সেশন মেয়াদোত্তীর্ণ হলে cachedToken ও localStorage উভয় জায়গা থেকে
// টোকেন মুছে ফেলতে হবে। নাহলে পরবর্তী রিকোয়েস্টে পুরোনো টোকেন ব্যবহার হতো।
export const clearAuthToken = (): void => {
  cachedToken = null;
  if (typeof window !== 'undefined') {
    try {
      // Issue #521 (FE-04): tokenStorage sweep — sessionStorage primary,
      // legacy localStorage entries removed too.
      clearUserToken();
      localStorage.removeItem('adminToken'); // বাংলা: legacy duplicate key — migration sweep

      // 🛡️ ISSUE #495: ব্যবহারকারী টোকেন শেষ হলে বা ব্যাকগ্রাউন্ড কল ফেইল করলে সচল admin JWT মোছা যাবে না।
      // শুধুমাত্র যদি admin টোকেনটি স্পষ্টভাবে মেয়াদোত্তীর্ণ হয়, তবেই এটি পরিষ্কার করা হবে।
      const adminToken = getAdminToken();
      if (adminToken) {
        try {
          const part = adminToken.split('.')[1];
          if (part) {
            const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
            const payload = JSON.parse(decodeURIComponent(atob(base64).split('').map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')));
            if (typeof payload?.exp === 'number' && payload.exp * 1000 <= Date.now()) {
              clearAdminToken();
            }
          }
        } catch {
          clearAdminToken();
        }
      }
    } catch (e) {
      // বাংলা: localStorage অনুপস্থিত (incognito / SSR) — নীরবে বাদ দেওয়া।
      console.warn("Failed to clear local storage", e);
    }
  }
  // বাংলা (single-frontend migration, roadmap Phase 2): টোকেন মুছলেই store status রিসেট
  // হতে হবে — নাহলে ProtectedRoute পুরোনো authStore.status='loggedIn' দেখে guarded page
  // দেখাতে থাকে (token/store desync বাগ)। Dynamic import ব্যবহার হচ্ছে circular
  // dependency এড়াতে (authStore এই মডিউলকে statically import করে)।
  if (typeof window !== 'undefined') {
    import('../store/authStore')
      .then(({ clearCanonicalSession }) => clearCanonicalSession())
      .catch(() => {
        // বাংলা: authStore লোড ব্যর্থ হলেও token পরিষ্কার হয়ে গেছে — নীরবে এগোনো যথেষ্ট।
      });
  }
};

// বাংলা মন্তব্য: SSE (EventSource) হেডার পাঠাতে পারে না, তাই টোকেন query param হিসেবে পাঠাতে হয়।
// admin token (supreme_admin_jwt) থাকলে তা প্রিফার করি, নচেৎ ইউজার token (supremeai_auth_token)।
export const getRawToken = (): string | null => {
  if (typeof window === 'undefined') return cachedToken;
  // Issue #521: tokenStorage reads (sessionStorage first, legacy localStorage swept).
  const admin = getAdminToken();
  if (admin) return admin;
  const user = getUserToken();
  if (user) return user;
  return cachedToken;
};

const isDev = () => {
  return Boolean(import.meta.env?.DEV);
};

const getCSRFToken = (): string => {
  // Get CSRF token from cookie or meta tag
  const metaTag = document.querySelector('meta[name="csrf-token"]');
  if (metaTag) return metaTag.getAttribute('content') || '';
  const cookieMatch = document.cookie.match(/(?:^|;\s*)supreme_csrf_token=([^;]+)/);
  return cookieMatch ? cookieMatch[1] : '';
};

export const getAuthHeaders = async (): Promise<Record<string, string>> => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // 🟢 Sprint 5: Backend API Integration
  if (cachedToken === null) {
    // Issue #521: tokenStorage reads (sessionStorage first, legacy localStorage swept).
    cachedToken = getAdminToken() || getUserToken() || '';
  }

  // 🔥 ফিক্স: admin-api endpoint গুলো admin-role JWT (`supreme_admin_jwt`) চায়।
  // admin dashboard ব্যবহার করলে admin token-ই Bearer হিসেবে পাঠানো হবে (প্রিফারেন্স), নচেৎ ইউজার token।
  const adminToken = getAdminToken();
  const effectiveToken = adminToken || cachedToken;

  if (effectiveToken) {
    headers['Authorization'] = `Bearer ${effectiveToken}`;
  }

  // 🔐 CSRF Protection
  const csrfToken = getCSRFToken();
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  // 🔐 Phase 2: Hybrid Fingerprint Login — AntiHackingContextMiddleware ব্যবহার করে
  // IP/country-এর পাশাপাশি তৃতীয় কনটেক্সট সিগন্যাল হিসেবে
  try {
    headers['X-Device-Fingerprint'] = await getDeviceFingerprint();
  } catch (e) {
    // বাংলা: WebCrypto অনুপস্থিত থাকলে (পুরনো ব্রাউজার) নীরবে বাদ দেওয়া হচ্ছে — request ব্লক হবে না
    console.warn("Failed to get device fingerprint", e);
  }

  // Issue #685 (Domain 15): one fresh correlation id per HTTP request. The
  // backend CORS allow-list already includes X-Request-ID, so no preflight
  // change is needed.
  headers['X-Request-ID'] = buildRequestId();

  return headers;
};

const handleResponse = async (res: Response) => {
  // Issue #685 (Domain 15): capture the correlation id echoed by the backend.
  // Readable because backend CORS expose_headers now lists X-Request-ID /
  // X-Correlation-ID (app_builder.py); falls back to the id we sent.
  const requestId = res.headers?.get('X-Request-ID') || res.headers?.get('X-Correlation-ID');
  if (requestId) lastRequestId = requestId;

  // 🔐 Phase 2 JIT-OTP Interceptor — Status 202 Accepted means JIT OTP is required
  if (res.status === 202) {
    const data = await res.json().catch(() => ({}));
    return {
      success: false,
      requiresOTP: true,
      message: data.message || 'JIT OTP verification required',
      data,
    };
  }

  if (!res.ok) {
    let errMsg = `HTTP error! status: ${res.status}`;
    try {
      const errData = await res.json();
      if (errData.detail) {
        errMsg = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail);
      } else if (errData.message) {
        errMsg = typeof errData.message === 'string' ? errData.message : JSON.stringify(errData.message);
      }
    } catch (e) {
      // JSON parsing failure fallback
      console.warn("Failed to parse error response JSON", e);
    }

    // Issue #685 (Domain 15): every thrown ApiError carries the correlation id.
    const apiError = (msg: string): ApiError => {
      const err = new ApiError(msg, res.status);
      err.requestId = requestId || lastRequestId || undefined;
      return err;
    };

    // 🛑 ZERO-GAP: Intercept specific critical HTTP exception statuses
    if (res.status === 429) {
      if (isDev()) console.warn("Rate limit exceeded (429). Throttling client requests.");
      throw apiError(`Rate limit exceeded: ${errMsg}. Please wait before retrying.`);
    }
    if (res.status === 402) {
      if (isDev()) console.warn("Payment/Budget Required (402). CostGuard rejected the request.");
      throw apiError(`Budget Limit Exceeded: ${errMsg}`);
    }
    if (res.status === 422) {
      if (isDev()) console.error("Validation error (422) detected in payload schema.");
      throw apiError(`Validation Error: ${errMsg}`);
    }
    if (res.status === 401 || res.status === 403) {
      if (isDev()) console.warn("Authorization failure (401/403). Session invalidated.");
      // বাংলা মন্তব্য (ROOT-CAUSE FIX): এই ফাংশন সব apiClient কল (background queries,
      // SSE-এর মতো non-critical এন্ডপয়েন্টসহ) হ্যান্ডেল করে। আগে যেকোনো একটা ক্ষণস্থায়ী
      // 401 (Redis blip, cold-start রেসিং কল) এলেই admin JWT ক্লিয়ার হয়ে যেত, ফলে পরের
      // রিকোয়েস্টগুলোও token-less হয়ে ব্যর্থ হতো এবং পুরো সেশন কার্যত লগআউট হয়ে যেত —
      // এটাই ছিল TOTP ভেরিফাই সফল হওয়ার পরপরই ড্যাশবোর্ড থেকে auto-logout হওয়ার মূল কারণ।
      // তাই নন-ক্রিটিক্যাল/ব্যাকগ্রাউন্ড এন্ডপয়েন্ট থেকে 401 এলে টোকেন ক্লিয়ার করা হবে না।
      const SESSION_VALIDATION_PATHS = [
        '/api/v1/auth/me',
        '/api/v1/auth/logout',
      ];
      const isSessionValidation = SESSION_VALIDATION_PATHS.some((p) => res.url?.includes(p));
      // A failed background or feature request must not destroy a valid login.
      // Only an explicit logout or confirmed termination should clear auth tokens.
      if ((res.status === 401 || res.status === 403) && isSessionValidation) {
        clearAuthToken();
      }
      throw apiError(errMsg);
    }
    throw apiError(errMsg);
  }
  return res.json();
};

// বাংলা মন্তব্য: রেন্ডার ফ্রি টিয়ার কোল্ড স্টার্ট (Wake up time ৩০-৫০ সেকেন্ড) সামলাতে এপিআই রিকোয়েস্ট টাইমআউট ৬০ সেকেন্ডে বৃদ্ধি করা হলো।
const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60000);

const fetchWithTimeout = async (url: string, options: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Response> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  // বাংলা মন্তব্য: JSDOM এবং node-fetch-এর সাথে AbortSignal টাইপ অমিল এড়াতে টেস্ট এনভায়রনমেন্টে signal বাদ দেওয়া হচ্ছে।
  const fetchOptions: RequestInit = { ...options };
  const isTest = typeof process !== 'undefined' && (process.env.NODE_ENV === 'test' || process.env.VITEST === 'true');
  if (!isTest) {
    // Issue #2522: কলার নিজের signal (stop button / probe timeout) পাঠালে তা
    // timeout signal-এর সাথে combine হয় — দুটির যেকোনো একটি ফায়ার করলেই abort।
    // আগে কলারের signal নীরবে ওভাররাইট হয়ে যেত, ফলে UI abort কাজ করত না।
    const callerSignal = options.signal;
    const signalAny = typeof AbortSignal !== 'undefined'
      ? (AbortSignal as unknown as { any?: (...signals: AbortSignal[]) => AbortSignal }).any
      : undefined;
    if (callerSignal && callerSignal.aborted) {
      fetchOptions.signal = callerSignal;
    } else if (callerSignal && typeof signalAny === 'function') {
      fetchOptions.signal = signalAny.call(AbortSignal, controller.signal, callerSignal);
    } else {
      fetchOptions.signal = controller.signal;
    }
  }

  try {
    return await fetch(url, fetchOptions);
  } catch (e) {
    if (controller.signal.aborted) {
      throw new Error(`Request timed out after ${timeoutMs}ms: ${url}`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
};

// বাংলা মন্তব্য: throttledFetch — p-queue দিয়ে একসাথে অতিরিক্ত রিকোয়েস্ট না যাওয়ার নিশ্চয়তা
const throttledFetch = async (url: string, options: RequestInit): Promise<Response> => {
  return requestQueue.add(async () => {
    const currentUrl = url;
    let attempts = 0;
    // FINAL-TEST FIX: mutate a shallow copy, not the caller's options object —
    // callers that reuse their options object across requests were being
    // silently modified (and could not opt out of cookie sending).
    const fetchOptions: RequestInit = { ...options, credentials: 'include' };

    // Issue #1679 (cold-start retry hardening): 2 attempts with linear 2s/4s
    // backoff was not enough for Render free-tier cold starts (30-50s).
    // Now: 4 attempts total with exponential backoff + jitter
    // (2^attempt * 2s + random(0..1s)) — 2s→~4-5s→~8-9s→~16-17s.
    const MAX_ATTEMPTS = 4;

    while (attempts < MAX_ATTEMPTS) {
      try {
        const res = await fetchWithTimeout(currentUrl, fetchOptions);
        // 502/503/504 মানে রেন্ডার সার্ভার স্লিপিং বা ডাউন — একই backend-এ রিট্রাই করব
        if (res.status >= 502 && res.status <= 504) {
          throw new Error("Server sleeping or down (50x)");
        }
        return res;
      } catch (e: unknown) {
        // Issue #2522: কলার abort (stop button / unmount) হলে retry অর্থহীন ও
        // ক্ষতিকর — বাতিল করা অনুরোধ ৪ বার পাঠানো হতো। সঙ্গে সঙ্গে ছড়িয়ে দিই।
        if (fetchOptions.signal?.aborted) throw e;
        attempts++;
        if (attempts >= MAX_ATTEMPTS) {
          if (isDev()) console.error(`[Queue Interceptor] Network failure for ${currentUrl} after ${MAX_ATTEMPTS} attempts:`, e);
          throw e;
        }

        // বাংলা মন্তব্য: একই URL-এ exponential backoff + jitter রিট্রাই — backend
        // কখনোই পাল্টানো হয় না (portal isolation)। Render free tier cold start
        // (৩০-৫০ সেকেন্ড) সামলাতে #1679 অনুযায়ী সূচকীয় ব্যাকঅফ + র‍্যান্ডম জিটার।
        const delayMs = Math.round(Math.pow(2, attempts) * 2000 + Math.random() * 1000);
        if (isDev()) console.warn(`[Retry] Network error: ${(e as Error).message}. Retrying same backend in ${delayMs}ms (attempt ${attempts + 1}/${MAX_ATTEMPTS})...`);
        await new Promise(resolve => setTimeout(resolve, delayMs));
      }
    }
    throw new Error("Backend request failed after retries");
  }) as Promise<Response>;
};

// ERR-S02 RESOLVED (2026-09-16): the backend's CORS allow-list now includes
// 'Idempotency-Key' (backend/core/app_builder.py — and api/server.py kept in
// sync), so the preflight failure described below can no longer happen.
// The scoped injection below is intentionally KEPT: the backend
// (backend/api/middleware.py → IDEMPOTENCY_PATHS) still REQUIRES the header
// on a small set of mutating paths (/api/task, /api/github,
// /api/auth/callback, /api/pr, /api/agent) — sending it only there both
// satisfies the middleware and keeps the CORS preflight surface minimal for
// every other call.
const IDEMPOTENCY_REQUIRED_PREFIXES = [
  '/api/task',
  '/api/github',
  '/api/auth/callback',
  '/api/pr',
  '/api/agent',
] as const;

export const pathRequiresIdempotencyKey = (url: string): boolean => {
  try {
    const base = typeof window !== 'undefined' ? window.location.origin : 'https://api.internal';
    const { pathname } = new URL(url, base);
    return IDEMPOTENCY_REQUIRED_PREFIXES.some((p) => pathname.startsWith(p));
  } catch (err) {
    // Malformed URL — err on the side of NOT sending the header (it can only
    // cause a CORS preflight failure; the middleware only enforces the 5
    // prefixes above, and a malformed URL can never reach them).
    console.warn('[api-client] URL parse failed, skipping idempotency header:', err);
    return false;
  }
};

const buildIdempotencyKey = (): string =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Issue #685 (Domain 15): per-request correlation id. The backend
// (SupremeContext/RequestId middleware) honors this header, echoes it back on
// the response, and uses it as the correlation id in its structured logs and
// LLM telemetry — one id end-to-end.
const buildRequestId = (): string =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Last correlation id seen on a backend response (success or error) — exposed
// for error reporting/support flows.
// ── Issue #1673: transparent token refresh ──────────────────────────────────
// বাংলা: access token মেয়াদোত্তীর্ণ হলে (401) সরাসরি লগআউটের বদলে প্রথমে
// /api/v1/auth/refresh ডাকা হয় (refresh token httpOnly cookie-তে থাকে,
// credentials:'include' দিয়ে যায়)। সফল হলে নতুন access token দিয়ে একবার
// মূল request রিট্রাই হয়। single-flight mutex — একসাথে ২০টা 401 এলেও
// refresh ঠিক একবারই হবে। refresh-exempt পাথ (login/register/refresh/me/
// logout) কখনো রিট্রাই হবে না, নাহলে লুপ তৈরি হতো।
const REFRESH_PATH = '/api/v1/auth/refresh';
const REFRESH_EXEMPT_PATHS = [
  REFRESH_PATH,
  '/api/v1/auth/login',
  '/api/v1/auth/register',
  '/api/v1/auth/me',
  '/api/v1/auth/logout',
];

let refreshInFlight: Promise<boolean> | null = null;

const tryRefreshSession = async (): Promise<boolean> => {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(buildUrl(getApiBaseUrl(REFRESH_PATH), REFRESH_PATH), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({}),
        });
        if (!res.ok) return false;
        const data = (await res.json().catch(() => null)) as { access_token?: string } | null;
        const newToken = data?.access_token;
        if (!newToken) return false;
        setUserToken(newToken);
        updateTokenCache(newToken);
        if (isDev()) console.warn('[Auth] Session refreshed via /auth/refresh after 401.');
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
};

const withAuthRetry = async <T>(path: string, attempt: () => Promise<T>): Promise<T> => {
  try {
    return await attempt();
  } catch (e) {
    const isAuthFailure = e instanceof ApiError && e.status === 401;
    const isExempt = REFRESH_EXEMPT_PATHS.some((p) => path.includes(p));
    if (!isAuthFailure || isExempt) throw e;
    const refreshed = await tryRefreshSession();
    if (!refreshed) throw e;
    return attempt();  // single retry with the fresh access token
  }
};

let lastRequestId: string = '';
export const getLastRequestId = (): string => lastRequestId;

export const apiClient = {
  get: async <T>(path: string, options?: RequestInit): Promise<T> => {
    // FIX (P1, review 2026-09-12): `options` was spread LAST, so a caller passing
    // `options.headers` silently REPLACED the merged auth headers. Spread options
    // first, then re-assert the computed method/headers/body.
    return withAuthRetry(path, async () => {
      const res = await throttledFetch(buildUrl(getApiBaseUrl(path), path), {
        ...options,
        method: 'GET',
        headers: {
          ...(options?.headers as Record<string, string>),
          ...(await getAuthHeaders()),
        },
      });
      return handleResponse(res);
    });
  },

  post: async <T>(path: string, body?: unknown, options?: RequestInit): Promise<T> => {
    const authHeaders = await getAuthHeaders();
    const finalUrl = buildUrl(getApiBaseUrl(path), path);
    if (
      !authHeaders['Idempotency-Key'] &&
      !(options?.headers as Record<string, string>)?.['Idempotency-Key'] &&
      pathRequiresIdempotencyKey(finalUrl)
    ) {
      authHeaders['Idempotency-Key'] = buildIdempotencyKey();
    }
    return withAuthRetry(path, async () => {
      const res = await throttledFetch(finalUrl, {
        // FIX (P1, review 2026-09-12): options first — see get() above.
        ...options,
        method: 'POST',
        headers: {
          ...(options?.headers as Record<string, string>),
          ...authHeaders,
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse(res);
    });
  },

  put: async <T>(path: string, body?: unknown, options?: RequestInit): Promise<T> => {
    const authHeaders = await getAuthHeaders();
    const finalUrl = buildUrl(getApiBaseUrl(path), path);
    if (
      !authHeaders['Idempotency-Key'] &&
      !(options?.headers as Record<string, string>)?.['Idempotency-Key'] &&
      pathRequiresIdempotencyKey(finalUrl)
    ) {
      authHeaders['Idempotency-Key'] = buildIdempotencyKey();
    }
    return withAuthRetry(path, async () => {
      const res = await throttledFetch(finalUrl, {
        // FIX (P1, review 2026-09-12): options first — see get() above.
        ...options,
        method: 'PUT',
        headers: {
          ...(options?.headers as Record<string, string>),
          ...authHeaders,
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse(res);
    });
  },

  // ERR-B02 (defect register 2026-09-15): multipart upload path. Unlike post(),
  // the body is passed through untouched (FormData) and NO Content-Type header is
  // set — the browser must generate the multipart boundary itself.
  postForm: async <T>(path: string, body: FormData, options?: RequestInit): Promise<T> => {
    const authHeaders = await getAuthHeaders();
    delete authHeaders['Content-Type'];
    return withAuthRetry(path, async () => {
      const res = await throttledFetch(buildUrl(getApiBaseUrl(path), path), {
        ...options,
        method: 'POST',
        headers: {
          ...(options?.headers as Record<string, string>),
          ...authHeaders,
        },
        body,
      });
      return handleResponse(res);
    });
  },

  patch: async <T>(path: string, body?: unknown, options?: RequestInit): Promise<T> => {
    const authHeaders = await getAuthHeaders();
    const finalUrl = buildUrl(getApiBaseUrl(path), path);
    if (
      !authHeaders['Idempotency-Key'] &&
      !(options?.headers as Record<string, string>)?.['Idempotency-Key'] &&
      pathRequiresIdempotencyKey(finalUrl)
    ) {
      authHeaders['Idempotency-Key'] = buildIdempotencyKey();
    }
    return withAuthRetry(path, async () => {
      const res = await throttledFetch(finalUrl, {
        // FIX (P1, review 2026-09-12): options first — see get() above.
        ...options,
        method: 'PATCH',
        headers: {
          ...(options?.headers as Record<string, string>),
          ...authHeaders,
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      return handleResponse(res);
    });
  },

  delete: async <T>(path: string, options?: RequestInit): Promise<T> => {
    // FIX (P1, review 2026-09-12): options first — see get() above.
    return withAuthRetry(path, async () => {
      const res = await throttledFetch(buildUrl(getApiBaseUrl(path), path), {
        ...options,
        method: 'DELETE',
        headers: {
          ...(options?.headers as Record<string, string>),
          ...(await getAuthHeaders()),
        },
      });
      return handleResponse(res);
    });
  },

  performSensitiveAction: async <T>(path: string, body?: unknown, otpCode?: string): Promise<T> => {
    const headers = await getAuthHeaders();
    if (otpCode) {
      headers['X-JIT-OTP'] = otpCode;
    }
    const res = await throttledFetch(buildUrl(getApiBaseUrl(path), path), {
      method: 'POST',
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    return handleResponse(res);
  },

  // Issue #2522: streaming/raw-response path — SSE, audio, blob download-এর জন্য।
  // throttledFetch-এর সব সুবিধা (concurrency queue, connect-timeout, cold-start
  // 50x retry) থাকে, কিন্তু handleResponse/response.json() হয় না — কলার নিজের
  // মতো body stream পড়ে। `auth: false` দিলে Authorization হেডার যায় না
  // (public endpoint)। connect-phase timeout শেষ হলে body streaming বন্ধ হয় না —
  // fetchWithTimeout-এর finally clearTimeout হেডার আসার সাথে সাথেই টাইমার মুছে দেয়।
  stream: async (path: string, options?: RequestInit & { auth?: boolean }): Promise<Response> => {
    const { auth = true, ...init } = options ?? {};
    const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
    if (auth) Object.assign(headers, await getAuthHeaders());
    return throttledFetch(buildUrl(getApiBaseUrl(path), path), { ...init, headers });
  },

  // 🟢 Non-blocking Telemetry / Background Check (10s timeout, silent fallback)
  // বাংলা মন্তব্য: Telemetry বা Analytics এর জন্য Non-blocking method, যা ফেইল করলে UI ক্র্যাশ করবে না।
  sendTelemetry: async <T>(path: string, body?: unknown, method: 'GET' | 'POST' = 'POST'): Promise<T | null> => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 seconds timeout

      const res = await fetch(buildUrl(getApiBaseUrl(path), path), {
        method,
        headers: await getAuthHeaders(),
        body: body && method === 'POST' ? JSON.stringify(body) : undefined,
        signal: controller.signal
      });

      clearTimeout(timeoutId);
      if (!res.ok) {
        return null; // Safe default value instead of throwing
      }
      return await res.json();
    } catch (e) {
      if (isDev()) console.warn(`[Telemetry] Silent fallback triggered (timeout or network error):`, e);
      return null; // Safe default value
    }
  },
};
