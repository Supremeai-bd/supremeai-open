import * as fs from "node:fs";
import * as path from "node:path";
import * as dotenv from "dotenv";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Type-safe environment loader — the SINGLE SSOT for environment config.
 * NEVER hardcodes values — only reads env var NAMES.
 *
 * Environment precedence (#109), highest first:
 *   1. Real process environment (shell export / Render / Docker injects).
 *   2. Repo-root `.env` file — loaded ONCE, below, by the only
 *      `dotenv.config()` call site in the codebase. dotenv never overrides
 *      already-set variables, so (1) always wins over (2).
 *   3. Infisical vault pull (`pullSecretsIntoProcessEnv()` in index.ts
 *      `main()`) — runs at boot AFTER this module has loaded, injecting
 *      vault secrets into process.env for lazy getters to pick up.
 *
 * This module is imported by index.ts BEFORE the rest of the tool/registry
 * import tree, so the `.env` file is available to every module body that
 * reads process.env at import time (client-registry.ts, tenant.registry.ts).
 */
const candidateEnvPaths = [
  path.resolve(__dirname, "../../../../.env"),
  path.resolve(__dirname, "../../../.env"),
  path.resolve(process.cwd(), ".env"),
  path.resolve(process.cwd(), "../../.env"),
];
for (const envPath of candidateEnvPaths) {
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath });
    break;
  }
}

function required(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`[env] Required env var missing: ${name}`);
  return v;
}

function optional(name: string, fallback = ""): string {
  return process.env[name] ?? fallback;
}

/**
 * Positive-integer knob (rate limits, timeouts, byte caps). Unset → fallback.
 * A set-but-invalid value (non-numeric, NaN, <= 0) FAILS LOUDLY (#109):
 * the old inline `Number(...) ?? fallback` parsing silently turned garbage
 * into NaN and NaN into the fallback, hiding misconfiguration.
 */
function positiveInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`[env] ${name} must be a positive number, got: ${JSON.stringify(raw)}`);
  }
  return Math.floor(value);
}

/**
 * Non-negative-integer knob (session caps, idle reap intervals). Unset →
 * fallback; 0 is meaningful ("disable the cap / never reap"); negative or
 * non-numeric fails loudly (same rationale as positiveInt).
 */
function nonNegativeInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`[env] ${name} must be a non-negative number, got: ${JSON.stringify(raw)}`);
  }
  return Math.floor(value);
}

function multiKey(name: string): string[] {
  const v = optional(name);
  const keys: string[] = v
    ? v
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean)
    : [];

  // Also discover numbered env vars ${NAME}_1, ${NAME}_2, ... (e.g. GEMINI_API_KEY_1, FIRECRAWL_API_KEY_1)
  for (let idx = 1; idx <= 20; idx++) {
    const nextVal = optional(`${name}_${idx}`);
    if (nextVal && !keys.includes(nextVal)) {
      keys.push(nextVal);
    }
  }

  return keys;
}

