import assert from "node:assert/strict";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  buildBridgePrBody,
  bridgeGuide,
  extractRequiredReflectionFields,
  readPullRequestTemplate,
  reflectionFixSnippet,
  REFLECTION_EVIDENCE_SECTION,
  registerBridgeTools,
  REQUIRED_REFLECTION_FIELDS,
  STALE_TEMPLATE_ERROR_PREFIX,
  validateReflectionEvidence,
} from "./src/tools/bridge.tools.js";

/**
 * Constitution Freshness Invariant tests (#567) — the tower slice.
 *
 * বাংলা মন্তব্য: যাচাই হয় —
 *   ১. bridge.guide লাইভ PR টেমপ্লেট ডাইজেস্ট বহন করে (source live|fallback,
 *      mandatory reflection fields, Rule P7 sizing) — কখনো সাইলেন্ট নয়।
 *   ২. readPullRequestTemplate: লাইভ টেমপ্লেট পড়া + fallback digest (সবসময়
 *      fail-closed ফিল্ড সেট সহ)।
 *   ৩. validateReflectionEvidence: knowledge-sharing-guard-এর bash সেমান্টিক্স
 *      মিরর করে (same-line অথবা nested bullet; '<...>' placeholder ব্যর্থ)।
 *   ৪. buildBridgePrBody: SSOT বডি বিল্ডার সবসময় Reflection Evidence বহন করে।
 *   ৫. e2e: bridge.submit_patch পুশের আগেই STALE_TEMPLATE_ERROR দেয় (কোনো
 *      নেটওয়ার্ক কল বা টোকেন ছাড়াই — গেট টোকেন রেজোলিউশনের আগে ফায়ার করে)।
 */

const LIVE_TEMPLATE = [
  "## Summary",
  "",
  "## Reflection Evidence (why + alternatives_rejected)",
  "- **why:** <replace: rationale>",
  "- **alternatives_rejected:**",
  "  - <replace: alternative>",
  "",
  "## Rollback Path",
].join("\n");

// ─── ১. bridge.guide carries the freshness digest ────────────────────────────
{
  const guide = bridgeGuide() as Record<string, any>;
  const freshness = guide.constitutionFreshness;
  assert.ok(freshness, "bridge.guide must carry a constitutionFreshness block (#567)");
  assert.ok(
    freshness.prTemplateSource === "live" || freshness.prTemplateSource === "fallback",
    "prTemplateSource must be live|fallback — never silent",
  );
  assert.deepEqual(
    freshness.mandatoryReflectionFields,
    ["why", "alternatives_rejected"],
    "mandatory reflection fields must be the SSOT pair",
  );
  assert.equal(
    freshness.requiredReflectionSection,
    REFLECTION_EVIDENCE_SECTION,
  );
  assert.match(freshness.ruleP7DomainSizing, /30 files/);
  assert.match(freshness.ruleP7DomainSizing, /200 KB/);
  assert.match(freshness.preValidation, /STALE_TEMPLATE_ERROR/);
  // The legacy contract block must remain untouched (no regression), and the
  // P7 sizing string stays consistent with it.
  const caps = guide.contract.diffCaps as { maxFiles: number; maxBytes: number };
  assert.equal(caps.maxFiles, 30, "bridge diff caps unchanged (30 files)");
  assert.equal(caps.maxBytes, 200 * 1024, "bridge diff caps unchanged (200 KB)");
}

// ─── ২. readPullRequestTemplate: live read + fail-closed fallback ───────────
{
  const live = readPullRequestTemplate((path) =>
    path === "../../.github/PULL_REQUEST_TEMPLATE.md" ? LIVE_TEMPLATE : null,
  );
  assert.equal(live.source, "live");
  assert.equal(live.templatePath, "../../.github/PULL_REQUEST_TEMPLATE.md");
  assert.deepEqual([...live.requiredFields], ["why", "alternatives_rejected"]);

  const scanned = readPullRequestTemplate(() => "## Reflection Evidence\n- **why:** x\n");
  assert.equal(scanned.source, "live");
  assert.deepEqual([...scanned.requiredFields], ["why"], "scan only finds declared fields");

  const noSection = readPullRequestTemplate(() => "# just a readme\n");
  assert.equal(noSection.source, "live");
  assert.deepEqual(
    [...noSection.requiredFields],
    ["why", "alternatives_rejected"],
    "live template without the section falls back to the SSOT field set",
  );

  const fallback = readPullRequestTemplate(() => null);
  assert.equal(fallback.source, "fallback");
  assert.equal(fallback.templatePath, null);
  assert.deepEqual([...fallback.requiredFields], ["why", "alternatives_rejected"]);
  assert.equal(fallback.ruleP7Sizing.maxFiles, 30, "P7 ceiling: 30 files");
  assert.equal(fallback.ruleP7Sizing.maxDiffBytes, 200 * 1024, "P7 ceiling: 200 KB");
}

