/*
 * Redis quota/latency guard for SupremeAI MCP Control Plane and Services.
 * Adapted from redis-governor.ts to safeguard Upstash Multi-Account Chain
 * from quota exhaustion, runaway writes, and latency spikes.
 * Deliberately suppresses key payload exposure in metrics/logs.
 */

export type RedisCommandResult<T> = { value: T; cacheHit: boolean; commands: number };

export interface RedisClient {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, options: { EX: number; NX?: boolean }): Promise<unknown>;
  del(key: string): Promise<unknown>;
}

export interface RedisGovernorOptions {
  namespace: string;
  defaultTtlSeconds: number;
  maxValueBytes?: number;
  maxCommandsPerMinute?: number;
  timeoutMs?: number;
  maxRetries?: number;
  failureCooldownMs?: number;
  metrics?: (event: Record<string, unknown>) => void;
}

const inflight = new Map<string, Promise<unknown>>();

function byteLength(value: string): number {
  return Buffer.byteLength(value, "utf8");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class RedisGovernor {
  private readonly client: RedisClient;
  private readonly opts: Required<RedisGovernorOptions>;
  private windowStarted = Date.now();
  private commandCount = 0;
  private circuitOpenUntil = 0;

  constructor(client: RedisClient, options: RedisGovernorOptions) {
    if (!options.namespace || !options.defaultTtlSeconds || options.defaultTtlSeconds <= 0) {
      throw new Error("RedisGovernor requires a namespace and positive default TTL");
    }
    this.client = client;
    this.opts = {
      maxValueBytes: 64 * 1024,
      maxCommandsPerMinute: 600,
      timeoutMs: 800,
      maxRetries: 1,
      failureCooldownMs: 5000,
      metrics: () => undefined,
      ...options,
    };
  }

  private key(key: string): string {
    if (!key || key.length > 300 || /\s/.test(key)) throw new Error("invalid Redis key");
    return `${this.opts.namespace}:${key}`;
  }

  private budget(): void {
    const now = Date.now();
    if (now - this.windowStarted >= 60_000) {
      this.windowStarted = now;
      this.commandCount = 0;
    }
    if (this.commandCount >= this.opts.maxCommandsPerMinute) {
      this.opts.metrics({ event: "redis_budget_exhausted", namespace: this.opts.namespace });
      throw new Error("redis command budget exhausted");
    }
    this.commandCount += 1;
  }

  private async call<T>(operation: () => Promise<T>): Promise<T> {
    if (Date.now() < this.circuitOpenUntil) throw new Error("redis circuit open");
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.opts.maxRetries; attempt += 1) {
      this.budget();
      try {
        const timer = new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("redis command timeout")), this.opts.timeoutMs)
        );
        return await Promise.race([operation(), timer]);
      } catch (err) {
        lastError = err;
        this.opts.metrics({
          event: "redis_command_error",
          attempt,
          namespace: this.opts.namespace,
          error: err instanceof Error ? err.message : "unknown",
        });
        if (attempt < this.opts.maxRetries) await sleep(50 * (attempt + 1));
      }
    }
    this.circuitOpenUntil = Date.now() + this.opts.failureCooldownMs;
    this.opts.metrics({
      event: "redis_circuit_opened",
      cooldownMs: this.opts.failureCooldownMs,
      namespace: this.opts.namespace,
    });
    throw lastError instanceof Error ? lastError : new Error("redis call failed");
  }

  async getOrSet<T>(
    key: string,
    fetcher: () => Promise<T>,
    ttlSeconds?: number
  ): Promise<RedisCommandResult<T>> {
    const redisKey = this.key(key);
    let commands = 0;

    try {
      commands += 1;
      const raw = await this.call(() => this.client.get(redisKey));
      if (raw !== null) {
        this.opts.metrics({ event: "redis_hit", namespace: this.opts.namespace });
        return { value: JSON.parse(raw) as T, cacheHit: true, commands };
      }
    } catch {
      // degraded mode: fall through to fetcher on cache error
    }

    if (!inflight.has(redisKey)) {
      const p = (async () => {
        try {
          const fresh = await fetcher();
          const serialized = JSON.stringify(fresh);
          const size = byteLength(serialized);
          if (size <= this.opts.maxValueBytes) {
            const ttl = ttlSeconds && ttlSeconds > 0 ? ttlSeconds : this.opts.defaultTtlSeconds;
            commands += 1;
            try {
              await this.call(() => this.client.set(redisKey, serialized, { EX: ttl }));
              this.opts.metrics({
                event: "redis_cached",
                bytes: size,
                ttl,
                namespace: this.opts.namespace,
              });
            } catch {
              // Circuit open or set failure in degraded mode: don't block fresh value return
            }
          } else {
            this.opts.metrics({
              event: "redis_skipped_large_value",
              bytes: size,
              namespace: this.opts.namespace,
            });
          }
          return fresh;
        } finally {
          inflight.delete(redisKey);
        }
      })();
      inflight.set(redisKey, p);
    }

    const value = (await inflight.get(redisKey)!) as T;
    return { value, cacheHit: false, commands };
  }

  async invalidate(key: string): Promise<void> {
    const redisKey = this.key(key);
    await this.call(() => this.client.del(redisKey));
    this.opts.metrics({ event: "redis_invalidated", namespace: this.opts.namespace });
  }
}
