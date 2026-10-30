import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage } from "node:http";

/**
 * Verified Slot Architecture — security verification suite (issue #48).
 *
 * Covers the 6 mandatory invariants + guardrails:
 *   1. Slot identity (pre-provisioned, no auto-elevation)
 *   2. Authentication (slot-bound credential; URL alone is NOT auth)
 *   3. Authorization (live registry check on every privileged call)
 *   4. Revocation (immediate-next-check termination, no reconnect)
 *   5. Database failure (fail-CLOSED denial)
 *   6. Audit trail (immutable slot/credential/role/tool/time rows)
 * plus: IP rotation immunity, cross-tenant isolation, credential rotation.
 *
 * Deterministic + zero-cost: file-backed registry, no network except the
 * deliberately unreachable endpoint in the DB-outage case.
 */

// The registry module reads MCP_CLIENT_REGISTRY_FILE at import time — set it
// BEFORE the dynamic imports below.
const workDir = mkdtempSync(join(tmpdir(), "slot-verify-"));
process.env.MCP_CLIENT_REGISTRY_FILE = join(workDir, "registry.json");

const {
  provisionSlot,
  approveSlot,
  suspendSlot,
  reinstateSlot,
  rotateSlotCredential,
  resolveSlotSession,
  assertSlotAuthorization,
  slotNameFromRequest,
} = await import("./src/policy/slot-verification.js");
const { toolAccessErrorAsync, classifyToolCapability } = await import("./src/policy/mcp-access.js");
const { RequestContextStore } = await import("./src/policy/auth.context.js");
type UserRole = import("./src/policy/auth.context.js").UserRole;
const { readSlotAudit, __clearSlotAuditForTests } = await import("./src/policy/slot-audit.js");
const {
  approveClient,
  changeClientRole,
  clientCredentialId,
  __setRegistryStoreForTests,
  registerClient,
  resolveClient,
} = await import("./src/policy/client-registry.js");
const { JsonFileClientRegistryStore, UpstashClientRegistryStore } = await import("./src/policy/client-registry.store.js");

function fakeReq(
  url: string,
  opts: { ip?: string; slotToken?: string; bearer?: string; userAgent?: string } = {},
): IncomingMessage {
  return {
    url,
    headers: {
      ...(opts.slotToken ? { "x-mcp-slot-token": opts.slotToken } : {}),
      ...(opts.bearer ? { authorization: `Bearer ${opts.bearer}` } : {}),
      "user-agent": opts.userAgent ?? "TestClient/1.0",
      "x-forwarded-for": opts.ip ?? "203.0.113.10",
    },
    socket: { remoteAddress: opts.ip ?? "203.0.113.10" },
  } as unknown as IncomingMessage;
}

/** Runs `fn` inside a request context carrying the given slot binding. */
async function withSlotContext(
  ctx: { slotId: string; credentialId?: string; role: UserRole; scopes?: string[] },
  fn: () => Promise<void>,
): Promise<void> {
  await RequestContextStore.run(
    {
      role: ctx.role,
      accessMode: ctx.role,
      authenticated: true,
      tenantBound: true,
      clientId: ctx.slotId,
      scopes: ctx.scopes ?? [],
      slotId: ctx.slotId,
      slotVerified: true,
      credentialId: ctx.credentialId,
    },
    fn,
  );
}

