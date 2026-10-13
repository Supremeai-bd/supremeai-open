import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

import { globalActionExecutor } from "./src/actions/executor.js";
import { buildRenderDeployAction } from "./src/adapters/render/actions.js";
import { globalApprovalManager } from "./src/policy/approvals/lifecycle.js";
import { globalAuditLogger } from "./src/audit/audit.js";

async function main() {
  console.log("=== Testing Action Executor (Phase 6) ===");

  const plan = buildRenderDeployAction("srv-test", false);

  console.log("\n--- Attempt 1: Without Approval (Expect PENDING_APPROVAL) ---");
  const res1 = await globalActionExecutor.execute(plan);
  console.log("Result 1:", res1);

  if (res1.status === "PENDING_APPROVAL" && res1.requestId) {
     console.log(`\n--- Simulating User Approval for ${res1.requestId} ---`);
     globalApprovalManager.resolveRequest(res1.requestId, "APPROVED");

     console.log("\n--- Attempt 2: With overrideRequestId ---");
     const res2 = await globalActionExecutor.execute(plan, res1.requestId);
     console.log("Result 2:", res2);
  }

  console.log("\n--- Audit Logs ---");
  console.log(globalAuditLogger.getLogs());
}

main().catch(console.error);
