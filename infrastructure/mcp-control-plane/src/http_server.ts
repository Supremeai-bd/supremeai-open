#!/usr/bin/env node
/**
 * SupremeAI MCP Control Tower — Main Entry Point
 * Supports both stdio (local: Claude Desktop, Cursor) and HTTP Streamable (remote)
 *
 * Environment loading (#109): ALL environment config — including the single
 * repo-root `.env` load — lives in `lib/env.ts` (SSOT). This file must not
 * parse `process.env` directly; every knob is a validated getter on `env`.
 */

import { timingSafeEqual, randomUUID } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { z } from "zod";
import { env } from "./lib/env.js";
import {
  mcpRateBuckets,
  toolIdentityRateBuckets,
  mcpRateLimitConfig,
  consumeSlidingWindow,
  consumeMcpRateLimit,
  toolRateLimitIdentity,
  consumeToolRateLimit,
  mutationToolGateError,
  toolPayloadError,
  ToolExecutionTimeoutError,
  truncateToolResult,
} from "./lib/mcp_rate_limit.js";
import { registerAllTools } from "./tools/index.js";
import { RequestContextStore, type UserRole } from "./policy/auth.context.js";
import { getServiceDescriptors } from "./service-circles.js";
import { nowTimestamp, timestampDetails, withTimestamp } from "./lib/timestamps.js";
import { deriveWatchdog, recordWatchdogAlarm } from "./health/watchdog.js";
import { approveClient, changeClientProfile, changeClientProvider, changeClientRole, countClientsByTenant, defaultClientScopes, DEFAULT_GUEST_ROLE, getClient, initClientRegistry, listClients, registerClient, resolveClient, revokeClient, rotateClient, roleAllows, scopeAllows, type ExternalClient } from "./policy/client-registry.js";
import { extractClientInfoName, recordPresence, listWorkforce, registerIoredis } from "./registry/mcp_presence.js";
import { createBuiltinManifest } from "./registry/mcp.contracts.js";
import { autoRegisterGuestClient, clientIpFor, isValidClientName } from "./policy/auto-register.js";
import { executeGeminiFunctionCall, geminiAdapterInfo, listGeminiTools } from "./adapters/gemini/gemini.adapter.js";
import { accessModeFor, publicAccessManifest, isPublicSafeResource, toolAccessErrorAsync } from "./policy/mcp-access.js";
import {
  assertSlotAuthorization,
  resolveSlotSession,
} from "./policy/slot-verification.js";
import { attachDiscoveryFilter, isValidToolProfile } from "./policy/tool-visibility.js";
import { pickPressureEvictionSessionId } from "./lib/session_admission.js";
import { verifyApprovalLink } from "./policy/approvals/signing.js";
import { hasWebhookSignature } from "./lib/webhook_signature.js";
import { registerBridgeIntake } from "./events/bridge_intake.js";
import { registerFederatedCiWatcher } from "./events/federated_ci_watcher.js";
import { registerCommandRouter } from "./events/command_router.js";
import { validateRuntimeKnobs } from "./lib/env.js";
import { pullSecretsIntoProcessEnv } from "./adapters/infisical/index.js";
import { MemorySubAdapter } from "./adapters/memory/index.js";
import {
  activateTenant,
  createTenant,
  getTenant,
  listTenants,
  rotateTenantAdminToken,
  suspendTenant,
  updateTenant,
  verifyTenantAdminToken,
} from "./tenancy/tenant.registry.js";
// #2596: সেন্ট্রাল টাস্ক কিউ — GitHub rate-limit ও ghost-state নির্মূলের লিজ-স্টেট মেশিন।
import {
  claimTask,
  completeTask,
  ensureFreshSync,
  heartbeatTask,
  initTaskRegistry,
  listTasks,
  refreshFromGitHub,
  taskQueueStatus,
  isGithubLocked,
} from "./tasks/task-registry.js";
const SERVER_NAME = "supremeai-control-tower";
const SERVER_VERSION = "1.0.0";
const MAX_REQUEST_BYTES = 1_048_576;
const MCP_MANIFEST_URI = "control-tower://server/manifest";

function requestPath(req: IncomingMessage): string {
  return new URL(req.url ?? "/", `http://${req.headers.host || "localhost"}`).pathname;
}
function writeJson(res: ServerResponse, status: number, payload: unknown, extraHeaders: Record<string, string> = {}): void {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...extraHeaders,
  });
  res.end(JSON.stringify(payload));
}

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}
function resolveRole(req: IncomingMessage): UserRole | null {
  let token = "";
  const authHeader = req.headers.authorization ?? "";
  const prefix = "Bearer ";
  if (authHeader.startsWith(prefix)) {
    token = authHeader.slice(prefix.length);
  }
  // SECURITY: token/key query parameters are no longer accepted. Query strings
  // leak into proxy/CDN logs, browser history and Referer headers. Browser
  // 1-click approval links use per-request expiring HMAC signatures instead —
  // see policy/approvals/signing.ts and the /approve route below.

  if (!token) return null;

  if (env.mcpAdminKey && safeEqual(token, env.mcpAdminKey)) return "admin";
  // ROOT-CAUSE FIX (#2720): MCP_API_KEY is the AGENT key, not an admin key.
  // Previously this line returned "admin" for any mcpApiKey holder, combined
  // with env.ts falling back mcpAdminKey → mcpApiKey, this meant the agent key
  // was effectively an admin key. Now: mcpApiKey grants "agent" role only.
  // Privileged operations (action_*, tenant_*, autonomy_kill_switch, approvals)
  // require the separate MCP_ADMIN_KEY.
  if (env.mcpApiKey && safeEqual(token, env.mcpApiKey)) return "agent";
  if (env.mcpAgentKey && safeEqual(token, env.mcpAgentKey)) return "agent";
  if (env.mcpViewerKey && safeEqual(token, env.mcpViewerKey)) return "viewer";
  const client = resolveClient(token);
  return client?.role ?? null;
}

/**
 * Tenant-aware caller context.
 * global admin (env keys) → isGlobalAdmin, tenant scope "*".
 * registered client   → tenantId клиента (tenant isolation).
 * tenant admin token  → управляет своим tenant через заголовок x-tenant-id.
 */
