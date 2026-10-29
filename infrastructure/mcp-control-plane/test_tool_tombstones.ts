import assert from "node:assert/strict";
import {
  TOOL_TOMBSTONES,
  resolveToolTombstone,
  suggestNearestTool
} from "./src/registry/tool_tombstones";

console.log("[test_tool_tombstones] Starting test run...");

// 1. Direct tombstone resolution
const qTombstone = resolveToolTombstone("bridge_work_queue");
assert.ok(qTombstone !== null, "bridge_work_queue must resolve as a tombstone");
assert.equal(qTombstone?.error, "tool_moved");
assert.equal(qTombstone?.use, "bridge.work_queue");
assert.equal(qTombstone?.code, -32602);
assert.match(qTombstone?.message ?? "", /has moved to canonical name/);

// 2. Guide-named dotted tombstone resolution (#2488 recovery)
const claimTombstone = resolveToolTombstone("work.claim");
assert.ok(claimTombstone !== null, "work.claim must resolve as a tombstone");
assert.equal(claimTombstone?.use, "work_claim");

const feedbackTombstone = resolveToolTombstone("bridge.read_feedback");
assert.ok(feedbackTombstone !== null, "bridge.read_feedback must resolve as a tombstone");
assert.equal(feedbackTombstone?.use, "bridge_read_feedback");

// 3. Unknown name returns null
const unknown = resolveToolTombstone("totally_nonexistent_tool");
assert.equal(unknown, null, "Unknown tool should not have a tombstone");

// 4. Nearest tool suggestion
const knownTools = ["bridge.work_queue", "bridge_submit_patch", "github.create_issue"];
const suggestion1 = suggestNearestTool("bridge_work_queue", knownTools);
assert.equal(suggestion1, "bridge.work_queue", "Should suggest bridge.work_queue for bridge_work_queue");

const suggestion2 = suggestNearestTool("github_create_issue", knownTools);
assert.equal(suggestion2, "github.create_issue", "Should suggest github.create_issue");

console.log("[test_tool_tombstones] ALL 4 CHECKS PASSED.");