export const env = {
  // ── MCP Server
  // INF-05 fix (issue #528): Render injects PORT (not MCP_PORT) and probes
  // 0.0.0.0:$PORT for readiness — preferring MCP_PORT made the control plane
  // bind :3771 on Render, so port detection never saw a listener. Precedence:
  // PORT (Render) → MCP_PORT (docker-compose mcp service sets it) → 3771.
  get port(): number { return parseInt(optional("PORT", optional("MCP_PORT", "3771"))); },
  get mcpApiKey(): string { return optional("MCP_API_KEY"); },
  // ROOT-CAUSE FIX (#2720): the fallback `optional("MCP_ADMIN_KEY", optional("MCP_API_KEY"))`
  // made MCP_ADMIN_KEY silently equal MCP_API_KEY when unset. Combined with
  // index.ts:523 granting admin role to mcpApiKey holders, this meant the
  // "agent" key was effectively an admin key. Admin must be a SEPARATE key —
  // if MCP_ADMIN_KEY is unset, return empty (no admin access via env keys).
  get mcpAdminKey(): string { return optional("MCP_ADMIN_KEY"); },
  get mcpViewerKey(): string { return optional("MCP_VIEWER_KEY"); },
  get mcpAgentKey(): string { return optional("MCP_AGENT_KEY"); },
  get githubWebhookSecret(): string { return optional("GITHUB_WEBHOOK_SECRET"); },
  get cloudflareWebhookSecret(): string { return optional("CLOUDFLARE_WEBHOOK_SECRET"); },
  get nodeEnv(): string { return optional("NODE_ENV", "development"); },
  get backendUrl(): string { return optional("SUPREMEAI_BACKEND_URL"); },
  get backendServiceToken(): string { return optional("SUPREMEAI_BACKEND_SERVICE_TOKEN"); },

  // ── Render (5 accounts)
  render: {
    primary: {
      get apiKey(): string { return optional("RENDER_API_KEY_1", optional("RENDER_API_KEY")); },
      get serviceId(): string { return optional("RENDER_PRIMARY_SVC_ID"); },
      get url(): string { return optional("RENDER_PRIMARY_URL"); },
    },
    worker: {
      get apiKey(): string { return optional("RENDER_API_KEY_2"); },
      get serviceId(): string { return optional("RENDER_WORKER_SVC_ID"); },
      get url(): string { return optional("RENDER_WORKER_URL"); },
    },
    scraper: {
      get apiKey(): string { return optional("RENDER_API_KEY_3"); },
      get serviceId(): string { return optional("RENDER_SCRAPER_SVC_ID"); },
      get url(): string { return optional("RENDER_SCRAPER_URL"); },
    },
    controlTower: {
      // Fallback to RENDER_API_KEY mirrors render.primary above: render.yaml
      // declares RENDER_API_KEY (sync:false) for this service, while the
      // numbered RENDER_API_KEY_4 only exists when Infisical injects it.
      get apiKey(): string { return optional("RENDER_API_KEY_4", optional("RENDER_API_KEY")); },
      get serviceId(): string { return optional("RENDER_MCP_SVC_ID"); },
      get url(): string { return optional("RENDER_MCP_URL"); },
    },
    api: {
      get apiKey(): string { return optional("RENDER_API_KEY_5", optional("RENDER_API_KEY_API")); },
      get serviceId(): string { return optional("RENDER_API_SVC_ID", "srv-dbappass728c7396p580"); }, // gitleaks:allow
      get url(): string { return optional("RENDER_API_URL", "https://supremeai-api-ulw0.onrender.com"); },
    },
    brain: {
      get apiKey(): string { return optional("RENDER_API_KEY_6"); },
      get serviceId(): string { return optional("RENDER_BRAIN_SVC_ID", "srv-dabm7dfqj5pc738jkbmg"); },
      get url(): string { return optional("RENDER_BRAIN_URL", "https://supremeai-primary-node.onrender.com"); },
    },
  },

  // ── Supabase
  supabase: {
    get url(): string { return optional("SUPABASE_URL"); },
    get anonKey(): string { return optional("SUPABASE_KEY"); },
    get serviceRoleKey(): string { return optional("SUPABASE_SERVICE_ROLE_KEY"); },
    get dbUrl(): string { return optional("SUPABASE_DATABASE_URL"); },
  },

  // ── Redis / Upstash (dual mode)
  redis: {
    get restUrl(): string { return optional("UPSTASH_REDIS_REST_URL"); },
    get restToken(): string { return optional("UPSTASH_REDIS_REST_TOKEN"); },
    get url(): string { return optional("REDIS_URL"); }, // rediss:// protocol
  },

  // ── Infisical (machine identity — NOT token)
  infisical: {
    get clientId(): string { return optional("INFISICAL_CLIENT_ID"); },
    get clientSecret(): string { return optional("INFISICAL_CLIENT_SECRET"); },
    get projectId(): string { return optional("INFISICAL_PROJECT_ID"); },
    get environment(): string { return optional("INFISICAL_ENVIRONMENT", "production"); },
  },

  // ── GitHub
  github: {
    get token(): string { return optional("GITHUB_TOKEN", optional("GITHUB_API_TOKEN")); },
    get repo(): string { return optional("GITHUB_REPO", "Supremeai-bd/supremeai"); },
  },

  // ── Runtime knobs (#109) — rate limits, tool governance, session caps.
  // Every knob below previously existed ONLY as an inline
  // `Number(process.env[...])` parse in index.ts (NaN-propagating). They now
  // validate through positiveInt/nonNegativeInt: a garbage value throws
  // instead of silently degrading into a default. All lazy getters —
  // re-read on each access so runtime env changes stay observable.
  runtime: {
    /** Transport selector: "http" (default) or "stdio". */
    get transport(): string { return optional("MCP_TRANSPORT", "http"); },
    /** Per-IP /mcp sliding window (#695). */
    get mcpRateLimitMax(): number { return positiveInt("MCP_RATE_LIMIT_MAX", 60); },
    get mcpRateLimitWindowMs(): number { return positiveInt("MCP_RATE_LIMIT_WINDOW_MS", 60_000); },
    /** Tool governance caps (#686). */
    get toolPayloadMaxBytes(): number { return positiveInt("MCP_TOOL_PAYLOAD_MAX_BYTES", 262_144); },
    get toolResultMaxBytes(): number { return positiveInt("MCP_TOOL_RESULT_MAX_BYTES", 524_288); },
    get toolTimeoutMs(): number { return positiveInt("MCP_TOOL_TIMEOUT_MS", 30_000); },
    get toolRateLimitMax(): number { return positiveInt("MCP_TOOL_RATE_LIMIT_MAX", 20); },
    get toolRateLimitWindowMs(): number { return positiveInt("MCP_TOOL_RATE_LIMIT_WINDOW_MS", 60_000); },
    /** Anonymous-mutation plane bound (#2363 Option A): per-(caller IP, tool)
     *  hourly window on the 4 anonymous-reachable mutation tools. Default
     *  30 writes/hour/tool per IP — writes/hour scale, read plane untouched. */
    get mutationRateLimitMax(): number { return positiveInt("MCP_MUTATION_RATE_LIMIT_MAX", 30); },
    get mutationRateLimitWindowMs(): number { return positiveInt("MCP_MUTATION_RATE_LIMIT_WINDOW_MS", 3_600_000); },
    /** HTTP session hygiene: idle reap interval + bounded session tables. */
    get httpSessionIdleMs(): number { return nonNegativeInt("MCP_HTTP_SESSION_IDLE_MS", 3_600_000); },
    get maxSseSessions(): number { return nonNegativeInt("MCP_MAX_SSE_SESSIONS", 100); },
    get maxHttpSessions(): number { return nonNegativeInt("MCP_MAX_HTTP_SESSIONS", 100); },
    /** Pressure-admission floor (#1886): min idle age before a FULL /mcp table
     *  may evict its least-recently-active session to admit a fresh
     *  initialize. 0 = refuse-only (historical behavior preserved). */
    get sessionAdmissionIdleFloorMs(): number { return nonNegativeInt("MCP_SESSION_ADMISSION_IDLE_FLOOR_MS", 60_000); },
  },

  // ── Memory sidecar flags (#109 — moved out of index.ts inline reads)
  get disableMemorySidecar(): boolean { return process.env.SUPREMEAI_DISABLE_MEMORY_SIDECAR === "1"; },
  /** Local-dev only: block-and-log when the sidecar becomes ready. */
  get logMemoryReady(): string { return optional("SUPREMEAI_LOG_MEMORY_READY"); },

  // ── Event-driven bridge intake (#69)
  // Arms the webhook → workflow-dispatch wake-up path. Fail-closed: disabled
  // unless explicitly enabled. See docs/BRIDGE_INTAKE.md for activation steps.
  bridgeIntake: {
    get enabled(): boolean { return process.env.BRIDGE_INTAKE_ENABLED === "true"; },
    get repo(): string { return optional("BRIDGE_INTAKE_REPO", "Supremeai-bd/supremeai-open"); },
    get workflow(): string { return optional("BRIDGE_INTAKE_WORKFLOW", "pipeline.yml"); },
    get ref(): string { return optional("BRIDGE_INTAKE_REF", "main"); },
    get minIntervalMs(): number { return parseInt(optional("BRIDGE_INTAKE_MIN_INTERVAL_MS", "60000"), 10) || 60000; },
    get maxAttempts(): number { return parseInt(optional("BRIDGE_INTAKE_MAX_ATTEMPTS", "5"), 10) || 5; },
    get outboxPath(): string { return optional("BRIDGE_INTAKE_OUTBOX_PATH", "var/bridge-intake-outbox.jsonl"); },
    get token(): string { return optional("GITHUB_TOKEN", optional("GITHUB_API_TOKEN")); },
  },

  // Arms the #199 federated CI failure reporter (workflow_run.completed →
  // failure issue on the control-plane board). Fail-closed: disabled unless
  // explicitly enabled. See docs/FEDERATED_CI_WATCHER.md for activation steps.
  federatedCiWatcher: {
    get enabled(): boolean { return process.env.FEDERATED_CI_WATCHER_ENABLED === "true"; },
    get reportRepo(): string { return optional("FEDERATED_CI_WATCHER_REPORT_REPO", "Supremeai-bd/supremeai-open"); },
    /** Comma-separated explicit allowlist; empty → same-org-as-reportRepo policy. */
    get repos(): string[] {
      return optional("FEDERATED_CI_WATCHER_REPOS", "").split(",").map((s) => s.trim()).filter((s) => s.length > 0);
    },
    get maxIssuesPerHour(): number { return parseInt(optional("FEDERATED_CI_WATCHER_MAX_PER_HOUR", "6"), 10) || 6; },
    get dedupeTtlMs(): number { return parseInt(optional("FEDERATED_CI_WATCHER_DEDUPE_TTL_MS", "86400000"), 10) || 86400000; },
    get maxAttempts(): number { return parseInt(optional("FEDERATED_CI_WATCHER_MAX_ATTEMPTS", "3"), 10) || 3; },
    get token(): string { return optional("GITHUB_TOKEN", optional("GITHUB_API_TOKEN")); },
  },

  // ── Cloudflare (5-account federation pool)
  cloudflare: {
    get apiToken(): string | undefined { return process.env.CLOUDFLARE_API_TOKEN; },
    get accountId(): string | undefined { return process.env.CLOUDFLARE_ACCOUNT_ID; },
    get zoneId(): string | undefined { return process.env.CLOUDFLARE_ZONE_ID; },
    get workerUrl(): string | undefined { return process.env.CLOUDFLARE_WORKER_URL || process.env.SUPREMEAI_CF_WORKER_URL; },
    secondary: {
      get accountId(): string | undefined { return process.env.CLOUDFLARE_SECONDARY_ACCOUNT_ID; },
      get workerUrl(): string | undefined { return process.env.CLOUDFLARE_SECONDARY_WORKER_URL; },
    },
    tertiary: {
      get accountId(): string | undefined { return process.env.CLOUDFLARE_TERTIARY_ACCOUNT_ID; },
      get workerUrl(): string | undefined { return process.env.CLOUDFLARE_TERTIARY_WORKER_URL; },
    },
    quaternary: {
      get accountId(): string | undefined { return process.env.CLOUDFLARE_QUATERNARY_ACCOUNT_ID; },
      get workerUrl(): string | undefined { return process.env.CLOUDFLARE_QUATERNARY_WORKER_URL; },
    },
    quinary: {
      get accountId(): string | undefined { return process.env.CLOUDFLARE_QUINARY_ACCOUNT_ID; },
      get workerUrl(): string | undefined { return process.env.CLOUDFLARE_QUINARY_WORKER_URL; },
    },
  },

  // #643: direct LLM provider key pools (Gemini/Groq/OpenRouter/OpenAI/
  // Anthropic/GitHub Models/Mistral) were REMOVED from the zero-credential
  // control plane. AI analysis is delegated to the external agent caller
  // context (or Core API) — the tower must not require or store provider
  // master keys. See adapters/ai/index.ts (delegation stub).

  // ── Kaggle (6-account pool)
  kaggle: {
    get tokens(): string[] {
      const explicit = multiKey("KAGGLE_API_TOKENS");
      if (explicit.length > 0) return explicit;
      const collected: string[] = [];
      for (let i = 1; i <= 6; i++) {
        const val = optional(`KAGGLE_API_TOKEN_${i}`);
        if (val) collected.push(val);
      }
      const single = optional("KAGGLE_API_TOKEN");
      if (single) collected.push(single);
      return collected;
    },
  },

  // ── Notifications
  notify: {
    get telegramBotToken(): string { return optional("TELEGRAM_BOT_TOKEN"); },
    get telegramChatId(): string { return optional("TELEGRAM_CHAT_ID"); },
    get whatsappAccessToken(): string { return optional("WHATSAPP_ACCESS_TOKEN", optional("WHATSAPP_API_KEY")); },
    get whatsappPhoneNumberId(): string { return optional("WHATSAPP_PHONE_NUMBER_ID"); },
    get whatsappRecipientPhone(): string { return optional("WHATSAPP_RECIPIENT_PHONE", optional("WHATSAPP_PHONE")); },
    get whatsappWebhookUrl(): string { return optional("WHATSAPP_WEBHOOK_URL", optional("WHATSAPP_API_URL")); },
  },

  // ── Stripe
  stripe: {
    get secretKey(): string { return optional("STRIPE_SECRET_KEY"); },
    get webhookSecret(): string { return optional("STRIPE_WEBHOOK_SECRET"); },
  },

  // ── Qdrant
  qdrant: {
    get url(): string { return optional("QDRANT_URL"); },
    get apiKey(): string { return optional("QDRANT_API_KEY"); },
  },

  // ── Vercel
  vercel: {
    get token(): string { return optional("VERCEL_TOKEN"); },
    get projectId(): string { return optional("VERCEL_PROJECT_ID"); },
  },

  // ── Firecrawl
  firecrawl: {
    get apiKeys(): string[] { return multiKey("FIRECRAWL_API_KEY"); },
  },

  // ── DevTools audit backend (#1673 — chrome-devtools-mcp as tool backend)
  devtools: {
    get chromePath(): string { return optional("DEVTOOLS_CHROME_PATH", "chrome"); },
    get defaultWaitMs(): number { return positiveInt("DEVTOOLS_AUDIT_WAIT_MS", 4000); },
    get defaultTimeoutMs(): number { return positiveInt("DEVTOOLS_AUDIT_TIMEOUT_MS", 30000); },
    get slowRequestMs(): number { return positiveInt("DEVTOOLS_SLOW_REQUEST_MS", 1500); },
    get resultCapBytes(): number { return positiveInt("DEVTOOLS_RESULT_CAP_BYTES", 30000); },
  },
};

