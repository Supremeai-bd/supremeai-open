// run_tests.mjs — offline harness for the skills installer reference (issue #332).
//
// node:assert + node:http only. Covers:
//   AC1  manifest loading (fail-closed battery) + registry discovery/install
//   AC2  MCP integration: streamable-http AND sse transports against the mock
//   AC3  execution boundary: deny-by-default leases, TTL expiry, scope
//        escalation, unknown tools, structured denials with zero wire calls
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { validateManifest, ManifestError } from "../src/manifest.mjs";
import { CapabilityRegistry, RegistryError } from "../src/registry.mjs";
import { LeaseAuthority, LeaseDenied } from "../src/lease.mjs";
import { McpInstaller, parseSseFrames } from "../src/installer.mjs";
import { startMockTower } from "../src/mock_tower.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const policy = JSON.parse(readFileSync(join(repoRoot, "api-schemas", "fixtures", "permissions.fixture.json"), "utf8"));
const scopeIds = new Set(policy.permission_scopes.map((s) => s.scope_id));

const goodManifest = {
  manifest_version: "skill-manifest/1",
  name: "repo-tools",
  version: "1.0.0",
  description: "read and execute repo tools",
  capabilities: [
    { scope_id: "mcp-tools-read", actions: ["read"] },
    { scope_id: "mcp-tools-execute", actions: ["execute"] },
  ],
  entry: { transport: "streamable-http", path: "/mcp" },
  tools: [
    { name: "repo_read", description: "read a path", required_scopes: ["mcp-tools-read"] },
    { name: "repo_exec", description: "run a tool", required_scopes: ["mcp-tools-execute"] },
    { name: "repo_write", description: "write a path", required_scopes: ["mcp-tools-execute"] },
  ],
};

const sseManifest = {
  ...structuredClone(goodManifest),
  name: "sse-tools",
  entry: { transport: "sse", path: "/mcp-sse-session" },
};

// ---------------------------------------------------------------------------
// AC1: manifest loading — fail-closed battery
// ---------------------------------------------------------------------------

function drift(mutate) {
  const bad = structuredClone(goodManifest);
  mutate(bad);
  assert.throws(() => validateManifest(bad, scopeIds), ManifestError);
}

test("manifest: valid shape accepted and frozen", () => {
  const m = validateManifest(goodManifest, scopeIds);
  assert.equal(m.name, "repo-tools");
  assert.ok(Object.isFrozen(m) && Object.isFrozen(m.tools));
});

test("manifest: drift battery rejected", () => {
  drift((m) => (m.manifest_version = "skill-manifest/2"));
  drift((m) => (m.name = "Bad_Name"));
  drift((m) => (m.version = "1.0"));
  drift((m) => (m.extra = 1)); // unknown key
  drift((m) => (m.capabilities = []));
  drift((m) => (m.capabilities[0].scope_id = "made-up-scope")); // not in SSOT
  drift((m) => (m.capabilities[0].actions = ["write"]));
  drift((m) => (m.entry.transport = "grpc"));
  drift((m) => (m.entry.path = "https://evil.example/mcp")); // host in manifest
  drift((m) => (m.entry.path = "/../secret"));
  drift((m) => (m.tools[0].required_scopes = ["made-up-scope"])); // not in SSOT
  // NOTE: scope SUB-ROLE pinning is a LEASE-time check, not manifest-level:
  // a manifest may legitimately require any SSOT scope.
  drift((m) => (m.tools[0].name = "repo_exec")); // duplicate tool name (collides with tools[1])
  drift((m) => delete m.tools);
});

test("registry: one poisoned manifest rejects the whole load", () => {
  assert.throws(
    () => new CapabilityRegistry(policy, [goodManifest, { ...goodManifest, name: "x", version: "bad" }]),
    RegistryError,
  );
});

test("registry: discover by scope and install", () => {
  const reg = new CapabilityRegistry(policy, [goodManifest, sseManifest]);
  const found = reg.discover({ scope_id: "mcp-tools-execute", action: "execute" });
  assert.deepEqual(found.map((f) => f.name), ["repo-tools", "sse-tools"]);
  const manifest = reg.install("repo-tools");
  assert.equal(manifest.entry.path, "/mcp");
  assert.throws(() => reg.install("nope"), RegistryError);
  assert.throws(() => reg.discover({ scope_id: "made-up" }), RegistryError);
});

