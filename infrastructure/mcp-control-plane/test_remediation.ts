import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

import { globalRemediationEngine } from "./src/remediation/engine.js";
import { globalKillSwitch } from "./src/remediation/killswitch.js";
import { IncidentAlert } from "./src/health/incident.js";

async function main() {
  console.log("=== Testing Autonomous Remediation (Phase 8) ===");

  const incident: IncidentAlert = {
    id: "INC-test1",
    provider: "render",
    type: "OUTAGE",
    message: "Provider render transitioned to down",
    timestamp: new Date().toISOString(),
    impactedServices: ["api"]
  };

  console.log("\n--- Attempt 1: Triggering Auto-Fix ---");
  await globalRemediationEngine.evaluateAndFix(incident);

  console.log("\n--- Attempt 2: Triggering immediately again (Expect Cooldown) ---");
  await globalRemediationEngine.evaluateAndFix(incident);

  console.log("\n--- Attempt 3: Killing Autonomy and Triggering ---");
  globalKillSwitch.emergencyStop();
  await globalRemediationEngine.evaluateAndFix(incident);
}

main().catch(console.error);
