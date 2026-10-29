/**
 * Hermetic contract tests for the output-truncation gate (truncateToolResult).
 *
 * Defect-class guard (#1882): the former byte-clip cut the serialized JSON
 * mid-structure and appended a prose marker, so every JSON-parsing client
 * failed on exactly the largest tool responses, and a cut landing inside a
 * multi-byte UTF-8 sequence emitted U+FFFD mojibake. The replacement prunes
 * the largest string leaves (UTF-8-safe, nested-JSON-aware) and emits VALID
 * JSON with in-band `_truncation` facts; a wholesale summary covers the
 * pathological floor case.
 *
 * House style: node:assert + plain script; no network, no credentials, no
 * services. Run: tsx scripts/test-runner.ts test_rate_limit_truncation.ts
 */

import assert from "node:assert/strict";
import { truncateToolResult } from "./src/lib/mcp_rate_limit.js";

const CAP = 4096; // deterministic test budget (env getter re-reads per call)

function withCap<T>(fn: () => T): T {
  const prev = process.env.MCP_TOOL_RESULT_MAX_BYTES;
  process.env.MCP_TOOL_RESULT_MAX_BYTES = String(CAP);
  try {
    return fn();
  } finally {
    if (prev === undefined) delete process.env.MCP_TOOL_RESULT_MAX_BYTES;
    else process.env.MCP_TOOL_RESULT_MAX_BYTES = prev;
  }
}

function bytesOf(s: string): number {
  return Buffer.byteLength(s, "utf8");
}

let passed = 0;
function ok(name: string, fn: () => void): void {
  fn();
  passed++;
  console.log(`  ✓ ${name}`);
}

// ---------------------------------------------------------------------------
console.log("=== test_rate_limit_truncation ===");

ok("within-budget result passes through by identity", () => {
  withCap(() => {
    const result = { content: [{ type: "text", text: "tiny" }], isError: false };
    assert.strictEqual(truncateToolResult("t", result), result);
  });
});

ok("non-object results pass through unchanged", () => {
  withCap(() => {
    assert.strictEqual(truncateToolResult("t", null), null);
    assert.strictEqual(truncateToolResult("t", "just a string"), "just a string");
    assert.strictEqual(truncateToolResult("t", 42), 42);
  });
});

ok("unserializable result (BigInt) passes through unchanged", () => {
  withCap(() => {
    const result = { content: [{ type: "text", text: "x" }], v: 1n };
    assert.strictEqual(truncateToolResult("t", result), result);
  });
});

ok("oversized JSON result: emitted text is VALID JSON, structure preserved", () => {
  withCap(() => {
    // mirrors the live repro: double-encoded envelope around a github runs payload.
    // 6 runs: metadata floor (~0.8KB) stays under budget so the JSON-prune path
    // converges before the prune floor (30 runs would exhaust it → wholesale).
    const runs = Array.from({ length: 6 }, (_, i) => ({
      id: 40600000000 + i,
      name: "CI — Open Unified Pipeline",
      head_branch: `bridge/bridge-20261028-pr-${i}`,
      conclusion: i % 5 === 0 ? "failure" : "success",
      logsSnippet: `2026-10-28T01:0${i}:00Z log line — ${"x".repeat(900)}`,
    }));
    const githubJson = JSON.stringify({ total_count: 7229, workflow_runs: runs });
    const envelope = JSON.stringify({ content: [{ type: "text", text: githubJson }] });
    const result = { content: [{ type: "text", text: envelope }], isError: false };
    assert.ok(bytesOf(JSON.stringify(result)) > CAP, "fixture must exceed the cap");

    const out = truncateToolResult("github_workflow_runs", result) as {
      content: { type: string; text: string }[];
      isError: boolean;
      metadata: Record<string, unknown>;
    };
    const outer = JSON.parse(out.content[0].text); // must not throw — THE contract
    assert.equal(out.isError, false);
    assert.equal(out.metadata.truncated, true);
    assert.equal(out.metadata.mode, "json-prune");
    assert.ok(bytesOf(out.content[0].text) <= CAP, "emitted text honors the byte cap");

    // nested layers preserved and parseable
    const inner1 = JSON.parse(outer.content[0].text);
    const github = JSON.parse(inner1.content[0].text);
    assert.equal(github.total_count, 7229);
    assert.equal(github.workflow_runs.length, 6, "run count preserved");
    const snip = github.workflow_runs[0].logsSnippet as string;
    assert.ok(snip.length < 900, "logsSnippet pruned");
    assert.ok(!snip.includes("\uFFFD"), "no mojibake in pruned snippet");

    // in-band facts
    const t = outer._truncation as Record<string, unknown>;
    assert.equal(t.truncated, true);
    assert.equal(t.tool, "github_workflow_runs");
    assert.ok((t.truncatedBytes as number) > 0);
    assert.equal(out.metadata.truncatedBytes, t.truncatedBytes, "metadata/_truncation agree");
  });
});

