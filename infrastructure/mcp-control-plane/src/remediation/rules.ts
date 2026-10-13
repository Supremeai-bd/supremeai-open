import { IncidentAlert } from "../health/incident.js";
import { ActionPlan } from "../actions/plan.js";
import { buildRenderDeployAction } from "../adapters/render/actions.js";
import { buildRedisFlushAction } from "../adapters/redis/actions.js";

export interface RemediationRule {
  id: string;
  description: string;
  confidence: number;
  evaluate: (incident: IncidentAlert) => ActionPlan | null;
}

export const builtInRules: RemediationRule[] = [
  {
    id: "render-restart-on-502",
    description: "Restart Render service if it is DOWN or throwing 502/Timeout",
    confidence: 0.96, // Above 0.95 auto-execute threshold
    evaluate: (incident) => {
      if (incident.provider === "render" && incident.type === "OUTAGE") {
         return buildRenderDeployAction("srv-auto-fix-demo", false);
      }
      return null;
    }
  },
  {
    id: "redis-cache-clear-on-oom",
    description: "Flush Redis cache if it is throwing OOM errors",
    confidence: 0.98,
    evaluate: (incident) => {
      if (incident.provider === "redis" && incident.type === "OUTAGE" && incident.message.toLowerCase().includes("oom")) {
         return buildRedisFlushAction();
      }
      return null;
    }
  }
];
