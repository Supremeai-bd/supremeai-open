/**
 * @supremeai/core-infrastructure
 * Shared infrastructure primitives for the SupremeAI monorepo.
 *
 * Directive 3 (Operational Zero-Gap): everything exported here is a REAL,
 * production implementation — no placeholders, no stubs. Modules that cannot
 * be implemented for real are deliberately absent, not faked.
 *
 * Runtime contract: Edge-safe (no node:crypto, no import.meta) so the same
 * primitives run in Next.js middleware, route handlers, Node services and
 * the browser.
 */

export { timingSafeEqualStr } from "./timing-safe";
export { CircuitBreaker, type CircuitState, type CircuitBreakerConfig } from "./circuit-breaker";
