import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

import { globalEventGateway } from "./src/events/gateway.js";
import { globalEventNormalizer } from "./src/events/normalizer.js";
import { globalTaskEngine } from "./src/tasks/engine.js";

// Import IncidentEngine so the event hook gets registered
import "./src/health/incident.js";

async function main() {
  console.log("=== Testing Event Gateway & Task Engine (Phase 7) ===");

  console.log("\n--- Dispatching INFO Event ---");
  const infoEvent = globalEventNormalizer.normalizeCloudflareEvent({ status: "up", url: "https://supremeai.app" });
  await globalEventGateway.dispatch(infoEvent);

  console.log("\n--- Dispatching CRITICAL Event (Should trigger Telegram) ---");
  const critEvent = globalEventNormalizer.normalizeCloudflareEvent({ status: "down", url: "https://supremeai.app" });
  await globalEventGateway.dispatch(critEvent);

  console.log("\n--- Testing Task Engine ---");
  const taskId = await globalTaskEngine.runTask("Mock Backup Task", async () => {
     console.log("Doing backup...");
     await new Promise(resolve => setTimeout(resolve, 500));
  });

  setTimeout(() => {
     console.log("Task Engine State:", globalTaskEngine.getTasks());
  }, 1000);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
