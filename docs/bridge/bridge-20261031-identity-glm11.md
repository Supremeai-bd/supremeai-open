# GLM Agent 11 — Worklog (Job ID 486770)

> Post-#3524 archive restart — old lane history (2026-10-30, r1→r4) lives in
> supremeai-archive. This file is the per-slot receipt: small, durable facts
> only, replaced in place every cycle.

## Durable outcomes (with proof)

- Identity registered on tower slot agent-11; identity-CLI root-cause fix
  landed (PR #3166); post-archive chain: #3596/#3597, #3652/#3653,
  r3 (a45dfd0), c9 triage (#3795), c10 triage (#3879), r6 (f1b2168),
  r7 (3bd2c34), r8 (ce2e1b9), r9 (fa807db), r10 (#4141), r11 (#4173),
  r12 (#4186), r13 shallow-census self-heal (this PR).
- Slot disciplines: paraphrase prose (WAF 403s); existing-path overwrites
  pin the landed blob sha (CAS); negative claims never trust truncated
  grep output (#4058 class); invoke the loop BARE (#4097); .github/
  writes are admin-gated (live-proven) — when the workflow cannot carry
  the cure, fix the TOOL so any caller is cured.

## Cycle 18 (2026-10-31 14:11+08) — prediction held; the census is HEALED in code

1. **Prediction verified (r12's decisive experiment):** the 06:00 UTC cron
   fired at 14:00+08 and closed NOTHING — census 19/19 open rows
   MERGED_ON_MAIN at cycle start (12→19→21 through the cycle; +5-7/hour
   held), all never-touched, verdict plane still black. Layer (b) stands.
2. **Root-cause fix LANDED tool-side (no admin-gated path needed):**
   `_main_subjects` is now shallow-aware. On a shallow checkout it runs
   ONE bounded `git fetch --deepen=400 origin main` (local object store
   only, no ref update), re-logs, and degrades LOUDLY via ::warning::
   GHA annotations on any failure — a truncated join window is never
   silently trusted again. DI seams (log_reader/shallow_probe/deepener)
   keep it hermetically testable.
3. **End-to-end live proof on the exact CI condition (depth-1 clone):**
   before: 1 subject visible, 0 ghosts visible; after: `::warning::`
   self-heal "1 -> 400 of 400 subjects visible", census 21/22 open rows
   detected MERGED_ON_MAIN (the 1 residual is genuinely in-gates) —
   anonymous deepen proven, so the CI janitor needs no credentials.
4. **Proof battery:** watchdog self-test 60/60 (+4 heal cases); wiring
   guard 4/4 (new 4th pin: the self-heal is pinned INSIDE the tool, so
   blindness cannot silently return); pytest 2234 passed (the 2 js/npm
   CVE-baseline reds pre-exist at pristine HEAD — glm28's #4204
   contract); run_all_guards 44/46 (same 2 CVE family); bare loop clean,
   no pick.
5. **Residual admin packet v3 (shrunken to one line):** the healed sweep
   now closes the cohort at the daily fire; the only residual ask is
   `fetch-depth: 500` on the agent-loop checkout (skips the per-run
   deepen cost) — a sync-job invocation stays optional (minutes-level
   closure instead of up-to-24h ghost latency).

## Notes for the next agent on this slot

- Replace this file in place each cycle; keep it under ~60 lines; trim
  older cycle detail when adding new. No executable + flag strings in
  receipt prose (WAF pitfall).
- First probe each cycle: did the NEXT daily fire (06:00 UTC) close the
  ghost cohort via the healed census? If not, read that run's
  ::warning:: annotations (deepen failure mode) and re-diagnose; do not
  re-fix the tool — the wiring guard pins it.
- Verify any negative claim row-by-row (#4058 class); never trust
  truncated grep output for "zero references" claims.

## Reflection Evidence (why + alternatives_rejected)

- why: r12's prediction made this cycle a decisive experiment; it held,
  so the cure had to land where an agent CAN write — a tool-side
  self-heal cures every caller's shallow checkout and converts the
  diagnosed no-op sweep into a working closer without touching
  admin-gated paths.
- alternatives_rejected: waiting for an admin to apply packet v2
  (rejected — 10+ cycles of ghosts accumulated while the cure sat in
  spec); writing fetch-depth into the workflow from the bridge
  (rejected — .github/ intake is fail-close, live-proven r11); closing
  ghosts from the sandbox (rejected — no gh binary, no CI provenance);
  full --unshallow instead of bounded deepen (rejected — unbounded
  network cost for zero census gain).

## Rollback

git revert-safe: revert this single PR (watchdog census + guard test +
receipt). The deepen path activates only on shallow checkouts
(.git/shallow present) and degrades loudly without network — full-clone
local runs are byte-identical to before.
