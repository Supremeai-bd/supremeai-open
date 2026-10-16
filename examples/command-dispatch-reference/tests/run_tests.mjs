/**
 * run_tests.mjs — offline test suite for the command dispatch reference (#331).
 *
 * Zero-dependency (node:assert + fs only). Runs against the REAL landed
 * contracts: api-schemas/instruction-envelope.schema.json (#30) and
 * api-schemas/fixtures/permissions.fixture.json (#28) — no mocks of the
 * contract shapes.
 *
 *   npm test   (or: node tests/run_tests.mjs)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { makeValidator, checkSchema, validate } from "../src/schema_lite.mjs";
import { createDispatcher } from "../src/dispatch.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..", "..");
const REFERENCE = resolve(HERE, "..");

const envelopeSchema = JSON.parse(
  readFileSync(resolve(REPO, "api-schemas/instruction-envelope.schema.json"), "utf-8"),
);
const canonicalPolicy = JSON.parse(
  readFileSync(resolve(REPO, "api-schemas/fixtures/permissions.fixture.json"), "utf-8"),
);

/** Canonical policy + the deployment-time task-ingestion grant (an admin
 * decision the canonical fixture has not made yet — used to demonstrate the
 * full accept path; the canonical instance must DENY, see T-failclosed). */
function extendedPolicy({ mfaRequired = false } = {}) {
  const policy = JSON.parse(JSON.stringify(canonicalPolicy));
  policy.permission_scopes.push({
    scope_id: "remote-task-injection",
    resource: "command-dispatch",
    actions: ["inject"],
    min_role_tier: 2,
    requires_mfa: mfaRequired,
  });
  // MUTATE the existing coder sub-role entry (the canonical fixture already
  // carries one — a duplicate push would be shadowed by the first match).
  const coder = policy.agent_sub_roles.find((s) => s.sub_role === "coder");
  coder.allowed_permission_scope_ids = [
    ...coder.allowed_permission_scope_ids,
    "remote-task-injection",
  ];
  return policy;
}

function makeValidEnvelope(issue = "331", objective = "Implement the dispatch reference") {
  return {
    schema_version: "1.0",
    envelope_format: "instruction-envelope-v1",
    target: {
      task_id: `task-${issue}`,
      issue,
      repository: "Supremeai-bd/supremeai",
      task_type: "IMPLEMENT",
      group: "agent-orchestration",
      priority: "P2",
    },
    section_1_role_contract: {
      role: "coder",
      role_description: "Implementation specialist",
      operating_constraints: ["Autonomous execution inside declared scope only."],
      stop_conditions: ["Security boundary hit", "Out of declared scope"],
    },
    section_2_task_scope: {
      objective,
      touching_files: ["scripts/agents/"],
      forbidden_paths: [".env*", "secrets/**"],
      acceptance_criteria: ["Objective satisfied", "Zero unhandled crashes"],
    },
    section_3_governing_rules: {
      policies: [
        { id: "smallest-safe-change", statement: "Smallest safe change only.", source: "AGENT_RULES.md U1" },
      ],
      admin_gate: { required: false, status: "NOT_REQUIRED" },
    },
    section_4_verification: {
      contract_version: "agent-loop-contract/1",
      tiers: [
        { tier: 1, name: "reflection_check", command: "git diff --stat", expectation: "Scope respected." },
        { tier: 2, name: "boot_smoke_test", command: "node --check", expectation: "Syntax clean." },
        { tier: 3, name: "test_suite", command: "npm test", expectation: "Suite green." },
      ],
      required_evidence: ["verification tier output"],
    },
    section_5_submission: {
      pathway: "bridge_submit_patch",
      base_branch: "main",
      branch_convention: "^feat/",
      pr_title_prefix: "feat(open):",
      issue_reference_required: true,
      closes_reference: `Closes #${issue}`,
      pr_body_template: `## Summary\nWork for #${issue}.\n\nCloses #${issue}\n`,
    },
  };
}

function dispatcher(opts = {}) {
  return createDispatcher({
    envelopeSchema,
    permissionsPolicy: opts.policy ?? extendedPolicy(),
    webhookSecret: opts.secret ?? "test-secret-0123456789",
    authorizedChatIds: opts.chatIds ?? [424242],
  });
}

const tests = [];
function test(name, fn) {
  tests.push([name, fn]);
}

// --- schema_lite (the validator itself) ------------------------------------------

test("schema_lite accepts the REAL envelope schema and a valid payload", () => {
  const validateEnvelope = makeValidator(envelopeSchema);
  const errors = validateEnvelope(makeValidEnvelope());
  assert.deepEqual(errors, []);
});

test("schema_lite rejects drift: missing section, bad const, bad pattern, extra prop", () => {
  const validateEnvelope = makeValidator(envelopeSchema);
  const missing = makeValidEnvelope();
  delete missing.section_3_governing_rules;
  assert.ok(validateEnvelope(missing).some((e) => e.includes("section_3_governing_rules")));

  const badFormat = makeValidEnvelope();
  badFormat.envelope_format = "instruction-envelope-v2";
  assert.ok(validateEnvelope(badFormat).some((e) => e.includes("const")));

  const badIssue = makeValidEnvelope("0");
  assert.ok(validateEnvelope(badIssue).some((e) => e.includes("pattern")));

  const extra = makeValidEnvelope();
  extra.sneaky = true;
  assert.ok(validateEnvelope(extra).some((e) => e.includes("additional property")));

  const badTaskId = makeValidEnvelope();
  badTaskId.target.task_id = "totally-random";
  assert.ok(validateEnvelope(badTaskId).some((e) => e.includes("pattern")));
});

test("schema_lite fails closed on unknown schema keywords", () => {
  assert.throws(() => checkSchema({ type: "object", unevaluatedProperties: false }),
    /unsupported keyword/);
  assert.throws(() => checkSchema({ type: "object", properties: { x: { $ref: "https://remote/x" } } }),
    /only local/);
  assert.throws(() => checkSchema({ type: "nope" }), /unknown type/);
});

// --- dispatcher configuration is fail-closed --------------------------------------

test("dispatcher config rejects insecure/absent configuration", () => {
  assert.throws(() => createDispatcher({}), /envelopeSchema/);
  assert.throws(() => createDispatcher({ envelopeSchema }), /permissionsPolicy/);
  assert.throws(() => createDispatcher({
    envelopeSchema, permissionsPolicy: extendedPolicy(), webhookSecret: "short",
  }), /webhookSecret/);
  assert.throws(() => createDispatcher({
    envelopeSchema, permissionsPolicy: extendedPolicy(), webhookSecret: "long-enough-secret",
    authorizedChatIds: [],
  }), /authorizedChatIds/);
  const permissive = JSON.parse(JSON.stringify(extendedPolicy()));
  permissive.defaults.unknown_action = "allow";
  assert.throws(() => createDispatcher({
    envelopeSchema, permissionsPolicy: permissive, webhookSecret: "long-enough-secret",
    authorizedChatIds: [1],
  }), /unknown_action/);
});

// --- webhook route (acceptance criterion 1 + 3) ------------------------------------

test("webhook without or with wrong secret header fails closed 403", () => {
  const d = dispatcher();
  const body = JSON.stringify(makeValidEnvelope());
  const noHeader = d.handleWebhook({ body, headers: {} });
  assert.equal(noHeader.status, 403);
  assert.equal(noHeader.error.code, "UNVERIFIED_SOURCE");
  const wrong = d.handleWebhook({ body, headers: { "x-supreme-signature": "nope" } });
  assert.equal(wrong.status, 403);
  assert.equal(wrong.error.code, "UNVERIFIED_SOURCE");
});

test("webhook malformed JSON fails closed 422 and nothing is processed", () => {
  const d = dispatcher();
  const r = d.handleWebhook({
    body: "{ not json",
    headers: { "x-supreme-signature": "test-secret-0123456789" },
  });
  assert.equal(r.status, 422);
  assert.equal(r.error.code, "MALFORMED_JSON");
});

test("webhook schema-invalid envelope fails closed 422 with structured errors", () => {
  const d = dispatcher();
  const envelope = makeValidEnvelope();
  delete envelope.section_5_submission;
  const r = d.handleWebhook({
    body: JSON.stringify(envelope),
    headers: { "x-supreme-signature": "test-secret-0123456789" },
  });
  assert.equal(r.status, 422);
  assert.equal(r.error.code, "ENVELOPE_INVALID");
  assert.ok(r.error.errors.length >= 1);
});

test("webhook valid envelope + granted policy is accepted 202", () => {
  const d = dispatcher();
  const r = d.handleWebhook({
    body: JSON.stringify(makeValidEnvelope()),
    headers: { "x-supreme-signature": "test-secret-0123456789" },
  });
  assert.equal(r.status, 202);
  assert.equal(r.accepted, true);
  assert.equal(r.task_id, "task-331");
  assert.equal(r.issue, "331");
});

