import { ActionContext, globalRiskEngine, RiskLevel } from "./risk.engine.js";

export type PolicyDecision = "ALLOW" | "DENY" | "REQUIRE_APPROVAL";

export interface PolicyResult {
  decision: PolicyDecision;
  riskLevel: RiskLevel;
  reason: string;
}

export class PolicyEngine {
  /**
   * Evaluates an action context against the policy rules.
   */
  public evaluateAction(context: ActionContext): PolicyResult {
    const riskLevel = globalRiskEngine.evaluate(context);

    // Rule 1: R6 (Catastrophic) requires strict Human-In-The-Loop Approval with explicit high-risk alert
    if (riskLevel === "R6") {
      return {
        decision: "REQUIRE_APPROVAL",
        riskLevel,
        reason: "Action is classified as R6 (Catastrophic/Disaster Risk). Requires explicit Admin Approval before execution."
      };
    }


    // Rule 2: R0 and R1 are generally safe and Auto-Allowed
    if (riskLevel === "R0" || riskLevel === "R1") {
      return {
        decision: "ALLOW",
        riskLevel,
        reason: `Action is classified as ${riskLevel} (Safe). Auto-approved.`
      };
    }

    // Rule 3: R2 - R5 require explicit Human-In-The-Loop Approval
    return {
      decision: "REQUIRE_APPROVAL",
      riskLevel,
      reason: `Action is classified as ${riskLevel}. Requires explicit human approval.`
    };
  }
}

export const globalPolicyEngine = new PolicyEngine();
