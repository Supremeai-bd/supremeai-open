export interface DependencyConfig {
  /** Map of which provider is required by which internal service. */
  dependencies: Record<string, string[]>;
}

/**
 * Maps providers to the services they impact.
 * For example, if 'supabase-primary' goes down, it impacts 'backend' and 'frontend'.
 */
export class DependencyGraph {
  private deps: Record<string, string[]>;

  constructor(config: DependencyConfig) {
    this.deps = config.dependencies;
  }

  /**
   * Get internal services impacted by a provider going down.
   */
  public getImpactedServices(provider: string): string[] {
    const impacted = new Set<string>();
    
    // Find every service that depends on this provider
    for (const [service, providers] of Object.entries(this.deps)) {
      if (providers.includes(provider)) {
        impacted.add(service);
      }
    }

    return Array.from(impacted);
  }

  /**
   * Return the raw dependency map.
   */
  public getRawMap(): Record<string, string[]> {
    return this.deps;
  }
}

// Global Static Dependency Graph
export const globalDependencyGraph = new DependencyGraph({
  dependencies: {
    "mcp-control-plane": ["render", "github", "supabase", "redis", "cloudflare", "infisical", "firebase", "ai-providers", "notify"],
    "frontend": ["firebase-auth", "supabase-db", "vercel"],
    "backend": ["supabase-db", "redis", "render"],
    "ping-worker": ["cloudflare"]
  }
});
