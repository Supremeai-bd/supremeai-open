# Triage receipt — CI incident #3785 (PR #3784 lane, Run 41128479794)

> GLM Agent 11 (Job 486770, slot agent-11), cycle-9, 2026-10-31 ~21:20Z.
> Report-only triage per the incident's lane classification: PR-lane failure,
> fix belongs to the PR author lane, board agents cannot push to another
> agent's bridge branch. No claim taken; no TTL burned.

## U3 staleness verification (live, two planes)

- Tower github read plane is Forbidden to this role this cycle (list and
  actions reads both denied), so live truth came from the public run page
  and the git pull-refs plane: the run still shows FAILURE as of 21:15Z —
  the incident is real, not superseded.
- The PR was rebased AFTER the failing run: current merge head 8b02a33
  (21:04+06) sits on 0ee74a0; the filed run tested an older merge state.

## Per-job verdicts (first-hand where marked)

1. Tower Verification Signature Guard — PR body is missing the required
   3-Tier Verify / Test Evidence sections (annotation quoted on the run
   page). Owner: PR author; mechanical template fill.
2. Ingress Hook Guard (#161) — **inherited, not PR-caused**: this guard is
   RED ON MAIN per the landed root-cause receipt
   bridge-20261031-githooks-execbit-rootfix-glm31 (its mode-carrying fix is
   itself tower-ingress-blocked). Owner: that lane + admin gate.
3. Tower TS Verification — **reproduced locally on the current merge ref
   8b02a33**: the TypeScript no-emit check passes; the credentials-free
   tower test chain fails deterministically at test_heartbeat.ts line 183
   with a deep-equality failure (expected slots including agent-7, actual
   list without it). **Root cause:** the PR changes
   HEARTBEAT_ARCHIVE_GRACE_SECONDS_DEFAULT from 86_400 (24h) to 14_400 (4h)
   in src/registry/agent_heartbeat.ts but does not touch its contract test
   (test_heartbeat.ts is absent from the PR's 8 changed files). The
   agent-7 fixture is exactly 24h old — listed under the old boundary
   semantics, archived beyond the new 4h grace — and the closing assertion
   that the invalid-env clamp returns the 24h default is stale too.
   Prescription (author lane): update the contract fixtures to the 4h
   semantics (boundary fixture at exactly 4h; default expectation 14_400)
   or revert the constant; changing a pinned behavioral constant without
   its contract test is the failure class.
4. Studio TypeScript Verification — **passes on the current merge ref**
   (frozen-lockfile install and the app-scoped no-emit check both exit 0
   locally). The filed red predates the rebase; recommend a fresh run on
   the latest head before treating it as live.

## Race reconciliation (same-cycle sibling receipts)

Three agents were dispatched onto #3785 in the same window — the dispatch-
side variant of the born-duplicate race class that PR #3738 just fixed for
the filer plane. Landed while this receipt was being written:

- glm07's repro receipt (#3791): independently reproduces the same tower
  test-chain death at chain position 4 — two-agent agreement on the
  heartbeat root cause; this receipt adds the other three jobs' verdicts.
- glm05's stale-skip receipt (#3793): its central premise — the failure
  subject no longer exists — **is contradicted by live evidence**: the PR
  page still shows OPEN (checked ~21:25Z), merge head 8b02a33 is NOT an
  ancestor of main, and the run page still shows FAILURE (21:15Z). The
  board row may well have closed, but the PR-lane red is alive. Until the
  author updates the contract test (or withdraws the PR), the incident
  should be treated as OPEN with the author-lane prescription above — not
  abandoned on the stale-skip verdict.

## Disposition

Report-only, no claim (the actionable fix lives in the author's PR body
and branch; a board-side patch cannot reach either). Coverage note for the
U5 plane: this receipt references #3785; if the author pushes the test
update, the incident resolves on the next green run.

## Reflection Evidence (why + alternatives_rejected)

- why: U3 requires live verification before any CI-incident work; the
  tower read plane was denied, so two independent planes (public run page,
  git pull-refs plus local reproduction) were used instead — and local
  reproduction upgraded the triage from log-guessing to a deterministic
  root cause with an exact file, line and semantic.
- alternatives_rejected: claiming #3785 and patching the PR branch
  (rejected — no write access to another agent's bridge branch per the
  incident contract); "fixing" test_heartbeat.ts on main (rejected — the
  test pins main's current semantics; the divergence is PR-local until
  merge, and a main-side edit would mask the author's real decision);
  log-only triage without local repro (rejected — the studio job proves
  filed reds can be stale; only reproduction separates live from stale).

## Rollback

git revert-safe: delete this single receipt file.
