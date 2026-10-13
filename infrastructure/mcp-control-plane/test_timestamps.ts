import assert from "node:assert/strict";
import { nowTimestamp, timestampDetails, withTimestamp } from "./src/lib/timestamps.js";
import { ApprovalManager } from "./src/policy/approvals/lifecycle.js";

const envelope = nowTimestamp();
assert.equal(envelope.timezone, "UTC");
assert.match(envelope.timestamp, /Z$/);
assert.equal(typeof envelope.timestampMs, "number");

const details = timestampDetails(envelope.timestampMs - 1000, envelope.timestampMs + 5000);
assert.match(details.createdAt, /Z$/);
assert.equal(details.timezone, "UTC");
assert.ok(details.ageMs >= 1000);
assert.ok((details.remainingMs ?? 0) > 0);

const wrapped = withTimestamp({ status: "ok" });
assert.equal(wrapped.status, "ok");
assert.match(wrapped.timestamp, /Z$/);

const manager = new ApprovalManager();
const request = manager.createRequest({ provider: "test", action: "read", riskLevel: "low" } as any);
assert.match(new Date(request.createdAtMs).toISOString(), /Z$/);
assert.ok(request.expiresAtMs > request.createdAtMs);
manager.resolveRequest(request.id, "APPROVED");
const resolved = manager.getRequest(request.id)!;
assert.ok(resolved.resolvedAtMs && resolved.resolvedAtMs >= resolved.createdAtMs);

console.log("timestamp contract tests passed");
