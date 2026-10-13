import { buildAccountRegistry, ProviderAccount } from "./account.registry.js";
import { Capability } from "./capability.registry.js";
import { ProviderName } from "./provider.registry.js";

export interface Resource {
  id: string; // The fully qualified ID, e.g. "render/render-primary"
  accountId: string;
  provider: ProviderName;
  name: string;
  role: string;
  url?: string;
  capabilities: Capability[];
  status: "unknown" | "healthy" | "degraded" | "down";
}

/**
 * Discovers and builds the active resource list based on available accounts.
 */
export async function listResources(): Promise<Resource[]> {
  const accounts = buildAccountRegistry();
  const resources: Resource[] = [];

  for (const account of accounts) {
    if (!account.available) continue;

    // For now, each account maps to a single macro-resource.
    // In Phase 3, the specific Provider Adapters will query the APIs 
    // to discover multiple micro-resources (e.g. 5 tables in Supabase).
    resources.push({
      id: `${account.provider}/${account.id}`,
      accountId: account.id,
      provider: account.provider,
      name: account.displayName,
      role: account.role,
      url: account.url,
      capabilities: account.capabilities,
      status: (await getResourceStatus(`${account.provider}/${account.id}`)) as Resource["status"],
    });
  }

  return resources;
}

export async function getResourceStatus(resourceId: string): Promise<string> {
  const { globalHealthCache } = await import("../health/snapshot.js");
  const provider = resourceId.split("/")[0];
  const snapshot = globalHealthCache.getSnapshot(provider);
  return snapshot?.status ?? "unknown";
}
