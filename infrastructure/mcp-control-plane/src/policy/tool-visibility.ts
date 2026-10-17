import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { RequestContextStore } from "./auth.context.js";
import { toolAccessError } from "./mcp-access.js";

/**
 * Tool Exposure Policy — capability registry vs client-visible tool surface.
 *
 * বাংলা মন্তব্য (founder অনুমোদিত নীতি):
 *   "Internal capability count ≠ Client-visible tool count"
 *
 * THE PROBLEM (#tool-exposure): the tower registers ~90 internal tools and the
 * SDK's default tools/list handler shows ALL of them to EVERY caller. The
 * call-path RBAC gate (#695) correctly DENIES most of them at execution time,
 * so anonymous ChatGPT guests see an 85+ tool menu where 81 entries answer
 * "Forbidden: requires agent role or higher". That is a discovery/
 * authorization MISMATCH — UX noise, not a security failure — but it poisons
 * tool-selection for LLM clients and misrepresents the tower's public surface.
 *
 * THE FIX (this file): a DISCOVERY choke point that curates WHAT A CLIENT
 * SEES, composed with — never replacing — the RBAC call gate:
 *
 *   visible(tool) = RBAC-allows-call(tool) AND profile-allows-visibility(tool)
 *
 * Design invariants (all enforced by test_tool_visibility.ts):
 *   1. list ⊆ call: nothing is ever ADVERTISED that the caller could not
 *      execute. The filter composes the SAME toolAccessError() used by the
 *      call wrapper — one RBAC source of truth, drift impossible.
 *   2. Visibility ≠ authorization: a profiled client that addresses a hidden
 *      tool directly still goes through the UNCHANGED RBAC call gate. Profiles
 *      curate prompts; RBAC enforces security. The profile layer can never
 *      become a shadow ACL.
 *   3. Fail-closed everywhere: no RequestContextStore ⇒ empty list. SDK
 *      internals drift ⇒ LOUD warning + degraded-but-STILL-FILTERED fallback.
 *   4. One choke point for every pillar: /sse, /messages, /mcp (stateful) and
 *      /gemini (stateless in-memory pair) ALL serve tools/list through the
 *      same wrapped handler, because all of them run inside a
 *      RequestContextStore that carries the caller's toolProfile.
 *   5. Kill-switch: MCP_DISCOVERY_FILTER=off restores the unfiltered SDK
 *      behavior (rollback = env flip, no redeploy of code).
 *
 * What this file deliberately does NOT do (rejected alternatives, see
 * docs/TOOL-EXPOSURE.md):
 *   - NO mega-tool grouping (github_inspect{operation} breaks per-tool zod
 *     validation and the policy-schema tool→provider→action→R-level SSoT).
 *   - NO parallel YAML metadata layer (a second source of truth re-creates
 *     the drift class #2429 removed — visibility DERIVES from the same
 *     classifyToolCapability the call path uses).
 */

/** Client tool-surface profiles. Absent/undefined profile = full RBAC surface. */
export type ToolProfile = "chatgpt" | "readonly";

/**
 * The curated ChatGPT surface: read-mostly, low-noise, high-value tools.
 * Names are SANITIZED wire names (dots→underscores — the same form
 * `classifyToolCapability` and the SDK's `_registeredTools` use).
 *
 * Curation principles:
 *  - every read/monitoring domain is represented (github/render/supabase/
 *    redis/cloudflare/ai/memory/docs/agents);
 *  - secret-class tools (infisical_*, github_list_secrets, render_get_env_vars)
 *    are NEVER listed (they are also RBAC admin-only — invariant 1 holds);
 *  - exactly TWO operational writes: notify_telegram (the one sanctioned
 *    outbound channel) and agent_review_workflow_execute (the guarded,
 *    policy-checked review flow);
 *  - autonomy_kill_switch and other destructive actions stay invisible
 *    (and remain RBAC-gated on the call path).
 */