interface CallerContext {
  role: UserRole | null;
  client?: ExternalClient;
  tenantId: string;
  isGlobalAdmin: boolean;
}
function resolveCaller(req: IncomingMessage): CallerContext {
  const role = resolveRole(req);
  const bearer = (req.headers.authorization ?? "").replace(/^Bearer\s+/i, "");
  const client = bearer ? resolveClient(bearer) : undefined;

  // ROOT-CAUSE FIX (#2720): isEnvAdmin must ONLY match MCP_ADMIN_KEY, not
  // MCP_API_KEY. The old `|| (env.mcpApiKey && safeEqual(bearer, env.mcpApiKey))`
  // branch granted global admin to any agent-key holder.
  const isEnvAdmin =
    Boolean(env.mcpAdminKey) && safeEqual(bearer, env.mcpAdminKey);

  // Tenant admin: отдельный заголовок x-tenant-id + x-tenant-admin-token
  const headerTenantId = String(req.headers["x-tenant-id"] ?? "");
  const headerAdminToken = String(req.headers["x-tenant-admin-token"] ?? "");
  let tenantId = "tenant_default";
  let isGlobalAdmin = false;

  if (isEnvAdmin || role === "admin") {
    if (isEnvAdmin) {
      isGlobalAdmin = true;
      tenantId = "*";
    } else {
      tenantId = client?.tenantId ?? "tenant_default";
    }
  } else if (client?.tenantId) {
    tenantId = client.tenantId;
  }

  // Tenant admin token override (only if not global admin already)
  if (!isGlobalAdmin && headerTenantId && headerAdminToken && verifyTenantAdminToken(headerTenantId, headerAdminToken)) {
    isGlobalAdmin = false; // tenant admin — НЕ global admin
    tenantId = headerTenantId;
  }

  return { role, client, tenantId, isGlobalAdmin };
}
async function startHttpServer(serverFactory: () => Promise<McpServer>): Promise<void> {
  // Dynamically import transports
  const { StreamableHTTPServerTransport } = await import(
    "@modelcontextprotocol/sdk/server/streamableHttp.js"
  );
  const { SSEServerTransport } = await import(
    "@modelcontextprotocol/sdk/server/sse.js"
  );

  type StreamableTransport = InstanceType<typeof StreamableHTTPServerTransport>;

  // Per-session transports for SSE
  const sseSessions = new Map<string, any>();
  const sseClientMap = new Map<string, ExternalClient>();
  // #48: per-session slot bindings — credential-verified slot identity that
  // every subsequent /messages re-checks live (immediate-next-check
  // revocation for in-flight SSE streams).
  const sseSlotMap = new Map<string, { slotId: string; credentialId?: string }>();

  // ── Per-session transports for streamable HTTP /mcp (#2588) ────────────────
  // The old boot-time GLOBAL singleton transport was the root cause of the
  // `404 -32001 Session not found` outage: once ANY client closed a session
  // the SDK marked the shared transport `_closed` and every subsequent
  // `initialize` from every new client (e.g. Gemini Spark) failed forever.
  // Like /sse, each `initialize` now gets a FRESH transport + a FRESH
  // per-session McpServer; later requests are routed by the Mcp-Session-Id
  // header. The auto-registered guest client is stored per session so every
  // request re-reads its role from the registry — admin role changes apply
  // instantly, with no server restart.
  interface HttpSessionEntry {
    transport: StreamableTransport;
    server: McpServer;
    client?: ExternalClient;
    lastActivityMs: number;
    /** #48: slot binding re-verified live on every session request. */
    slot?: { slotId: string; credentialId?: string };
  }
  const httpSessions = new Map<string, HttpSessionEntry>();

  /** Drop idle /mcp sessions so long-lived processes cannot leak transports. */
  function reapIdleHttpSessions(): void {
    // #109: idle interval through the validated env SSOT (0 = never reap).
    const idleMs = env.runtime.httpSessionIdleMs;
    if (idleMs <= 0 || httpSessions.size === 0) return;
    const cutoff = Date.now() - idleMs;
    for (const entry of httpSessions.values()) {
      if (entry.lastActivityMs >= cutoff) continue;
      // transport.close() → onclose → map delete + per-session server release.
      try { entry.transport.close(); } catch {
        const sid = entry.transport.sessionId;
        if (sid) httpSessions.delete(sid);
        void Promise.resolve().then(() => entry.server.close()).catch(() => undefined);
      }
    }
  }

  // #621 Phase 3: enforce the sliding idle window CONTINUOUSLY, not only
  // lazily on the next initialize. The bounded session table previously only
  // reaped when a NEW client initialized, so idle/dead sessions could occupy
  // table slots between initializes; a 60s unref'd sweep keeps the table
  // honest (lastActivityMs stays the single sliding-expiry signal).
  const sessionReaperTimer = setInterval(reapIdleHttpSessions, 60_000);
  // Never hold the process open just for the reaper — Render spin-down must
  // stay possible; the timer dies with the event loop.

  // #2710 watchdog increment (#2673 remedy pt.2): >10min without ANY sweep
  // completion (scheduled or manual) is the #2665 live-but-empty class
  // signature — alarm on the RISING EDGE only, re-arm on the next completion.
  // Anti-false-clear: a one-off manual sweep re-stamps the completion clock
  // and buys exactly one staleness window of silence; it cannot permanently
  // silence this alarm. The alarm is also mirrored into the durable health
  // history (__watchdog__ rows) so post-mortems survive restarts.
  const healthWatchdogBootedAtMs = Date.now();
  let healthWatchdogAlarmActive = false;
  const healthWatchdogTimer = setInterval(() => {
    void (async () => {
      try {
        const { globalHealthCache } = await import("./health/snapshot.js");
        const view = deriveWatchdog(
          Date.now(),
          healthWatchdogBootedAtMs,
          globalHealthCache.getLastCompletedSweepMs(),
          globalHealthCache.getSweepCompletions(),
        );
        if (view.alarmDue && !healthWatchdogAlarmActive) {
          healthWatchdogAlarmActive = true;
          console.error(
            `[HealthWatchdog] no sweep completion in >10min (completions=${view.sweepCompletions}, lastCompletedSweepAt=${String(view.lastCompletedSweepAt)}) — live-but-empty class #2665: registry is stale, not verified-healthy`,
          );
          await recordWatchdogAlarm(view);
        } else if (!view.stale) {
          // Fresh completion landed — re-arm so the NEXT gap re-alarms.
          healthWatchdogAlarmActive = false;
        }
      } catch {
        // The watchdog must never throw into the event loop.
      }
    })();
  }, 60_000);
  if (typeof healthWatchdogTimer.unref === "function") healthWatchdogTimer.unref();

  /** True when the parsed JSON-RPC body is an `initialize` request (or batch containing one). */
  function isMcpInitializeRequest(body: unknown): boolean {
    if (!body) return false;
    if (Array.isArray(body)) return body.some((m) => m && typeof m === "object" && (m as { method?: unknown }).method === "initialize");
    return typeof body === "object" && (body as { method?: unknown }).method === "initialize";
  }

  const httpServer = createServer(async (req: IncomingMessage, res: ServerResponse) => {
    const url = req.url ?? "/";
    let pathname = requestPath(req);
    const caller = resolveCaller(req);
    const role = caller.role;
    const client = caller.client;
    const tenantId = caller.tenantId;
    const isGlobalAdmin = caller.isGlobalAdmin;
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, x-api-key, mcp-session-id, x-tenant-id, x-tenant-admin-token");

    // Preflight CORS request
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    // #48: `/agents/<slot>/sse|mcp` — the slot URL form from the issue. The
    // URL is an identity doorway ONLY: it normalizes to `?client=<slot>` and
    // authentication still requires the slot credential (slot-verification.ts
    // resolveSlotSession — URL alone never grants the slot's stored role).
    const agentsRoute = /^\/agents\/([^/]+)\/(sse|mcp)$/.exec(pathname);
    if (agentsRoute) {
      const slotName = agentsRoute[1] ?? "";
      if (!isValidClientName(slotName)) {
        writeJson(res, 400, { error: "Invalid slot name in /agents/<slot>/ path" });
        return;
      }
      req.url = `/${agentsRoute[2]}?client=${encodeURIComponent(slotName)}`;
      pathname = `/${agentsRoute[2]}`;
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // বাংলা মন্তব্য: অথেনটিকেশন ও অ্যাক্সেস কন্ট্রোল পলিসি (MCP Auth Architecture)
    // ১. /mcp এন্ডপয়েন্ট: Claude Web (claude.ai), v0, Cursor বা যেকোনো পাবলিক এআই ক্লায়েন্টের 
    //    জন্য ওপেন রাখা হয়েছে (role = 'viewer' বা টোকেন দিলে সেই অনুযায়ী 'admin'/'agent')। 
    //    Claude Web যেহেতু ক���স্টম হেডার পাঠাতে পারে না, তাই এটি কোনো OAuth ছাড়াই সহজে সংযুক্ত হতে পারবে।
    // ২. অ্যাডমিন রুটসমূহ (/approve, /approvals, /clients, /autonomy/kill): এগুলো জীবনঘাতী বা সংবেদনশীল 
    //    অপারেশন। এগুলো কঠোরভাবে শুধুমাত্র ভ্যালিড MCP_API_KEY বা MCP_ADMIN_KEY দ্বারা সুরক্ষিত।
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // #698: admin-only routes must PREFIX-match consistently with the handlers
    // below, so suffix paths (/approvals/list, /autonomy/killswitch,
    // /approveXYZ, …) can never slip past the gate. The handlers themselves
    // re-check the caller role (defense in depth).
    const adminOnlyRoute = pathname.startsWith("/approve") || pathname.startsWith("/approvals") || pathname.startsWith("/clients") || pathname.startsWith("/autonomy/kill") || pathname.startsWith("/tenants");

    // Browser 1-click approval links: an HMAC signature bound to the request id,
    // the decision and an expiry — never a permanent credential in the URL.
    // The signature is verified again at the /approve endpoint (defense in depth).
    let isSignedApprovalLink = false;
    if (pathname === "/approve") {
      try {
        const guardUrl = new URL(url, `http://${req.headers.host || "localhost"}`);
        const gid = guardUrl.searchParams.get("id") ?? "";
        const gDecision = guardUrl.searchParams.get("decision") || "APPROVED";
        isSignedApprovalLink = Boolean(gid) && verifyApprovalLink(gid, gDecision, guardUrl.searchParams.get("exp") ?? "", guardUrl.searchParams.get("sig") ?? "");
      } catch {}
    }

    if (env.nodeEnv === "production" && adminOnlyRoute && !env.mcpApiKey && !env.mcpAdminKey) {
      res.writeHead(503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "MCP_API_KEY is required in production" }));
      return;
    }

    // Tenant routes: глобальный админ ИЛИ tenant admin (по заголовкам x-tenant-*).
    const isTenantAdminByHeader = Boolean(
      req.headers["x-tenant-id"] && req.headers["x-tenant-admin-token"] &&
      verifyTenantAdminToken(String(req.headers["x-tenant-id"]), String(req.headers["x-tenant-admin-token"]))
    );
    const canAccessProtectedRoute = role === "admin" || (pathname.startsWith("/clients") && (isTenantAdminByHeader || isGlobalAdmin));

    if (adminOnlyRoute && !canAccessProtectedRoute && !isSignedApprovalLink) {
      res.writeHead(role ? 403 : 401, { "Content-Type": "application/json", "WWW-Authenticate": "Bearer" });
      res.end(JSON.stringify({ error: role ? "Forbidden: Admin role required for this endpoint" : "Unauthorized: Invalid or missing MCP Bearer token" }));
      return;
    }
    if (adminOnlyRoute && pathname.startsWith("/tenants") && role !== "admin") {
      res.writeHead(403, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Forbidden: Tenants endpoints require global admin" }));
      return;
    }


    if (url === "/health" || url === "/") {
      // ROOT-CAUSE FIX (#2724): /health was hardcoded `status: "ok"` regardless
      // of actual service health. This violated AGENTS.md Rule #3 (Graceful
      // Degradation: "Honesty over polish"). Now: /health queries the same
      // globalHealthCache that /health/summary uses, and returns an honest
      // aggregate status. Uptime monitors probing /health will now correctly
      // alert when services are degraded.
      try {
        const { globalHealthCache } = await import("./health/snapshot.js");
        const snapshots = globalHealthCache.getAllSnapshots();
        const services = Object.entries(snapshots).map(([provider, snapshot]) => ({
          provider,
          status: snapshot.status,
        }));
        const unhealthy = services.filter((s) => s.status !== "healthy").length;
        // #2681: an empty snapshot table (post-restart, before any check ran) must NOT
        // read "ok" — that is the #2665 live-but-empty signature ("ok" + total:0 while
        // the system runs work). Boot-state honesty: derive "starting" (remains 200 —
        // a boot state is not an outage). Empty-array vacuous truth is the trap:
        // unhealthy === 0 is vacuously true over services = [].
        const status: string = services.length === 0 ? "starting" : unhealthy === 0 ? "ok" : unhealthy < services.length ? "degraded" : "outage";
        const httpStatus = status === "outage" ? 503 : 200;
        // #2710 watchdog increment: additive staleness telemetry so consumers
        // can distinguish "all-clear" from "no data / data too old" (the #2665
        // anti-false-clear requirement). Additive keys only — existing
        // consumers read status/services and are unaffected.
        const watchdogView = deriveWatchdog(
          Date.now(),
          healthWatchdogBootedAtMs,
          globalHealthCache.getLastCompletedSweepMs(),
          globalHealthCache.getSweepCompletions(),
        );
        res.writeHead(httpStatus, { "Content-Type": "application/json", "Cache-Control": "no-store" });
        res.end(JSON.stringify(withTimestamp({
          status,
          server: SERVER_NAME,
          version: SERVER_VERSION,
          services: { healthy: services.length - unhealthy, degraded: unhealthy, total: services.length },
          lastCompletedSweepAt: watchdogView.lastCompletedSweepAt,
          sweepCompletions: watchdogView.sweepCompletions,
          stale: watchdogView.stale,
        })));
      } catch {
        // Fallback: if health cache isn't loaded yet (cold start), report "starting" —
        // #2681: an unreadable cache is never evidence that everything is healthy,
        // so the fallback must not emit a bare "ok" either.
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(withTimestamp({ status: "starting", server: SERVER_NAME, version: SERVER_VERSION, note: "health cache not yet loaded", stale: true, lastCompletedSweepAt: null, sweepCompletions: 0 })));
      }
      return;
    }

    // ── #3297: Unified workforce telemetry — autonomous + interactive ─────────
    if (pathname === "/api/agents" && req.method === "GET") {
      // বাংলা: ড্যাশবোর্ড/টেলিমেট্রির জন্য একীভূত agent-গণনা —
      // autonomous Git worker + interactive AI client উভয়ই, শ্রেণিবিভাগসহ।
      // Read-only; viewer ভূমিকাই যথেষ্ট (sensitive metadata নেই)।
      if (!role) {
        writeJson(res, 401, { error: "Unauthorized: MCP Bearer token required" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      try {
        const workforce = await listWorkforce();
        writeJson(res, 200, workforce, { "Cache-Control": "no-store" });
      } catch (err) {
        writeJson(res, 503, { error: `Workforce telemetry unavailable: ${(err as Error).message}` });
      }
      return;
    }

    if (url === "/health/summary") {
      try {
        const { globalHealthCache } = await import("./health/snapshot.js");
        const snapshots = globalHealthCache.getAllSnapshots();
        const services = Object.entries(snapshots).map(([provider, snapshot]) => ({
          provider,
          status: snapshot.status,
          checkedAt: snapshot.checkedAt,
          latencyMs: snapshot.latencyMs,
        }));
        const unhealthy = services.filter((service) => !["healthy"].includes(service.status)).length;
        res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
        res.end(JSON.stringify({
          status: unhealthy ? "degraded" : "healthy",
          serviceCount: services.length,
          unhealthyCount: unhealthy,
          services: services.map((service) => ({
            ...service,
            circle: getServiceDescriptors().find((descriptor) => descriptor.provider === service.provider)?.circle ?? "unknown",
            configured: getServiceDescriptors().find((descriptor) => descriptor.provider === service.provider)?.configured ?? false,
          })),
          ...nowTimestamp(),
        }));
      } catch {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "unknown", error: "Summary unavailable" }));
      }
      return;
    }

    if (url === "/health/dashboard") {
      if (env.nodeEnv === "production" && !resolveRole(req)) {
        res.writeHead(401, { "Content-Type": "application/json", "WWW-Authenticate": "Bearer" });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
      }
      try {
        const { globalHealthCache } = await import("./health/snapshot.js");
        const { globalDependencyGraph } = await import("./health/dependency.js");
        res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
        res.end(JSON.stringify({
          snapshots: globalHealthCache.getAllSnapshots(),
          dependencies: globalDependencyGraph.getRawMap(),
          timestamp: new Date().toISOString(),
        }));
      } catch {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "unknown", error: "Dashboard unavailable" }));
      }
      return;
    }

    if (url === "/health/sweep") {
      if (env.nodeEnv === "production" && !resolveRole(req)) {
        res.writeHead(401, { "Content-Type": "application/json", "WWW-Authenticate": "Bearer" });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
      }

      try {
        const { globalHealthEngine } = await import("./health/engine.js");
        const report = await globalHealthEngine.runFullSweep();
        res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
        res.end(JSON.stringify(report));
      } catch {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "unknown", error: "Health sweep failed" }));
      }
      return;
    }

    if (url === "/health/summary" || url === "/health/dashboard" || url === "/health/sweep") {
      try {
        const { globalHealthEngine } = await import("./health/engine.js");
        const { globalHealthCache } = await import("./health/snapshot.js");
        const { globalDependencyGraph } = await import("./health/dependency.js");
        const isSweep = url === "/health/sweep";
        const report = isSweep ? await globalHealthEngine.runFullSweep() : undefined;
        const snapshots = report?.snapshots ?? globalHealthCache.getAllSnapshots();
        const services = Object.entries(snapshots).map(([provider, snapshot]) => ({
          provider,
          status: snapshot.status,
          checkedAt: snapshot.checkedAt,
          latencyMs: snapshot.latencyMs,
        }));
        const payload = url === "/health/dashboard"
          ? { snapshots, dependencies: globalDependencyGraph.getRawMap(), timestamp: new Date().toISOString() }
          : { status: report?.overallStatus ?? (services.some((service) => service.status !== "healthy") ? "degraded" : "healthy"), serviceCount: services.length, unhealthyCount: services.filter((service) => service.status !== "healthy").length, services, timestamp: new Date().toISOString() };
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(payload));
      } catch {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "unknown", error: "Health aggregation failed" }));
      }
      return;
    }

    if (url === "/health/ready") {
      try {
        const { globalHealthEngine } = await import("./health/engine.js");
        const report = await globalHealthEngine.runFullSweep();
        const degraded = Object.values(report.snapshots).filter((snapshot) => snapshot.status !== "healthy");
        res.writeHead(degraded.length ? 503 : 200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: degraded.length ? "degraded" : "ready", report }));
      } catch (error) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "unknown", error: "Readiness sweep failed" }));
      }
      return;
    }

    if (url === "/clients" && req.method === "GET") {
      const scope = isGlobalAdmin ? "*" : tenantId;
      res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify(withTimestamp({ scope, tenants: isGlobalAdmin ? listTenants() : undefined, clients: listClients(scope) })));
      return;
    }

    if (url === "/clients" && req.method === "POST") {
      let body = "";
      req.on("data", (chunk) => { body += chunk.toString(); });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          if (typeof input.name !== "string" || !input.name.trim()) throw new Error("name is required");
          if (!["viewer", "agent", "admin"].includes(input.role)) throw new Error("role must be viewer, agent, or admin");
          const provider = typeof input.provider === "string" && input.provider.trim() ? input.provider.trim() : "generic";
          const protocol = ["streamable-http", "sse", "stdio", "custom"].includes(input.protocol) ? input.protocol : "streamable-http";
          // Tenant isolation: client токен создаётся в tenant вызывающего.
          const targetTenant = isGlobalAdmin
            ? (typeof input.tenantId === "string" && input.tenantId ? input.tenantId : "tenant_default")
            : tenantId;
          const toolProfile = isValidToolProfile(input.toolProfile) ? input.toolProfile : undefined;
          const result = registerClient(input.name.trim(), input.role, input.scopes ?? defaultClientScopes(input.role), input.expiresAt, provider, protocol, targetTenant, undefined, toolProfile);
          res.writeHead(201, { "Content-Type": "application/json", "Cache-Control": "no-store" });
          res.end(JSON.stringify(withTimestamp({ ...result, tenantId: targetTenant })));
        } catch (error: any) { res.writeHead(400, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: error.message })); }
      });
      return;
    }

    if (url.startsWith("/clients/") && url.endsWith("/approve") && req.method === "POST") {
      const id = url.slice("/clients/".length, -"/approve".length);
      const scope = isGlobalAdmin ? "*" : tenantId;
      const client = approveClient(id, scope);
      res.writeHead(client ? 200 : 409, { "Content-Type": "application/json" });
      res.end(JSON.stringify(withTimestamp(client ?? { error: "Client is not pending or was not found" })));
      return;
    }

    if (url.startsWith("/clients/") && req.method === "PATCH") {
      const id = url.slice("/clients/".length);
      const scope = isGlobalAdmin ? "*" : tenantId;
      let body = "";
      req.on("data", (chunk) => { body += chunk.toString(); });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          let client;
          if (input.role) {
            if (!["viewer", "agent", "admin"].includes(input.role)) throw new Error("role must be viewer, agent, or admin");
            client = changeClientRole(id, input.role, scope);
          } else if (input.provider) {
            client = changeClientProvider(id, String(input.provider), scope);
          } else if ("toolProfile" in input) {
            // Tool Exposure Policy: set ('chatgpt' | 'readonly') or clear (null).
            if (input.toolProfile !== null && !isValidToolProfile(input.toolProfile)) {
              throw new Error("toolProfile must be 'chatgpt', 'readonly', or null");
            }
            client = changeClientProfile(id, input.toolProfile ?? null, scope);
          } else {
            throw new Error("Provide 'role', 'provider' or 'toolProfile' to update");
          }
          if (!client) throw new Error("Client not found or inactive");
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(withTimestamp(client)));
        } catch (error: any) { res.writeHead(400, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: error.message })); }
      });
      return;
    }

    if (url.startsWith("/clients/") && req.method === "DELETE") {
      const id = url.slice("/clients/".length);
      const scope = isGlobalAdmin ? "*" : tenantId;
      const ok = revokeClient(id, scope);
      res.writeHead(ok ? 200 : 404, { "Content-Type": "application/json" });
      res.end(JSON.stringify(withTimestamp({ revoked: ok, id })));
      return;
    }

    if (url.startsWith("/clients/") && url.endsWith("/rotate") && req.method === "POST") {
      const id = url.slice("/clients/".length, -"/rotate".length);
      const scope = isGlobalAdmin ? "*" : tenantId;
      const result = rotateClient(id, scope);
      res.writeHead(result ? 200 : 404, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify(withTimestamp(result ?? { error: "Client not found or inactive" })));
      return;
    }

    const TENANT_BAD_REQUEST = 400;

    if (url === "/tenants" && req.method === "GET") {
      const tenants = listTenants();
      res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify(withTimestamp({ tenants, scope: tenantId })));
      return;
    }

    if (url === "/tenants" && req.method === "POST") {
      let body = "";
      req.on("data", (chunk) => { body += chunk.toString(); });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          if (typeof input.name !== "string" || !input.name.trim()) throw new Error("name is required");
          const ownerEmail = typeof input.ownerEmail === "string" && input.ownerEmail.trim()
            ? input.ownerEmail.trim()
            : `${input.name.trim().toLowerCase().replace(/[^a-z0-9]/g, "")}@tenant.supremeai.local`;
          const limits = {
            ...(typeof input.maxClients === "number" && input.maxClients > 0 ? { maxClients: input.maxClients } : {}),
            ...(typeof input.maxToolsPerMinute === "number" && input.maxToolsPerMinute > 0 ? { maxToolsPerMinute: input.maxToolsPerMinute } : {}),
          };
          const result = createTenant({
            name: input.name.trim(),
            ownerEmail,
            type: input.type === "admin" ? "admin" : "customer",
            description: input.description,
            limits,
            plan: input.plan,
          });
          res.writeHead(201, { "Content-Type": "application/json", "Cache-Control": "no-store" });
          res.end(JSON.stringify(withTimestamp(result)));
        } catch (error: any) { res.writeHead(400, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: error.message })); }
      });
      return;
    }

    if (url === "/tenants" && req.method === "PATCH") {
      let body = "";
      req.on("data", (chunk) => { body += chunk.toString(); });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          const targetId = String(input.id ?? tenantId);
          if (!isGlobalAdmin && targetId !== tenantId) throw new Error("Forbidden: can only modify own tenant");
          if (input.activate !== undefined || input.suspend !== undefined || input.status !== undefined) {
            if (input.activate) { activateTenant(targetId); }
            else if (input.suspend || input.status === "suspended") { suspendTenant(targetId); }
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify(withTimestamp({ id: targetId, status: getTenant(targetId)?.status ?? "unknown" })));
            return;
          }
          if (input.rotate !== undefined) {
            const result = rotateTenantAdminToken(targetId);
            res.writeHead(201, { "Content-Type": "application/json", "Cache-Control": "no-store" });
            res.end(JSON.stringify(withTimestamp(result)));
            return;
          }
          if (input.name !== undefined || input.description !== undefined || input.status !== undefined || input.plan !== undefined || input.limits !== undefined) {
            const existing = getTenant(targetId);
            if (!existing) throw new Error("Tenant not found");
            const updated = updateTenant(targetId, {
              name: input.name !== undefined ? String(input.name) : existing.name,
              description: input.description !== undefined ? String(input.description) : existing.description,
              status: input.status !== undefined ? input.status : existing.status,
              plan: input.plan !== undefined ? input.plan : existing.plan,
              limits: input.limits ? {
                ...existing.limits,
                ...(typeof input.limits.maxClients === "number" ? { maxClients: input.limits.maxClients } : {}),
                ...(typeof input.limits.maxToolsPerMinute === "number" ? { maxToolsPerMinute: input.limits.maxToolsPerMinute } : {}),
              } : existing.limits,
            });
            res.writeHead(200, { "Content-Type": "application/json" });
            res.end(JSON.stringify(withTimestamp(updated)));
            return;
          }
          throw new Error("PATCH body must include activate, suspend, name/description/status/plan/limits, or rotate");
        } catch (error: any) { res.writeHead(400, { "Content-Type": "application/json" }); res.end(JSON.stringify({ error: error.message })); }
      });
      return;
    }


    if (url.startsWith("/tenants/") && url.endsWith("/clients") && req.method === "GET") {
      const tid = url.slice("/tenants/".length, -"/clients".length);
      const scope = isGlobalAdmin ? "*" : tenantId;
      if (!isGlobalAdmin && tid !== tenantId) {
        res.writeHead(403, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Forbidden: can only view own tenant clients" }));
        return;
      }
      const clients = listClients(scope === "*" ? "*" : scope);
      const count = countClientsByTenant(tid);
      res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      res.end(JSON.stringify(withTimestamp({ tenantId: tid, clientCount: count, clients })));
      return;
    }

    // ── #2596: সেন্ট্রাল টাস্ক কিউ এন্ডপয়েন্ট ─────────────────────────────
    // বাংলা মন্তব্য: এজেন্টরা এখন টাস্ক খোঁজা/ক্লেইম/হার্টবিট/সমাপ্তির জন্য টাওয়ারেই
    // আসবে — GitHub API-তে সরাসরি হাত দিয়ে rate-limit শেষ করার দরকার নেই।
    // অ্যাক্সেস: admin + agent (viewer/public নয় — লিজ নেওয়া write-অপারেশন)।
    if (pathname === "/tasks" && req.method === "GET") {
      if (role !== "admin" && role !== "agent") {
        writeJson(res, role ? 403 : 401, { error: role ? "Forbidden: agent or admin role required" : "Unauthorized: Invalid or missing MCP Bearer token" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      // বাসি ক্যাশ হলে ব্যাকগ্রাউন্ড সিঙ্ক (non-blocking) — ?refresh=1 হলে force-await।
      const forceRefresh = new URL(req.url ?? "/", `http://${req.headers.host || "localhost"}`).searchParams.get("refresh") === "1";
      if (forceRefresh) {
        await refreshFromGitHub();
      } else {
        ensureFreshSync();
      }
      const tasks = listTasks();
      writeJson(res, 200, withTimestamp({
        tasks: tasks.map((t) => ({ ...t, claimToken: undefined, githubLocked: isGithubLocked(t) })),
        status: taskQueueStatus(),
      }));
      return;
    }

    if (pathname === "/tasks/claim" && req.method === "POST") {
      if (role !== "admin" && role !== "agent") {
        writeJson(res, role ? 403 : 401, { error: role ? "Forbidden: agent or admin role required" : "Unauthorized: Invalid or missing MCP Bearer token" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      let body = "";
      req.on("data", (chunk: Buffer) => {
        body += chunk.toString();
        if (body.length > MAX_REQUEST_BYTES) {
          req.destroy();
          writeJson(res, 413, { error: "Payload too large" });
          return;
        }
      });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          const result = claimTask({ issue: input.issue, slot: input.slot, agent: input.agent });
          if (!result.ok) {
            writeJson(res, result.reason === "not-found" ? 404 : 409, withTimestamp({ ok: false, reason: result.reason, error: result.error, heldBy: result.heldBy ?? undefined }));
            return;
          }
          writeJson(res, 200, withTimestamp({
            ok: true,
            issue: result.task.issue,
            state: result.task.state,
            claimToken: result.claimToken,
            leaseExpiresAtMs: result.leaseExpiresAtMs,
            idempotentReclaim: result.idempotentReclaim,
            // বাংলা: টোকেন একবারই ফেরানো হয় — কিউ লিস্টিং-এ কখনো ফাঁস হবে না।
            task: { ...result.task, claimToken: undefined },
          }));
        } catch (error) {
          writeJson(res, 400, { error: (error as Error).message });
        }
      });
      return;
    }

    if (pathname === "/tasks/heartbeat" && req.method === "POST") {
      if (role !== "admin" && role !== "agent") {
        writeJson(res, role ? 403 : 401, { error: role ? "Forbidden: agent or admin role required" : "Unauthorized: Invalid or missing MCP Bearer token" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      let body = "";
      req.on("data", (chunk: Buffer) => {
        body += chunk.toString();
        if (body.length > MAX_REQUEST_BYTES) {
          req.destroy();
          writeJson(res, 413, { error: "Payload too large" });
          return;
        }
      });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          const result = heartbeatTask({ issue: input.issue, slot: input.slot, claimToken: input.claimToken });
          if (!result.ok) {
            writeJson(res, result.reason === "not-found" ? 404 : 409, withTimestamp({ ok: false, reason: result.reason, error: result.error }));
            return;
          }
          writeJson(res, 200, withTimestamp({ ok: true, issue: result.task.issue, state: result.task.state, leaseExpiresAtMs: result.leaseExpiresAtMs, lastHeartbeatAt: result.task.lastHeartbeatAt }));
        } catch (error) {
          writeJson(res, 400, { error: (error as Error).message });
        }
      });
      return;
    }

    if (pathname === "/tasks/complete" && req.method === "POST") {
      if (role !== "admin" && role !== "agent") {
        writeJson(res, role ? 403 : 401, { error: role ? "Forbidden: agent or admin role required" : "Unauthorized: Invalid or missing MCP Bearer token" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      let body = "";
      req.on("data", (chunk: Buffer) => {
        body += chunk.toString();
        if (body.length > MAX_REQUEST_BYTES) {
          req.destroy();
          writeJson(res, 413, { error: "Payload too large" });
          return;
        }
      });
      req.on("end", () => {
        try {
          const input = JSON.parse(body || "{}");
          const result = completeTask({
            issue: input.issue,
            slot: input.slot,
            claimToken: input.claimToken,
            knowledge: input.knowledge,
          });
          if (!result.ok) {
            const status = result.reason === "not-found" ? 404 : result.reason === "already-completed" ? 410 : 409;
            writeJson(res, status, withTimestamp({ ok: false, reason: result.reason, error: result.error }));
            return;
          }
          writeJson(res, 200, withTimestamp({ ok: true, issue: result.task.issue, state: result.task.state, completedAt: result.task.completedAt, knowledge: result.task.knowledge ?? null }));
        } catch (error) {
          writeJson(res, 400, { error: (error as Error).message });
        }
      });
      return;
    }

    // বাংলা মন্তব্য: /mcp-তে টোকেন ছাড়া সংযোগ public_viewer হিসেবে safe, public read-only capability পায়।
    // Support SSE transport for Web AI clients (like Claude Web or legacy MCP SSE)
    if (pathname === "/sse" && req.method === "GET") {
      // Bounded session table: each SSE session pins a transport + socket.
      // Without a cap, reconnect storms exhaust memory on small instances.
      // #109: cap through the validated env SSOT (0 = refuse all sessions).
      const maxSseSessions = env.runtime.maxSseSessions;
      if (sseSessions.size >= maxSseSessions) {
        writeJson(res, 503, { error: "Too many concurrent SSE sessions", activeSessions: sseSessions.size });
        return;
      }

      // #1767 + #2588: Dynamic Auto-Registration for No-Auth AI clients —
      // VENDOR-AGNOSTIC and shared with /mcp (see policy/auto-register.ts).
      // #48 Verified Slot Architecture: the URL alone is NEVER authentication.
      // A presented `?client=`/`/agents/<slot>/` identity adopts its stored
      // role ONLY when the request also presents a credential that verifies
      // live against the operational registry — otherwise the strict
      // `viewer` fallback applies (an observability record is still created
      // so the dashboard sees the connected AI).
      const session = await resolveSlotSession(req, { client, role, tenantId, protocol: "sse" });
      const effectiveClient = session.client;
      // #3297 auto-presence: SSE connect — interactive client সংযুক্ত হলো;
      // presence key লিখে রাখি (fire-and-forget)।
      void recordPresence({
        clientName: effectiveClient?.name ?? "sse-client",
        clientId: effectiveClient?.id ?? clientIpFor(req),
        protocol: "sse",
        tenantId,
      }).catch(() => undefined);

      const activeRole = session.role;
      const authenticated = session.authenticated;
      const accessMode = accessModeFor(activeRole, authenticated);
      const scopes = session.scopes.length > 0 ? session.scopes : defaultClientScopes(activeRole);
      const slotBinding = session.slotId && session.slotVerified ? { slotId: session.slotId, credentialId: session.credentialId } : undefined;
      const sseTransport = new SSEServerTransport("/messages", res);
      sseSessions.set(sseTransport.sessionId, sseTransport);
      if (effectiveClient) {
        sseClientMap.set(sseTransport.sessionId, effectiveClient);
      }
      if (slotBinding) {
        sseSlotMap.set(sseTransport.sessionId, slotBinding);
      }
      // P0 crash-loop fix: the MCP SDK forbids connecting one Protocol instance
      // to a second transport while another is live ("Already connected to a
      // transport"). Every session therefore gets its OWN McpServer via the
      // factory (full tool registration + RBAC wrapper included) — /sse and
      // /mcp alike (#2588). NEVER re-throw from the request handler: an
      // uncaught rejection here terminates the Node process.
      let sseServer: McpServer;
      try {
        sseServer = await serverFactory();
      } catch (err) {
        console.error("[MCP] SSE per-session server init failed:", err);
        sseSessions.delete(sseTransport.sessionId);
        sseClientMap.delete(sseTransport.sessionId);
        try { writeJson(res, 503, { error: "SSE session unavailable: server init failed" }); } catch {}
        return;
      }
      let dropped = false;
      const dropSession = () => {
        if (dropped) return;
        dropped = true;
        sseSessions.delete(sseTransport.sessionId);
        sseClientMap.delete(sseTransport.sessionId);
        sseSlotMap.delete(sseTransport.sessionId);
        try { sseTransport.close(); } catch {}
        // Release the per-session server + transport.
        void Promise.resolve().then(() => sseServer.close()).catch(() => undefined);
      };
      // The SDK's onclose can miss abrupt TCP drops (client crash, proxy idle
      // timeout). The socket 'close' event is ground truth — clean up on either.
      res.once("close", dropSession);
      sseTransport.onclose = dropSession;
      try {
        const effectiveGlobalAdmin = isGlobalAdmin || activeRole === "admin";
        await RequestContextStore.run({ role: activeRole, accessMode, authenticated, tenantBound: Boolean(effectiveClient?.id), clientId: effectiveClient?.id, scopes, toolProfile: effectiveClient?.toolProfile, isGlobalAdmin: effectiveGlobalAdmin, tenantId: effectiveGlobalAdmin ? "*" : tenantId, slotId: session.slotId, slotVerified: session.slotVerified, credentialId: session.credentialId }, async () => {
          await sseServer.connect(sseTransport);
        });
      } catch (err) {
        console.error("[MCP] SSE session failed to establish:", err);
        dropSession();
        // NEVER re-throw from the request handler: an uncaught rejection here
        // terminates the Node process (that was the P0). The client sees a
        // dropped/failed SSE stream and can retry.
        try { writeJson(res, 503, { error: "SSE session could not be established" }); } catch {}
        return;
      }
      return;
    }


    if (pathname === "/messages" && req.method === "POST") {
      const parsedUrl = new URL(req.url ?? "/", `http://${req.headers.host || "localhost"}`);
      const sid = parsedUrl.searchParams.get("sessionId");
      const sseTransport = sid ? sseSessions.get(sid) : undefined;
      if (!sseTransport) {
        // #621 Phase 3: structured + recoverable (same contract as /mcp).
        writeJson(res, 404, { error: "Session not found", code: "session_not_found", recoverable: true, action: "reconnect-sse" });
        return;
      }
      // #48: slot-bound sessions are re-authorized LIVE on every message —
      // suspension, demotion and credential rotation terminate the in-flight
      // stream on the immediate-next check (execution cancellation).
      const slotBinding = sid ? sseSlotMap.get(sid) : undefined;
      let slotRole: UserRole | undefined;
      let slotScopes: string[] | undefined;
      if (slotBinding && sid) {
        const verdict = await assertSlotAuthorization(slotBinding.slotId, slotBinding.credentialId, { operation: "message" });
        if (!verdict.allowed) {
          const transport = sseSessions.get(sid);
          if (transport) { try { transport.close(); } catch {} }
          sseSessions.delete(sid);
          sseClientMap.delete(sid);
          sseSlotMap.delete(sid);
          writeJson(res, 403, {
            error: `Forbidden: slot '${slotBinding.slotId}' authorization failed (${verdict.reason ?? "denied"}) — SSE session terminated (fail-closed, #48).`,
            code: "slot_authorization_failed",
          });
          return;
        }
        slotRole = verdict.role;
        slotScopes = verdict.scopes;
      }
      // Re-read client from map to pick up live database role upgrades (#1767)
      const mappedClient = sid ? sseClientMap.get(sid) : undefined;
      const refreshedClient = mappedClient?.id ? (getClient(mappedClient.id) ?? mappedClient) : client;
      // #3663 (P0 root-cause): the pre-production URL-gets-admin shortcut is gone —
      const activeRole = slotRole ?? refreshedClient?.role ?? role ?? DEFAULT_GUEST_ROLE; // #3663 fail-closed (was ?? "admin")
      const authenticated = Boolean(slotBinding || refreshedClient || role !== null);
      const accessMode = accessModeFor(activeRole, authenticated);
      const scopes = slotScopes ?? refreshedClient?.scopes ?? defaultClientScopes(activeRole);
      const effectiveGlobalAdmin = isGlobalAdmin || activeRole === "admin";
      await RequestContextStore.run({ role: activeRole, accessMode, authenticated, tenantBound: Boolean(refreshedClient?.id || slotBinding), clientId: refreshedClient?.id ?? slotBinding?.slotId, scopes, toolProfile: refreshedClient?.toolProfile, isGlobalAdmin: effectiveGlobalAdmin, tenantId: effectiveGlobalAdmin ? "*" : tenantId, slotId: slotBinding?.slotId, slotVerified: Boolean(slotBinding), credentialId: slotBinding?.credentialId }, async () => {
        await sseTransport.handlePostMessage(req, res);
      });
      return;
    }

    if (pathname === "/mcp") {
      // Per-IP rate limit (#695): sliding window, 429 + Retry-After when exceeded.
      const rate = consumeMcpRateLimit(clientIpFor(req));
      if (!rate.allowed) {
        writeJson(
          res,
          429,
          { error: "Rate limit exceeded for /mcp", retryAfterMs: rate.retryAfterMs },
          { "Retry-After": String(Math.ceil(rate.retryAfterMs / 1000)) }
        );
        return;
      }
      if (!["GET", "POST", "DELETE"].includes(req.method ?? "")) {
        writeJson(res, 405, { error: "Method not allowed" }, { Allow: "GET, POST, DELETE" });
        return;
      }
      const contentLength = Number(req.headers["content-length"] ?? 0);
      if (Number.isFinite(contentLength) && contentLength > MAX_REQUEST_BYTES) {
        writeJson(res, 413, { error: "MCP request exceeds the maximum size" });
        return;
      }
      const activeRole = role ?? DEFAULT_GUEST_ROLE; // #3663 fail-closed (was ?? "admin": anonymous → global-admin context)
      const authenticated = Boolean(role !== null || client);
      const accessMode = accessModeFor(activeRole, authenticated);
      const scopes = client?.scopes ?? defaultClientScopes(activeRole);
      const requiredRole = accessMode === "admin" ? "admin" : accessMode === "agent" ? "agent" : "viewer";
      if (!roleAllows(activeRole, requiredRole)) {
        writeJson(res, 403, { error: "Forbidden: client role cannot access MCP tools", code: "protected_capability" });
        return;
      }

      // Accept header compatibility (allow generic web fetchers that omit Accept)
      if (!req.headers["accept"] || req.headers["accept"] === "*/*") {
        req.headers["accept"] = "application/json, text/event-stream";
      }

      // ── Per-session stateful routing (#2588) ────────────────────────────────
      // The OLD code forced every client through ONE boot-time global transport
      // (auto-injecting the shared session id into headerless requests and
      // poking `(transport as any)._webStandardTransport._initialized` on
      // re-initialize). Once any client closed its session the shared transport
      // went `_closed` and EVERY new client got `404 -32001 Session not found`
      // forever — the live Gemini Spark failure. Canonical stateful pattern:
      // existing requests route by Mcp-Session-Id header; only a fresh
      // `initialize` (no header) mints a NEW per-session transport + server.
      let body = "";
      req.on("data", (chunk) => { body += chunk.toString(); });
      req.on("end", async () => {
        let parsedBody: any;
        try {
          if (body) parsedBody = JSON.parse(body);
        } catch {}

        // ── Anonymous-mutation plane bound (#2363 Option A) ──
        // Per-(caller IP, tool) hourly window on the 4 mutation tools.
        // 429 + Retry-After at the HTTP layer; read plane and malformed
        // bodies fail open into the downstream RBAC/limits untouched.
        const mutationGate = mutationToolGateError(parsedBody, clientIpFor(req));
        if (mutationGate) {
          writeJson(
            res,
            429,
            { error: `Rate limit exceeded for mutation tool '${mutationGate.tool}'`, tool: mutationGate.tool, retryAfterMs: mutationGate.retryAfterMs },
            { "Retry-After": String(Math.ceil(mutationGate.retryAfterMs / 1000)) }
          );
          return;
        }

        const sessionIdHeader = typeof req.headers["mcp-session-id"] === "string"
          ? (req.headers["mcp-session-id"] as string)
          : undefined;

        // ── Existing session: route by header, refresh role LIVE from the ──
        // registry (admin role changes apply instantly, like /messages #1767).
        // #48: slot-bound sessions additionally re-authorize live on EVERY
        // request — suspension/demotion/rotation fail closed immediately.
        if (sessionIdHeader) {
          const entry = httpSessions.get(sessionIdHeader);
          if (!entry) {
            // #621 Phase 3: session loss is EXPECTED after redeploys/spin-downs
            // (the session table is in-memory by design). Structured, recoverable
            // error so automated agents self-heal with a fresh initialize instead
            // of treating -32001 as fatal.
            writeJson(res, 404, { jsonrpc: "2.0", error: { code: -32001, message: "Session not found. Send a new initialize request to establish a session.", data: { code: "session_not_found", recoverable: true, action: "send-initialize" } }, id: null });
            return;
          }
          entry.lastActivityMs = Date.now();
          let slotRole: UserRole | undefined;
          let slotScopes: string[] | undefined;
          if (entry.slot) {
            const verdict = await assertSlotAuthorization(entry.slot.slotId, entry.slot.credentialId, { operation: "message" });
            if (!verdict.allowed) {
              const sessionError = {
                jsonrpc: "2.0" as const,
                error: {
                  code: -32001,
                  message: `Slot '${entry.slot.slotId}' authorization failed (${verdict.reason ?? "denied"}) — session terminated (fail-closed, #48). Send a new initialize request.`,
                  data: { code: "slot_authorization_failed", reason: verdict.reason ?? "denied" },
                },
                id: null,
              };
              try { entry.transport.close(); } catch {}
              httpSessions.delete(sessionIdHeader);
              writeJson(res, 403, sessionError);
              return;
            }
            slotRole = verdict.role;
            slotScopes = verdict.scopes;
          }
          const refreshedClient = entry.client?.id ? (getClient(entry.client.id) ?? entry.client) : undefined;
          // #3297 auto-presence: প্রতিটি সেশন-রিকোয়েস্টই interactive client-এর
          // liveness প্রমাণ — sliding-TTL presence রিফ্রেশ (fire-and-forget,
          // presence কখনোই মূল পাথ ভাঙবে না)।
          void recordPresence({
            clientName: refreshedClient?.name ?? entry.client?.name ?? "mcp-session",
            clientId: refreshedClient?.id ?? entry.client?.id ?? sessionIdHeader,
            protocol: "streamable-http",
            tenantId,
          }).catch(() => undefined);
      // #3663 (P0 root-cause): the pre-production URL-gets-admin shortcut is gone —
          const sessionRole = slotRole ?? refreshedClient?.role ?? role ?? DEFAULT_GUEST_ROLE; // #3663 fail-closed (was ?? "admin")
          const sessionAuthenticated = Boolean(entry.slot || refreshedClient || role !== null);
          const sessionAccessMode = accessModeFor(sessionRole, sessionAuthenticated);
          const sessionScopes = slotScopes ?? refreshedClient?.scopes ?? defaultClientScopes(sessionRole);
          const effectiveGlobalAdmin = isGlobalAdmin || sessionRole === "admin";
          await RequestContextStore.run({ role: sessionRole, accessMode: sessionAccessMode, authenticated: sessionAuthenticated, tenantBound: Boolean(refreshedClient?.id || entry.slot), clientId: refreshedClient?.id ?? entry.slot?.slotId, scopes: sessionScopes, toolProfile: refreshedClient?.toolProfile, isGlobalAdmin: effectiveGlobalAdmin, tenantId: effectiveGlobalAdmin ? "*" : tenantId, slotId: entry.slot?.slotId, slotVerified: Boolean(entry.slot), credentialId: entry.slot?.credentialId }, async () => {
            await entry.transport.handleRequest(req, res, parsedBody);
          });
          return;
        }

        // ── No session header: only a fresh `initialize` may create one. ──
        if (!isMcpInitializeRequest(parsedBody)) {
          writeJson(res, 400, { jsonrpc: "2.0", error: { code: -32000, message: `Bad Request: Mcp-Session-Id header missing. ${req.method === "GET" ? "The GET method requires an active session." : "Send an initialize request first."}` }, id: null });
          return;
        }

        // Bounded session table (mirror of the SSE cap) + idle reaping.
        reapIdleHttpSessions();
        const maxHttpSessions = env.runtime.maxHttpSessions;
        if (httpSessions.size >= maxHttpSessions) {
          // #1886: pressure-eviction admission. Under sustained short-lived
          // client churn (cron fleet reconnecting per dispatch, tokenless AI
          // crawlers) the reaper's 1 h idle TTL cannot free slots fast enough
          // and the full table refuses EVERY fresh initialize — a steady-state
          // fleet-door lockout (live incident 2026-10-28, /mcp 503
          // activeSessions:100 while /sse stayed open). Admit by evicting the
          // single least-recently-active occupant IF it has been idle ≥
          // sessionAdmissionIdleFloorMs; the victim gets the table's existing
          // structured recovery path (404/-32001 send-initialize, same as
          // redeploys/spin-downs), so no new client-visible failure mode.
          // floor=0 keeps the historical refuse-only behavior.
          const evictId = pickPressureEvictionSessionId(
            Array.from(httpSessions.entries(), ([sessionId, e]) => ({ sessionId, lastActivityMs: e.lastActivityMs })),
            Date.now(),
            env.runtime.sessionAdmissionIdleFloorMs,
          );
          if (evictId !== null) {
            const victim = httpSessions.get(evictId);
            if (victim) {
              // Same release mechanics as reapIdleHttpSessions(): transport
              // close fires onclose → map delete + per-session server close;
              // the catch branch releases manually if onclose never fires.
              try { victim.transport.close(); } catch {
                httpSessions.delete(evictId);
                void Promise.resolve().then(() => victim.server.close()).catch(() => undefined);
              }
            }
          }
          if (httpSessions.size >= maxHttpSessions) {
            writeJson(res, 503, { jsonrpc: "2.0", error: { code: -32000, message: "Too many concurrent MCP sessions", activeSessions: httpSessions.size }, id: null });
            return;
          }
        }

        // Zero-manual-registration hook (#2588): a tokenless client — Gemini
        // Spark, xAI Grok, ANY AI — is auto-registered in the database on its
        // very first handshake, with protocol, client id, IP and timestamps.
        // #48 Verified Slot Architecture: a `?client=<slot>` / `/agents/<slot>/`
        // URL only adopts the slot's stored role when a credential verifies
        // live; otherwise the strict viewer fallback applies.
        const session = await resolveSlotSession(req, { client, role, tenantId, protocol: "streamable-http" });
        const effectiveClient = session.client;
        // #3297 auto-presence: নতুন initialize handshake-ই interactive client-এর
        // প্রথম সংযোগ-সংকেত — clientInfo.name (MCP spec) বা auto-registered
        // guest label থেকে identity, Redis-এ 300s sliding TTL।
        void recordPresence({
          clientName:
            extractClientInfoName(parsedBody) ??
            effectiveClient?.name ??
            "unknown-mcp-client",
          clientId: effectiveClient?.id ?? clientIpFor(req),
          protocol: "streamable-http",
          tenantId,
        }).catch(() => undefined);
        const initRole = session.role;
        const initAuthenticated = session.authenticated;
        const initAccessMode = accessModeFor(initRole, initAuthenticated);
        const initScopes = session.scopes.length > 0 ? session.scopes : defaultClientScopes(initRole);
        const slotBinding = session.slotId && session.slotVerified ? { slotId: session.slotId, credentialId: session.credentialId } : undefined;

        const httpTransport = new StreamableHTTPServerTransport({
          sessionIdGenerator: () => randomUUID(),
        });
        let sessionServer: McpServer;
        try {
          sessionServer = await serverFactory();
        } catch (err) {
          console.error("[MCP] /mcp per-session server init failed:", err);
          try { httpTransport.close(); } catch {}
          try { writeJson(res, 503, { jsonrpc: "2.0", error: { code: -32000, message: "MCP session unavailable: server init failed" }, id: null }); } catch {}
          return;
        }
        let dropped = false;
        const dropSession = () => {
          if (dropped) return;
          dropped = true;
          const sid = httpTransport.sessionId;
          if (sid) httpSessions.delete(sid);
          void Promise.resolve().then(() => sessionServer.close()).catch(() => undefined);
        };
        // SDK close (DELETE termination, protocol error) is the lifecycle hook.
        httpTransport.onclose = dropSession;
        try {
          await sessionServer.connect(httpTransport);
        } catch (err) {
          console.error("[MCP] /mcp session connect failed:", err);
          dropSession();
          try { writeJson(res, 503, { jsonrpc: "2.0", error: { code: -32000, message: "MCP session could not be established" }, id: null }); } catch {}
          return;
        }
        const effectiveGlobalAdmin = isGlobalAdmin || initRole === "admin";
        await RequestContextStore.run({ role: initRole, accessMode: initAccessMode, authenticated: initAuthenticated, tenantBound: Boolean(effectiveClient?.id), clientId: effectiveClient?.id, scopes: initScopes, toolProfile: effectiveClient?.toolProfile, isGlobalAdmin: effectiveGlobalAdmin, tenantId: effectiveGlobalAdmin ? "*" : tenantId, slotId: session.slotId, slotVerified: session.slotVerified, credentialId: session.credentialId }, async () => {
          await httpTransport.handleRequest(req, res, parsedBody);
        });
        // The SDK assigns the session id DURING the initialize handshake; only
        // register the entry if the handshake actually established one (and
        // did not already tear the session down).
        if (httpTransport.sessionId && !dropped) {
          httpSessions.set(httpTransport.sessionId, { transport: httpTransport, server: sessionServer, client: effectiveClient, lastActivityMs: Date.now(), slot: slotBinding });
        }
      });
      return;
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // /gemini — Universal 3rd Pillar: Gemini Function Calling Adapter (#2590)
    // বাংলা মন্তব্য: Gemini Spark / AI Studio native function-calling ক্লায়েন্টরা
    // MCP handshake করে না — তাদের জন্য সম্পূর্ণ stateless adapter:
    //   GET  /gemini        → adapter info (৩-পিলার manifest)
    //   GET  /gemini/tools  → Gemini functionDeclarations (সব MCP tool-এর রূপান্তর)
    //   POST /gemini        → { name, args } function-call execution
    // Tool-এর SSoT একটাই — serverFactory (RBAC + rate-limit + timeout সহ);
    // /gemini শুধু একটি প্রোটোকল-মুখ, কোনো tool logic duplicate নয়।
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if (pathname === "/gemini" || pathname.startsWith("/gemini/")) {
      // /mcp-র একই per-IP sliding-window rate limit — একটাই budget table।
      const geminiRate = consumeMcpRateLimit(clientIpFor(req));
      if (!geminiRate.allowed) {
        writeJson(res, 429, { error: "Rate limit exceeded for /gemini", retryAfterMs: geminiRate.retryAfterMs }, { "Retry-After": String(Math.ceil(geminiRate.retryAfterMs / 1000)) });
        return;
      }

      // Vendor-agnostic zero-manual-registration (#2588 pattern): tokenless
      // caller → auto-registered guest (public read-only scope পায়)।
      // #48: same verified-slot rule as /sse + /mcp — a `?client=<slot>` URL
      // never authenticates on its own; without a verifying credential the
      // strict viewer fallback applies.
      const geminiSession = await resolveSlotSession(req, { client, role, tenantId, protocol: "custom" });
      const geminiClient = geminiSession.client;
      const geminiRole = geminiSession.role;
      const geminiAuthenticated = geminiSession.authenticated;
      const geminiAccessMode = accessModeFor(geminiRole, geminiAuthenticated);
      const geminiScopes = geminiSession.scopes.length > 0 ? geminiSession.scopes : defaultClientScopes(geminiRole);
      const geminiEffectiveGlobalAdmin = isGlobalAdmin || geminiRole === "admin";
      const geminiRequestContext = { role: geminiRole, accessMode: geminiAccessMode, authenticated: geminiAuthenticated, tenantBound: Boolean(geminiClient?.id), clientId: geminiClient?.id, scopes: geminiScopes, toolProfile: geminiClient?.toolProfile, isGlobalAdmin: geminiEffectiveGlobalAdmin, tenantId: geminiEffectiveGlobalAdmin ? "*" : tenantId, slotId: geminiSession.slotId, slotVerified: geminiSession.slotVerified, credentialId: geminiSession.credentialId };
      const geminiAdapterContext = { serverName: SERVER_NAME, serverVersion: SERVER_VERSION, serverFactory };

      // ── GET /gemini — adapter info manifest ──
      if (req.method === "GET" && (pathname === "/gemini" || pathname === "/gemini/")) {
        writeJson(res, 200, withTimestamp(geminiAdapterInfo(geminiAdapterContext)));
        return;
      }

      // ── GET /gemini/tools — Gemini functionDeclarations ──
      if (req.method === "GET" && pathname === "/gemini/tools") {
        try {
          const manifest = await RequestContextStore.run(geminiRequestContext, async () => listGeminiTools(geminiAdapterContext));
          writeJson(res, 200, withTimestamp(manifest));
        } catch (err) {
          // বাংলা মন্তব্য: manifest generation fail → honest 503 (graceful
          // degradation, Invariant #3) — কখনো fake empty list নয়।
          console.error("[MCP] /gemini/tools manifest failed:", err);
          writeJson(res, 503, { error: "Gemini function manifest unavailable" });
        }
        return;
      }

      // ── POST /gemini — stateless function-call execution ──
      if (req.method === "POST" && (pathname === "/gemini" || pathname === "/gemini/")) {
        const contentLength = Number(req.headers["content-length"] ?? 0);
        if (Number.isFinite(contentLength) && contentLength > MAX_REQUEST_BYTES) {
          writeJson(res, 413, { error: "Gemini function call exceeds the maximum size" });
          return;
        }
        let geminiBody = "";
        req.on("data", (chunk) => { geminiBody += chunk.toString(); });
        req.on("end", async () => {
          let parsedGeminiBody: { name?: unknown; args?: unknown; arguments?: unknown };
          try {
            parsedGeminiBody = geminiBody ? JSON.parse(geminiBody) : {};
          } catch {
            writeJson(res, 400, { error: "Invalid JSON body for Gemini function call" });
            return;
          }
          const functionName = typeof parsedGeminiBody?.name === "string" ? parsedGeminiBody.name.trim() : "";
          if (!functionName) {
            writeJson(res, 400, { error: "Missing 'name' field for the Gemini function call" });
            return;
          }
          const functionArgs = (parsedGeminiBody.args ?? parsedGeminiBody.arguments) as Record<string, unknown> | undefined;
          try {
            const callResult = await RequestContextStore.run(geminiRequestContext, async () =>
              executeGeminiFunctionCall(geminiAdapterContext, functionName, functionArgs),
            );
            writeJson(res, 200, withTimestamp(callResult));
          } catch (err) {
            console.error(`[MCP] /gemini function call '${functionName}' failed:`, err);
            const message = err instanceof Error ? err.message : String(err);
            if (message.includes("Unknown tool") || message.includes("not found")) {
              writeJson(res, 404, { ok: false, tool: functionName, error: `Unknown tool: ${functionName}. Fetch GET /gemini/tools for the list of valid function names.` });
            } else if (err instanceof SyntaxError || message.includes("arguments")) {
              writeJson(res, 400, { ok: false, tool: functionName, error: `Invalid arguments for tool '${functionName}': ${message}` });
            } else {
              writeJson(res, 503, { ok: false, tool: functionName, error: "Gemini function call failed at the transport layer" });
            }
          }
        });
        return;
      }

      writeJson(res, 405, { error: "Method not allowed for /gemini" }, { Allow: "GET, POST" });
      return;
    }

    if (url === "/approvals" || url.startsWith("/approvals")) {
      // Defense in depth (#698): the route gate prefix-matches /approvals*, but
      // the handler re-checks the caller role itself.
      if (role !== "admin") {
        writeJson(res, role ? 403 : 401, { error: role ? "Forbidden: Admin role required for approval listings" : "Unauthorized: Invalid or missing MCP Bearer token" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      try {
        const { globalApprovalManager } = await import("./policy/approvals/lifecycle.js");
        const items = globalApprovalManager.getAllRequests().map(req => ({
          id: req.id,
          action: `${req.context.provider}.${req.context.action}`,
          target: req.context.provider,
          requested_by: "agent",
          requested_at: new Date(req.createdAtMs).toISOString(),
          reason: `Action requires approval. Parameters: ${JSON.stringify(req.metadata ?? {})}`,
          status: req.state.toLowerCase(),
          ...timestampDetails(req.createdAtMs, req.expiresAtMs, req.resolvedAtMs ?? req.createdAtMs),
          resolvedAt: req.resolvedAtMs ? new Date(req.resolvedAtMs).toISOString() : undefined,
          resolvedAtMs: req.resolvedAtMs,
        }));
        res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
        res.end(JSON.stringify({ items, total: items.length, storage: globalApprovalManager.storageMode }));
      } catch (err: any) {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      }
      return;
    }

    if (url.startsWith("/approve")) {
      const parsedUrl = new URL(url, `http://${req.headers.host}`);
      const id = parsedUrl.searchParams.get("id");
      const decision = (parsedUrl.searchParams.get("decision") || "APPROVED") as "APPROVED" | "REJECTED";
      if (!id) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Missing id parameter" }));
        return;
      }
      // Signed-link callers have no admin role; verify their signature again here
      // (the guard above already validated it — this is defense in depth).
      if (!role) {
        const linkOk = verifyApprovalLink(id, decision, parsedUrl.searchParams.get("exp") ?? "", parsedUrl.searchParams.get("sig") ?? "");
        if (!linkOk) {
          res.writeHead(401, { "Content-Type": "application/json", "WWW-Authenticate": "Bearer" });
          res.end(JSON.stringify({ error: "Unauthorized: invalid, expired or missing approval link signature" }));
          return;
        }
      }
      // Defense in depth (#698): an authenticated non-admin can never resolve
      // approvals — only admin tokens or a valid signed link may.
      if (role && role !== "admin") {
        res.writeHead(403, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Forbidden: Admin role or signed approval link required" }));
        return;
      }
      try {
        const { globalApprovalManager } = await import("./policy/approvals/lifecycle.js");
        globalApprovalManager.resolveRequest(id, decision);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: decision.toLowerCase(), id }));
      } catch (err: any) {
        res.writeHead(409, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message, code: "approval_transition_rejected" }));
      }
      return;
    }

    if (url.startsWith("/webhooks/")) {
      let body = "";
      req.on("data", chunk => body += chunk.toString());
      req.on("end", async () => {
        try {
          const isGithub = url === "/webhooks/github";
          const secret = isGithub ? env.githubWebhookSecret : env.cloudflareWebhookSecret;
          const signatureHeader = isGithub ? "x-hub-signature-256" : "x-cloudflare-signature";
          if (env.nodeEnv === "production" && !hasWebhookSignature(req.headers[signatureHeader]?.toString(), body, secret ?? "")) {
            res.writeHead(401, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: "Invalid webhook signature" }));
            return;
          }
          const payload = JSON.parse(body || "{}");
          const { globalEventGateway } = await import("./events/gateway.js");
          const { globalEventNormalizer } = await import("./events/normalizer.js");

          if (url === "/webhooks/github") {
            const eventName = req.headers["x-github-event"] as string || "unknown";
            // #69: delivery id rides the normalized event for idempotency.
            const deliveryId = (req.headers["x-github-delivery"] as string) || undefined;
            const normalized = globalEventNormalizer.normalizeGitHubEvent(eventName, payload, deliveryId);
            await globalEventGateway.dispatch(normalized);
          } else if (url === "/webhooks/cloudflare") {
            const normalized = globalEventNormalizer.normalizeCloudflareEvent(payload);
            await globalEventGateway.dispatch(normalized);
          }
          
          res.writeHead(200);
          res.end(JSON.stringify({ status: "received" }));
        } catch (err: any) {
          res.writeHead(400);
          res.end(JSON.stringify({ error: err.message }));
        }
      });
      return;
    }

    if (url.startsWith("/autonomy/kill")) {
      // Defense in depth (#698): the route gate prefix-matches /autonomy/kill*,
      // but the handler re-checks the caller role itself.
      if (role !== "admin") {
        writeJson(res, role ? 403 : 401, { error: role ? "Forbidden: Admin role required for the autonomy kill switch" : "Unauthorized: Invalid or missing MCP Bearer token" }, { "WWW-Authenticate": "Bearer" });
        return;
      }
      try {
        const { globalKillSwitch } = await import("./remediation/killswitch.js");
        globalKillSwitch.emergencyStop();
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(`<h1>🚨 AUTONOMY KILLED</h1><p>System dropped to L0 mode.</p>`);
      } catch (err: any) {
        res.writeHead(500, { "Content-Type": "text/html" });
        res.end(`<h1>Error</h1><p>${err.message}</p>`);
      }
      return;
    }

    res.writeHead(404);
    res.end("Not found");
  });

  // #2588: no boot-time global transport/server connection anymore — every
  // /sse and /mcp session connects its OWN fresh McpServer instance (see the
  // session tables above). This was the root cause of the shared-transport
  // `404 -32001 Session not found` lockout.

  httpServer.listen(env.port, () => {
    console.error(`[MCP] SupremeAI Control Tower → http://localhost:${env.port}/mcp`);
    console.error(`[MCP] Health → http://localhost:${env.port}/health`);
  });
}

export { startHttpServer };
