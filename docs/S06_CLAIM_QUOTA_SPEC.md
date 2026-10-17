# S06 — Single Active Claim Quota Spec (work.claim concurrency guard, #479)

Status: r1 · 2026-10-17 · Author: Z.ai Code (session web-26454b1b)
Scope: `infrastructure/mcp-control-plane/src/tools/bridge.tools.ts`
(work.claim handler) + `infrastructure/mcp-control-plane/test_bridge_onboarding.ts`.
Reference implementation + offline contract tests ship with this spec
(pure-new-file lane): `scripts/tower/claim_quota_reference.py`,
`tests/test_s06_claim_quota.py`. The TS edits themselves follow the
exact hunks in §5.

## 1. Problem

`work.claim` (S0.1, #456) only checks whether the TARGET issue has an
existing lock. It never asks whether the CALLING agent already holds a
live claim on another unresolved issue. A single external agent —
task #479 names `zai-web` as the observed example — can claim every
open board issue simultaneously and starve all other agents. Task #479
mandates a strict Single Active Claim Quota: Max 1 In-Flight Claim per
Agent, enforced fail-closed at claim time.

## 2. Behavior contract

- Precondition: the S0.1 target-issue decision matrix runs first,
  unchanged. The quota gate runs AFTER that matrix and BEFORE any
  write (label, comment, audit).
- Gated paths: the grant decisions `GRANT_NEW` and `GRANT_RENEW`
  (spec-literal) plus `GRANT_TAKEOVER` (defense-in-depth: taking a
  freshly expired lease while holding another live claim would
  reintroduce hoarding; trimming this path requires an ops note).
  `NOOP_SELF` (idempotent re-claim, mutates nothing) bypasses the scan.
- Scan: open issues in `Supremeai-bd/supremeai-open` carrying
  `status:claimed`, latest S0.1 atomic-claim marker parsed, marker
  issue must equal the issue number (mismatch = garbage, ignored),
  marker agent must equal the calling agentId, lease live per
  `ttl` (default 30m, strict-greater expiry — exactly-TTL is live).
- Rejection (fail-closed), exact MCP envelope:

```json
{
  "isError": true,
  "code": "AGENT_CONCURRENCY_LIMIT_REACHED",
  "message": "Agent '<agentId>' already holds active claim on Issue #<existing_issue>. Submit patch or release before claiming new work."
}
```

- Determinism: when multiple live claims exist, the rejection cites
  the lowest issue number (deterministic anchor; active set reported
  ascending).
- Renewal: re-claiming an issue already in the agent's own live set is
  a renewal of that slot and never counts as a hoard.
- Limit constant: `MAX_ACTIVE_CLAIMS = 1` (task #479 normative). This
  supersedes the S0.1 reference placeholder `MAX_ACTIVE_CLAIMS = 3`,
  which was declared but never enforced. The quota predicate takes
  `max_active` as an ops-tunable argument (default 1).
- Unattributable claims (label-plane `status:claimed` with no S0.1
  marker and no `label_claimed_at`) cannot be proven to belong to the
  calling agent and never block; the guard blocks provable hoards
  only. Label-plane claims with a `label_claimed_at` timestamp are
  honored with the default TTL (Rule 9 parity).

## 3. Release semantics (slot freed)

A claim stops counting against the agent's quota when any of:
1. **Lease expired** — Rule 9 arithmetic, strict-greater: now > ts + ttl.
2. **Holding issue closed** — scan covers open issues only.
3. **Work Order submitted and verified** — tower-visible intake ack
   (board field `wo_verified=True` on the holding issue). A queued WO
   (`wo_verified=False`) does NOT free the slot; the tower cannot see
   the internal-repo PR lifecycle, so intake ack is the strongest
   verifiable signal (documented policy trade-off: an agent may hold
   one fresh claim plus queued WOs; the stale-claim releaser (#470,
   Rule 9) still bounds neglect).

Clock skew (now earlier than a parsed claim time) raises/aborts
fail-closed — never silently grants.

## 4. Why not the alternatives

- **Submit-time enforcement in bridge_submit_patch** — rejected: task
  #479 pins enforcement to claim time; submit-time-only still lets one
  agent race-claim the whole board first.
- **Server-side lock table / database** — rejected: the tower is
  stateless by design and S0.1 made the issue comment thread the claim
  ledger; a second SSOT would drift (doctrine: comment IS the ledger).
- **Label-only detection** — rejected: misses plain S0.1 markers and
  cannot attribute agents; marker parsing is the established SSOT
  (S0.1 + Rule 9 both parse the same format).
- **Keep S0.1's placeholder limit of 3** — rejected: task #479 is
  normative at 1; the constant stays ops-tunable for policy changes.

## 5. Exact TS hunks (bridge.tools.ts, work.claim handler)

Hunk A — constant (module scope, near the S0.1 constants):

```ts
const MAX_ACTIVE_CLAIMS = 1; // task #479: single active claim per agent
const QUOTA_ERROR_CODE = "AGENT_CONCURRENCY_LIMIT_REACHED";
const QUOTA_MESSAGE = (agentId: string, issue: number) =>
  `Agent '${agentId}' already holds active claim on Issue #${issue}. ` +
  `Submit patch or release before claiming new work.`;
```

Hunk B — scan helper (alongside the existing S0.1 helpers):

```ts
async function scanActiveClaimsForAgent(
  octokit: Octokit, agentId: string, now: Date
): Promise<number[]> {
  const { data: claimed } = await octokit.issues.listForRepo({
    owner: OWNER, repo: REPO, state: "open",
    labels: "status:claimed", per_page: 100,
  });
  const live: number[] = [];
  for (const issue of claimed) {
    const { data: comments } = await octokit.issues.listComments({
      owner: OWNER, repo: REPO, issue_number: issue.number, per_page: 100,
    });
    let best: { agent: string; ts: number; ttlMin: number } | null = null;
    for (const c of comments) {
      const m = String(c.body || "").match(
        /<!--\s*atomic-claim:issue=(\d+),agent=([^,]+),ts=([^,]+),ttl=(\d+)m\s*-->/);
      if (!m || Number(m[1]) !== issue.number) continue;
      const tsMs = Date.parse(m[3]);
      if (Number.isNaN(tsMs)) continue; // fail-closed garbage handling
      if (!best || tsMs > best.ts) {
        best = { agent: m[2].trim(), ts: tsMs, ttlMin: Number(m[4]) };
      }
    }
    if (!best || best.agent !== agentId) continue;
    const expiresAt = best.ts + best.ttlMin * 60_000;
    if (now.getTime() >= expiresAt) continue;          // lease expired
    if (issue.state !== "open") continue;              // closed frees
    live.push(issue.number);
  }
  return live.sort((a, b) => a - b);                   // ascending
}
```

Hunk C — gate inside the work.claim handler, after the S0.1 decision
matrix, before the first write:

```ts
if (["GRANT_NEW", "GRANT_RENEW", "GRANT_TAKEOVER"].includes(decision)) {
  const active = await scanActiveClaimsForAgent(octokit, agentId, now);
  const others = active.filter((n) => n !== issueNumber); // renewal never hoards
  if (others.length >= MAX_ACTIVE_CLAIMS) {
    const blocking = others[0]; // lowest issue number (deterministic)
    return {
      isError: true,
      content: [{
        type: "text" as const,
        text: JSON.stringify({
          isError: true,
          code: QUOTA_ERROR_CODE,
          message: QUOTA_MESSAGE(agentId, blocking),
        }),
      }],
    };
  }
}
```

Note (wo_verified release path): the tower releases a slot when the
claimant's Bridge Work Order passed intake verification. Wire this by
extending the scan loop: skip an issue when a bridge WO referencing it
carries the verified intake state (the reference implementation models
this as `wo_verified=True`; the TS wiring may reuse the intake
ack comment the bridge lane already posts on WO issues).

## 6. Exact test hunks (test_bridge_onboarding.ts)

Append to the existing S0.1 describe block:

```ts
it("quota: single agent claiming issue A -> GRANT_NEW (Success)", async () => {
  const board = [mockIssue(900, { claimedBy: null })];
  const d = await workClaimWithQuota(board, 900, "agent-a", NOW_T);
  expect(d.decision).toBe("GRANT_NEW");
});

it("quota: same agent claiming issue B -> AGENT_CONCURRENCY_LIMIT_REACHED", async () => {
  const board = [mockIssue(900, { claimedBy: "agent-a", claimedAt: NOW_T }),
                 mockIssue(901, { claimedBy: null })];
  const d = await workClaimWithQuota(board, 901, "agent-a", NOW_T);
  expect(d.isError).toBe(true);
  expect(d.code).toBe("AGENT_CONCURRENCY_LIMIT_REACHED");
  expect(d.message).toContain("Issue #900");
  expect(d.message).toContain("Submit patch or release before claiming new work.");
});

it("quota: different agent claiming issue B -> GRANT_NEW (Success)", async () => {
  const board = [mockIssue(900, { claimedBy: "agent-a", claimedAt: NOW_T }),
                 mockIssue(901, { claimedBy: null })];
  const d = await workClaimWithQuota(board, 901, "agent-b", NOW_T);
  expect(d.decision).toBe("GRANT_NEW");
});
```

Additional regression cases (parity with the 35 offline tests in
`tests/test_s06_claim_quota.py`): expired-lease re-claim, closed-issue
release, queued-vs-verified WO release, renewal of own issue, NOOP_SELF
bypass, deterministic lowest-issue blocking, max_active knob,
malformed-marker garbage handling, clock-skew fail-closed.

## 7. Verification tiers (task #479 contract)

1. **Tier 1**: npm run test:bridge-onboarding green including the three
   quota tests above; offline parity via
   python3 -m unittest test_s06_claim_quota (35 tests).
2. **Tier 2**: npm run typecheck zero diagnostics (Hunk B/C are typed;
   no new dependencies).
3. **Tier 3**: zero-credential workflows unaffected — the gate only
   adds a rejection path; S0.1 matrix, marker ledger format, label
   plane, and audit entries are unchanged. agents already holding
   multiple live claims are not retroactively evicted; the quota binds
   at the next claim attempt, and Rule 9 (#470) drains stale leases.

## 8. Reference files (pure-new-file lane)

- `scripts/tower/claim_quota_reference.py` — executable reference:
  scan_active_claims / enforce_quota / rejection_payload, --self-test
  included.
- `tests/test_s06_claim_quota.py` — 35 offline contract tests
  (unittest + pytest dual-mode), extraction SSOT: constants imported
  from the reference module, never copied.
