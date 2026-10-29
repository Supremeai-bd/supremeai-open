import { randomUUID } from "node:crypto";
import { globalHealthHistoryStore } from "./history.js";

/**
 * #2665 watchdog increment — post-restart live-but-empty honesty telemetry
 * (#2710, #2673 remedy pt.2).
 *
 * The #2665 mechanism: after a tower restart the scheduled check loop can stay
 * dead while the snapshot registry sits empty for hours (hollow "ok" shape).
 * A single MANUAL health.full_sweep re-seeds the registry, and every external
 * watchdog that sampled the post-sweep moment read an all-clear that the next
 * hour falsified (first-hand: c42 receipt 16:01-16:03Z corroboration).
 *
 * Therefore freshness is defined by SWEEP-COMPLETION AGE, not registry
 * emptiness: any completed sweep (scheduled or manual) re-stamps the clock,
 * which buys exactly one staleness window of silence — after that the alarm
 * re-arms by itself unless completions RECUR. An all-clear must never be
 * permanently purchasable; that is the anti-false-clear property.
 */

/** A sweep completion older than this makes the plane stale (10 minutes). */
export const SWEEP_STALE_AFTER_MS = 600_000;

/** Boot grace: never alarm before the process has had this long to sweep. */
export const WATCHDOG_BOOT_GRACE_MS = 600_000;

export interface WatchdogView {
  /** ISO timestamp of process boot (when this module was first imported). */
  bootedAt: string;
  /** ISO timestamp of the last completed sweep, or null if none ever completed. */
  lastCompletedSweepAt: string | null;
  /** How many sweep completions have been stamped since boot. */
  sweepCompletions: number;
  /** True when the plane must NOT be read as all-clear (no data or data too old). */
  stale: boolean;
  /** Rising-edge alarm condition: stale AND boot grace elapsed. */
  alarmDue: boolean;
}

/**
 * Pure staleness derivation — exported for the semantic truth table in
 * test_health_watchdog.ts (the #2681 hollow-guard precedent: the contract
 * lives in code, not documentation, so prose cannot defeat assertions).
 *
 * Boundary semantics: a completion EXACTLY at the window edge is still fresh
 * (strictly-greater comparison); the alarm fires only strictly past the edge.
 */
export function deriveWatchdog(
  nowMs: number,
  bootedAtMs: number,
  lastCompletedSweepMs: number | null,
  sweepCompletions: number
): WatchdogView {
  const lastCompletedSweepAt =
    lastCompletedSweepMs === null ? null : new Date(lastCompletedSweepMs).toISOString();
  const sinceLastSweepMs =
    lastCompletedSweepMs === null ? null : nowMs - lastCompletedSweepMs;
  const stale =
    lastCompletedSweepMs === null || (sinceLastSweepMs as number) > SWEEP_STALE_AFTER_MS;
  const alarmDue = stale && nowMs - bootedAtMs > WATCHDOG_BOOT_GRACE_MS;
  return {
    bootedAt: new Date(bootedAtMs).toISOString(),
    lastCompletedSweepAt,
    sweepCompletions,
    stale,
    alarmDue,
  };
}

/**
 * Append a __watchdog__ row to the durable health history. Best-effort by
 * contract (mirrors the history store's own persistence posture): a failure
 * to record the alarm must never break the live tower.
 */
export async function recordWatchdogAlarm(view: WatchdogView): Promise<void> {
  try {
    await globalHealthHistoryStore.append({
      provider: "__watchdog__",
      status: "unknown",
      overallStatus: "unknown",
      incident: {
        id: randomUUID(),
        provider: "__watchdog__",
        timestamp: new Date().toISOString(),
        type: "DEGRADED",
        message:
          `No sweep completion in >10min (completions=${view.sweepCompletions}, ` +
          `lastCompletedSweepAt=${String(view.lastCompletedSweepAt)}) — live-but-empty ` +
          `class #2665: registry is stale, not verified-healthy; manual sweeps only ` +
          `bound this window temporarily.`,
        impactedServices: [],
      },
    });
  } catch (err) {
    console.warn(
      `[HealthWatchdog] history append failed (${(err as Error).message}) — alarm stays console-side`
    );
  }
}
