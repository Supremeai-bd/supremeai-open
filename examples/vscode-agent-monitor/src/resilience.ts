/**
 * resilience.ts — reconnect backoff + bounded output buffer (issue #333 AC3).
 *
 * Backoff: exponential with full jitter, capped; resets after a stable
 * connection. Buffer: bounded line buffer that drops OLDEST lines with an
 * explicit truncation marker — a flooded stream can stall a stream, it can
 * never freeze the IDE (AC3).
 */

/** Backoff schedule: full jitter over exponential windows. */
export class ReconnectBackoff {
  private attempt = 0;
  constructor(
    private readonly baseMs = 1000,
    private readonly capMs = 60_000,
    private readonly rng: () => number = Math.random,
  ) {
    if (baseMs <= 0 || capMs < baseMs) {
      throw new Error("backoff: require 0 < baseMs <= capMs (fail-closed)");
    }
  }

  /** Next delay in ms; deterministic given the injected rng. */
  next(): number {
    const exp = Math.min(this.capMs, this.baseMs * Math.pow(2, this.attempt));
    this.attempt += 1;
    const jitter = Math.floor(this.rng() * exp * 0.5);
    return Math.min(this.capMs, exp - jitter);
  }

  /** A stable connection resets the schedule (spec etiquette). */
  reset(): void {
    this.attempt = 0;
  }

  get attempts(): number {
    return this.attempt;
  }
}

export const TRUNCATION_MARKER = "... earlier lines dropped (buffer cap)";

/** Bounded output buffer: keeps the most recent maxLines, marks truncation. */
export class BoundedOutputBuffer {
  private lines: string[] = [];
  private truncated = false;
  constructor(private readonly maxLines = 2000) {
    if (!Number.isInteger(maxLines) || maxLines < 10) {
      throw new Error("buffer: maxLines must be an integer >= 10 (fail-closed)");
    }
  }

  push(line: string): void {
    if (this.lines.length >= this.maxLines) {
      this.lines.shift();
      this.truncated = true;
    }
    this.lines.push(line);
  }

  drain(): string[] {
    const out = this.truncated ? [TRUNCATION_MARKER, ...this.lines] : [...this.lines];
    this.lines = [];
    this.truncated = false;
    return out;
  }

  get size(): number {
    return this.lines.length;
  }
}