const CHATGPT_CURATED_TOOLS: readonly string[] = [
  // system / observability
  "system_summary",
  "system_health",
  "system_dependencies",
  "health_dashboard",
  // github (read)
  "github_read_file",
  "github_read_external_file",
  "github_repo_info",
  "github_repo_tree",
  "github_list_prs",
  "github_workflow_runs",
  "github_get_failed_logs",
  "github_search_repos",
  "github_collect_highlights",
  // render (read)
  "render_list_services",
  "render_service_health",
  "render_get_logs",
  // supabase (read)
  "supabase_read_table",
  "supabase_health",
  // redis (read)
  "redis_ping",
  "redis_read_key",
  "redis_stats",
  // cloudflare (read)
  "cloudflare_worker_status",
  "cloudflare_analytics",
  // ai
  "ai_analyze_code",
  "ai_list_providers",
  "ai_available_providers",
  // memory / resources / autonomy visibility
  "memory_status",
  "resource_list",
  "autonomy_status",
  // agents (status + guarded workflow execution)
  "agent_status",
  "agent_review_workflow_status",
  "agent_review_workflow_execute",
  "guardian_evaluate_pr",
  // bridge onboarding (public front door — zero-credential external agents)
  "bridge_guide",
  "bridge_work_queue",
  "bridge_work_order",
  "bridge_submit_patch",
  "work_claim",
  // docs
  "docs_search",
  "docs_list",
  // the single sanctioned outbound notify channel
  "notify_telegram",
];

/** The mutating tools inside the curated surface (excluded from `readonly`). */
const MUTATING_TOOLS: readonly string[] = [
  "notify_telegram",
  "agent_review_workflow_execute",
  "bridge_submit_patch",
  "work_claim",
];

export const TOOL_PROFILES: Record<ToolProfile, readonly string[]> = {
  chatgpt: CHATGPT_CURATED_TOOLS,
  readonly: CHATGPT_CURATED_TOOLS.filter((name) => !MUTATING_TOOLS.includes(name)),
};

export function isValidToolProfile(value: unknown): value is ToolProfile {
  return value === "chatgpt" || value === "readonly";
}

/**
 * Provider → default profile for auto-registered guests (#1767/#2588).
 * ONLY chatgpt guests get a curated surface by default; every other client
 * keeps the full list (its call path stays RBAC-gated as before). Admins can
 * override per client via client.set_profile / PATCH /clients/:id.
 */
const PROVIDER_DEFAULT_PROFILES: Readonly<Record<string, ToolProfile>> = {
  chatgpt: "chatgpt",
};

export function profileForProvider(provider: string | undefined | null): ToolProfile | undefined {
  if (!provider) return undefined;
  return PROVIDER_DEFAULT_PROFILES[provider];
}

function profileForCurrentContext(): ToolProfile | undefined {
  return RequestContextStore.get()?.toolProfile;
}

/**
 * THE single discovery decision function — the composition of the call-path
 * RBAC gate and the client profile. Returns `null` when the CURRENT caller
 * (RequestContextStore) may both SEE and CALL the tool, or a denial reason.
 *
 * Used by attachDiscoveryFilter for tools/list; the call path keeps using
 * plain toolAccessError() (invariant 2: visibility curates, RBAC enforces).
 */
export function toolListAccessError(toolName: string): string | null {
  // Layer 1 — the SAME call-path RBAC gate (#695). If the caller could not
  // execute the tool, it must never appear in their list (list ⊆ call).
  const callDenial = toolAccessError(toolName);
  if (callDenial) return callDenial;
  // Layer 2 — the client's exposure profile (absent = full surface).
  const profile = profileForCurrentContext();
  if (!profile) return null;
  if (!TOOL_PROFILES[profile].includes(toolName)) {
    return `Hidden: tool '${toolName}' is not part of the '${profile}' tool surface for this client.`;
  }
  return null;
}

/** Rollback switch: MCP_DISCOVERY_FILTER=off restores the unfiltered SDK list. */
function discoveryFilterDisabled(): boolean {
  return (process.env.MCP_DISCOVERY_FILTER ?? "").trim().toLowerCase() === "off";
}

interface MinimalServer {
  server: {
    setRequestHandler(schema: typeof ListToolsRequestSchema, handler: (request: unknown, extra: unknown) => unknown): void;
    // SDK 1.30.0 internals (verified against the pinned source): the Protocol
    // base class stores handlers in a Map keyed by the request method literal
    // ("tools/list"); setRequestHandler REPLACES by key (last-set-wins).
    _requestHandlers?: Map<string, (request: unknown, extra: unknown) => unknown>;
  };
  // SDK 1.30.0 internals: plain record of pre-built tool entries, keyed by
  // the sanitized wire name; `enabled: false` entries are excluded by the
  // SDK's own list handler.
  _registeredTools?: Record<
    string,
    { description?: string; inputSchema?: unknown; enabled?: boolean } | undefined
  >;
}

