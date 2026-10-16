import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { buildAccountRegistry, ProviderAccount } from "../registry/account.registry.js";
import { listResources, getResourceStatus } from "../registry/resource.registry.js";
import { httpRequest } from "../lib/http.js";
import { env } from "../lib/env.js";
import { RequestContextStore } from "../policy/auth.context.js";
import { activeAccountChain } from "../lib/redis_chain.js";

/**
 * System-level MCP tools: summary, health, dependencies, and resource discovery.
 */

/* ── Provider-aware health probing ──────────────────────────────────────
 * Every provider exposes health differently: Render services answer /health,
 * GitHub's health IS the repo API with auth, Supabase has a public
 * /auth/v1/health, Upstash Redis speaks the REST protocol with a bearer
 * token. A blind `${url}/api/v1/health` appended to all of them produced
 * false "degraded" statuses (404/403/401) for services that were perfectly
 * healthy — the probe below checks what can actually be healthy. */

type HealthStatus = "healthy" | "degraded" | "unreachable" | "unconfigured";

interface HealthProbe {
  id: string;
  displayName: string;
  url: string;
  status: HealthStatus;
  httpStatus: number | null;
  latencyMs: number | null;
  error?: string;
}

function bearerFor(apiKeyRef: string): string | undefined {
  const primary = process.env[apiKeyRef];
  if (primary && primary.length > 0) return primary;
  // GitHub accounts allow generic fallback names (same rule as the registry)
  const altPat = process.env["GITHUB_PAT_PAYKARIBAZARONLINE"];
  if (altPat && altPat.length > 0) return altPat;
  const alt = process.env["GITHUB_TOKEN"];
  if (alt && alt.length > 0) return alt;
  const ghToken = process.env["GH_TOKEN"];
  if (ghToken && ghToken.length > 0) return ghToken;
  return undefined;
}

type ProbeOutcome = "degraded" | "unreachable" | { ok: true; status: number; latencyMs: number };

async function probeHttp(url: string, headers: Record<string, string> = {}, timeoutMs = 6000): Promise<ProbeOutcome> {
  try {
    const res = await httpRequest(url, { timeoutMs, retries: 0, headers });
    if (res.ok) return { ok: true, status: res.status, latencyMs: res.latencyMs };
    return "degraded";
  } catch {
    return "unreachable";
  }
}

/**
 * Upstash REST ping helper:
 * Converts rediss://default:TOKEN@host:6379 or https://host to https://host/ping
 * Extracts auth token from password (or username) if present in URL.
 */
