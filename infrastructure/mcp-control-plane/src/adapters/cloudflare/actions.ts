import { ActionPlan } from "../../actions/plan.js";
import { env } from "../../lib/env.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";

export function buildCloudflarePurgeCacheAction(): ActionPlan {
  return {
    context: { provider: "cloudflare", action: "purge_cache" },
    description: `Purge Everything from Cloudflare Cache`,
    parameters: {},
    executeFn: async () => {
      const { apiToken, zoneId } = env.cloudflare;
      if (!apiToken || !zoneId) throw new Error("Cloudflare credentials missing");
      const res = await httpRequest(`https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`, {
        method: "POST",
        headers: bearerAuth(apiToken),
        body: { purge_everything: true }
      });
      return res.data;
    }
  };
}