export type Env = typeof env;

/**
 * Fail-fast knob validation (#109): touches every validated runtime getter so
 * a misconfigured numeric env var aborts boot with a loud, named error
 * instead of surfacing as NaN-driven misbehavior on the first request.
 * Call once from main() inside the boot try-block.
 */
export function validateRuntimeKnobs(): void {
  void env.runtime.transport;
  void env.runtime.mcpRateLimitMax;
  void env.runtime.mcpRateLimitWindowMs;
  void env.runtime.toolPayloadMaxBytes;
  void env.runtime.toolResultMaxBytes;
  void env.runtime.toolTimeoutMs;
  void env.runtime.toolRateLimitMax;
  void env.runtime.toolRateLimitWindowMs;
  void env.runtime.mutationRateLimitMax;
  void env.runtime.mutationRateLimitWindowMs;
  void env.runtime.httpSessionIdleMs;
  void env.runtime.maxSseSessions;
  void env.runtime.maxHttpSessions;
  // #1673 — devtools audit knobs (validated the same loud way on boot)
  void env.devtools.defaultWaitMs;
  void env.devtools.defaultTimeoutMs;
  void env.devtools.slowRequestMs;
  void env.devtools.resultCapBytes;
  void env.runtime.sessionAdmissionIdleFloorMs;
}


