import assert from "node:assert/strict";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { RequestContextStore } from "./src/policy/auth.context.js";
import { defaultClientScopes } from "./src/policy/client-registry.js";
import { toolAccessError, classifyToolCapability, publicSafeCapabilities } from "./src/policy/mcp-access.js";
import { TOOL_PROFILES, attachDiscoveryFilter } from "./src/policy/tool-visibility.js";
import {
  BRIDGE_QUEUE_LABEL,
  bridgeGuide,
  bridgeOpenRepo,
  isIssueNotPullRequest,
  normalizeQueueItem,
  queueFromIssues,
  registerBridgeTools,
  scanFileForSecrets,
} from "./src/tools/bridge.tools.js";

/**
 * Bridge onboarding contract tests (#123).
 *
 * বাংলা মন্তব্য: যাচাই হয় —
 *   ১. তিনটি bridge tool public_viewer-এর কাছে callable + listable (list ⊆ call)
 *   ২. anonymous surface-এ কোনো write/destructive/secret tool ফাঁসি হয় না
 *   ৩. чистая queue normalization (PR বাদ, sanitize, cap, sort)
 *   ৪. guide payload-এর বাধ্যতামূলক contract keys
 *   ৫. e2e: anonymous client — bridge.guide সত্যিই ডাকা যায় (zero network)
 */

// ─── ১. RBAC: public_viewer may call the bridge tools ────────────────────────
const anonCtx = {
  role: "viewer" as const,
  accessMode: "public_viewer" as const,
  authenticated: false,
  tenantBound: false,
  scopes: [],
};
const agentCtx = { role: "agent" as const, authenticated: true, scopes: defaultClientScopes("agent") };

for (const name of ["bridge_guide", "bridge_work_queue", "bridge_work_order"]) {
  // The call-path gate (the same one index.ts wraps every handler with).
  await RequestContextStore.run(anonCtx, async () => {
    assert.equal(toolAccessError(name), null, `anonymous call must be allowed for ${name}`);
  });
  // Classification: safe + public + R0, no scope required.
  const capability = classifyToolCapability(name);
  assert.equal(capability.access, "safe", `${name} must be classified safe`);
  assert.equal(capability.dataClassification, "public", `${name} must be public`);
  assert.equal(capability.requiredScope, undefined, `${name} must not require a scope`);
  // Registered in the public manifest (what publicAccessManifest() advertises).
  assert.ok(
    publicSafeCapabilities.some((entry) => entry.kind === "tool" && entry.name === name),
    `${name} must be advertised in publicSafeCapabilities`,
  );
  // Agent role keeps access (no regression for elevated callers).
  await RequestContextStore.run(agentCtx, async () => {
    assert.equal(toolAccessError(name), null, `agent call must be allowed for ${name}`);
  });
}

// ─── ২. Fail-closed unchanged: the rest of the registry stays denied ─────────
await RequestContextStore.run(anonCtx, async () => {
  for (const name of [
    "github_read_file",
    "render_list_services",
    "notify_telegram",
    "autonomy_kill_switch",
    "infisical_list",
    "github_list_secrets",
    "action_render_deploy",
    "client_register",
  ]) {
    assert.ok(toolAccessError(name), `anonymous call must stay denied for ${name}`);
  }
});