type ToolDescriptor = { name: string; inputSchema: Record<string, unknown> };

/**
 * Install the discovery filter on a McpServer instance.
 *
 * Preferred path (zero-drift): CAPTURE the SDK's own tools/list handler and
 * wrap it — descriptor building (name/description/inputSchema/annotations/
 * outputSchema/_meta) stays 100% SDK-owned forever; we only filter the final
 * array by name via toolListAccessError(). Verified against the pinned SDK
 * 1.30.0 source: the handler lives at `_requestHandlers.get("tools/list")`
 * and `setRequestHandler` replaces by method literal.
 *
 * Degraded path A (SDK renamed the handler map): rebuild descriptors from
 * `_registeredTools` with zod-4 native `z.toJSONSchema(..., { io: "input" })`
 * — still filtered, still loud.
 *
 * Degraded path B (even _registeredTools is gone): fail-closed — advertise
 * ONLY the RBAC-passing subset of the public-safe tools, nothing else.
 *
 * In every path the filter reads the RequestContextStore PER REQUEST, so one
 * installation covers /sse, /messages, /mcp and /gemini alike (each pillar
 * runs its sessions inside a context carrying the caller's toolProfile).
 */
export function attachDiscoveryFilter(server: McpServer): void {
  if (discoveryFilterDisabled()) {
    console.error(
      "[tool-visibility] MCP_DISCOVERY_FILTER=off — discovery filter NOT installed; every client sees the full registry (rollback mode).",
    );
    return;
  }
  const minimal = server as unknown as MinimalServer;
  const inner = minimal.server;
  const original = inner._requestHandlers?.get("tools/list");

  if (typeof original === "function") {
    inner.setRequestHandler(ListToolsRequestSchema, async (request, extra) => {
      const result = (await original(request, extra)) as { tools?: Array<{ name: string }> } | undefined;
      if (result && Array.isArray(result.tools)) {
        result.tools = result.tools.filter((tool) => !toolListAccessError(tool.name));
      }
      return result;
    });
    return;
  }

  const registered = minimal._registeredTools;
  if (registered && typeof registered === "object") {
    console.error(
      "[tool-visibility] ⚠️ SDK internals drift: could not capture the built-in tools/list handler — using the _registeredTools mirror fallback (STILL FILTERED, but verify the pinned SDK version).",
    );
    inner.setRequestHandler(ListToolsRequestSchema, () => {
      const tools: ToolDescriptor[] = [];
      for (const [name, entry] of Object.entries(registered)) {
        if (entry?.enabled === false) continue;
        if (toolListAccessError(name)) continue;
        tools.push({ name, inputSchema: inputSchemaFor(entry?.inputSchema) });
      }
      return { tools };
    });
    return;
  }

  // Last resort: fail-closed. Advertise only the public-safe tools that the
  // current caller may call (for anonymous guests: the safe tools; for
  // others: whichever safe tools pass RBAC). NEVER the full registry.
  // bridge_guide is static (zero-network) so it stays listed even when the
  // SDK's internals drift — an external agent must always keep the contract.
  console.error(
    "[tool-visibility] ⚠️ SDK internals drift: no tools/list handler AND no _registeredTools — FAIL-CLOSED discovery (public-safe tools only). Update tool-visibility.ts for the new SDK.",
  );
  inner.setRequestHandler(ListToolsRequestSchema, () => {
    const failClosedSafe = ["system_summary", "system_health", "agent_status", "agent_heartbeat", "bridge_guide"];
    return { tools: failClosedSafe.filter((name) => !toolListAccessError(name)).map((name) => ({ name, inputSchema: { type: "object" } })) };
  });
}

/** zod-4 native schema mirroring for the degraded path (best-effort, per tool). */
function inputSchemaFor(schema: unknown): Record<string, unknown> {
  if (!schema) return { type: "object" };
  try {
    const mirrored = z.toJSONSchema(schema as z.ZodType, { io: "input", target: "draft-7" });
    return typeof mirrored === "object" && mirrored !== null ? (mirrored as Record<string, unknown>) : { type: "object" };
  } catch {
    return { type: "object" };
  }
}