ok("UTF-8-safe cut: no U+FFFD when the clip straddles Bengali glyphs", () => {
  withCap(() => {
    // 3-byte glyphs; a naive subarray at the cap would split one mid-sequence
    const bangla = "আমাদের কাস্টমার যেন সর্বোত্তম এক্সপেরিয়েন্স পায়। ".repeat(400);
    const result = { content: [{ type: "text", text: bangla }], isError: false };
    const out = truncateToolResult("bengali_tool", result) as {
      content: { type: string; text: string }[];
      metadata: Record<string, unknown>;
    };
    const text = out.content[0].text;
    assert.ok(bytesOf(text) <= CAP);
    JSON.parse(text); // valid JSON
    assert.ok(!text.includes("\uFFFD"), "no replacement chars anywhere");
  });
});

ok("prune floor reached (many tiny strings) → wholesale VALID-JSON summary", () => {
  withCap(() => {
    const tiny: Record<string, string> = {};
    for (let i = 0; i < 20000; i++) tiny[`k${i}`] = "v" + "x".repeat(20); // ~27 B values, all < floor
    const result = { content: [{ type: "text", text: "payload" }], data: tiny, isError: false };
    assert.ok(bytesOf(JSON.stringify(result)) > CAP);
    const out = truncateToolResult("tiny_tool", result) as {
      content: { type: string; text: string }[];
      metadata: Record<string, unknown>;
    };
    const parsed = JSON.parse(out.content[0].text); // valid JSON, not a corrupt half-doc
    assert.equal(parsed.truncated, true);
    assert.equal(parsed.tool, "tiny_tool");
    assert.ok(typeof parsed.note === "string" && parsed.note.length > 0);
    assert.equal(out.metadata.mode, "wholesale");
  });
});

ok("isError flag preserved through truncation", () => {
  withCap(() => {
    const result = { content: [{ type: "text", text: "y".repeat(20000) }], isError: true };
    const out = truncateToolResult("t", result) as { isError: boolean; metadata: Record<string, unknown> };
    assert.equal(out.isError, true);
    assert.equal(out.metadata.truncated, true);
  });
});

ok("_truncation key collision: user field untouched", () => {
  withCap(() => {
    const result = {
      content: [{ type: "text", text: "z".repeat(20000) }],
      _truncation: { marker: "user" },
      isError: false,
    };
    const out = truncateToolResult("t", result) as { content: { text: string }[] };
    const parsed = JSON.parse(out.content[0].text);
    assert.deepEqual(parsed._truncation, { marker: "user" }, "injection skipped on collision");
  });
});

ok("array-root result truncates without _truncation injection", () => {
  withCap(() => {
    const result = [{ type: "text", text: "w".repeat(20000) }];
    const out = truncateToolResult("t", result) as unknown as {
      content: { text: string }[];
      metadata: Record<string, unknown>;
    };
    JSON.parse(out.content[0].text); // valid JSON
    assert.equal(out.metadata.mode, "json-prune");
  });
});

console.log(`\nALL ${passed} CHECKS PASSED (rate-limit truncation contract)`);