let passed = 0;
async function check(name: string, fn: () => Promise<void> | void): Promise<void> {
  try {
    await fn();
    passed += 1;
    console.log(`  ok - ${name}`);
  } catch (err) {
    console.error(`  NOT OK - ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

// ── 1. Slot identity: pre-provisioned, pending, no auto-elevation ───────────
await check("provision creates a PENDING slot (no auto-elevation)", () => {
  const { slot, credential } = provisionSlot({ name: "agent-7", role: "agent" });
  assert.equal(slot.id, "slot_agent-7");
  assert.equal(slot.status, "pending");
  assert.ok(credential.startsWith("slot_"), "slot credentials carry the slot_ prefix");
  assert.match(clientCredentialId(slot.id)!, /^[0-9a-f]{12}$/, "audit fingerprint is 12-hex");
});

await check("duplicate provision + invalid names are rejected", () => {
  assert.throws(() => provisionSlot({ name: "agent-7", role: "agent" }), /already registered/);
  assert.throws(() => provisionSlot({ name: "../evil", role: "agent" }), /slot name must match/);
  assert.throws(() => provisionSlot({ name: "", role: "agent" }), /slot name must match/);
});

// ── 2. Authentication: credential-bound; URL alone is NOT authentication ────
const authSlot = provisionSlot({ name: "auth-slot", role: "agent" });
approveSlot(authSlot.slot.id);
const authSlotId = authSlot.slot.id;

await check("verified credential authenticates and adopts the LIVE role", async () => {
  const session = await resolveSlotSession(fakeReq("/mcp?client=auth-slot", { slotToken: authSlot.credential }), {
    role: null,
    tenantId: "tenant_default",
  });
  assert.equal(session.authenticated, true);
  assert.equal(session.role, "agent");
  assert.equal(session.slotVerified, true);
  assert.equal(session.slotId, authSlotId);
  assert.equal(session.credentialId, clientCredentialId(authSlotId));
});

await check("URL ALONE (no credential) -> fail-closed viewer fallback (#3663)", async () => {
  const session = await resolveSlotSession(fakeReq("/mcp?client=auth-slot"), { role: null, tenantId: "tenant_default" });
  assert.equal(session.authenticated, false, "the URL alone is never authentication (#48/#3663)");
  assert.equal(session.role, "viewer", "uncredentialed URL caller lands on the fail-closed guest default");
  assert.ok(!session.scopes.includes("*"), "fallback scopes must never be omni");
  assert.equal(session.slotVerified, false);
  assert.equal(session.fallbackReason, "slot-credential-missing");
});

await check("/agents/<slot>/sse URL without credential -> fail-closed viewer fallback (#3663)", async () => {
  const session = await resolveSlotSession(fakeReq("/agents/auth-slot/sse"), { role: null, tenantId: "tenant_default" });
  assert.equal(session.role, "viewer");
  assert.equal(session.authenticated, false);
});

await check("wrong credential -> fail-closed viewer fallback (#3663)", async () => {
  const session = await resolveSlotSession(fakeReq("/agents/auth-slot/sse", { slotToken: "slot_bogus" }), {
    role: null,
    tenantId: "tenant_default",
  });
  assert.equal(session.role, "viewer");
  assert.equal(session.fallbackReason, "slot-credential-mismatch");
});

await check("pending slot: even the CORRECT credential cannot authenticate (falls back to fail-closed viewer)", async () => {
  const pending = provisionSlot({ name: "pending-slot", role: "admin" });
  const session = await resolveSlotSession(fakeReq("/mcp?client=pending-slot", { slotToken: pending.credential }), {
    role: null,
    tenantId: "tenant_default",
  });
  assert.equal(session.authenticated, false, "an unapproved slot must not authenticate (#3663)");
  assert.equal(session.role, "viewer");
  assert.equal(session.fallbackReason, "slot-not-approved");
});

// ── 3. IP-drift immunity (the original #48 problem statement) ───────────────
await check("IP rotation across message turns does NOT demote a verified slot", async () => {
  const ipA = await resolveSlotSession(fakeReq("/mcp?client=auth-slot", { ip: "198.51.100.1", slotToken: authSlot.credential }), { role: null, tenantId: "tenant_default" });
  const ipB = await resolveSlotSession(fakeReq("/mcp?client=auth-slot", { ip: "198.51.100.2", slotToken: authSlot.credential }), { role: null, tenantId: "tenant_default" });
  const ipC = await resolveSlotSession(fakeReq("/mcp?client=auth-slot", { ip: "198.51.100.3", slotToken: authSlot.credential }), { role: null, tenantId: "tenant_default" });
  assert.equal(ipA.role, "agent");
  assert.equal(ipB.role, "agent");
  assert.equal(ipC.role, "agent");
  assert.equal(ipA.slotId, ipB.slotId);
  assert.equal(ipB.slotId, ipC.slotId);
});

// ── 4. Revocation: immediate-next-check, no reconnect ───────────────────────
await check("suspension terminates access on the immediate-next check", async () => {
  const before = await assertSlotAuthorization(authSlotId, clientCredentialId(authSlotId));
  assert.equal(before.allowed, true);

  suspendSlot(authSlotId, "security review");
  const after = await assertSlotAuthorization(authSlotId, clientCredentialId(authSlotId));
  assert.equal(after.allowed, false);
  assert.equal(after.reason, "slot-suspended");

  const session = await resolveSlotSession(fakeReq("/mcp?client=auth-slot", { slotToken: authSlot.credential }), { role: null, tenantId: "tenant_default" });
  assert.equal(session.authenticated, false, "a suspended slot falls back to the fail-closed viewer (#3663)");
  assert.equal(session.role, "viewer");
});

await check("reinstate restores access", async () => {
  reinstateSlot(authSlotId);
  const after = await assertSlotAuthorization(authSlotId, clientCredentialId(authSlotId));
  assert.equal(after.allowed, true);
});

await check("credential rotation kills the OLD credential on the next check", async () => {
  const oldFingerprint = clientCredentialId(authSlotId)!;
  const rotated = rotateSlotCredential(authSlotId);
  assert.ok(rotated, "rotation returns the new credential once");
  const oldCheck = await assertSlotAuthorization(authSlotId, oldFingerprint);
  assert.equal(oldCheck.allowed, false, "the rotated-away credential is rejected immediately");
  assert.equal(oldCheck.reason, "slot-credential-rotated");
  const newCheck = await assertSlotAuthorization(authSlotId, clientCredentialId(authSlotId));
  assert.equal(newCheck.allowed, true);
});

await check("role demotion applies on the immediate-next tool call (live gate)", async () => {
  // Slot is currently 'agent' — a restricted (agent-level) tool passes.
  await withSlotContext(
    { slotId: authSlotId, credentialId: clientCredentialId(authSlotId), role: "agent", scopes: ["tools:execute"] },
    async () => {
      const allowed = await toolAccessErrorAsync("render_list_services");
      assert.equal(allowed, null, "agent slot may call agent-level tools while active");
    },
  );
  // Admin demotes the slot mid-session — NO reconnect.
  changeClientRole(authSlotId, "viewer");
  await withSlotContext(
    { slotId: authSlotId, credentialId: clientCredentialId(authSlotId), role: "agent", scopes: ["tools:execute"] },
    async () => {
      const denied = await toolAccessErrorAsync("render_list_services");
      assert.ok(denied !== null, "the demoted slot must be denied on the very next call");
      assert.match(denied!, /requires agent role or higher|live registry check/);
    },
  );
  // Restore for later cases.
  changeClientRole(authSlotId, "agent");
});

// ── 5. Fail-closed on operational-store outage ──────────────────────────────
await check("unreachable operational store -> fail-CLOSED denial (Invariant 5)", async () => {
  process.env.UPSTASH_REDIS_REST_URL = "http://127.0.0.1:1";
  process.env.UPSTASH_REDIS_REST_TOKEN = "unreachable-for-test";
  __setRegistryStoreForTests(new UpstashClientRegistryStore("supremeai:test:client-registry"));
  try {
    const verdict = await assertSlotAuthorization(authSlotId, clientCredentialId(authSlotId));
    assert.equal(verdict.allowed, false, "a privileged check must NOT pass while the store is unverifiable");
    assert.equal(verdict.reason, "slot-store-unreachable");
    await withSlotContext(
      { slotId: authSlotId, credentialId: clientCredentialId(authSlotId), role: "agent", scopes: ["tools:execute"] },
      async () => {
        const denied = await toolAccessErrorAsync("system_summary");
        assert.ok(denied !== null && /fail-closed/.test(denied), "tool gate must fail closed too");
      },
    );
  } finally {
    delete process.env.UPSTASH_REDIS_REST_URL;
    delete process.env.UPSTASH_REDIS_REST_TOKEN;
    // Restore the file-backed store for subsequent suites.
    __setRegistryStoreForTests(new JsonFileClientRegistryStore(process.env.MCP_CLIENT_REGISTRY_FILE!));
  }
});

await check("unverified named guest (?client=...) is NOT subjected to fail-closed slot store check (#610)", async () => {
  process.env.UPSTASH_REDIS_REST_URL = "http://127.0.0.1:1";
  process.env.UPSTASH_REDIS_REST_TOKEN = "unreachable-for-test";
  __setRegistryStoreForTests(new UpstashClientRegistryStore("supremeai:test:client-registry"));
  try {
    const session = await resolveSlotSession(fakeReq("/sse?client=unverified-guest"), { role: null, tenantId: "tenant_default" });
    assert.equal(session.slotVerified, false, "uncredentialed caller must not be slotVerified");
    assert.equal(session.role, "viewer", "uncredentialed caller falls back to the fail-closed guest default (#3663)");
    // Verify that assertSlotAuthorization on a non-slot identity does not fail-close with slot-store-unreachable
    const namedId = session.client?.id ?? "named_unverified-guest";
    const verdict = await assertSlotAuthorization(namedId);
    assert.notEqual(verdict.reason, "slot-store-unreachable", "unverified named guest must not be blocked by slot-store-unreachable");
  } finally {
    delete process.env.UPSTASH_REDIS_REST_URL;
    delete process.env.UPSTASH_REDIS_REST_TOKEN;
    __setRegistryStoreForTests(new JsonFileClientRegistryStore(process.env.MCP_CLIENT_REGISTRY_FILE!));
  }
});

// ── Cross-tenant isolation ──────────────────────────────────────────────────
await check("cross-tenant slot operations are denied (tenant scope)", () => {
  const tenantSlot = provisionSlot({ name: "tenant-a-slot", role: "agent", tenantId: "tenant_a" });
  approveSlot(tenantSlot.slot.id);
  // Another tenant's admin cannot suspend/reinstate/rotate it (fail-closed:
  // the scope guard refuses the mutation).
  assert.throws(() => suspendSlot(tenantSlot.slot.id, "x", "tenant_b"), /another tenant/);
  assert.throws(() => reinstateSlot(tenantSlot.slot.id, "tenant_b"), /another tenant/);
  assert.throws(() => rotateSlotCredential(tenantSlot.slot.id, "tenant_b"), /another tenant/);
  // The owning tenant can.
  assert.ok(suspendSlot(tenantSlot.slot.id, "x", "tenant_a"));
});

// ── 6. Audit trail (immutable) ──────────────────────────────────────────────
await check("audit trail records slot + credential fingerprint + role + tool + outcome", async () => {
  __clearSlotAuditForTests();
  const { slot, credential } = provisionSlot({ name: "audit-slot", role: "agent" });
  approveSlot(slot.id);
  await resolveSlotSession(fakeReq("/mcp?client=audit-slot", { slotToken: credential }), { role: null, tenantId: "tenant_default" });
  await resolveSlotSession(fakeReq("/mcp?client=audit-slot"), { role: null, tenantId: "tenant_default" }); // denied: url-only
  await withSlotContext({ slotId: slot.id, credentialId: clientCredentialId(slot.id), role: "agent", scopes: ["tools:execute"] }, async () => {
    await toolAccessErrorAsync("system_summary");
  });
  suspendSlot(slot.id, "audit-check");
  await withSlotContext({ slotId: slot.id, credentialId: clientCredentialId(slot.id), role: "agent", scopes: ["tools:execute"] }, async () => {
    const denied = await toolAccessErrorAsync("system_summary");
    assert.ok(denied !== null, "tool call after suspension is denied");
  });

  const events = readSlotAudit({ slotId: slot.id });
  assert.ok(events.length >= 5, `expected >=5 audit rows, got ${events.length}`);
  const serialized = JSON.stringify(events);
  assert.ok(!serialized.includes(credential), "the raw credential must NEVER appear in the audit trail");
  assert.ok(events.some((e) => e.outcome === "allowed" && e.operation === "connect" && e.role === "agent"));
  assert.ok(events.some((e) => e.outcome === "denied" && e.reason === "slot-credential-missing"));
  assert.ok(events.some((e) => e.outcome === "allowed" && e.operation === "tool-call" && e.tool === "system_summary"));
  assert.ok(events.some((e) => e.outcome === "denied" && e.reason === "slot-suspended"));
  for (const event of events) {
    assert.ok(event.ts, "every audit row is timestamped");
    if (event.credentialId) assert.match(event.credentialId, /^[0-9a-f]{12}$/, "credentialId is a 12-hex fingerprint");
  }
});

// ── Classification + URL parsing surface ────────────────────────────────────
await check("slot admin tools classify as admin-only; slot_status is agent-level", () => {
  assert.equal(classifyToolCapability("slot_provision").dataClassification, "secret");
  assert.equal(classifyToolCapability("slot_suspend").dataClassification, "secret");
  assert.equal(classifyToolCapability("slot_rotate_credential").dataClassification, "secret");
  assert.equal(classifyToolCapability("slot_audit_trail").dataClassification, "secret");
  assert.equal(classifyToolCapability("slot_status").dataClassification, "internal");
});

await check("slot name parsing: ?client=, /agents/<slot>/sse|mcp, sanitization", () => {
  assert.equal(slotNameFromRequest("/mcp?client=abc"), "abc");
  assert.equal(slotNameFromRequest("/agents/abc/sse"), "abc");
  assert.equal(slotNameFromRequest("/agents/abc/mcp"), "abc");
  assert.equal(slotNameFromRequest("/agents/../evil/sse"), null, "path separators never parse as a slot name");
  assert.equal(slotNameFromRequest("/mcp?client=../evil"), null);
  assert.equal(slotNameFromRequest("/mcp"), null);
});

await check("registry token clients (Bearer) keep working through the slot gate", async () => {
  const { client, token } = registerClient("bearer-client", "agent", ["tools:execute"]);
  approveClient(client.id);
  // index.ts resolves the Bearer credential first (resolveCaller), then hands
  // the resolved principal to resolveSlotSession — mirror that here.
  const resolved = resolveClient(token);
  assert.ok(resolved, "the registry credential resolves");
  const session = await resolveSlotSession(fakeReq("/mcp", { bearer: token }), {
    client: resolved,
    role: resolved?.role ?? null,
    tenantId: "tenant_default",
  });
  assert.equal(session.authenticated, true);
  assert.equal(session.role, "agent");
  assert.equal(session.slotVerified, true);
  assert.equal(session.slotId, client.id);
});

// ── Summary ─────────────────────────────────────────────────────────────────
console.log(`\nSlot verification suite: ${passed} checks passed${process.exitCode ? " (FAILURES present)" : ""}`);
rmSync(workDir, { recursive: true, force: true });
