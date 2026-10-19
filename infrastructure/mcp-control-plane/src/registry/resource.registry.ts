import { buildAccountRegistry, getAccountsForRole, ProviderAccount } from "./account.registry.js";
import { Capability } from "./capability.registry.js";
import { ProviderName } from "./provider.registry.js";
import { RequestContextStore, type UserRole } from "../policy/auth.context.js";

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
 * Discovers and builds the active resource list based on available accounts,
 * filtered by the caller's role (core monorepo and org monitor restricted to admin).
 */
export async function listResources(role?: UserRole): Promise<Resource[]> {
  const store = RequestContextStore.get();
  const effectiveRole = role ?? store?.role;
  const accounts = getAccountsForRole(effectiveRole);
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
