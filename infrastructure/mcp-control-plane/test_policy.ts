import "dotenv/config";
import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

// FIX (#140): `test:unit` must be runnable in a clean environment (no external
// secrets required). HITL approval signing (src/policy/approvals/signing.ts)
// fails closed when neither MCP_ADMIN_KEY nor MCP_API_KEY is present, which
// crashed test_policy.ts with
// "Cannot sign approval link: MCP_ADMIN_KEY/MCP_API_KEY not configured".
// Inject a deterministic fixture key BEFORE exercising HITL signing so the
// policy/HITL/lifecycle flow can be validated offline. `||=` keeps any real,
// operator-configured key untouched; the fixture is a throwaway dummy and is
// never logged (signing only emits HMAC hex digests).
process.env.MCP_ADMIN_KEY ||= "test-admin-key-fixture-0123456789";

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