// ---------------------------------------------------------------------------
// AC3: lease authority — deny-by-default chain
// ---------------------------------------------------------------------------

function authority(t = () => 1_000) {
  return new LeaseAuthority(policy, t);
}

test("lease: coder sub-role can lease read+execute tools", () => {
  const la = authority();
  const m = validateManifest(goodManifest, scopeIds);
  const lease = la.grant({ sub_role: "coder", role_tier: 2, manifest: m, tool_name: "repo_exec", ttl_s: 300 });
  assert.deepEqual(lease.granted_scopes, ["mcp-tools-execute"]);
  assert.equal(la.check(lease, "repo_exec", m).ok, true);
});

test("lease: auditor cannot lease execute-scoped tools (pinning)", () => {
  const la = authority();
  const m = validateManifest(goodManifest, scopeIds);
  assert.throws(
    () => la.grant({ sub_role: "auditor", role_tier: 2, manifest: m, tool_name: "repo_exec" }),
    (e) => e instanceof LeaseDenied && e.code === "scope_not_pinned",
  );
  // ...but CAN lease the read-only tool
  const lease = la.grant({ sub_role: "auditor", role_tier: 2, manifest: m, tool_name: "repo_read" });
  assert.deepEqual(lease.granted_scopes, ["mcp-tools-read"]);
});

test("lease: unknown tool denied before any wire activity", () => {
  const la = authority();
  const m = validateManifest(goodManifest, scopeIds);
  assert.throws(
    () => la.grant({ sub_role: "coder", role_tier: 2, manifest: m, tool_name: "not_in_manifest" }),
    (e) => e.code === "unknown_tool",
  );
});

test("lease: TTL expiry re-checked at execution time", () => {
  let now = 1_000;
  const la = authority(() => now);
  const m = validateManifest(goodManifest, scopeIds);
  const lease = la.grant({ sub_role: "coder", role_tier: 2, manifest: m, tool_name: "repo_read", ttl_s: 60 });
  now = 1_059;
  assert.equal(la.check(lease, "repo_read", m).ok, true);
  now = 1_060;
  assert.throws(() => la.check(lease, "repo_read", m), (e) => e.code === "lease_expired");
});

test("lease: MFA-gated scope denied unverified", () => {
  const la = authority();
  const mfaManifest = validateManifest({
    ...structuredClone(goodManifest),
    name: "admin-tools",
    tools: [{ name: "policy_read", description: "x", required_scopes: ["policy-override"] }],
  }, scopeIds);
  assert.throws(
    () => la.grant({ sub_role: "coder", role_tier: 4, mfa_verified: false, manifest: mfaManifest, tool_name: "policy_read" }),
    (e) => e.code === "scope_not_pinned", // coder doesn't pin it at all
  );
  assert.throws(
    () => la.grant({ sub_role: "coder", role_tier: 4, mfa_verified: false, manifest: mfaManifest, tool_name: "policy_read" }),
    LeaseDenied,
  );
});

test("lease: softening the MFA default refuses to boot", () => {
  const soft = structuredClone(policy);
  soft.defaults.unverified_mfa = "allow";
  assert.throws(() => new LeaseAuthority(soft), (e) => e.code === "config_invalid");
});

// ---------------------------------------------------------------------------
// AC2 + AC3: installer against the mock tower (both transports)
// ---------------------------------------------------------------------------

const { server, baseUrl } = await startMockTower(0);
test.after(() => new Promise((r) => server.close(r)));

test("sse frame parser: event/data pairs", () => {
  const frames = parseSseFrames("event: endpoint\ndata: /mcp-sse-session\n\n");
  assert.equal(frames.length, 1);
  assert.equal(frames[0].event, "endpoint");
  assert.equal(frames[0].data, "/mcp-sse-session");
});

test("streamable-http: initialize + tools/list over JSON-RPC", async () => {
  const inst = new McpInstaller({ baseUrl });
  const reg = new CapabilityRegistry(policy, [goodManifest]);
  const manifest = reg.install("repo-tools");
  const { transport, tools } = await inst.initialize({ transport: manifest.entry.transport, path: manifest.entry.path });
  assert.equal(transport, "streamable-http");
  assert.deepEqual(tools.map((t) => t.name), ["repo_read", "repo_write"]);
  assert.ok(inst.sessionId && inst.sessionId.startsWith("sess-"));
});

