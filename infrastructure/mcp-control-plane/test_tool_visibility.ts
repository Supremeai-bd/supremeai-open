import assert from "node:assert/strict";
import type { IncomingMessage } from "node:http";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { RequestContextStore } from "./src/policy/auth.context.js";
import { defaultClientScopes, changeClientProfile, registerClient } from "./src/policy/client-registry.js";
import { autoRegisterGuestClient } from "./src/policy/auto-register.js";
import { toolAccessError } from "./src/policy/mcp-access.js";
import {
  TOOL_PROFILES,
  attachDiscoveryFilter,
  isValidToolProfile,
  profileForProvider,
  toolListAccessError,
} from "./src/policy/tool-visibility.js";

/**
 * Tool Exposure Policy contract tests.
 *
 * বাংলা মন্তব্য: যাচাই হয় —
 *   ১. profile helpers (validation, provider-derivation, profile invariants)
 *   ২. toolListAccessError = toolAccessError ∩ profile (list ⊆ call invariant)
 *   ৩. fail-closed: context ছাড়া list কখনোই tool দেখায় না
 *   ৪. attachDiscoveryFilter e2e (real InMemoryTransport): RBAC × profile
 *      matrix, wrap পথে descriptor fidelity, kill-switch no-op
 *   ৫. visibility ≠ authorization: hidden tool সরাসরি call করলে RBAC-ই ভোট দেয়
 *   ৬. client-registry integration (register/set/clear/derive-once guests)
 */

// ─── ১. Profile helpers ────────────────────────────────────────────────────
assert.equal(isValidToolProfile("chatgpt"), true);
assert.equal(isValidToolProfile("readonly"), true);
assert.equal(isValidToolProfile("full"), false);
assert.equal(isValidToolProfile(undefined), false);
assert.equal(isValidToolProfile("GODMODE"), false);

assert.equal(profileForProvider("chatgpt"), "chatgpt");
assert.equal(profileForProvider("ChatGPT"), undefined, "provider labels are lowercase — no accidental match");
assert.equal(profileForProvider("claude"), undefined, "only chatgpt gets a default profile");
assert.equal(profileForProvider(undefined), undefined);

// Profile invariants: sanitized wire names, no dupes, readonly ⊆ chatgpt,
// and NEVER a secret-class tool in any profile (invariant 1 + #695 SSoT).
const SECRET_CLASS = ["infisical_list", "infisical_get", "infisical_set", "github_list_secrets", "render_get_env_vars"];
for (const [profile, tools] of Object.entries(TOOL_PROFILES)) {
  assert.equal(new Set(tools).size, tools.length, `${profile} profile must not contain duplicates`);
  for (const name of tools) {
    assert.match(name, /^[a-z_][a-z_0-9]*$/, `${profile}/${name} must be a sanitized wire name`);
    assert.ok(!name.includes("."), `${profile}/${name} must be sanitized (dots→underscores)`);
    assert.ok(!SECRET_CLASS.includes(name), `${profile} must never expose secret-class tools (${name})`);
  }
  assert.ok(tools.length > 10, `${profile} profile must stay useful (${tools.length} tools)`);
}
for (const name of TOOL_PROFILES.readonly) {
  assert.ok(TOOL_PROFILES.chatgpt.includes(name), "readonly ⊆ chatgpt");
}
assert.ok(!TOOL_PROFILES.readonly.includes("notify_telegram"), "readonly excludes the notify write channel");
assert.ok(!TOOL_PROFILES.readonly.includes("agent_review_workflow_execute"), "readonly excludes workflow execution");

// ─── ২+৩. toolListAccessError matrix (RBAC ∩ profile, fail-closed) ─────────// No context at all → fail-closed: nothing is listable.
assert.ok(toolListAccessError("system_summary"), "no context must deny listing (fail-closed)");
assert.ok(toolListAccessError("github_read_file"), "no context must deny listing (fail-closed)");

