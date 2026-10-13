import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

import { globalHealthEngine } from "./src/health/engine.js";

async function main() {
  console.log("Starting Health Engine Sweep...");
  const report = await globalHealthEngine.runFullSweep();
  console.log("Sweep completed in", report.durationMs, "ms");
  console.log("\n--- Incidents ---");
  console.dir(report.incidents, { depth: null });
  console.log("\n--- Snapshots Summary ---");
  for (const [provider, snap] of Object.entries(report.snapshots)) {
    console.log(`[${provider}] ${snap.status} (Failures: ${snap.consecutiveFailures})`);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