// --- RBAC fail-closed (acceptance criterion 3) --------------------------------------

test("canonical policy (no ingestion scope) DENIES ingestion — deny by default", () => {
  const d = dispatcher({ policy: canonicalPolicy });
  const r = d.handleWebhook({
    body: JSON.stringify(makeValidEnvelope()),
    headers: { "x-supreme-signature": "test-secret-0123456789" },
  });
  assert.equal(r.status, 403);
  assert.equal(r.error.code, "UNAUTHORIZED");
  assert.match(r.error.reason, /deny by default/);
});

test("sub-role without the scope grant is denied even with the scope present", () => {
  const policy = extendedPolicy();
  // auditor's sub-role list does NOT include remote-task-injection
  const d = dispatcher({ policy });
  const r = d.ingestEnvelope(JSON.stringify(makeValidEnvelope()), "auditor");
  assert.equal(r.status, 403);
  assert.match(r.error.reason, /sub-role 'auditor' is not granted/);
});

test("viewer tier below min_role_tier is denied", () => {
  const policy = extendedPolicy();
  policy.agent_sub_roles.push({
    sub_role: "viewer-helper",
    description: "non-specialist probe",
    allowed_permission_scope_ids: ["remote-task-injection"],
  });
  const d = dispatcher({ policy });
  // "viewer" is a tier name (tier 1) not a specialist role -> tier check fires
  const verdict = d.authorize("viewer", "remote-task-injection", "inject");
  assert.equal(verdict.allowed, false);
  assert.match(verdict.reason, /below min_role_tier/);
});

test("MFA-required scope denies without token and accepts with token", () => {
  const policy = extendedPolicy({ mfaRequired: true });
  const d = dispatcher({ policy });
  const without = d.ingestEnvelope(JSON.stringify(makeValidEnvelope()), "coder");
  assert.equal(without.status, 403);
  assert.match(without.error.reason, /MFA/);
  const withToken = d.ingestEnvelope(JSON.stringify(makeValidEnvelope()), "coder",
    { mfaToken: "totp-123456" });
  assert.equal(withToken.status, 202);
});

// --- Telegram route (acceptance criterion 1 + 3) -------------------------------------

test("telegram update from unauthorized chat fails closed 403", () => {
  const d = dispatcher();
  const r = d.handleTelegramUpdate({
    message: { chat: { id: 999 }, text: "/task 331 do the thing" },
  });
  assert.equal(r.status, 403);
  assert.equal(r.error.code, "UNAUTHORIZED_CHAT");
});

test("telegram non-task and malformed commands fail closed 422", () => {
  const d = dispatcher();
  const chatter = d.handleTelegramUpdate({ message: { chat: { id: 424242 }, text: "hello" } });
  assert.equal(chatter.status, 422);
  assert.equal(chatter.error.code, "NOT_A_TASK_COMMAND");
  const malformed = d.handleTelegramUpdate({ message: { chat: { id: 424242 }, text: "/task" } });
  assert.equal(malformed.status, 422);
  assert.equal(malformed.error.code, "MALFORMED_COMMAND");
});

test("telegram valid /task command builds a schema-valid envelope and is accepted", () => {
  const d = dispatcher();
  const r = d.handleTelegramUpdate({
    message: { chat: { id: 424242 }, text: "/task 331 implement the dispatch reference" },
  });
  assert.equal(r.status, 202, JSON.stringify(r));
  assert.equal(r.accepted, true);
  assert.equal(r.task_id, "task-331");
  assert.equal(r.source, "telegram");
});

test("telegram valid command under canonical policy is DENIED (sub-role not granted)", () => {
  const d = dispatcher({ policy: canonicalPolicy });
  const r = d.handleTelegramUpdate({
    message: { chat: { id: 424242 }, text: "/task 331 implement the dispatch reference" },
  });
  assert.equal(r.status, 403);
});

// --- runner ---------------------------------------------------------------------------

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`  PASS | ${name}`);
  } catch (exc) {
    failed += 1;
    console.log(`  FAIL | ${name}: ${exc.message?.split("\n")[0] ?? exc}`);
  }
}
console.log(`${tests.length - failed}/${tests.length} tests passed`);
process.exit(failed ? 1 : 0);
