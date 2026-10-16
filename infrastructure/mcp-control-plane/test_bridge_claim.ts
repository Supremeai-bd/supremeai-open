import assert from "node:assert/strict";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  BRIDGE_QUEUE_LABEL,
  CLAIM_MARKER,
  CLAIMED_LABELS,
  bridgeGuide,
  buildClaimComment,
  evaluateClaimGate,
  registerBridgeTools,
  scanFileForSecrets,
} from "./src/tools/bridge.tools.js";

/**
 * Atomic claim-step battery (Two-Tier Ingress Invariant #430).
 *
 * বাংলা মন্তব্য: submit_patch এর optional claimTaskIssue ধাপের pure-plane
 * যাচাই — guard-parity (label plane + marker plane), fail-closed বহুমুখী,
 * idempotent re-submission, byte-deterministic claim comment, secret-scan
 * cleanliness, guide lifecycle-এ claim ধাপ, এবং tool schema-তে param-এর
 * উপস্থিতি (e2e InMemoryTransport listing)। কোনো network I/O নেই।
 */

const TASK = "bridge-20261017-tower-claim-step-r2";
let checks = 0;
function ok(cond: unknown, msg: string): void {
  assert.ok(cond, msg);
  checks++;
}

// ---- 1. evaluateClaimGate: fail-closed matrix + guard parity ----
ok(!evaluateClaimGate({ issueState: "closed", labels: [], comments: [], claimTaskIssue: 404, taskId: TASK }).ok,
  "closed task issue fails closed");
ok(!evaluateClaimGate({ labels: [], comments: [], claimTaskIssue: 404, taskId: TASK }).ok,
  "unreadable state fails closed");
ok(!evaluateClaimGate({ issueState: 42, labels: [], comments: [], claimTaskIssue: 404, taskId: TASK }).ok,
  "malformed state fails closed");
ok(evaluateClaimGate({ issueState: "open", labels: [{ name: "status:claimed" }], comments: [], claimTaskIssue: 430, taskId: TASK }).ok,
  "status:claimed label passes");
const inProg = evaluateClaimGate({ issueState: "open", labels: ["status:in-progress"], comments: [], claimTaskIssue: 430, taskId: TASK });
ok(inProg.ok && !inProg.alreadyClaimedBySelf, "status:in-progress label passes");
ok(!evaluateClaimGate({ issueState: "open", labels: ["bridge:rejected", "P2-medium"], comments: [], claimTaskIssue: 404, taskId: TASK }).ok,
  "unrelated labels fail closed");
const own = evaluateClaimGate({ issueState: "open", labels: [], comments: [{ body: `${CLAIM_MARKER}\n🪝 Atomic Claim — ${TASK}` }], claimTaskIssue: 404, taskId: TASK });
ok(own.ok && own.alreadyClaimedBySelf === true, "own-taskId marker is idempotent-pass");
ok(!evaluateClaimGate({ issueState: "open", labels: [], comments: [{ body: `${CLAIM_MARKER}\n🪝 Atomic Claim — bridge-20260101-someone-else` }], claimTaskIssue: 404, taskId: TASK }).ok,
  "foreign atomic claim fails closed");
ok(!evaluateClaimGate({ issueState: "open", labels: [], comments: [{ body: "I claim this issue, working on it now" }], claimTaskIssue: 404, taskId: TASK }).ok,
  "marker-free prose is not a claim");
ok(!evaluateClaimGate({ issueState: "open", labels: [], comments: [{ nope: 1 }, "string-shape", null], claimTaskIssue: 404, taskId: TASK }).ok,
  "malformed comment shapes fail closed");
ok(!evaluateClaimGate({ issueState: "open", labels: [], comments: [], claimTaskIssue: 404, taskId: TASK }).ok,
  "no claim plane fails closed");
ok(typeof evaluateClaimGate({ issueState: "open", labels: [], comments: [], claimTaskIssue: 404, taskId: TASK }).reason === "string",
  "fail verdict carries a reason");

// ---- 2. constants: guard grep parity ----
ok(CLAIM_MARKER === "<!-- atomic-claim -->", "marker literal matches the open repo guards' grep");
ok(CLAIMED_LABELS.includes("status:claimed") && CLAIMED_LABELS.includes("status:in-progress"),
  "claimed-label registry matches the open repo guards");

// ---- 3. buildClaimComment: byte-deterministic + clean ----
const c1 = buildClaimComment(TASK, "zai-autonomous-contributor (session 31)");
const c2 = buildClaimComment(TASK, "zai-autonomous-contributor (session 31)");
ok(c1 === c2, "claim comment is byte-deterministic");
ok(c1.includes(CLAIM_MARKER) && c1.includes(TASK), "claim comment carries marker + taskId");
ok(c1.startsWith(CLAIM_MARKER), "marker is the very first byte sequence (grep-safe)");
ok(scanFileForSecrets(c1) === null, "claim comment is secret-scan clean");
ok(scanFileForSecrets(CLAIM_MARKER) === null, "marker literal is secret-scan clean");
ok(buildClaimComment(TASK).includes("zero-credential-mcp-agent"), "identity falls back to the tower default");

// ---- 4. guide lifecycle carries the claim step ----
const guide = bridgeGuide();
ok(guide.lifecycle.length >= 6, "guide lifecycle >= 6 (claim step added)");
ok(guide.lifecycle.some((s: string) => s.includes("claimTaskIssue") && s.includes("atomic-claim")),
  "lifecycle names the claim mechanism explicitly");
ok(guide.contract.secretScanFamilies.length >= 10, "contract still publishes the full scan-family table");
ok(guide.entrypoints.openRepo === bridgeGuide().entrypoints.openRepo, "guide is deterministic");

// ---- 5. e2e: submit_patch schema exposes optional claimTaskIssue (no network) ----
const server = new McpServer({ name: "claim-battery", version: "0.0.0" });
await registerBridgeTools(server);
const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
const client = new Client({ name: "claim-battery-client", version: "0.0.0" });
await server.connect(serverTransport);
await client.connect(clientTransport);
const tools = await client.listTools();
const submit = tools.tools.find((t) => t.name === "bridge.submit_patch");
ok(Boolean(submit), "bridge.submit_patch is listed");
const props = (submit?.inputSchema as { properties?: Record<string, unknown> })?.properties ?? {};
ok("claimTaskIssue" in props, "claimTaskIssue param exposed in the tool schema");
ok(!tools.tools.some((t) => t.name === "bridge.claim_task"), "no separate claim tool surface (param rides submit_patch)");
ok(typeof BRIDGE_QUEUE_LABEL === "string" && BRIDGE_QUEUE_LABEL.startsWith("bridge:"), "queue label registry intact");

console.log(`test_bridge_claim.ts — ALL PASS (${checks} checks)`);
await client.close();
await server.close();
process.exit(0);
