import { env } from "../lib/env.js";
import { getActiveRedisAccount } from "../lib/redis_chain.js";
import { ProviderName } from "./provider.registry.js";
import { Capability } from "./capability.registry.js";

export interface ProviderAccount {
  id: string;
  provider: ProviderName;
  displayName: string;
  role: string;
  environment: "production" | "staging" | "development";
  capabilities: Capability[];
  /** Env var name for API key — NOT the value itself */
  apiKeyRef: string;
  /** Optional fallback env var NAMES, tried in order when apiKeyRef is
   *  absent. Fixes the render-mcp / render.yaml mismatch: render.yaml
   *  declares RENDER_API_KEY while accounts referenced RENDER_API_KEY_4 —
   *  deployment only receives RENDER_API_KEY, so the account must be
   *  resolvable (and marked available) via the generic key. */
  apiKeyRefs?: string[];
  /** Optional: URL or endpoint */
  url?: string;
  /** Optional: service/resource ID */
  serviceId?: string;
  /** Optional: explicit health-check path appended to `url` (system.health).
   *  When absent, the probe tries /health then /api/v1/health. Providers with
   *  non-HTTP health semantics (github/supabase/redis) get dedicated probes. */
  healthPath?: string;
  /** Is this account available? (key present in env) */
  available: boolean;
}

function isAvailable(envRef: string): boolean {
  const val = process.env[envRef] ?? "";
  return val.length > 0;
}

/**
 * Canonical federation repositories under the Supremeai-bd organization
 * (SSOT: ECOSYSTEM_MAP.md §2). Used as the guaranteed baseline for discovery.
 */
export const CANONICAL_FEDERATION_REPOS = [
  "supremeai",
  "supremeai-open",
  "supremeai-command",
  "supremeai-skills",
  "supremeai-vscode",
  "supremeai-agents",
  "supremeai-browser",
  "supremeai-api",
  "supremeai-studio",
  "supremeai-infrastructure",
  "supremeai-core",
  "supremeai-sdk",
  "supremeai-mcp-control-plane",
  "supremeai-archive",
] as const;

export const GITHUB_ORGANIZATION = "Supremeai-bd";

// In-memory registry of discovered repositories under the organization.
// Initialized with canonical federation repos to guarantee zero-network baseline.
const discoveredOrgRepos = new Set<string>(CANONICAL_FEDERATION_REPOS);

/**
 * Register a newly discovered repository name under the organization.
 */
export function registerDiscoveredOrgRepo(repoName: string): void {
  const normalized = repoName.trim().toLowerCase();
  // Ghost Cloaking: supremeai-api is never tracked or exposed in regular repo lists
  if (normalized === "supremeai-api") return;
  if (normalized && !discoveredOrgRepos.has(normalized)) {
    discoveredOrgRepos.add(normalized);
  }
}

/**
 * Get all tracked repository names under the organization.
 */
export function getTrackedOrgRepos(): string[] {
  return Array.from(discoveredOrgRepos);
}

/**
 * Dynamically discover repositories under Supremeai-bd from GitHub API.
 * Updates discoveredOrgRepos in memory without requiring server restart or code edits.
 */
