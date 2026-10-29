/**
 * T2 smoke: replay the LIVE failure payload shape (triple-encoded, 524KB scale)
 * through the new truncateToolResult and prove the original defect is gone:
 * old code → invalid JSON (client parse failure); new code → valid JSON in/out.
 * Run: npx tsx test_truncation_live_replay.ts   (offline, no services)
 */
import assert from "node:assert/strict";
import { truncateToolResult } from "./src/lib/mcp_rate_limit.js";

process.env.MCP_TOOL_RESULT_MAX_BYTES = String(524_288);

// Build the exact live shape: MCP result → tower envelope (content[].text) → github API JSON (workflow_runs with embedded failed-job logs)
const runs = Array.from({ length: 30 }, (_, i) => ({
  id: 40600000000 + i,
  name: "CI — Open Unified Pipeline",
  node_id: "WFR_kwLOU_tPBM8AAAAJdMiU1Q",
  head_branch: `bridge/bridge-20261028-lease-ssot-wiring-${i}`,
  head_sha: "6d57b4b298fda1b0b2b7b6a6d562087a02a4a1b4",
  event: "pull_request",
  status: "completed",
  conclusion: i % 3 === 0 ? "failure" : "success",
  created_at: "2026-10-28T01:20:18Z",
  logsSnippet: ("2026-10-28T01:0" + (i % 10) + ":45.5514260Z ##[endgroup] Post job cleanup. " +
    "Adding repository directory to the temporary git global config as a safe directory. ").repeat(125),
}));
const githubJson = JSON.stringify({ total_count: 7229, workflow_runs: runs });
const towerEnvelope = JSON.stringify({ content: [{ type: "text", text: githubJson }] });
const mcpResult = { content: [{ type: "text", text: towerEnvelope }], isError: false };

const serialized = JSON.stringify(mcpResult);
const originalBytes = Buffer.byteLength(serialized, "utf8");
console.log("fixture serialized bytes:", originalBytes, "(live failure was 523,977 + marker)");
assert.ok(originalBytes > 524_288, "fixture must exceed the real 512KB cap");

const out = truncateToolResult("github_workflow_runs", mcpResult) as {
  content: { type: string; text: string }[];
  isError: boolean;
  metadata: Record<string, unknown>;
};

// OLD behavior equivalent (for the record): byte-clip would produce unparseable text:
const oldStyle = Buffer.from(serialized, "utf8").subarray(0, 524_288).toString("utf8") + "\n...[truncated N bytes]";
let oldParseOk = true;
try { JSON.parse(oldStyle); } catch { oldParseOk = false; }
console.log("old byte-clip parseable:", oldParseOk, "(expected false — the defect)");

const text = out.content[0].text;
const emitted = Buffer.byteLength(text, "utf8");
console.log("new emitted bytes:", emitted, "| mode:", out.metadata.mode);
assert.equal(oldParseOk, false, "old behavior must be the documented defect");
assert.ok(emitted <= 524_288, "cap honored");

const layer1 = JSON.parse(text); // MCP envelope — THE original failure point, now valid
const l1 = layer1 as { _truncation?: Record<string, unknown>; content: { text: string }[] };
assert.ok(l1._truncation, "in-band _truncation present");
const layer2 = JSON.parse(l1.content[0].text);
const l2 = layer2 as { content: { text: string }[] };
const layer3 = JSON.parse(l2.content[0].text);
const l3 = layer3 as { total_count: number; workflow_runs: { id: number; logsSnippet: string }[] };
assert.equal(l3.total_count, 7229);
assert.equal(l3.workflow_runs.length, 30, "all 30 runs preserved at triple-nest depth");
assert.ok(
  l3.workflow_runs[0].logsSnippet.length < runs[0].logsSnippet.length,
  "logsSnippet pruned (largest-first minimal cutting, not uniform clipping)",
);
assert.ok(!text.includes("\uFFFD"), "no mojibake");

console.log("\nLIVE-REPLAY SMOKE PASSED: triple-encoded 524KB payload → parseable at all 3 layers, cap honored, 0 mojibake");