// ─── ৩. Queue normalization (pure) ───────────────────────────────────────────
const rawIssues = [
  { number: 41, title: "docs: update client example", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/41", created_at: "2026-10-12T10:00:00Z", labels: [{ name: "bridge:queued" }, "good first issue"], comments: 2 },
  { number: 42, title: "test: client harness", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/42", created_at: "2026-10-12T11:00:00Z", labels: [{ name: "bridge:queued" }], comments: 0 },
  { number: 43, title: "PR thread, not a work order", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/pull/43", created_at: "2026-10-12T12:00:00Z", labels: [], pull_request: { url: "x" } },
  { number: 44, title: "closed again", state: "closed", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/44", labels: [] },
  { number: 45, title: "[Anchor Hub] Supremeai-bd/supremeai-studio", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/45", labels: ["P1-high", "area:governance"] },
  { number: 46, title: "[Federation Hub] CI Failures Desk", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/46", labels: ["P1-high"] },
  { number: 47, title: "failed work order", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/47", labels: ["bridge:rejected"] },
  { number: 48, title: "landed work order", state: "open", html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/48", labels: ["bridge:landed"] },
  null,
];

const queue = queueFromIssues(rawIssues);
assert.deepEqual(queue.map((item) => item.number), [42, 41], "PRs/nulls filtered, newest first, no cap hit");
assert.deepEqual(queue[1]!.labels, ["bridge:queued", "good first issue"], "labels flattened to names");
assert.equal(queue[1]!.comments, 2, "comment count preserved");

const capped = queueFromIssues(rawIssues, 1);
assert.deepEqual(capped.map((item) => item.number), [42], "limit caps the queue");
assert.deepEqual(queueFromIssues("not-an-array"), [], "non-array payload → empty queue (fail-safe)");

// Strings and objects are neither treated as issues.
assert.equal(isIssueNotPullRequest({ pull_request: {} }), false);
assert.equal(isIssueNotPullRequest({}), true);
assert.equal(normalizeQueueItem({ number: "x", title: 7, body: "leak me" }).title, "", "non-string fields sanitized");

// ─── ৪. Guide payload contract ───────────────────────────────────────────────
const guide = bridgeGuide();
assert.ok(guide.mission.length > 50, "guide explains the mission");
assert.equal(guide.entrypoints.openRepo, bridgeOpenRepo(), "guide points at the open repo");
assert.ok(guide.lifecycle.length >= 5, "guide has a full lifecycle");
assert.equal(guide.contract.diffCaps.maxBytes, 200 * 1024, "diff cap matches operator contract (200 KB)");
assert.equal(guide.contract.diffCaps.maxFiles, 30, "file cap matches operator contract (30 files)");
assert.ok(guide.contract.protectedPathsToAdminReview.includes(".github/"), "protected paths documented");
assert.ok(guide.contract.secretScanFamilies.includes("ghp_"), "secret-scan families documented");
assert.equal(guide.contract.landingAuthority.includes("constitutional gates"), true, "landing authority documented");
assert.equal(BRIDGE_QUEUE_LABEL, "bridge:queued", "queue label matches the bridge pipeline");
assert.equal(bridgeOpenRepo(), "Supremeai-bd/supremeai-open", "default open repo is the public front door");

// ─── ৫. Profiles: read-only bridge tools ride the curated surfaces ───────────
for (const name of ["bridge_guide", "bridge_work_queue", "bridge_work_order"]) {
  assert.ok(TOOL_PROFILES.chatgpt.includes(name), `${name} must be in the chatgpt curated surface`);
  assert.ok(TOOL_PROFILES.readonly.includes(name), `${name} must be in the readonly surface (read-only)`);
  assert.match(name, /^[a-z_][a-z_0-9]*$/, `${name} must be a sanitized wire name`);
}

// ─── ৬. e2e: anonymous client lists AND calls the public bridge surface ──────
async function makeBridgeServer(): Promise<McpServer> {
  const server = new McpServer({ name: "bridge-onboarding-test", version: "0.0.1" });
  // Mirror index.ts: sanitize names + wrap EVERY handler in the RBAC gate.
  const originalTool = server.tool.bind(server);
  (server as unknown as { tool: unknown }).tool = (name: string, ...args: unknown[]) => {
    const sanitizedName = name.replace(/\./g, "_");
    let handlerIndex = -1;
    for (let i = args.length - 1; i >= 0; i--) { if (typeof args[i] === "function") { handlerIndex = i; break; } }
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
  // #2423 option A: mirror the production registerTool shim (index.fixed.ts) —
  // bridge.work_queue/work_order now register through the SDK-blessed
  // registerTool surface (outputSchema carriers), so the harness must apply
  // the SAME name sanitization + toolAccessError gate on that surface too.
  const originalRegisterTool = (server as unknown as { registerTool: (n: string, c: unknown, cb: unknown) => unknown }).registerTool.bind(server);
  (server as unknown as { registerTool: unknown }).registerTool = (name: string, config: unknown, cb: unknown) => {
    const sanitizedName = name.replace(/\./g, "_");
    const governed = typeof cb === "function"
      ? async (toolArgs: unknown) => {
          const denial = toolAccessError(sanitizedName);
          if (denial) return { isError: true, content: [{ type: "text", text: denial }] };
          return (cb as (a: unknown, e: unknown) => unknown)(toolArgs, {});
        }
      : cb;
    return originalRegisterTool(sanitizedName, config, governed);
  };
  await registerBridgeTools(server);
  attachDiscoveryFilter(server);
  return server;
}

{
  const server = await makeBridgeServer();
  const client = new Client({ name: "bridge-onboarding-client", version: "0.0.1" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  try {
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    await RequestContextStore.run(anonCtx, async () => {
      // Discovery: the anonymous caller sees the bridge tools (and the safe system tools).
      const list = await client.listTools();
      const names = (list.tools ?? []).map((tool) => tool.name);
      for (const name of ["bridge_guide", "bridge_work_queue", "bridge_work_order"]) {
        assert.ok(names.includes(name), `anonymous discovery must list ${name}`);
      }
      // No write/destructive/secret tool leaks into the anonymous list.
      for (const name of names) {
        assert.equal(toolAccessError(name), null, "listed tool must be callable (list ⊆ call)");
      }
      assert.ok(!names.includes("notify_telegram"), "no mutating tool in the anonymous surface");
      assert.ok(!names.includes("autonomy_kill_switch"), "no destructive tool in the anonymous surface");
      // Execution: bridge.guide is static — an anonymous caller gets the contract with zero network.
      const call = await client.callTool({ name: "bridge_guide", arguments: {} });
      assert.notEqual((call as { isError?: boolean }).isError, true, "bridge.guide must execute for anonymous callers");
      const payload = JSON.parse((call as { content: Array<{ text: string }> }).content[0]!.text) as ReturnType<typeof bridgeGuide>;
      assert.equal(payload.entrypoints.openRepo, "Supremeai-bd/supremeai-open");
      assert.ok(payload.contract.diffCaps.maxBytes > 0, "guide carries the operator contract");
    });
  } finally {
    try { await client.close(); } catch { /* already closed */ }
    try { await server.close(); } catch { /* already closed */ }
  }
}

// ─── ৭. No-context fail-closed stays intact for the new tools ────────────────
assert.ok(toolAccessError("bridge_guide"), "no request context ⇒ bridge tools stay denied (fail-closed)");

// ─── ৮. Secret scan: false-positive prevention + real-key detection ───────────
console.log("\n=== 8. Secret scan (structure-aware: reject benign 'sk-' substrings, catch real keys) ===");

const benignSamples = [
  `ENVELOPE_VERSION = 1 # task-envelope-v1`,
  `task_id=f"task-abc-123"`,
  `parser.add_argument("--task-envelope", ...)`,
  `// task_registry handles task-queue lease management`,
  `function task_envelope() { return sk_identity() }`,
  `const mask_key = ref("task-key")`,
  `disk-key rotation policy`,
  `slack-key integration`,
  `The desk-key is stored in redis-v2 config.`,
];
for (const s of benignSamples) {
  assert.equal(scanFileForSecrets(s), null, `benign sample must NOT trigger: ${s}`);
}
console.log("  ✓ all benign 'sk-' substrings pass without false positive");

const realSecrets: Array<[string, string]> = [
  [`sk_key = "sk-proj-abc123def456ghi789jkl012mno345pqr678ste"`, "sk-"], // gitleaks:allow
  [`token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD"`, "ghp_"], // gitleaks:allow
  [`app_token = "ghs_rstuvwxyzabcdefghijklmnopqrstuvwxyz0123456789AB"`, "ghs_"], // gitleaks:allow
  [`pat = "github_pat_1234567890abcdefghijklmnopqrstuvwxyzA"`, "github_pat_"], // gitleaks:allow
  [`aws_key = "AKIAIOSFODNN7EXAMPLE1234"`, "AKIA"], // gitleaks:allow
  [`slack = "xoxb-12345678901-abcdef1234567"`, "xox"], // gitleaks:allow
  [`api_key = "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8"`, "AIza"], // gitleaks:allow
  [`// PEM\n-----BEGIN PRIVATE KEY-----\nMIIEvA==`, "PEM"], // gitleaks:allow
  [`var x = "literal-secret-value-12345"`, "literal-secret"], // gitleaks:allow
  [`config = { "redis-url": "redis://user:pass@host:6379" }`, "redis-url"], // gitleaks:allow
];
for (const [content, family] of realSecrets) {
  const hit = scanFileForSecrets(content);
  assert.equal(hit, family, `real ${family} secret must be detected in: ${content.slice(0, 40)}`);
}
console.log("  ✓ all real secret shapes detected");

assert.equal(guide.contract.secretScanFamilies.includes("sk-"), true, "sk- family still documented in contract");
assert.equal(guide.contract.secretScanFamilies.includes("ghp_"), true, "ghp_ family still documented in contract");

console.log("Bridge onboarding contract tests passed (#123)");