// ─── ৩. extractRequiredReflectionFields ─────────────────────────────────────
{
  assert.deepEqual(extractRequiredReflectionFields("no template here"), []);
  assert.deepEqual(extractRequiredReflectionFields(LIVE_TEMPLATE), [
    "why",
    "alternatives_rejected",
  ]);
}

// ─── ৪. validateReflectionEvidence mirrors the CI guard ─────────────────────
{
  // No section at all -> everything missing.
  assert.deepEqual(validateReflectionEvidence("## Summary\nhello"), [
    "why",
    "alternatives_rejected",
  ]);

  // Raw template placeholders -> both missing (guard rejects unfilled fields).
  assert.deepEqual(validateReflectionEvidence(LIVE_TEMPLATE), [
    "why",
    "alternatives_rejected",
  ]);

  // Filled why + real nested alternatives -> nothing missing.
  const filled = [
    REFLECTION_EVIDENCE_SECTION,
    "- **why:** The loop executed against a stale constitution and failed CI.",
    "- **alternatives_rejected:**",
    "  - Hard-coding the field list in the tool: rejected because it drifts.",
    "  - Post-merge lint warning: rejected because it wastes a submission.",
  ].join("\n");
  assert.deepEqual(validateReflectionEvidence(filled), []);

  // why filled, alternatives still placeholder -> only alts missing.
  const halfFilled = [
    REFLECTION_EVIDENCE_SECTION,
    "- **why:** Real rationale here.",
    "- **alternatives_rejected:**",
    "  - <replace: alternative>",
  ].join("\n");
  assert.deepEqual(validateReflectionEvidence(halfFilled), ["alternatives_rejected"]);

  // Inline (same-line) alternatives also pass — like the CI guard.
  const inlineAlts = [
    REFLECTION_EVIDENCE_SECTION,
    "- **why:** Real rationale.",
    "- **alternatives_rejected:** polling-only design, rejected because SSE halves latency",
  ].join("\n");
  assert.deepEqual(validateReflectionEvidence(inlineAlts), []);

  // Section must be H2 — an H3 section does not satisfy the template.
  const h3 = filled.replace(REFLECTION_EVIDENCE_SECTION, "### Reflection Evidence");
  assert.deepEqual(validateReflectionEvidence(h3), ["why", "alternatives_rejected"]);

  // Empty why with no nested bullet -> missing.
  const emptyWhy = [
    REFLECTION_EVIDENCE_SECTION,
    "- **why:**",
    "- **alternatives_rejected:** real alternative, rejected because X",
  ].join("\n");
  assert.deepEqual(validateReflectionEvidence(emptyWhy), ["why"]);
}

