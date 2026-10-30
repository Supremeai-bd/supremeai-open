/**
 * Claim-marker parsing — the pure, offline-testable core of the atomic-claim
 * plane (label plane + comment plane, Two-Tier Ingress Invariant #430).
 *
 * Extracted from src/tools/bridge.tools.ts following the #2344/#621 house
 * pattern (pure decision cores live in src/lib so regression batteries can
 * replay live failures offline, zero network).
 *
 * THE BUG THIS FIXES (live instances 2026-10-28 → 10-30): the release handler
 * already writes a machine-readable release marker
 * (`<!-- atomic-claim-release:issue=N,agent=A,ts=ISO -->`) and older releases
 * posted the deterministic prose `**Claim released by Agent (`A`)** via Tower
 * `bridge.work.release` (#621)` — but the parser only ever looked at CLAIM
 * markers. Result: after every release, `bridge_read_feedback` kept
 * projecting the dead claim from `latestClaim`, and consumers (pick-path
 * pre-verify `_feedback_claim_active`, GUARD doctrine, agents) had to
 * cross-check the comment plane by hand on every read. Three live instances:
 *   • #2557 c51 released 2026-10-30T01:38Z — projected 5h+ later;
 *   • #2201 released 2026-10-28 — still projected +38h later;
 *   • #3093 released 2026-10-30T08:56Z — still projected +18min later.
 *
 * EPOCH SEMANTICS: an issue's comments form a claim/release timeline. A
 * release marker (new hidden marker OR legacy prose — retroactive heal for
 * every release already on the boards) CLOSES the claim epoch:
 *   • no claim after the last release → `{ first: null, latest: null }`
 *     (feedback plane reports `latestClaim: null` — the released truth);
 *   • claim(s) after the last release → fresh epoch: `latest` = newest
 *     claim, `first` = FIRST claim at-or-after the last release, so the
 *     180m total-lease budget resets per epoch ("release + re-claim is the
 *     honest path", #621 Phase 1.2).
 * Events are ordered by parsed timestamp (comment array order is only a
 * tiebreak), so out-of-order API pages parse identically.
 */

/** One atomic-claim marker (label plane + comment plane, Invariant #430). */
export interface ParsedClaimMarker {
  agent: string;
  issueNumber: number;
  ts: Date;
  ttlMinutes: number;
}

export interface ClaimMarkerView {
  first: ParsedClaimMarker | null;
  latest: ParsedClaimMarker | null;
}

export const ATOMIC_CLAIM_RE =
  /<!--\s*atomic-claim:issue=(\d+),agent=([A-Za-z0-9_.:-]+),ts=([^,]+),ttl=(\d+)m\s*-->/;

/** Machine-readable release marker written by the bridge.work.release handler. */
export const ATOMIC_CLAIM_RELEASE_RE =
  /<!--\s*atomic-claim-release:issue=(\d+),agent=([A-Za-z0-9_.:-]+),ts=([^,]+?)\s*-->/;

/**
 * Legacy releases (pre-marker writer) posted this exact prose shape from the
 * same handler — parsing it retroactively heals every stale projection
 * already on the boards without any data migration.
 */
export const LEGACY_RELEASE_RE =
  /\*\*Claim released by Agent \(`([A-Za-z0-9_.:-]+)`\)\*\* via Tower `bridge\.work\.release`/;

/**
 * Parse ALL claim/release events from an issue's comments and return the
 * CURRENT epoch's markers (latest ts wins; `first` = epoch start for the
 * total-lease budget). Pure + offline. Fails open: any unparsable or
 * date-invalid comment is ignored — a dark/malformed plane must not invent
 * claim state.
 */
export function parseClaimMarkers(
  comments: ReadonlyArray<{ body?: unknown; created_at?: unknown }>,
): ClaimMarkerView {
  type ClaimEvent = { kind: "claim" | "release"; ts: Date; claim?: ParsedClaimMarker };
  const events: ClaimEvent[] = [];
  for (const c of comments ?? []) {
    const body = typeof c?.body === "string" ? c.body : "";
    if (!body) continue;

    // Release events first (one marker comment is exactly one event).
    const release = ATOMIC_CLAIM_RELEASE_RE.exec(body);
    if (release) {
      const ts = new Date(release[3] ?? "");
      if (!isNaN(ts.getTime())) {
        events.push({ kind: "release", ts });
        continue;
      }
    } else if (LEGACY_RELEASE_RE.test(body)) {
      // Legacy prose release — timestamp from the comment's created_at.
      const ts = new Date(typeof c?.created_at === "string" ? c.created_at : "");
      if (!isNaN(ts.getTime())) {
        events.push({ kind: "release", ts });
        continue;
      }
    }

    // Claim markers (current hidden-marker shape, then legacy JSON fallback —
    // the SAME two shapes the live work.claim handler has always written).
    const match = ATOMIC_CLAIM_RE.exec(body);
    if (match) {
      const ts = new Date(match[3] ?? "");
      if (!isNaN(ts.getTime())) {
        events.push({
          kind: "claim",
          ts,
          claim: {
            issueNumber: parseInt(match[1] ?? "0", 10),
            agent: match[2] ?? "unknown",
            ts,
            ttlMinutes: parseInt(match[4] ?? "30", 10) || 30,
          },
        });
      }
    } else if (body.includes("<!-- atomic-claim -->") && body.includes('"claimedAt"')) {
      try {
        const jsonMatch = /```json\s*(\{[\s\S]*?\})\s*```/.exec(body);
        const parsed = jsonMatch ? JSON.parse(jsonMatch[1]) : null;
        const ts = parsed?.claimedAt ? new Date(parsed.claimedAt) : null;
        if (ts && !isNaN(ts.getTime())) {
          events.push({
            kind: "claim",
            ts,
            claim: {
              issueNumber: typeof parsed.issueNumber === "number" ? parsed.issueNumber : 0,
              agent: typeof parsed.claimedBy === "string" ? parsed.claimedBy : "legacy-agent",
              ts,
              ttlMinutes: typeof parsed.leaseMinutes === "number" ? parsed.leaseMinutes : 30,
            },
          });
        }
      } catch {
        /* malformed legacy marker — ignore */
      }
    }
  }

  if (events.length === 0) return { first: null, latest: null };
  events.sort((a, b) => a.ts.getTime() - b.ts.getTime() || 0);

  // Find the last release; everything after it in the current epoch.
  let lastReleaseIdx = -1;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i]!.kind === "release") {
      lastReleaseIdx = i;
      break;
    }
  }
  const epoch: ParsedClaimMarker[] = [];
  for (let i = lastReleaseIdx + 1; i < events.length; i++) {
    const e = events[i]!;
    if (e.kind === "claim" && e.claim) epoch.push(e.claim);
  }
  if (epoch.length === 0) return { first: null, latest: null };
  return { first: epoch[0]!, latest: epoch[epoch.length - 1]! };
}
