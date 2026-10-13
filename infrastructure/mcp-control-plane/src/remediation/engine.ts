import { IncidentAlert } from "../health/incident.js";
import { builtInRules } from "./rules.js";
import { globalActionExecutor } from "../actions/executor.js";
import { globalKillSwitch } from "./killswitch.js";

export class RemediationEngine {
  private autoExecuteThreshold = 0.95;
  private cooldownsMs = 10 * 60 * 1000; // 10 minutes
  private lastRemediated = new Map<string, number>();

  /**
   * Evaluates an incident against all rules and attempts to auto-fix.
   */
  public async evaluateAndFix(incident: IncidentAlert): Promise<void> {
    if (!globalKillSwitch.isAutonomyEnabled()) {
      console.log(`[REMEDIATION] Ignored incident ${incident.id} because Autonomy is DISABLED.`);
      return;
    }

    console.log(`[REMEDIATION] Evaluating incident ${incident.id} on ${incident.provider}...`);

    for (const rule of builtInRules) {
      const plan = rule.evaluate(incident);
      if (plan) {
        console.log(`[REMEDIATION] Match found! Rule: ${rule.id} (Confidence: ${rule.confidence})`);
        
        // 1. Check Cooldown
        const lastTime = this.lastRemediated.get(incident.provider) || 0;
        if (Date.now() - lastTime < this.cooldownsMs) {
           console.log(`[REMEDIATION] Aborting fix for ${incident.provider}. It is in COOLDOWN.`);
           return;
        }

        // 2. Check Blast Radius (simplified: only 1 provider targeted, we enforce this by design of the action context)
        // Set cooldown
        this.lastRemediated.set(incident.provider, Date.now());

        // 3. Execute based on confidence
        if (rule.confidence >= this.autoExecuteThreshold) {
           console.log(`[REMEDIATION] Confidence >= ${this.autoExecuteThreshold}. Attempting AUTO-FIX...`);

           // SECURITY (#698): high confidence no longer bypasses HITL via the
           // removed "SYS-AUTO-FIX" override magic string. The plan goes through
           // the normal policy path: R0/R1 auto-execute, anything riskier
           // raises a REAL approval request that a human must resolve.
           const res = await globalActionExecutor.execute(plan);
           console.log(`[REMEDIATION] Auto-Fix Result:`, res);
        } else {
           console.log(`[REMEDIATION] Confidence < ${this.autoExecuteThreshold}. Triggering manual execution pipeline...`);
           const res = await globalActionExecutor.execute(plan);
           console.log(`[REMEDIATION] Execution pipelined:`, res);
        }

        return; // Only apply the first matching rule
      }
    }

    console.log(`[REMEDIATION] No matching rules found for incident ${incident.id}.`);
  }
}

export const globalRemediationEngine = new RemediationEngine();

// Hook into Incident Engine / Event Gateway
import("../events/gateway.js").then(({ globalEventGateway }) => {
  globalEventGateway.subscribe(async (event) => {
    // If the event is an internal incident being broadcast
    // In Phase 7 we just sent Telegram alerts. Let's assume IncidentEngine emits to EventGateway too.
    // Wait, let's just hook it up directly to IncidentEngine.
  });
}).catch(console.error);