// ─── ৫. reflectionFixSnippet is copy-pasteable and passes its own gate ──────
{
  const snippet = reflectionFixSnippet();
  assert.match(snippet, /## Reflection Evidence/);
  assert.match(snippet, /- \*\*why:\*\*/);
  assert.match(snippet, /- \*\*alternatives_rejected:\*\*/);
}

// ─── ৬. buildBridgePrBody — SSOT body always carries the evidence ───────────
{
  const body = buildBridgePrBody({
    taskId: "bridge-20261017-freshness",
    summary: "Enforce constitution freshness",
    issueNumber: 567,
    scopePaths: ["core/freshness.py"],
    testsEvidence: "25/25 unittest green",
    reflectionWhy: "Stale-context submissions waste full cycles on mechanical CI rejections.",
    alternativesRejected: "post-merge lint warning\nmanual operator review",
    rollbackPath: "git revert-safe",
  });
  assert.match(body, /## Summary/);
  assert.match(body, /## Linked Work Order/);
  assert.match(body, /Closes #567/);
  assert.match(body, /## Reflection Evidence \(why \+ alternatives_rejected\)/);
  assert.match(body, /- \*\*why:\*\* Stale-context submissions/);
  assert.match(body, /  - post-merge lint warning/);
  assert.match(body, /  - manual operator review/);
  assert.match(body, /## Test Evidence \(3-tier contract\)/);
  assert.deepEqual(validateReflectionEvidence(body), []);

  const specOnlyBody = buildBridgePrBody({
    taskId: "bridge-20261027-spec",
    summary: "Add spec order",
    issueNumber: 888,
    scopePaths: ["docs/bridge/bridge-spec.md"],
    testsEvidence: "doc valid",
    reflectionWhy: "Spec needed first",
    alternativesRejected: "no spec",
  });
  assert.match(specOnlyBody, /Refs #888/);
  assert.ok(!specOnlyBody.includes("Closes #888"), "spec-only PR must NEVER auto-close issue");

  const noIssue = buildBridgePrBody({
    taskId: "bridge-20261017-freshness",
    summary: "Enforce constitution freshness",
    scopePaths: ["a.ts"],
    testsEvidence: "evidence",
    reflectionWhy: "why",
    alternativesRejected: "alt, rejected because z",
  });
  assert.ok(!noIssue.includes("Linked Work Order"), "no issue -> no linked section");
}

// ─── ৭. e2e: submit_patch fail-closes PRE-PUSH (no token, no network) ───────
{
  const server = new McpServer({ name: "freshness-test", version: "1.0.0" });
  await registerBridgeTools(server);
  const client = new Client({ name: "freshness-client", version: "1.0.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);

  const baseArgs = {
    taskId: "bridge-20261017-freshness",
    summary: "Enforce constitution freshness across the loop and tower",
    scopePaths: ["docs/CONSTITUTION_FRESHNESS_INVARIANT.md"],
    testsEvidence: "reflection: done; boot smoke: verify-only exit 0; tests: 25/25 unittest",
    files: [
      {
        path: "docs/CONSTITUTION_FRESHNESS_INVARIANT.md",
        content: "# Constitution Freshness Invariant\n\nDoc content for the gate.\n",
      },
    ],
  };

  // Stale submission (no reflection params) -> STALE_TEMPLATE_ERROR, pre-token.
  // NOTE: raw McpServer (no index.ts wrapper) keeps the dotted registration
  // name; the production tower exposes it as bridge_submit_patch.
  const stale = await client.callTool({ name: "bridge.submit_patch", arguments: { ...baseArgs } });
  assert.equal((stale as any).isError, true, "stale body must be rejected");
  const staleText = (stale as any).content[0].text as string;
  assert.ok(
    staleText.startsWith(STALE_TEMPLATE_ERROR_PREFIX),
    `error must be the #567 contract error, got: ${staleText.slice(0, 120)}`,
  );
  assert.match(staleText, /- \*\*why:\*\*/);
  assert.match(staleText, /alternatives_rejected/);
  assert.match(staleText, /Re-read bridge\.guide/);
  // The gate fires BEFORE token resolution / network — the rejection text
  // must not leak token or HTTP internals.
  assert.ok(!staleText.includes("Bearer"), "no token material in the error");

  // Fresh submission passes the gate: it proceeds past 2.5 into token
  // resolution. In this tokenless test environment the very next step is the
  // token error — the KEY assertion is that the error is NOT the stale one.
  const fresh = await client.callTool({
    name: "bridge.submit_patch",
    arguments: {
      ...baseArgs,
      reflectionWhy: "Fail-closed pre-push beats post-merge CI rejection waste.",
      alternativesRejected:
        "Post-merge lint warning: rejected because it wastes a full submission cycle.",
    },
  });
  const freshText = (fresh as any).content[0].text as string;
  assert.ok(
    !freshText.startsWith(STALE_TEMPLATE_ERROR_PREFIX),
    "fresh body must pass the #567 gate",
  );

  await client.close();
  await server.close();
}

console.log("✅ test_bridge_freshness: all #567 tower-slice assertions passed");
