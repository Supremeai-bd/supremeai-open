/// <reference types="vite/client" />

// Issue #554 (FE-12): declare every VITE_* variable actually read via
// `import.meta.env` across frontend/src. Vite injects env values as strings
// (or undefined when unset), so every entry is `readonly X?: string`.

interface ImportMetaEnv {
  // --- API / backend endpoints ---
  readonly VITE_API_BASE?: string;
  readonly VITE_API_URL?: string;
  readonly VITE_BACKEND_URL?: string;
  readonly VITE_USER_BACKEND?: string;
  readonly VITE_ADMIN_BACKEND?: string;
  readonly VITE_WORKER_URL?: string;
  readonly VITE_ECOSYSTEM_API_URL?: string;
  readonly VITE_MCP_CONTROL_PLANE_URL?: string;
  readonly VITE_ADMIN_FRONTEND_URL?: string;
  readonly VITE_USE_RELATIVE_PATH?: string;

  // --- Scraper backend (canonical + aliases) ---
  readonly VITE_SCRAPER_BACKEND?: string;
  readonly VITE_SCRAPER_URL?: string;
  readonly VITE_SCRAPER_SERVICE_URL?: string;

  // --- WebSocket ---
  readonly VITE_DASHBOARD_WS_URL?: string;
  readonly VITE_WS_BASE_URL?: string;

  // --- Request tuning / resilience ---
  readonly VITE_API_CONCURRENCY?: string;
  readonly VITE_MAX_CONCURRENCY?: string;
  readonly VITE_API_TIMEOUT_MS?: string;
  readonly VITE_MAX_RETRIES?: string;
  readonly VITE_CIRCUIT_FAILURE_THRESHOLD?: string;
  readonly VITE_CIRCUIT_RECOVERY_MS?: string;

  // --- Firebase ---
  readonly VITE_FIREBASE_API_KEY?: string;
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string;
  readonly VITE_FIREBASE_PROJECT_ID?: string;
  readonly VITE_FIREBASE_STORAGE_BUCKET?: string;
  readonly VITE_FIREBASE_MESSAGING_SENDER_ID?: string;
  readonly VITE_FIREBASE_APP_ID?: string;
  readonly VITE_FIREBASE_AUTH_URL?: string;

  // --- Infra service health probes (ServiceHealthMonitor) ---
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_FIRESTORE_URL?: string;
  readonly VITE_EDGE_WORKER_URL?: string;
  readonly VITE_GITHUB_API_URL?: string;
  readonly VITE_VERCEL_API_URL?: string;
  readonly VITE_KROGGER_URL?: string;
  readonly VITE_INFISICAL_URL?: string;

  // SECURITY (#2510): Upstash Redis env declarations were REMOVED on purpose.
  // Upstash REST tokens are server-side admin credentials — a VITE_ prefix
  // bakes them into the browser bundle. Cache features that need Redis must
  // go through a backend proxy route that holds the token.

  // --- Feature flags / runtime config ---
  readonly VITE_UNIFIED_STORE?: string;
  readonly VITE_SELF_HEALING?: string;
  readonly VITE_COST_GUARD?: string;
  readonly VITE_DEFAULT_ADMIN_EMAIL?: string;

  // --- Non-VITE-prefixed legacy reads ---
  readonly NEXT_PUBLIC_API_URL?: string;
  readonly NEXT_PUBLIC_DASHBOARD_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __APP_BUILD_TIME__: string;
