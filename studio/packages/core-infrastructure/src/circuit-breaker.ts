/**
 * Circuit breaker — canonical monorepo primitive.
 *
 * WHY single-sourced (DRY Phase 1-B3): @supremeai/core-infrastructure shipped
 * a placeholder (`execute: async (fn) => fn()`) while the REAL implementation
 * lived privately in frontend/src/utils/api.ts (FrontendCircuitBreaker).
 * Zero consumers ever imported the stub. This is a faithful semantic port:
 * CLOSED → OPEN (after N consecutive failures) → HALF_OPEN (after recovery
 * timeout) → CLOSED (first success), with fast-fail while OPEN.
 */

export type CircuitState = "CLOSED" | "OPEN" | "HALF_OPEN";

export interface CircuitBreakerConfig {
  /** Circuit name used in error messages / warnings. */
  name: string;
  /** Consecutive failures before the circuit opens. */
  failureThreshold: number;
  /** ms the circuit stays open before allowing a HALF_OPEN probe. */
  recoveryTimeoutMs: number;
  /** Injectable clock (defaults to Date.now) — keeps the class testable. */
  now?: () => number;
}

export class CircuitBreaker {
  private state: CircuitState = "CLOSED";
  private failures = 0;
  private lastFailureTime = 0;
  private readonly config: Required<Pick<CircuitBreakerConfig, "name" | "failureThreshold" | "recoveryTimeoutMs">> & { now: () => number };

  constructor(config: CircuitBreakerConfig) {
    this.config = {
      name: config.name,
      failureThreshold: config.failureThreshold,
      recoveryTimeoutMs: config.recoveryTimeoutMs,
      now: config.now ?? (() => Date.now()),
    };
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === "OPEN") {
      const elapsed = this.config.now() - this.lastFailureTime;
      if (elapsed >= this.config.recoveryTimeoutMs) {
        this.state = "HALF_OPEN";
      } else {
        throw new Error(
          `Circuit '${this.config.name}' is OPEN. Retry in ~${Math.ceil((this.config.recoveryTimeoutMs - elapsed) / 1000)}s`,
        );
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    this.failures = 0;
    if (this.state === "HALF_OPEN") {
      this.state = "CLOSED";
    }
  }

  private onFailure(): void {
    this.failures++;
    this.lastFailureTime = this.config.now();
    if (this.failures >= this.config.failureThreshold) {
      this.state = "OPEN";
      console.warn(`⚡ Circuit '${this.config.name}' opened after ${this.failures} failures`);
    }
  }

  getState(): CircuitState {
    return this.state;
  }

  getRecoveryTimeMs(): number {
    if (this.state !== "OPEN") return 0;
    return Math.max(0, this.config.recoveryTimeoutMs - (this.config.now() - this.lastFailureTime));
  }
}
