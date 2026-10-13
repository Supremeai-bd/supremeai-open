import assert from "node:assert/strict";
import * as os from "node:os";
import * as path from "node:path";
import { promises as fs } from "node:fs";
import { HealthHistoryStore } from "./src/health/history.js";

async function main() {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "health-history-"));
  const file = path.join(tmpDir, "history.jsonl");

  const store = new HealthHistoryStore(file, 10);
  await store.init(); // first run: file does not exist yet

  // Append a sweep summary + an incident.
  await store.append({ provider: "__sweep__", status: "healthy", overallStatus: "healthy" });
  await store.append({
    provider: "render",
    status: "down",
    incident: {
      id: "INC-test",
      provider: "render",
      timestamp: new Date().toISOString(),
      type: "OUTAGE",
      message: "provider transitioned to down",
      impactedServices: ["api"],
    },
  });

  assert.equal(store.getEntryCount(), 2, "expected 2 in-memory entries");
  assert.equal(store.query("render").length, 1, "expected 1 render entry via query");
  assert.equal(store.query("render")[0].incident?.id, "INC-test");

  // Durability: a fresh store instance over the same file must replay history.
  const reloaded = new HealthHistoryStore(file, 10);
  await reloaded.init();
  assert.equal(reloaded.getEntryCount(), 2, "expected history to survive restart");
  assert.equal(reloaded.query("__sweep__")[0].overallStatus, "healthy");
  // seq continues after reload rather than resetting.
  await reloaded.append({ provider: "__sweep__", status: "degraded", overallStatus: "degraded" });
  const seqAfterReload = reloaded.query("__sweep__").slice(-1)[0].seq;
  assert.ok(seqAfterReload >= 3, "seq must continue after reload");

  // Ring-buffer cap: append past max keeps bounded memory.
  for (let i = 0; i < 12; i++) {
    await reloaded.append({ provider: `p${i}`, status: "healthy" });
  }
  assert.equal(reloaded.getEntryCount(), 10, "ring buffer must be capped at 10");

  // Query filtering still works on the ring.
  const p9 = reloaded.query("p9");
  assert.equal(p9.length, 1, "p9 entry present after ring rollover");

  await fs.rm(tmpDir, { recursive: true, force: true });
  console.log("✅ test_health_history: all assertions passed");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });