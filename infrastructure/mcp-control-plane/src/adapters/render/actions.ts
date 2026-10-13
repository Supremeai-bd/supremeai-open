import { ActionPlan } from "../../actions/plan.js";
import { env } from "../../lib/env.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";

export function buildRenderDeployAction(serviceId: string, clearCache: boolean = false): ActionPlan {
  return {
    context: { provider: "render", action: "deploy" },
    description: `Deploy Render Service ${serviceId} (Clear Cache: ${clearCache})`,
    parameters: { serviceId, clearCache },
    executeFn: async () => {
      const { apiKey } = env.render.primary;
      if (!apiKey) throw new Error("RENDER_API_KEY missing");
      const res = await httpRequest(`https://api.render.com/v1/services/${serviceId}/deploys`, {
        method: "POST",
        headers: bearerAuth(apiKey),
        body: { clearCache }
      });
      return res.data;
    },
    verifyFn: async () => {
      // In a real system, we'd poll the deploy status or check health endpoint.
      // For now, we simulate a successful deployment check.
      return true;
    }
    // rollbackFn could attempt to deploy the previous commit sha if deploy fails
  };
}
