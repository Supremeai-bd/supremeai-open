# Audit receipt: `federation_anchors.py --verify-live` was structurally unusable from the agent lane (quota economics) — fixed with a zero-quota preflight and actionable 403 diagnostics (Refs #761 #3851 #3888, report-only)

- **Task ID:** `bridge-20261031-glm23-audit-anchor-quota-preflight`
- **Agent:** GLM Agent 23 (Job 486814, slot agent-23)
- **Lane:** auditor cycle — one code fix + tests + this receipt; no board claim held; no closure requested
- **Probed live:** 2026-10-31 ~23:23–23:31Z, zero-credential reads only

## U3 live verification (before → after, same window)

**Before (pre-fix, observed twice):** `--verify-live` fired 14 unauthenticated issue
queries serially; the shared egress IP's 60 req/h org budget was already drained by
the fleet, so runs ended with 4–5 `❌ Failed to query … HTTP Error 403: rate limit
exceeded` lines (8–9 partial successes wasted), exit 1, and a message carrying **zero
actionable information** (no remaining, no reset time, no token advice).

**After (post-fix, live):** the run performs **one zero-cost probe first**
(`GET /rate_limit` does not consume the core budget) and exits immediately:

```
❌ [verify-live] GitHub API quota too low to verify 14 anchors: remaining=0,
   resets 2026-10-31T00:20:59Z UTC. Re-run later or set GITHUB_TOKEN.
   (0 of 14 anchors verified — NOT a clean pass.)
```

exit 1, 0 issue queries fired. The reset instant is read from the probe response, so
an operator knows exactly when a re-run becomes possible.

## The audit arc (including the falsified hypothesis — method value)

1. **Falsified: "verify-live is fail-open".** The first observation (4×403 yet
   `LIVE_EXIT=0`) suggested a false-green guard. Re-measurement without a pipe
   (`python3 … > file; echo $?`) returned **1** — the script's fail-closed contract
   (`errors += 1` on every failure path, `return 1` when `errors > 0`) was always
   correct; the zero was `tail`'s exit code, not Python's. **Method note for the
   fleet: exit codes behind a pipe are the pipe's, not the program's — re-measure
   bare before filing a fail-open claim.** No false incident was filed.
2. **Confirmed: quota economics make the guard dead in the agent lane.** 14 serial
   unauthenticated queries cannot fit a shared-IP budget that other fleet members
   are also spending; the guard is permanently red from here — and a permanently
   red guard carries zero information (the #3851 stale-red/false-green family's
   core lesson).
3. **Fix (root cause, guard semantics unchanged):**
   - `_check_rate_limit()`: zero-quota pre-flight; probe failure degrades to the
     legacy path (pre-flight can never block a verification that had budget).
   - pre-flight `remaining < 14` → fail-fast exit 1 with remaining + reset + advice,
     explicitly labeled "NOT a clean pass" (no silent skip).
   - every 403 now renders `X-RateLimit-Remaining` / `X-RateLimit-Reset` and the
     `GITHUB_TOKEN` guidance via `_httperror_quota_hint()` (non-403 HTTP errors and
     the generic except path unchanged).
   - `errors > 0 → return 1` untouched: fail-closed preserved.

## Verification matrix (all local, all green)

- `tests/test_federation_anchors.py`: **10 passed + 12 subtests** — 6 pre-existing
  contract tests untouched, 4 new: preflight-blocks-low (exit 1, 0 issue calls),
  preflight-degrades-gracefully (probe down → normal verification still completes),
  403-diagnostic (remaining/reset/token strings in output), fail-closed-preserved
  (wrong anchor state still exit 1).
- `--self-test`: all 14 Anchor Hub contracts verified (no regression).
- `--verify-live`: live pre-flight path exercised against the real drained budget
  (quoted above) — the exact scenario the fix targets.

## Audit context: the constitution's topology claim itself is sound

The trigger for this audit was the freshly landed constitution commit fe02b999
("Golden 8-Satellite Topology"). Cross-checked `AGENTS.md` against the SSOT registry
it cites: the 8 active repos and 8 anchor numbers (#749/#750/#751/#754/#756/#760/
#761/#762) and the 6 retired hubs (#752/#753/#755/#757/#758/#759) match
`ACTIVE_ANCHOR_HUBS`/`RETIRED_ANCHOR_HUBS` **exactly**. Pre-fix `--verify-live` also
confirmed 10/14 anchors on the live board (6 active open, 4 retired closed) before
quota ran out — #749/#753/#754/#757 remain owner-verifiable after the budget resets.

## Honest limitations

- The fix has **not** had a 14/14 all-green live pass inside this window (quota
  remaining was 0; the reset instant falls after this cycle's end). The CI Guardian
  evaluating this PR runs on its own runner IP with an independent budget, so the
  landing pipeline will exercise the full path naturally; a maintainer re-run after
  `2026-10-31T00:20:59Z` closes the loop agent-side.
- A deeper economy fix — replacing the 14 serial single-issue queries with one
  list call — requires first verifying that the anchors share a stable label
  contract (their titles mix `[Anchor Hub]` and `[Federation Hub]`); that
  prerequisite is not agent-verifiable at remaining=0, so it is left as an
  owner-lane follow-up rather than bundled unverified (the R49-refresh verified-only
  discipline).
- `get_default_token()` remains the sole token source; no new credential surface
  was introduced.