export async function refreshDiscoveredOrgRepos(): Promise<string[]> {
  const token =
    process.env["GITHUB_PAT_PAYKARIBAZARONLINE"] ||
    process.env["GITHUB_TOKEN"] ||
    process.env["GH_TOKEN"];
  try {
    const res = await fetch(`https://api.github.com/orgs/${GITHUB_ORGANIZATION}/repos?per_page=100`, {
      headers: {
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (res.ok) {
      const repos = (await res.json()) as Array<{ name?: string }>;
      for (const r of repos) {
        if (r.name) registerDiscoveredOrgRepo(r.name);
      }
    }
  } catch {}
  return getTrackedOrgRepos();
}

/**
 * Registry is built dynamically from env at startup.
 * Adding a new account = add env vars + add entry here.
 */
export function buildAccountRegistry(): ProviderAccount[] {
  return [
    // ── Render ──────────────────────────────────────────
    {
      id: "render-primary",
      provider: "render",
      displayName: "Render Primary (Core API)",
      role: "core-api",
      environment: "production",
      capabilities: ["health", "logs", "deploy", "restart", "env_vars"],
      apiKeyRef: "RENDER_API_KEY_1",
      apiKeyRefs: ["RENDER_API_KEY"],
      url: env.render.primary.url,
      serviceId: env.render.primary.serviceId,
      healthPath: "/health", // FastAPI core API public health check
      available: isAvailable("RENDER_API_KEY_1") || isAvailable("RENDER_API_KEY"),
    },
    {
      id: "render-worker",
      provider: "render",
      displayName: "Render Worker (Async Tasks)",
      role: "async-worker",
      environment: "production",
      capabilities: ["health", "logs", "deploy", "restart", "env_vars"],
      apiKeyRef: "RENDER_API_KEY_2",
      url: env.render.worker.url,
      serviceId: env.render.worker.serviceId,
      healthPath: "/health",
      available: isAvailable("RENDER_API_KEY_2"),
    },
    {
      id: "render-scraper",
      provider: "render",
      displayName: "Render Scraper (Browser/Scraping)",
      role: "browser-scraper",
      environment: "production",
      capabilities: ["health", "logs", "deploy", "restart", "env_vars"],
      apiKeyRef: "RENDER_API_KEY_3",
      url: env.render.scraper.url,
      serviceId: env.render.scraper.serviceId,
      healthPath: "/health",
      available: isAvailable("RENDER_API_KEY_3"),
    },
    {
      id: "render-mcp",
      provider: "render",
      displayName: "Render MCP (Control Tower)",
      role: "mcp-control",
      environment: "production",
      capabilities: ["health", "logs", "deploy", "restart", "env_vars"],
      apiKeyRef: "RENDER_API_KEY_4",
      apiKeyRefs: ["RENDER_API_KEY"],
      url: env.render.controlTower.url,
      serviceId: env.render.controlTower.serviceId,
      healthPath: "/health", // control tower's own health endpoint
      // render.yaml declares RENDER_API_KEY (sync:false) for this service;
      // RENDER_API_KEY_4 may only exist if Infisical provides it explicitly.
      // Without this fallback the tower was marked unavailable and every
      // render.* tool failed even though a valid key was provisioned.
      available: isAvailable("RENDER_API_KEY_4") || isAvailable("RENDER_API_KEY"),
    },

    // ── GitHub — SupremeAI Primary (Supremeai-bd/supremeai) ────────
    // Note: SaifulHaqueNiloy/supremeai and the pre-migration personal e-commerce namespace
    // are excluded. Only canonical SupremeAI ecosystem repositories are monitored.
    {
      id: "github-primary",
      provider: "github",
      displayName: `GitHub Repo (${GITHUB_ORGANIZATION}/supremeai)`,
      role: "source-control",
      environment: "production",
      capabilities: ["health", "logs", "metrics"],
      apiKeyRef: "GITHUB_PAT_PAYKARIBAZARONLINE",
      url: `https://api.github.com/repos/${GITHUB_ORGANIZATION}/supremeai`,
      available: isAvailable("GITHUB_PAT_PAYKARIBAZARONLINE") || isAvailable("GITHUB_TOKEN") || isAvailable("GH_TOKEN"),
    },

    // ── GitHub — Supremeai-bd Organization Level Monitor ──
    {
      id: "github-org-supremeai-bd",
      provider: "github",
      displayName: `GitHub Organization (${GITHUB_ORGANIZATION})`,
      role: "organization",
      environment: "production",
      capabilities: ["health", "metrics"],
      apiKeyRef: "GITHUB_PAT_PAYKARIBAZARONLINE",
      url: `https://api.github.com/orgs/${GITHUB_ORGANIZATION}`,
      available: isAvailable("GITHUB_PAT_PAYKARIBAZARONLINE") || isAvailable("GITHUB_TOKEN") || isAvailable("GH_TOKEN"),
    },

    // ── GitHub — Supremeai-bd federation (Dynamic Org-Wide Auto-Discovery) ──
    ...getTrackedOrgRepos().map((repoName) => ({
      id: `github-pay-${repoName}`,
      provider: "github" as const,
      displayName: `GitHub Repo (${GITHUB_ORGANIZATION}/${repoName})`,
      role: "source-control",
      environment: "production" as const,
      capabilities: ["health", "logs", "metrics"] as Capability[],
      apiKeyRef: "GITHUB_PAT_PAYKARIBAZARONLINE",
      url: `https://api.github.com/repos/${GITHUB_ORGANIZATION}/${repoName}`,
      available: isAvailable("GITHUB_PAT_PAYKARIBAZARONLINE") || isAvailable("GITHUB_TOKEN") || isAvailable("GH_TOKEN"),
    })),

    // ── Supabase ──────────────────────────────────────────
    {
      id: "supabase-primary",
      provider: "supabase",
      displayName: "Supabase Primary (Postgres + Auth)",
      role: "primary-db",
      environment: "production",
      capabilities: ["health", "metrics"],
      apiKeyRef: "SUPABASE_SERVICE_ROLE_KEY",
      url: env.supabase.url,
      available: isAvailable("SUPABASE_SERVICE_ROLE_KEY"),
    },

    // ── Redis (Upstash) — Auto-Rotating Multi-Account Chain (#26) ────
    (() => {
      const active = getActiveRedisAccount();
      const label = active?.label || "primary";
      const tokenRef = label === "primary" ? "UPSTASH_REDIS_REST_TOKEN" : `UPSTASH_REDIS_${label.toUpperCase()}_REST_TOKEN`;
      return {
        id: "redis-primary",
        provider: "redis" as const,
        displayName: label === "primary" ? "Upstash Redis (Cache + Queue)" : `Upstash Redis (Cache + Queue [auto-rotated: ${label}])`,
        role: "cache",
        environment: "production" as const,
        capabilities: ["health", "metrics", "storage"] as const,
        apiKeyRef: tokenRef,
        // Prefer the active account's REST URL (https, port 443)
        url: active?.restUrl || env.redis.restUrl || env.redis.url,
        available: isAvailable(tokenRef) || isAvailable("UPSTASH_REDIS_REST_TOKEN") || isAvailable("REDIS_URL"),
      };
    })(),

    // ── Cloudflare (5-Account Federation Pool) ────────────
    {
      id: "cloudflare-primary",
      provider: "cloudflare",
      displayName: "Cloudflare Primary (DNS + Workers + Edge)",
      role: "edge",
      environment: "production",
      capabilities: ["health", "metrics", "logs"],
      apiKeyRef: "CLOUDFLARE_API_TOKEN",
      available: isAvailable("CLOUDFLARE_API_TOKEN") || isAvailable("CLOUDFLARE_GLOBAL_API_KEY"),
    },
    {
      id: "cloudflare-secondary",
      provider: "cloudflare",
      displayName: "Cloudflare Secondary (Edge Failover)",
      role: "edge-secondary",
      environment: "production",
      capabilities: ["health", "metrics", "logs"],
      apiKeyRef: "CLOUDFLARE_SECONDARY_GLOBAL_API_KEY",
      available: isAvailable("CLOUDFLARE_SECONDARY_GLOBAL_API_KEY"),
    },
    {
      id: "cloudflare-tertiary",
      provider: "cloudflare",
      displayName: "Cloudflare Tertiary (Edge Failover)",
      role: "edge-tertiary",
      environment: "production",
      capabilities: ["health", "metrics", "logs"],
      apiKeyRef: "CLOUDFLARE_TERTIARY_GLOBAL_API_KEY",
      available: isAvailable("CLOUDFLARE_TERTIARY_GLOBAL_API_KEY"),
    },
    {
      id: "cloudflare-quaternary",
      provider: "cloudflare",
      displayName: "Cloudflare Quaternary (Edge Failover)",
      role: "edge-quaternary",
      environment: "production",
      capabilities: ["health", "metrics", "logs"],
      apiKeyRef: "CLOUDFLARE_QUATERNARY_GLOBAL_API_KEY",
      available: isAvailable("CLOUDFLARE_QUATERNARY_GLOBAL_API_KEY"),
    },
    {
      id: "cloudflare-quinary",
      provider: "cloudflare",
      displayName: "Cloudflare Quinary (Edge Failover)",
      role: "edge-quinary",
      environment: "production",
      capabilities: ["health", "metrics", "logs"],
      apiKeyRef: "CLOUDFLARE_QUINARY_GLOBAL_API_KEY",
      available: isAvailable("CLOUDFLARE_QUINARY_GLOBAL_API_KEY"),
    },

    // ── Infisical ─────────────────────────────────────────
    {
      id: "infisical-primary",
      provider: "infisical",
      displayName: "Infisical (Secrets Manager)",
      role: "secrets",
      environment: "production",
      capabilities: ["health", "secrets"],
      apiKeyRef: "INFISICAL_CLIENT_SECRET",
      available: isAvailable("INFISICAL_CLIENT_SECRET"),
    },

    // ── Firebase ──────────────────────────────────────────
    {
      id: "firebase-primary",
      provider: "firebase",
      displayName: "Firebase (Auth + Storage)",
      role: "auth-storage",
      environment: "production",
      capabilities: ["health", "auth", "storage"],
      apiKeyRef: "FIREBASE_SERVICE_ACCOUNT_JSON",
      available: isAvailable("FIREBASE_SERVICE_ACCOUNT_JSON"),
    },

    // #643: direct LLM provider pools (gemini/groq/openrouter/mistral) were
    // REMOVED from the zero-credential control plane — AI analysis is delegated
    // to the external agent caller context (or Core API). No apiKeyRef for any
    // LLM provider is required or stored in the tower runtime env anymore.

    // ── Kaggle ────────────────────────────────────────────
    {
      id: "kaggle-pool",
      provider: "kaggle",
      displayName: "Kaggle Accounts Pool (6 keys)",
      role: "data-science",
      environment: "production",
      capabilities: ["health", "storage"],
      apiKeyRef: "KAGGLE_API_TOKENS",
      available: env.kaggle.tokens.length > 0,
    },

    // ── Notifications ─────────────────────────────────────
    {
      id: "telegram-primary",
      provider: "telegram",
      displayName: "Telegram Alerts Bot",
      role: "alerts",
      environment: "production",
      capabilities: ["health", "notify"],
      apiKeyRef: "TELEGRAM_BOT_TOKEN",
      available: isAvailable("TELEGRAM_BOT_TOKEN"),
    },
    {
      id: "whatsapp-primary",
      provider: "whatsapp",
      displayName: "WhatsApp Alerts Bot",
      role: "alerts",
      environment: "production",
      capabilities: ["health", "notify"],
      apiKeyRef: "WHATSAPP_ACCESS_TOKEN",
      available: isAvailable("WHATSAPP_ACCESS_TOKEN") || isAvailable("WHATSAPP_PHONE_NUMBER_ID") || isAvailable("WHATSAPP_WEBHOOK_URL"),
    },
  ];
}
