# S0.1 — Atomic Claim Tool (work.claim) — Full Specification

Task issue: #456 · Seq S0.1 of the Simplification Roadmap · P0-critical
Author: Z.ai Code autonomous contributor (session web-26454b1b, zero-credential bridge lane)
Status: DELIVERED — spec + reference implementation + executable contract tests

---

## 1. Problem — the claim wall, proven in battle

Claiming a task issue today requires up to four separate planes, and an
autonomous agent without a credential can perform none of them:

| Plane | Mechanism | Who can do it |
|---|---|---|
| Label | maintainer adds status:claimed to the task issue | operator token only |
| Comment | comment body contains the atomic-claim marker | operator token only |
| Branch | webhook creates the work branch on WO intake | bridge (automatic) |
| TTL | stale claims must expire or be renewed | nobody (manual today) |

Incident record (2026-10-16/17): WO #435 (parity-399, 552-line verifier) was
rejected by claim-guard purely because issue #399 carried no claim. The work
itself was valuable; it was rescued only because a maintainer manually added
the label and reopened the WO. During the same window, 20 open task issues
carried zero claims while the contributing fleet idled. The wall, not the
work, was the bottleneck.

Design consequence (roadmap principle: make the correct path the only path):
claiming must be ONE call, self-serve, zero-credential, and atomic — or
agents will keep losing hours of landed-quality work to process friction.

## 2. Solution — one tool, one transaction

Add a single Control Tower MCP tool:

    work.claim(issueNumber: integer, agentId?: string) -> ClaimResult

agentId defaults to the authenticated caller identity supplied by the tower.
When invoked, the tower (server-side GitHub App, scoped to issues:write on
this repository) performs ALL of the following as one logical transaction:

1. Validates the target issue (exists, state open, is a task issue).
2. Adds the status:claimed label to the issue.
3. Posts exactly one marker comment on the issue:
   <!-- atomic-claim:issue=456,agent=AGENT_ID,ts=2026-10-17T02:40:52Z,ttl=30m -->
4. Removes the status:unclaimed label if present.
5. Records the claim in the tower audit log (who, what, when, TTL).

All-or-nothing: if step 2 fails, steps 3-5 are not attempted; if step 3
fails, step 2 is rolled back (label removed). A partial claim is worse than
no claim because claim-guard accepts either plane and a mismatched pair
hides state.

## 3. Decision matrix (normative)

| Situation on target issue | Result | HTTP-level effect |
|---|---|---|
| no claim | GRANT_NEW | label added + marker comment posted |
| claim by SAME agent, unexpired | NOOP_SELF | 200, nothing written (idempotent) |
| claim by SAME agent, expired | GRANT_RENEW | marker comment re-posted, label ensured |
| claim by OTHER agent, unexpired | CONFLICT_OTHER | error, nothing written |
| claim by OTHER agent, expired | GRANT_TAKEOVER | re-claim granted, expiry noted |
| issue closed or missing | ISSUE_CLOSED / ISSUE_NOT_FOUND | error, nothing written |

The decision matrix is implemented, executable, and tested in
scripts/tower/work_claim_reference.py (reference implementation, pure
functions, zero network in unit mode).

## 4. TTL and self-healing

- Default TTL: 30 minutes, sourced from AUTONOMOUS_TRANSIT_PIPELINE.md
  (stale claim expiry). Single source of truth: the constant TTL_MINUTES in
  the reference implementation; tests import it, never copy it.
- Expiry is derived from the ts field inside the marker comment — no tower
  database required. The comment IS the ledger (failover-as-data principle).
- Renewal: the claimer calls work.claim again before expiry (NOOP_SELF).
  A heartbeat-style renewal loop fits inside a normal implementation cycle.
- A periodic tower sweeper (optional, Phase S2) may demote expired claims:
  swap status:claimed for status:unclaimed and append a ttl-expired note.
  Even without the sweeper, expiry is enforced at claim time via the
  decision matrix above.

## 5. Error contract

| Code | Meaning | Retry advice |
|---|---|---|
| CLAIM_CONFLICT_OTHER | live claim held by another agent | call work.next, pick another task |
| ISSUE_NOT_FOUND | issue number invalid | fix the argument |
| ISSUE_CLOSED | issue already resolved | pick another task |
| CLAIM_TAKENOVER | your expired claim was taken over | re-run work.next |
| RATE_LIMITED | agent holds more than MAX_ACTIVE_CLAIMS | finish or release one first |

Every error is terminal-safe: claim-guard remains fail-closed for all
parties. The tool can only ADD claims correctly; it can never fabricate a
passing gate for an unclaimed issue.

## 6. Guard integration (why this kills the wall without weakening it)

claim-guard (pipeline.yml @ 2f05e1e) accepts a claim via the label plane OR
the comment plane, and fails closed when lookup fails. work.claim writes
BOTH planes atomically, so:

- zero-credential agents gain a real claim channel (the tower holds the App
  credential; agents never see it — the one-key principle);
- the guard loses nothing: its accepted evidence is exactly what the tool
  writes, and expiry keeps claims honest;
- the maintainer rescue pattern (proven on #435) becomes unnecessary except
  for genuine overrides (guard-exempt label stays maintainer-only).

## 7. Security and abuse limits

- The GitHub App credential never leaves the tower. Agents authenticate to
  the tower exactly as they do today for bridge_submit_patch (no new keys —
  the one-key principle: SUPREMEAI_API_KEY).
- Per-agent cap: MAX_ACTIVE_CLAIMS (default 3) concurrent live claims.
- Audit trail: every claim/renew/takeover is appended to the tower audit
  log with issue, agent, ts, decision — greppable forensics for maintainers.
- The marker comment is the only trusted comment plane: parsers must match
  the exact marker prefix and must only unescape, never strip, HTML comment
  tags (doctrine x).

## 8. Acceptance criteria (all machine-checked)

1. work.claim appears in the tower tool catalog with arguments
   issueNumber (integer, required) and agentId (string, optional).
2. Claiming an unclaimed issue produces BOTH the label and the marker
   comment within one invocation.
3. Re-claim by the same agent inside TTL is a 200 no-op (idempotent).
4. Re-claim by a different agent inside TTL fails with CLAIM_CONFLICT_OTHER.
5. Claim past TTL is takeable by any agent (GRANT_TAKEOVER).
6. All five error codes are reachable and documented.
7. Unit tests of the decision matrix pass with zero network access.
8. Live-contract tests pass against the tower once the tool lands
   (skip-until-landed pattern until then).

Criteria 1-2 are verified by tests/test_s01_atomic_claim_contract.py in
contract mode; criteria 3-7 run today in unit mode against the reference
implementation; criterion 8 activates on landing.

## 9. Migration path (roadmap alignment)

- S0.1 (this spec): work.claim — one call, atomic, TTL-aware.
- S0.3: work.next() — computed actionable queue; its claimability filter is
  exactly the decision matrix in section 3 (a claimed-and-live issue is not
  actionable; an expired claim IS).
- S0.4: tower tool consolidation 9 -> 5; work.claim survives as one of the
  five because it is the front door of the entire pipeline.

## 10. References

- Task issue #456 (S0.1 contract) · roadmap siblings #457 #458 #459
- Claim-guard: .github/workflows/pipeline.yml @ 2f05e1e
- Incident: WO #435 rejection + maintainer rescue (2026-10-16 20:59-21:18Z)
- Transit doctrine: AUTONOMOUS_TRANSIT_PIPELINE.md (30-min claim TTL)
- Deliverables: scripts/tower/work_claim_reference.py (reference impl),
  tests/test_s01_atomic_claim_contract.py (dual-mode suite)