// Anonymous ChatGPT guest (public_viewer): sees ONLY the curated tools that
// also pass RBAC — before the fix this caller saw the FULL ~90-tool registry.
await RequestContextStore.run({ role: "viewer", accessMode: "public_viewer", authenticated: false, scopes: [] }, async () => {
  assert.ok(toolListAccessError("github_read_file")?.includes("agent"), "public_viewer must not see restricted tools");
  assert.ok(toolListAccessError("autonomy_kill_switch"), "public_viewer must never see destructive tools");
});

// Agent WITHOUT a profile → full RBAC surface (unchanged behavior).
await RequestContextStore.run({ role: "agent", authenticated: true, scopes: defaultClientScopes("agent") }, async () => {
  assert.equal(toolListAccessError("github_read_file"), null);
  assert.equal(toolListAccessError("autonomy_kill_switch"), null, "no profile → no profile filtering");
  assert.equal(toolListAccessError("echo_with_schema"), null);
});

// Agent WITH the chatgpt profile → curated subset only.
await RequestContextStore.run({ role: "agent", authenticated: true, scopes: defaultClientScopes("agent"), toolProfile: "chatgpt" }, async () => {
  assert.equal(toolListAccessError("github_read_file"), null);
  assert.equal(toolListAccessError("notify_telegram"), null);
  assert.ok(toolListAccessError("autonomy_kill_switch")?.includes("'chatgpt'"), "profile hides non-curated tools");
  assert.ok(toolListAccessError("echo_with_schema")?.includes("'chatgpt'"), "profile hides unknown tools");
  assert.ok(toolListAccessError("github_list_secrets")?.includes("admin"), "RBAC denial wins over profile (secret-class)");
});

// Agent WITH the readonly profile → notify write channel hidden too.
await RequestContextStore.run({ role: "agent", authenticated: true, scopes: defaultClientScopes("agent"), toolProfile: "readonly" }, async () => {
  assert.ok(toolListAccessError("notify_telegram")?.includes("'readonly'"), "readonly profile hides mutating tools");
  assert.equal(toolListAccessError("github_read_file"), null);
});

// Admin + profile → still curated (profile applies to every role).
await RequestContextStore.run({ role: "admin", accessMode: "admin", authenticated: true, scopes: ["*"] }, async () => {
  assert.equal(toolListAccessError("autonomy_kill_switch"), null);
});

// ─── ৪. attachDiscoveryFilter — real InMemoryTransport e2e ────────────────
async function makeFilteredServer(): Promise<McpServer> {
  const server = new McpServer({ name: "tower-visibility-test", version: "1.0.0" });
  // Mirror index.ts: sanitize names + wrap EVERY handler in the RBAC gate.
  const originalTool = server.tool.bind(server);
  (server as unknown as { tool: unknown }).tool = (name: string, ...args: unknown[]) => {
    const sanitizedName = name.replace(/\./g, "_");
    let handlerIndex = -1;
    for (let i = args.length - 1; i >= 0; i--) {
      if (typeof args[i] === "function") { handlerIndex = i; break; }
    }
    if (handlerIndex >= 0) {
      const originalHandler = args[handlerIndex] as (toolArgs: unknown, extra: unknown) => unknown;
      args[handlerIndex] = async (toolArgs: unknown) => {
        const denial = toolAccessError(sanitizedName);
        if (denial) return { isError: true, content: [{ type: "text", text: denial }] };
        return originalHandler(toolArgs, {});
      };
    }
    return (originalTool as unknown as (n: string, ...a: unknown[]) => unknown)(sanitizedName, ...args);
  };

  server.tool("system.summary", "System summary", {}, async () => ({ content: [{ type: "text", text: "summary" }] }));
  server.tool("system.health", "Tower health", {}, async () => ({ content: [{ type: "text", text: "healthy" }] }));
  server.tool("github.read_file", "Read a repo file", { path: z.string() }, async () => ({ content: [{ type: "text", text: "file" }] }));
  server.tool("notify.telegram", "Send a telegram note", { text: z.string() }, async () => ({ content: [{ type: "text", text: "sent" }] }));
  server.tool("autonomy.kill_switch", "Destructive admin action", {}, async () => ({ content: [{ type: "text", text: "killed" }] }));
  server.tool("echo.with_schema", "Nested schema echo", { payload: z.object({ value: z.string() }) }, async (toolArgs: unknown) => ({ content: [{ type: "text", text: JSON.stringify(toolArgs) }] }));

  attachDiscoveryFilter(server);
  return server;
}

