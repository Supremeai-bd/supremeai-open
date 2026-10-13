import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

import { globalPolicyEngine } from "./src/policy/policy.engine.js";
import { globalApprovalManager } from "./src/policy/approvals/lifecycle.js";
import { globalHITLManager } from "./src/policy/approvals/hitl.js";

async function main() {
  console.log("=== Testing Policy Engine ===");

  const actions = [
    { provider: "system", action: "summary" },
    { provider: "render", action: "deploy" },
    { provider: "render", action: "delete" },
    { provider: "supabase", action: "restart" },
  ];

  for (const act of actions) {
    const result = globalPolicyEngine.evaluateAction(act);
    console.log(`[Policy] ${act.provider}.${act.action} -> [${result.riskLevel}] ${result.decision}`);
    
    if (result.decision === "REQUIRE_APPROVAL") {
      console.log(`[HITL] Creating approval request for ${act.provider}.${act.action}...`);
      const req = globalApprovalManager.createRequest(act);
      await globalHITLManager.requestApproval(req, result.riskLevel);
      
      console.log(`[Lifecycle] Resolving request ${req.id} as APPROVED...`);
      globalApprovalManager.resolveRequest(req.id, "APPROVED");
      console.log(`[Lifecycle] Request ${req.id} state: ${globalApprovalManager.getRequest(req.id)?.state}`);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