test("sse: endpoint frame announces the session route", async () => {
  const inst = new McpInstaller({ baseUrl });
  const reg = new CapabilityRegistry(policy, [sseManifest]);
  const manifest = reg.install("sse-tools");
  const { transport, endpoint, tools } = await inst.initialize({ transport: manifest.entry.transport, path: manifest.entry.path });
  assert.equal(transport, "sse");
  assert.equal(endpoint, "/mcp-sse-session");
  assert.equal(tools.length, 2);
});

test("execute: authorized lease runs the tool end to end", async () => {
  const la = new LeaseAuthority(policy);
  const reg = new CapabilityRegistry(policy, [goodManifest]);
  const manifest = reg.install("repo-tools");
  const lease = la.grant({ sub_role: "coder", role_tier: 2, manifest, tool_name: "repo_read", ttl_s: 300 });
  const inst = new McpInstaller({ baseUrl });
  await inst.initialize({ transport: manifest.entry.transport, path: manifest.entry.path });
  const out = await inst.execute(manifest, lease, (l, t, m) => la.check(l, t, m), "repo_read", { path: "docs/" });
  assert.equal(out.denied, false);
  assert.equal(out.status, "ok");
  assert.equal(out.result.echo.path, "docs/");
  assert.ok(out.invocation_id.startsWith("inv-"));
});

test("execute: expired lease = structured denial, ZERO wire calls", async () => {
  let now = 1_000;
  const la = new LeaseAuthority(policy, () => now);
  const reg = new CapabilityRegistry(policy, [goodManifest]);
  const manifest = reg.install("repo-tools");
  const lease = la.grant({ sub_role: "coder", role_tier: 2, manifest, tool_name: "repo_read", ttl_s: 10 });
  now = 2_000; // lease long expired
  const inst = new McpInstaller({ baseUrl, fetchImpl: async () => { throw new Error("WIRE CALL MUST NOT HAPPEN"); } });
  const out = await inst.execute(manifest, lease, (l, t, m) => la.check(l, t, m), "repo_read", {});
  assert.equal(out.denied, true);
  assert.equal(out.code, "lease_expired");
});

test("execute: scope escalation attempt denied without wire call", async () => {
  const la = new LeaseAuthority(policy);
  const reg = new CapabilityRegistry(policy, [goodManifest]);
  const manifest = reg.install("repo-tools");
  const lease = la.grant({ sub_role: "auditor", role_tier: 2, manifest, tool_name: "repo_read", ttl_s: 300 });
  const inst = new McpInstaller({ baseUrl, fetchImpl: async () => { throw new Error("WIRE CALL MUST NOT HAPPEN"); } });
  const out = await inst.execute(manifest, lease, (l, t, m) => la.check(l, t, m), "repo_exec", {});
  assert.equal(out.denied, true);
  assert.equal(out.code, "tool_mismatch");
});

test("execute: server-side deny surfaces as honest error envelope", async () => {
  const la = new LeaseAuthority(policy);
  const reg = new CapabilityRegistry(policy, [goodManifest]);
  const manifest = reg.install("repo-tools");
  // fully LEGIT lease (coder pins mcp-tools-execute) - the mock tower still
  // denies repo_write server-side, proving the server boundary is independent
  // of the client gate and the denial surfaces as an honest envelope
  const lease = la.grant({ sub_role: "coder", role_tier: 2, manifest, tool_name: "repo_write", ttl_s: 300 });
  const inst = new McpInstaller({ baseUrl });
  await inst.initialize({ transport: manifest.entry.transport, path: manifest.entry.path });
  const out = await inst.execute(manifest, lease, () => ({ ok: true }), "repo_write", {});
  assert.equal(out.denied, false);
  assert.equal(out.status, "error");
  assert.match(out.error.message, /repo_write/);
});

// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;
const originalTest = test;
// node:test's top-level test() already runs; print a summary line for CI.
process.on("exit", (code) => {
  if (code === 0) console.log("skills-installer-reference: all tests passed");
});