async function listToolsUnder(context: Parameters<typeof RequestContextStore.run>[0]): Promise<string[]> {
  const server = await makeFilteredServer();
  const client = new Client({ name: "visibility-test-client", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    return await RequestContextStore.run(context, async () => {
      const result = await client.listTools();
      return (result.tools ?? []).map((tool) => tool.name);
    });
  } finally {
    try { await client.close(); } catch { /* already closed */ }
    try { await server.close(); } catch { /* already closed */ }
  }
}

const adminCtx = { role: "admin" as const, accessMode: "admin" as const, authenticated: true, scopes: ["*"] };
const agentCtx = { role: "agent" as const, authenticated: true, scopes: defaultClientScopes("agent") };
const agentChatgptCtx = { ...agentCtx, toolProfile: "chatgpt" as const };
const viewerCtx = { role: "viewer" as const, authenticated: true, scopes: defaultClientScopes("viewer") };

// Admin, no profile → everything (registration order preserved by the wrap).
const adminList = await listToolsUnder(adminCtx);
assert.deepEqual(adminList, ["system_summary", "system_health", "github_read_file", "notify_telegram", "autonomy_kill_switch", "echo_with_schema"]);

// Agent, no profile → full RBAC surface (same 6).
const agentList = await listToolsUnder(agentCtx);
assert.deepEqual(agentList, adminList);

// Agent + chatgpt profile → exactly the curated members of this fixture.
const agentChatgptList = await listToolsUnder(agentChatgptCtx);
assert.deepEqual(agentChatgptList, ["system_summary", "system_health", "github_read_file", "notify_telegram"]);

// Authenticated viewer, no profile → only the RBAC-visible safe tools.
const viewerList = await listToolsUnder(viewerCtx);
assert.deepEqual(viewerList, ["system_summary", "system_health"]);

// No context → empty list (fail-closed).
{
  const server = await makeFilteredServer();
  const client = new Client({ name: "visibility-test-client", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    // NOTE: deliberately NO RequestContextStore.run — discovery must fail closed.
    const result = await client.listTools();
    assert.deepEqual(result.tools ?? [], [], "no request context ⇒ EMPTY discovery (fail-closed)");
  } finally {
    try { await client.close(); } catch { /* already closed */ }
    try { await server.close(); } catch { /* already closed */ }
  }
}

// list ⊆ call invariant, checked per context over the REAL decision fns.
for (const [label, context, list] of [
  ["admin", adminCtx, adminList],
  ["agent", agentCtx, agentList],
  ["agent+chatgpt", agentChatgptCtx, agentChatgptList],
  ["viewer", viewerCtx, viewerList],
] as const) {
  await RequestContextStore.run(context, async () => {
    for (const name of list) {
      assert.equal(toolAccessError(name), null, `${label}: listed tool '${name}' must be callable`);
      assert.equal(toolListAccessError(name), null, `${label}: listed tool '${name}' must pass the full discovery gate`);
    }
  });
}

// ─── ৫. Visibility ≠ authorization: hidden-but-callable stays RBAC-gated ──
{
  const server = await makeFilteredServer();
  const client = new Client({ name: "visibility-test-client", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    await RequestContextStore.run(agentChatgptCtx, async () => {
      // autonomy_kill_switch is HIDDEN from this caller's list…
      const list = await client.listTools();
      assert.ok(!(list.tools ?? []).some((tool) => tool.name === "autonomy_kill_switch"));
      // …but the CALL path still goes through RBAC alone (agent may call it).
      const call = await client.callTool({ name: "autonomy_kill_switch", arguments: {} });
      assert.notEqual((call as { isError?: boolean }).isError, true, "profile hides; RBAC decides calls");
      // And the RBAC gate still denies roles that lack permission.
      const viewerResult = await RequestContextStore.run(viewerCtx, async () =>
        client.callTool({ name: "github_read_file", arguments: { path: "x" } }),
      );
      assert.equal((viewerResult as { isError?: boolean }).isError, true, "viewer still denied by the call-path RBAC gate");
    });
  } finally {
    try { await client.close(); } catch { /* already closed */ }
    try { await server.close(); } catch { /* already closed */ }
  }
}

// Wrap path preserves SDK descriptor fidelity (schemas survive).
{
  const server = await makeFilteredServer();
  const client = new Client({ name: "visibility-test-client", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    await RequestContextStore.run(adminCtx, async () => {
      const result = await client.listTools();
      const echo = (result.tools ?? []).find((tool) => tool.name === "echo_with_schema");
      assert.ok(echo, "admin must see echo_with_schema");
      const props = (echo!.inputSchema as { properties?: Record<string, unknown> }).properties ?? {};
      assert.ok(props["payload"], "wrapped handler must keep the SDK-built input schema");
    });
  } finally {
    try { await client.close(); } catch { /* already closed */ }
    try { await server.close(); } catch { /* already closed */ }
  }
}

// ─── Kill-switch: MCP_DISCOVERY_FILTER=off installs NOTHING ───────────────
{
  process.env.MCP_DISCOVERY_FILTER = "off";
  try {
    const server = await makeFilteredServer();
    // makeFilteredServer already ran attachDiscoveryFilter with the kill-switch
    // ON — it must have been a NO-OP: the profile below would otherwise filter
    // the list down, but the SDK's unfiltered handler still returns all 6.
    const client = new Client({ name: "visibility-test-client", version: "1.0.0" });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    try {
      await server.connect(serverTransport);
      await client.connect(clientTransport);
      await RequestContextStore.run({ role: "agent", authenticated: true, scopes: [], toolProfile: "chatgpt" }, async () => {
        const result = await client.listTools();
        assert.equal((result.tools ?? []).length, 6, "kill-switch → unfiltered SDK behavior");
      });
    } finally {
      try { await client.close(); } catch { /* already closed */ }
      try { await server.close(); } catch { /* already closed */ }
    }
  } finally {
    delete process.env.MCP_DISCOVERY_FILTER;
  }
}

// ─── ৬. Client-registry integration ──────────────────────────────────────
function fakeReq(userAgent: string, ip = "203.0.113.99"): IncomingMessage {
  return {
    headers: { "user-agent": userAgent, "x-forwarded-for": ip },
    socket: { remoteAddress: ip },
  } as unknown as IncomingMessage;
}

const profiled = registerClient("Profiled AI", "agent", defaultClientScopes("agent"), undefined, "generic", "streamable-http", "tenant_default", undefined, "chatgpt");
assert.equal(profiled.client.toolProfile, "chatgpt");

const updated = changeClientProfile(profiled.client.id, "readonly");
assert.equal(updated?.toolProfile, "readonly");
const cleared = changeClientProfile(profiled.client.id, null);
assert.equal(cleared?.toolProfile, undefined);
assert.throws(() => changeClientProfile(profiled.client.id, "godmode" as never), /toolProfile must be/);

// Guest derivation: chatgpt guests get the curated profile via the REAL
// auto-register hook; reconnects must never CLEAR an existing profile
// (derive-once rule), and non-chatgpt providers keep the full surface.
const guest = autoRegisterGuestClient(fakeReq("ChatGPT-User/1.0", "198.51.100.77"), "sse");
assert.ok(guest.id.startsWith("guest_chatgpt_"), `unexpected guest id: ${guest.id}`);
assert.equal(guest.toolProfile, "chatgpt", "chatgpt guests auto-carry the curated profile");
const guestReconnect = autoRegisterGuestClient(fakeReq("ChatGPT-User/1.0", "198.51.100.77"), "streamable-http");
assert.equal(guestReconnect.id, guest.id);
assert.equal(guestReconnect.toolProfile, "chatgpt", "reconnect keeps the profile");

const otherGuest = autoRegisterGuestClient(fakeReq("claude-web/2.1", "198.51.100.78"), "sse");
assert.equal(otherGuest.toolProfile, undefined, "non-chatgpt guests keep the full surface");

console.log("Tool visibility (Tool Exposure Policy) tests passed");
