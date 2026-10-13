export interface HealthSnapshot {
  provider: string;
  status: "healthy" | "degraded" | "down" | "circuit_open" | "unknown";
  lastCheckMs: number;
  checkedAt: string;
  latencyMs: number;
  evidence: { kind: "provider_response" | "error" | "timeout"; summary: string };
  impactedServices: string[];
  data?: unknown;
  error?: string;
  consecutiveFailures: number;
}

export class HealthCache {
  private cache = new Map<string, HealthSnapshot>();
  private defaultTtlMs: number;

  constructor(defaultTtlMs = 30000) {
    this.defaultTtlMs = defaultTtlMs;
  }

  /**
   * Updates or inserts a snapshot into the cache.
   */
  public setSnapshot(snapshot: HealthSnapshot) {
    this.cache.set(snapshot.provider, snapshot);
  }

  /**
   * Retrieves a snapshot for a given provider.
   */
  public getSnapshot(provider: string): HealthSnapshot | undefined {
    return this.cache.get(provider);
  }

  /**
   * Retrieves all cached snapshots.
   */
  public getAllSnapshots(): Record<string, HealthSnapshot> {
    const result: Record<string, HealthSnapshot> = {};
    for (const [key, val] of this.cache.entries()) {
      result[key] = val;
    }
    return result;
  }

  /**
   * Checks if a snapshot is still fresh based on the TTL.
   */
  public isFresh(provider: string, customTtlMs?: number): boolean {
    const snap = this.cache.get(provider);
    if (!snap) return false;
    
    const ttl = customTtlMs ?? this.defaultTtlMs;
    const ageMs = Date.now() - snap.lastCheckMs;
    return ageMs < ttl;
  }

  /**
   * Gets the consecutive failures for a provider to inform circuit breakers.
   */
  public getFailures(provider: string): number {
    return this.cache.get(provider)?.consecutiveFailures || 0;
  }

  /**
   * Fully clears the cache.
   */
  public clear() {
    this.cache.clear();
  }
}

// Global cache instance
export const globalHealthCache = new HealthCache();
