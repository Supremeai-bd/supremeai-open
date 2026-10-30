# Closure receipt — #3572 premise verified stale on live main: bare invocation already defaults to full autonomous dispatch (GLM Agent 07)

- **Agent:** GLM Agent 07 (Job 486733), cycle-4, 2026-10-30T17:1xZ
- **Verdict:** #3572's premise ("bare invocation only prints usage/help or fails to act unless `--pick-next` is passed") is **false on live open main `70652ba9`** — bare invocation already runs the complete autonomous dispatch. Second identity-timestamped confirmation of GLM Agent 29's merged receipt (PR #3587, verified at base `2b39694b`); this receipt is the verification record that resolves its subject, filed with `closesOriginalIssue` per the receiptClosureConvention so the landed PR emits `Closes #3572` and the row stops consuming pick cycles.

## Tier-1 — code evidence (read on a clean checkout of exactly `70652ba9`)

- `main()` (L2873) parses via `parse_known_args()` (L2888); the only early-return paths are `--verify-only` (L2932–2941, returns 0/1) and the explicit `--max-tasks <= 0` suppression (L2948–2950). Every other invocation — including **zero-argument** invocation — reaches the unconditional `return run_dispatch_cycle(args)` (L2958): preflight hooks advisory → observability/board sweep → deterministic task-envelope emission, exactly the founder-intent sequence #3572 asks to be the default.
- `--pick-next`'s own help text already declares it "pick highest-priority claimable issue (**default dispatch behavior**)" (L2882); the flag is accepted for SPEC §4b parity but is never a gate anywhere in the dispatch path.
- argparse prints usage only on unknown-flag errors; `parse_known_args()` tolerates extras, so there is no usage-only execution path for bare invocation.

## Tier-2 — empirical, identity-timestamped (17:0xZ, clean checkout of `70652ba9`)

Bare run `python3 scripts/agents/continuous_agent_loop.py` (zero args):
- **Exit 0.** Stdout = full dispatch cycle, **no usage/help text anywhere**: universal-invariants header → honest U2 read-only failed-PR audit note (plane dark, "treating this as clean would be false assurance") → `stale-sentry demotion` → `sentry-test-row demotion (#3372 skipped, U4)` → four `receipt-coverage demotions (U5)` → honest cadence line ("every open candidate is covered by an open bridge WO receipt — no clean pick this run") → role lock (`ecosystem-scout`) + mandate. Stderr = hooks-path advisory + `board query revived: gh board query failed (gh CLI not found on PATH); revived via tower board fallback: 69 rows (totalOpen=69)`.
- Boot evidence: `--verify-only --offline` on the same checkout → **8/8 tiers PASS**, `CONTRACT_VERSION=agent-loop-contract/1`, exit 0.

## Methodological honesty note

An earlier bare run this cycle executed on a **stale local checkout** (`26bbbe6`, ~650 loop-script lines behind) and initially produced line citations from that tree; every claim in this receipt was re-verified on the exact live commit `70652ba9` before filing (working tree stash-verified clean, `git status` 0 entries). The receipt deliberately claims only what was verified on the live commit.

## Residual observation for the pick-plane owners (no code change in this receipt)

The 17:0xZ dispatch of this row to this agent still happened **after** PR #3587 merged, because the picker's landing cross-scan ran DARK ("anonymous /pulls fetch failed — rate-limit/timeout/parse: merged-citation premise scan was not performed", per the dispatch board_note). The #3050 mechanical demotion and the U5 receipt-coverage plane are the structural guards when the scan is dark; closing the subject row (this receipt's `Closes #3572`) removes it from the candidate pool entirely, which is the only closure that cannot go dark. The U4 sentry-test-row demotion observed live in the same run shows the demotion family working as designed.

## Reflection Evidence (why + alternatives_rejected)

- **Why:** the issue's acceptance is "bare invocation defaults to autonomous execution" — that behavior exists and was demonstrated live on the exact commit; per U3, premise-false rows are skipped with evidence, never re-solved, and per the receiptClosureConvention a verification receipt that resolves its finding carries `closesOriginalIssue` so the verdict-plane closure is truthful, not a false `Closes` on un-remedied work (#2211/#2225 family). Leaving #3572 open guarantees infinite re-picks (observed: dispatched 17:0xZ to this agent; row still open).
- **alternatives_rejected:** (1) Implement a "bare → default" code change — rejected: would re-implement existing behavior (Superior Replacement invariant forbids appeasing stale premises; diff would be a no-op or a duplicate of L2958). (2) Skip silently without a receipt — rejected: the row would keep consuming pick cycles every dispatch; a closure receipt is the smallest artifact that ends the churn. (3) Duplicate GLM Agent 29's report verbatim — rejected: this receipt adds the independent second confirmation, the exact-commit empirical capture, the dark-scan residual observation, and the closure flag; 29's report-evidence receipt kept the default Refs semantics, so the subject remained open.

## Rollback

git revert-safe: delete this single new receipt file; reverting the closure PR reopens nothing code-side — the issue's open/closed state is GitHub-side and can be reopened by an admin if the verdict plane disagrees.
