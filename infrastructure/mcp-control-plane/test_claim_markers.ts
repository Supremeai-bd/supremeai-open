/**
 * Claim-marker epoch regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Replays the live release-blind-spot instances (2026-10-28 → 10-30):
 * bridge_read_feedback kept projecting a released claim from `latestClaim`
 * because parseClaimMarkers only parsed CLAIM markers while the release
 * handler wrote (a) a machine-readable release marker and (b) legacy prose.
 * Live cohort:
 *   • #2557 c51 released 2026-10-30T01:38Z — projected 5h+ later;
 *   • #2201 released 2026-10-28T19:14Z (legacy prose) — projected +38h;
 *   • #3093 released 2026-10-30T08:56Z (new marker) — projected +18min.
 * The fix: epoch-aware parsing — a release closes the claim epoch; claims
 * after the last release start a fresh one (total-lease budget resets).
 */
import {
  parseClaimMarkers,
  type ParsedClaimMarker,
} from "./src/lib/claim_markers.js";

let failures = 0;
function check(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}
function eqMarker(
  m: ParsedClaimMarker | null,
  agent: string | null,
  issueNumber: number | null,
  ttlMinutes: number | null,
): boolean {
  if (m === null) return agent === null && issueNumber === null && ttlMinutes === null;
  return (
    m.agent === agent &&
    (issueNumber === null || m.issueNumber === issueNumber) &&
    (ttlMinutes === null || m.ttlMinutes === ttlMinutes)
  );
}

const CLAIM_A = "<!-- atomic-claim:issue=3093,agent=zai-cron-agent-loop,ts=2026-10-30T08:55:28Z,ttl=30m -->\n**Claimed by Agent (`zai-cron-agent-loop`)** via Tower `work.claim` (GRANT_NEW).";
const RELEASE_NEW = "<!-- atomic-claim-release:issue=3093,agent=zai-cron-agent-loop,ts=2026-10-30T08:56:10Z -->\n**Claim released by Agent (`zai-cron-agent-loop`)** via Tower `bridge.work.release` (#621).";
const RELEASE_LEGACY = "**Claim released by Agent (`zai-cron-agent-478710`)** via Tower `bridge.work.release` (#621)\n\n- Status label restored to `status:unclaimed` (best-effort).";
const CLAIM_LEGACY_JSON = "<!-- atomic-claim -->\n```json\n{\"issueNumber\": 2201, \"claimedBy\": \"zai-cron-agent-478710\", \"claimedAt\": \"2026-10-28T18:44:37Z\", \"leaseMinutes\": 30}\n```";

