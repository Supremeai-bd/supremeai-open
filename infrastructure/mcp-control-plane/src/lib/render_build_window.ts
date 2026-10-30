/**
 * Month-window build-minute accounting for the Render adapter (#2811 window class).
 *
 * Witness #2811 (platform-guardian cycle-47): the tower's render_service_health
 * ledger readings moved DOWNWARD hour-over-hour during the retry-fail deploy
 * loop, once with an exact dual-account mirror (ΔbuildMin == −ΔfreeLimit on
 * both accounts in the same hour). Usage cannot decrease — every drop was the
 * adapter's own fixed 20-deploy window sliding: as new deploys pushed older,
 * longer builds out of the fetch window, the computed month-to-date total
 * dropped and freeLimitRemaining (= 500 − monthlyBuildMinutes, the same
 * variable) rose by exactly that amount. A truncated window under-counts
 * month-to-date burn during retry-fail months and can present a false safe
 * posture to every consumer of these numbers.
 *
 * The fix: cursor-paginate the deploys list until the month window is
 * saturated (a parsed deploy predating month start, or a short page), so the
 * reported figure is a true month-to-date sum — monotone with respect to
 * actual burn, and self-consistent with its derived free-limit remainder.
 *
 * Pure and offline: no fetches here, only summation + stop-rule math, so the
 * battery in test_render_build_window.ts can pin it deterministically.
 */

/** Render caps a deploys page at 100 entries. */
export const BUILD_WINDOW_PAGE_SIZE = 100;

/** Page cap: 12 × 100 = 1200 deploys, far beyond any observed month. */
export const BUILD_WINDOW_MAX_PAGES = 12;

/** Both Render envelopes: a bare deploy object or { deploy: {...} }. */
export interface RawDeployItem {
  deploy?: Partial<DeployRecord>;
  id?: string;
  createdAt?: string;
  finishedAt?: string;
  status?: string;
}

export interface DeployRecord {
  id?: string;
  createdAt?: string;
  finishedAt?: string;
  status?: string;
}

export function unwrapDeploy(item: unknown): DeployRecord {
  if (!item || typeof item !== "object") return {};
  const raw = item as RawDeployItem;
  const dep = raw.deploy;
  return dep && typeof dep === "object" ? (dep as DeployRecord) : (raw as DeployRecord);
}

/** UTC calendar-month start containing `now`. */
export function monthStartUtc(now: Date): Date {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
}

export interface MonthWindowSum {
  /** Total build seconds of deploys started within the month window. */
  totalSeconds: number;
  /** Deploy records counted (started in-month, positive duration). */
  count: number;
  /** A parsed deploy predates monthStart — the page stream is saturated. */
  sawPreMonth: boolean;
}

/**
 * Sum deploys started within [monthStart, ·) from one page of the newest-first
 * deploys list. Records with missing/unparseable timestamps are skipped (they
 * carry no decision-grade burn); non-positive durations add zero seconds.
 * `sawPreMonth` is the pagination stop rule: with Render listing newest-first,
 * reaching a pre-month start certifies the stream has covered the window.
 */
export function sumMonthBuildSeconds(items: unknown[], monthStart: Date): MonthWindowSum {
  let totalSeconds = 0;
  let count = 0;
  let sawPreMonth = false;
  for (const item of items) {
    const dep = unwrapDeploy(item);
    if (!dep.createdAt || !dep.finishedAt) continue;
    const started = new Date(dep.createdAt);
    const finished = new Date(dep.finishedAt);
    if (Number.isNaN(started.getTime()) || Number.isNaN(finished.getTime())) continue;
    if (started < monthStart) {
      sawPreMonth = true;
      continue;
    }
    const duration = (finished.getTime() - started.getTime()) / 1000;
    if (duration > 0) {
      totalSeconds += duration;
      count += 1;
    }
  }
  return { totalSeconds, count, sawPreMonth };
}

/** True when pagination can stop: short page or the window is saturated. */
export function windowSaturated(pageItems: unknown[], monthStart: Date): boolean {
  if (pageItems.length < BUILD_WINDOW_PAGE_SIZE) return true;
  return sumMonthBuildSeconds(pageItems, monthStart).sawPreMonth;
}

/** Cursor for the next older page: the last item's deploy id. */
export function nextCursor(pageItems: unknown[]): string | undefined {
  const last = pageItems.length > 0 ? pageItems[pageItems.length - 1] : undefined;
  const dep = unwrapDeploy(last);
  return dep.id;
}
