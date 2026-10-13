import { globalRiskEngine } from "./src/policy/risk.engine.js";
import { POLICY_SCHEMA } from "./src/policy/policy.schema.generated.js";
import { globalPolicyEngine } from "./src/policy/policy.engine.js";

/**
 * #2429 — MCP policy parity dump (TS পাশ)।
 *
 * বাংলা মন্তব্য:
 * এটি একটি parity-harness entry — scripts/ci/check_mcp_policy_parity.py
 * এটিকে `npx tsx` দিয়ে চালিয়ে সব (provider, action) combo-র TS ফলাফল JSON-এ
 * সংগ্রহ করে, তারপর Python ইঞ্জিনের একই combo-র ফলাফলের সাথে তুলনা করে।
 * Production server-এ কোনো প্রভাব নেই — শুধু drift-detection gate-এর জন্য।
 */

// Combo সেট: schema-র সব known (provider, action) জোড়া + tool mapping-এর
// সব (provider, action) + edge cases (unknown, read-only keyword variants)।
const combos: Array<{ provider: string; action: string }> = [];
for (const [provider, rules] of Object.entries(POLICY_SCHEMA.providers)) {
  for (const action of Object.keys(rules.actions)) {
    combos.push({ provider, action });
  }
  combos.push({ provider, action: "__unknown_action__" });
}
for (const [tool, [provider, action]] of Object.entries(POLICY_SCHEMA.toolProviderAction)) {
  combos.push({ provider, action, tool });
}
// Edge cases: read-only keyword semantics + unknown provider + system/health।
for (const action of ["read_graph", "list_services", "get_status", "search_nodes", "verify_proof", "query_db", "fetch_all", "open_file", "summary_report", "deploy_all", "restart", "delete"]) {
  combos.push({ provider: "edge", action });
}
combos.push({ provider: "system", action: "anything" });
combos.push({ provider: "health", action: "full_sweep" });
combos.push({ provider: "unknown_provider", action: "unknown_action" });
combos.push({ provider: "memory", action: "brand_new_write" });
combos.push({ provider: "mesh", action: "brand_new_op" });

const results = combos.map(({ provider, action, tool }) => {
  const riskLevel = globalRiskEngine.evaluate({ provider, action });
  const policyResult = globalPolicyEngine.evaluateAction({ provider, action });
  return {
    provider,
    action,
    ...(tool ? { tool } : {}),
    risk: riskLevel,
    decision: policyResult.decision,
  };
});

console.log(JSON.stringify({
  engine: "typescript",
  schemaVersion: POLICY_SCHEMA.schemaVersion,
  schemaHash: POLICY_SCHEMA.schemaHash,
  caseCount: results.length,
  results,
}, null, 2));