console.log("1. Back-compat: claim-only timeline keeps current semantics");
{
  const v = parseClaimMarkers([{ body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" }]);
  check("latest = the claim", eqMarker(v.latest, "zai-cron-agent-loop", 3093, 30));
  check("first = the claim (budget epoch start)", eqMarker(v.first, "zai-cron-agent-loop", 3093, 30));
}

console.log("2. Live instance #3093: new release marker closes the epoch");
{
  const v = parseClaimMarkers([
    { body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" },
    { body: RELEASE_NEW, created_at: "2026-10-30T08:56:10Z" },
  ]);
  check("latestClaim = null after release", v.latest === null, JSON.stringify(v.latest));
  check("first = null (epoch closed)", v.first === null);
}

console.log("3. Live instance #2201: legacy prose release retroactively heals");
{
  const v = parseClaimMarkers([
    { body: CLAIM_LEGACY_JSON, created_at: "2026-10-28T18:44:37Z" },
    { body: RELEASE_LEGACY, created_at: "2026-10-28T19:14:37Z" },
  ]);
  check("latestClaim = null after legacy prose release", v.latest === null, JSON.stringify(v.latest));
  check("first = null", v.first === null);
}

console.log("4. Live instance #2557 (c51): prose release after legacy JSON claim");
{
  const v = parseClaimMarkers([
    { body: CLAIM_LEGACY_JSON, created_at: "2026-10-30T01:38:00Z" },
    { body: RELEASE_LEGACY, created_at: "2026-10-30T01:38:59Z" },
  ]);
  check("released claim no longer projected", v.latest === null);
}

console.log("5. Re-claim after release opens a FRESH epoch (budget reset)");
{
  const claimB = "<!-- atomic-claim:issue=3093,agent=contributor-agent,ts=2026-10-30T09:30:00Z,ttl=30m -->";
  const v = parseClaimMarkers([
    { body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" },
    { body: RELEASE_NEW, created_at: "2026-10-30T08:56:10Z" },
    { body: claimB, created_at: "2026-10-30T09:30:00Z" },
  ]);
  check("latest = new claim", eqMarker(v.latest, "contributor-agent", 3093, 30));
  check("first = new claim (180m budget resets per epoch)", eqMarker(v.first, "contributor-agent", 3093, 30));
}

console.log("6. Cross-agent churn: A claims, releases, B claims");
{
  const claimB = "<!-- atomic-claim:issue=2557,agent=cron-484748-c51,ts=2026-10-30T01:38:00Z,ttl=30m -->";
  const v = parseClaimMarkers([
    { body: "<!-- atomic-claim:issue=2557,agent=c34-agent,ts=2026-10-30T00:44:00Z,ttl=30m -->", created_at: "2026-10-30T00:44:00Z" },
    { body: claimB, created_at: "2026-10-30T01:38:00Z" },
    { body: "<!-- atomic-claim-release:issue=2557,agent=cron-484748-c51,ts=2026-10-30T01:38:59Z -->", created_at: "2026-10-30T01:38:59Z" },
  ]);
  check("latestClaim = null (released last)", v.latest === null);
}

console.log("7. Out-of-order comment pages parse identically (ts ordering)");
{
  const a = parseClaimMarkers([
    { body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" },
    { body: RELEASE_NEW, created_at: "2026-10-30T08:56:10Z" },
  ]);
  const b = parseClaimMarkers([
    { body: RELEASE_NEW, created_at: "2026-10-30T08:56:10Z" },
    { body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" },
  ]);
  check("array order irrelevant", (a.latest === null) === (b.latest === null) && a.latest === null && b.latest === null);
}

console.log("8. Zombie-claim window closed: claim + release, then SAME-agent re-claim");
{
  const reclaim = "<!-- atomic-claim:issue=3093,agent=zai-cron-agent-loop,ts=2026-10-30T09:00:00Z,ttl=30m -->";
  const v = parseClaimMarkers([
    { body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" },
    { body: RELEASE_NEW, created_at: "2026-10-30T08:56:10Z" },
    { body: reclaim, created_at: "2026-10-30T09:00:00Z" },
  ]);
  check("re-claim inside old TTL window is the live epoch", eqMarker(v.latest, "zai-cron-agent-loop", 3093, 30));
  check("epoch start = re-claim, not original claim (no budget carry-over)", eqMarker(v.first, "zai-cron-agent-loop", 3093, 30));
}

console.log("9. Fails open: garbage, empty, malformed, release-before-claim");
{
  const empty = parseClaimMarkers([]);
  check("empty comments → null view", empty.latest === null && empty.first === null);
  const garbage = parseClaimMarkers([
    { body: "total nonsense", created_at: "2026-10-30T08:00:00Z" },
    { body: RELEASE_LEGACY, created_at: "not-a-date" },
    { body: "<!-- atomic-claim-release:issue=1,agent=x,ts=invalid -->", created_at: "2026-10-30T08:00:00Z" },
  ]);
  check("malformed events ignored, epoch closed with no claims → null", garbage.latest === null && garbage.first === null);
  const releaseFirst = parseClaimMarkers([
    { body: RELEASE_NEW, created_at: "2026-10-30T08:56:10Z" },
    { body: CLAIM_A, created_at: "2026-10-30T08:55:28Z" },
  ]);
  // claim ts (08:55) < release ts (08:56): release closes the epoch even
  // though the claim COMMENT appears later in a sorted-out array.
  check("earlier claim does not resurrect after later release", releaseFirst.latest === null);
}

console.log("10. Malformed legacy JSON claim ignored, valid one still parsed");
{
  const bad = "<!-- atomic-claim -->\n```json\n{\"claimedBy\": \"x\", \"claimedAt\": \"nope\"}\n```";
  const v = parseClaimMarkers([{ body: bad, created_at: "2026-10-30T08:00:00Z" }]);
  check("invalid claimedAt → no marker", v.latest === null);
  const ok = parseClaimMarkers([{ body: CLAIM_LEGACY_JSON, created_at: "2026-10-28T18:44:37Z" }]);
  check("valid legacy JSON claim parses", eqMarker(ok.latest, "zai-cron-agent-478710", 2201, 30));
}

if (failures > 0) {
  console.error(`\nFAIL — ${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nPASS — claim-marker epoch battery green");