export function upstashRestUrl(rawUrl: string): { url: string; token?: string } | null {
  try {
    const parsed = new URL(rawUrl.replace(/^rediss:\/\//, "https://").replace(/^redis:\/\//, "https://"));
    // The password field holds the auth token in rediss://default:TOKEN@host:6379
    // Fall back to username if password is empty (e.g. legacy token@host formats)
    const token = decodeURIComponent(parsed.password || parsed.username || "");
    // Upstash REST API lives on 443 — raw redis ports (6379/6380) are TCP-only
    // and would make every REST probe fail with "fetch failed".
    const host = parsed.host.replace(/:(6379|6380)$/, "");
    return { url: `https://${host}/ping`, token: token || undefined };
  } catch {
    return null;
  }
}

/**
 * Concurrency-bounded mapSettled helper: runs up to `concurrency` asynchronous
 * tasks in parallel to avoid socket/TLS contention and CPU throttling on shared containers.
 */
export async function mapConcurrentSettled<T, R>(
  items: T[],
  concurrency: number,
  fn: (item: T) => Promise<R>
): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let index = 0;

  async function worker(): Promise<void> {
    while (index < items.length) {
      const i = index++;
      try {
        const val = await fn(items[i]!);
        results[i] = { status: "fulfilled", value: val };
      } catch (err) {
        results[i] = { status: "rejected", reason: err };
      }
    }
  }

  const workerCount = Math.min(concurrency, items.length);
  const workers = Array.from({ length: workerCount }, () => worker());
  await Promise.all(workers);
  return results;
}

async function probeServiceHealth(svc: ProviderAccount): Promise<HealthProbe> {
  const base: Pick<HealthProbe, "id" | "displayName"> = { id: svc.id, displayName: svc.displayName };

  // ── GitHub: repo API with auth IS the health check ──
  if (svc.provider === "github") {
    const token = bearerFor(svc.apiKeyRef);
    try {
      const res = await httpRequest(svc.url!, {
        timeoutMs: 6000,
        retries: 0,
        headers: {
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      return {
        ...base,
        url: svc.url!,
        status: res.ok ? "healthy" : "degraded",
        httpStatus: res.status,
        latencyMs: res.latencyMs,
        ...(res.ok ? {} : { error: res.status === 401 || res.status === 403 ? "GitHub auth rejected — token missing, invalid or expired" : `GitHub responded ${res.status}` }),
      };
    } catch (err) {
      return { ...base, url: svc.url!, status: "unreachable", httpStatus: null, latencyMs: null, error: (err as Error).message };
    }
  }

  // ── Supabase: auth health endpoint (needs an apikey header on modern projects) ──
  if (svc.provider === "supabase") {
    const url = `${svc.url!.replace(/\/+$/, "")}/auth/v1/health`;
    const key = bearerFor(svc.apiKeyRef);
    const out = await probeHttp(url, key ? { apikey: key } : {});
    if (out === "unreachable") return { ...base, url, status: "unreachable", httpStatus: null, latencyMs: null, error: "connection failed" };
    if (out === "degraded") return { ...base, url, status: "degraded", httpStatus: null, latencyMs: null, error: "auth health endpoint responded non-2xx" };
    return { ...base, url, status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
  }

  // ── Redis (Upstash): REST ping with URL/apiKeyRef bearer token (chain failover supported) ──
  if (svc.provider === "redis") {
    const rest = upstashRestUrl(svc.url!);
    if (!rest) return { ...base, url: svc.url!, status: "unreachable", httpStatus: null, latencyMs: null, error: "unparseable redis URL" };
    // Prefer token extracted from URL password/username, or fall back to apiKeyRef from env (crucial for auto-rotated accounts like tertiary/quaternary)
    const token = rest.token || bearerFor(svc.apiKeyRef);
    try {
      const res = await httpRequest<{ result?: string }>(rest.url, {
        timeoutMs: 5000,
        retries: 0,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      // Upstash REST replies {"result":"PONG"} — compare case-insensitively
      const pong = res.ok && String(res.data?.result ?? "").toLowerCase() === "pong";
      if (!pong) {
        // Fallback: iterate active account chain if primary or rotated account fails/exhausted
        const chain = activeAccountChain();
        for (const candidate of chain) {
          if (!candidate.restUrl) continue;
          const candRest = upstashRestUrl(candidate.restUrl);
          const candToken = candidate.restToken || candRest?.token;
          if (candRest && candRest.url !== rest.url && candToken) {
            try {
              const secRes = await httpRequest<{ result?: string }>(candRest.url, {
                timeoutMs: 4000,
                retries: 0,
                headers: { Authorization: `Bearer ${candToken}` },
              });
              const secPong = secRes.ok && String(secRes.data?.result ?? "").toLowerCase() === "pong";
              if (secPong) {
                return { ...base, url: candRest.url, status: "healthy", httpStatus: secRes.status, latencyMs: secRes.latencyMs };
              }
            } catch {}
          }
        }
      }
      return { ...base, url: rest.url, status: pong ? "healthy" : "degraded", httpStatus: res.status, latencyMs: res.latencyMs, ...(pong ? {} : { error: "PING did not return pong" }) };
    } catch (err) {
      // Also try failover on network/connection error across the active chain
      const chain = activeAccountChain();
      for (const candidate of chain) {
        if (!candidate.restUrl) continue;
        const candRest = upstashRestUrl(candidate.restUrl);
        const candToken = candidate.restToken || candRest?.token;
        if (candRest && candRest.url !== rest.url && candToken) {
          try {
            const secRes = await httpRequest<{ result?: string }>(candRest.url, {
              timeoutMs: 4000,
              retries: 0,
              headers: { Authorization: `Bearer ${candToken}` },
            });
            const secPong = secRes.ok && String(secRes.data?.result ?? "").toLowerCase() === "pong";
            if (secPong) {
              return { ...base, url: candRest.url, status: "healthy", httpStatus: secRes.status, latencyMs: secRes.latencyMs };
            }
          } catch {}
        }
      }
      return { ...base, url: rest.url, status: "unreachable", httpStatus: null, latencyMs: null, error: (err as Error).message };
    }
  }

  // ── Cloudflare: token verify (or Global API Key verify) against the management API ──
  if (svc.provider === "cloudflare") {
    const token = bearerFor(svc.apiKeyRef);
    if (!token) {
      // Honest signal: the edge itself is NOT down — the tower simply cannot
      // manage/observe it without an API token.
      return { ...base, url: "https://api.cloudflare.com/client/v4", status: "unconfigured", httpStatus: null, latencyMs: null, error: `${svc.apiKeyRef} missing in tower env` };
    }
    const isGlobalKey = svc.apiKeyRef.includes("GLOBAL_API_KEY");
    const emailRef = svc.apiKeyRef.replace("_GLOBAL_API_KEY", "_EMAIL");
    const email = process.env[emailRef];

    try {
      if (isGlobalKey && email) {
        // Global API Key authentication uses X-Auth-Key and X-Auth-Email headers
        const res = await httpRequest<{ success?: boolean }>("https://api.cloudflare.com/client/v4/user", {
          timeoutMs: 6000,
          retries: 0,
          headers: { "X-Auth-Key": token, "X-Auth-Email": email },
        });
        const verified = res.ok && res.data?.success === true;
        return {
          ...base,
          url: "https://api.cloudflare.com/client/v4/user",
          status: verified ? "healthy" : "degraded",
          httpStatus: res.status,
          latencyMs: res.latencyMs,
          ...(verified ? {} : { error: "Cloudflare global API key rejected" }),
        };
      }

      const res = await httpRequest<{ success?: boolean; errors?: unknown[] }>("https://api.cloudflare.com/client/v4/user/tokens/verify", {
        timeoutMs: 6000,
        retries: 0,
        headers: { Authorization: `Bearer ${token}` },
      });
      const verified = res.ok && res.data?.success === true;
      return {
        ...base,
        url: "https://api.cloudflare.com/client/v4",
        status: verified ? "healthy" : "degraded",
        httpStatus: res.status,
        latencyMs: res.latencyMs,
        ...(verified ? {} : { error: "Cloudflare token verify failed — invalid or expired" }),
      };
    } catch (err) {
      return { ...base, url: "https://api.cloudflare.com/client/v4", status: "unreachable", httpStatus: null, latencyMs: null, error: (err as Error).message };
    }
  }

  // ── Infisical: public status endpoint (secrets-plane reachability) ──
  if (svc.provider === "infisical") {
    const url = "https://app.infisical.com/api/status";
    const out = await probeHttp(url);
    if (out === "unreachable") return { ...base, url, status: "unreachable", httpStatus: null, latencyMs: null, error: "connection failed" };
    if (out === "degraded") return { ...base, url, status: "degraded", httpStatus: null, latencyMs: null, error: "status endpoint responded non-2xx" };
    return { ...base, url, status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
  }

  // ── Firebase: service-account JSON config validation (no public unauth probe exists) ──
  if (svc.provider === "firebase") {
    const url = "config://firebase-service-account";
    try {
      const parsed = JSON.parse(env.firebase.serviceAccountJson || "null") as { project_id?: string; client_email?: string } | null;
      const ok = Boolean(parsed?.project_id && parsed?.client_email);
      return {
        ...base,
        url,
        status: ok ? "healthy" : "degraded",
        httpStatus: null,
        latencyMs: null,
        ...(ok ? {} : { error: "service account JSON missing project_id/client_email or unparseable" }),
      };
    } catch {
      return { ...base, url, status: "degraded", httpStatus: null, latencyMs: null, error: "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON" };
    }
  }

  // ── AI providers: authenticated models-list probes ──
  if (svc.provider === "ai") {
    const groqKey = env.ai.groqKeys[0];
    const openrouterKey = env.ai.openrouterKeys[0];
    const mistralKey = env.ai.mistralKey;
    const probes: Record<string, { url: string; headers: Record<string, string>; authOptional?: boolean }> = {
      "ai-gemini": { url: "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", headers: { "x-goog-api-key": env.ai.geminiKeys[0] ?? "" } },
      "ai-groq": { url: "https://api.groq.com/openai/v1/models", headers: groqKey ? { Authorization: `Bearer ${groqKey}` } : {} },
      "ai-openrouter": { url: "https://openrouter.ai/api/v1/models", headers: openrouterKey ? { Authorization: `Bearer ${openrouterKey}` } : {}, authOptional: true },
      "ai-mistral": { url: "https://api.mistral.ai/v1/models", headers: mistralKey ? { Authorization: `Bearer ${mistralKey}` } : {} },
    };
    const target = probes[svc.id];
    if (!target) return { ...base, url: "—", status: "unreachable", httpStatus: null, latencyMs: null, error: `no AI probe implemented for ${svc.id}` };
    const out = await probeHttp(target.url, target.headers);
    if (out === "unreachable") return { ...base, url: target.url, status: "unreachable", httpStatus: null, latencyMs: null, error: "connection failed" };
    if (out === "degraded") {
      const reason = target.authOptional ? "models endpoint responded non-2xx" : "key rejected or non-2xx (check validity/quota/region)";
      return { ...base, url: target.url, status: "degraded", httpStatus: null, latencyMs: null, error: reason };
    }
    return { ...base, url: target.url, status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
  }

  // ── Kaggle: pool config + authenticated competitions list (first token) ──
  if (svc.provider === "kaggle") {
    const url = "https://www.kaggle.com/api/v1/competitions/list";
    const tokens = env.kaggle.tokens;
    if (tokens.length === 0) return { ...base, url, status: "unconfigured", httpStatus: null, latencyMs: null, error: "KAGGLE_API_TOKENS missing in tower env" };
    const firstToken = tokens[0];
    const isBearer = firstToken.startsWith("KGAT_");
    const authHeader = isBearer ? `Bearer ${firstToken}` : `Basic ${Buffer.from(firstToken).toString("base64")}`;
    const out = await probeHttp(url, { Authorization: authHeader });
    if (out === "unreachable") return { ...base, url, status: "unreachable", httpStatus: null, latencyMs: null, error: "connection failed" };
    if (out === "degraded") return { ...base, url, status: "degraded", httpStatus: null, latencyMs: null, error: "first pool token rejected or non-2xx" };
    return { ...base, url, status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
  }

  // ── Telegram: getMe verifies the bot token (URL masked in output — token never echoed) ──
  if (svc.provider === "telegram") {
    const maskedUrl = "https://api.telegram.org";
    const token = env.notify.telegramBotToken;
    if (!token) return { ...base, url: maskedUrl, status: "unconfigured", httpStatus: null, latencyMs: null, error: "TELEGRAM_BOT_TOKEN missing in tower env" };
    try {
      const res = await httpRequest<{ ok?: boolean }>(`https://api.telegram.org/bot${token}/getMe`, { timeoutMs: 6000, retries: 0 });
      const ok = Boolean(res.data?.ok);
      return { ...base, url: maskedUrl, status: ok ? "healthy" : "degraded", httpStatus: res.status, latencyMs: res.latencyMs, ...(ok ? {} : { error: "getMe rejected the bot token" }) };
    } catch (err) {
      return { ...base, url: maskedUrl, status: "unreachable", httpStatus: null, latencyMs: null, error: (err as Error).message };
    }
  }

  // ── WhatsApp: Meta Graph API / Webhook health probe ──
  if (svc.provider === "whatsapp") {
    const maskedUrl = "https://graph.facebook.com/whatsapp";
    const { whatsappAccessToken, whatsappPhoneNumberId, whatsappWebhookUrl } = env.notify;
    if (!whatsappAccessToken && !whatsappWebhookUrl) {
      return { ...base, url: maskedUrl, status: "unconfigured", httpStatus: null, latencyMs: null, error: "WHATSAPP_ACCESS_TOKEN or WHATSAPP_WEBHOOK_URL missing in tower env" };
    }
    try {
      if (whatsappPhoneNumberId && whatsappAccessToken) {
        const res = await httpRequest<{ id?: string }>(`https://graph.facebook.com/v20.0/${whatsappPhoneNumberId}`, {
          timeoutMs: 6000,
          retries: 0,
          headers: { Authorization: `Bearer ${whatsappAccessToken}` },
        });
        const ok = Boolean(res.data?.id);
        return { ...base, url: maskedUrl, status: ok ? "healthy" : "degraded", httpStatus: res.status, latencyMs: res.latencyMs, ...(ok ? {} : { error: "Meta API rejected phone number or token" }) };
      }
      if (whatsappWebhookUrl) {
        const out = await probeHttp(whatsappWebhookUrl);
        if (out === "unreachable") return { ...base, url: "webhook://whatsapp", status: "unreachable", httpStatus: null, latencyMs: null, error: "webhook unreachable" };
        if (out === "degraded") return { ...base, url: "webhook://whatsapp", status: "degraded", httpStatus: null, latencyMs: null, error: "webhook returned non-2xx" };
        return { ...base, url: "webhook://whatsapp", status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
      }
      return { ...base, url: maskedUrl, status: "degraded", httpStatus: null, latencyMs: null, error: "WHATSAPP_PHONE_NUMBER_ID missing for Meta Cloud API" };
    } catch (err) {
      return { ...base, url: maskedUrl, status: "unreachable", httpStatus: null, latencyMs: null, error: (err as Error).message };
    }
  }

  // ── HTTP services (render et al.): explicit path → /health → /api/v1/health ──
  if (!svc.url) {
    return { ...base, url: "—", status: "unreachable", httpStatus: null, latencyMs: null, error: `no probeable URL for provider '${svc.provider}'` };
  }
  const candidates = [
    ...(svc.healthPath ? [svc.healthPath] : []),
    "/health",
    "/api/v1/health",
  ].map((p) => `${svc.url!.replace(/\/+$/, "")}${p}`);

  for (const url of candidates) {
    const out = await probeHttp(url);
    if (out !== "unreachable" && out !== "degraded") {
      return { ...base, url, status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
    }
  }

  // No 2xx anywhere — one more pass to classify degraded (HTTP answered) vs unreachable
  for (const url of candidates) {
    const out = await probeHttp(url);
    if (out === "degraded") {
      return { ...base, url, status: "degraded", httpStatus: null, latencyMs: null, error: "health endpoint responded non-2xx" };
    }
    if (out !== "unreachable") {
      return { ...base, url, status: "healthy", httpStatus: out.status, latencyMs: out.latencyMs };
    }
  }
  return { ...base, url: candidates[0], status: "unreachable", httpStatus: null, latencyMs: null, error: "no health endpoint answered" };
}

export async function registerSystemTools(server: McpServer): Promise<void> {

  // ── system.summary
  server.tool(
    "system.summary",
    "Get a high-level summary of all SupremeAI services — availability, roles, and capabilities",
    {},
    async () => {
      const registry = buildAccountRegistry();
      const byProvider = registry.reduce(
        (acc, r) => {
          const key = r.provider;
          if (!acc[key]) acc[key] = [];
          acc[key]!.push({
            id: r.id,
            displayName: r.displayName,
            role: r.role,
            available: r.available,
            capabilities: r.capabilities,
          });
          return acc;
        },
        {} as Record<string, unknown[]>
      );

      const available = registry.filter((r) => r.available).length;
      const total = registry.length;

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                summary: `${available}/${total} services available`,
                timestamp: new Date().toISOString(),
                byProvider,
              },
              null,
              2
            ),
          },
        ],
      };
    }
  );

  // ── system.health (ping all HTTP services)
  server.tool(
    "system.health",
    "Ping all backend services and report their HTTP health status",
    {},
    async () => {
      const registry = buildAccountRegistry();

      // Probe every registry row with bounded concurrency (8 workers) to avoid
      // saturating container socket pools and inflating probe latencies.
      const results = await mapConcurrentSettled(
        registry,
        8,
        async (svc) => {
          if (!svc.available) {
            return {
              id: svc.id,
              displayName: svc.displayName,
              url: svc.url ?? "—",
              status: "unconfigured" as const,
              httpStatus: null,
              latencyMs: null,
              error: `${svc.apiKeyRef} missing in tower env`,
            };
          }
          return probeServiceHealth(svc);
        }
      );

      const health = results.map((r) => (r.status === "fulfilled" ? r.value : r.reason));
      const count = (s: string) => health.filter((h: Record<string, unknown>) => h.status === s).length;
      const healthy = count("healthy");
      const degraded = count("degraded");
      const unreachable = count("unreachable");
      const unconfigured = count("unconfigured");

      // #695: non-admin callers get the health summary WITHOUT internal URL
      // enumeration — endpoint URLs, HTTP statuses and probe error text are
      // stripped; only id/status/latency remain.
      const includeNetworkDetails = RequestContextStore.get()?.role === "admin";
      const services = includeNetworkDetails
        ? health
        : health.map((entry) => {
            const safe = { ...(entry as Record<string, unknown>) };
            delete safe["url"];
            delete safe["httpStatus"];
            delete safe["error"];
            return safe;
          });

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                summary: `${healthy} healthy · ${degraded} degraded · ${unreachable} unreachable · ${unconfigured} unconfigured (of ${health.length})`,
                timestamp: new Date().toISOString(),
                services,
              },
              null,
              2
            ),
          },
        ],
      };
    }
  );

  // NOTE (master audit 2026-09-02): the static "system.dependencies" tool that
  // lived here was removed — it collided with the dynamic, richer implementation
  // in system.summary.tools.ts (the MCP SDK throws
  // "Tool system.dependencies is already registered" on duplicates, which
  // crashed the whole control tower at boot). The dynamic
  // globalDependencyGraph.getRawMap() version supersedes this static graph.

  // ── resource.list
  server.tool(
    "resource.list",
    "List all discovered resources across all configured providers.",
    {},
    async () => {
      const resources = await listResources();
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                total: resources.length,
                resources,
              },
              null,
              2
            ),
          },
        ],
      };
    }
  );

  // ── resource.status
  server.tool(
    "resource.status",
    "Get the current status of a specific resource by ID.",
    {
      resourceId: z.string().describe("The ID of the resource (e.g. render/render-primary)"),
    },
    async ({ resourceId }) => {
      const status = await getResourceStatus(resourceId);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                resourceId,
                status,
              },
              null,
              2
            ),
          },
        ],
      };
    }
  );
}
