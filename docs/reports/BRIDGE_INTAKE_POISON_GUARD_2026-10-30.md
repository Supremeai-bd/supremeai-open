# Bridge Intake Poison-Order Resilience Guards (2026-10-30)

**Part of #2792** — implements RCA guards 1, 2, amp-3 and 4 from
`docs/reports/INTAKE_RCA_2792_2026-10-30.md`, all inside
`scripts/bridge/bridge_intake.py`. The issue stays open: the RCA calls the
runtime copy "private-only", so operator confirmation that the private
runtime picks up this canonical public source (or an admin-side pull) remains
the closure step, plus the optional alerting guard (.github/, admin-owned).

## Live state at claim time (U3 verified)

`github.workflow_runs` on the private repo: the Bridge Intake gate **recovered
— run 40961066544 at 2026-10-29T21:50:06Z = success**, after the #327-#329
failure streak (02:28Z / 10:05Z / 16:56Z). The outage self-cleared, but the
RCA-named mechanism (zero-diff order → commit-less branch → POST /pulls 422 →
intake exit-2 → sync/reporting dead) is structural: the next stale order
re-arms it. This patch removes the mechanism.

## Guards implemented (all fail-honest, per-order)

1. **Zero-diff reject (root cause)** — after `fetch_patch`, before caps:
   `if not files or not diff.strip(): reject("zero-diff patch branch — content
   already merged elsewhere or empty branch; nothing effective to land
   (#2792)")`. The poison order now leaves the queue with an honest terminal
   label instead of arming the 422 chain.
2. **Effective-landing belt** — `_has_effective_landing(has_staged,
   already_applied)` checked after `git add`/staging, BEFORE branch push and
   POST /pulls. Fresh no-op (False/False) → clean reject; E4-resume with the
   commit already on the land branch (False/True) still proceeds to
   push+PR exactly as before.
3. **`gh_ok` errors[] detail (amp-3)** — 422 responses now carry GitHub's
   `errors[]` sub-cause ("No commits between main and …") into the BridgeError
   message, so the verdict plane shows *why*, not just "Validation Failed".
4. **Sync always runs (amp-2)** — `main()` no longer skips `cmd_sync` when
   intake returns non-zero; both rc values print separately and the process
   returns the max. One bad order can no longer kill landed/rejected
   reporting for a whole streak (the #327-#329 amplifier).

## Evidence

- `tests/test_bridge_intake_poison_guard.py` — 10 offline tests: 3 wiring pins
  (guard-1 after size cap and before guard-2; guard-2 before POST /pulls;
  no skip-sync in `main()`), 4 truth-table cases for
  `_has_effective_landing` (incl. the E4-resume path), 3 `gh_ok` unit tests
  (errors[] appended, absent-errors unchanged, 201 passthrough).
- Battery on this tree: poison-guard + split-brain suites 23/23;
  `-k "intake or bridge or landing"` 82 passed, 3 skipped, 0 new failures;
  `continuous_agent_loop.py --verify-only` 8/8 PASS.

## Follow-ups (documented, not implemented here)

- Operator: confirm the private runtime picks up this canonical public source
  (or pull manually); then #2792 can close on admin review.
- Optional fail-loud alerting on 2+ consecutive intake failures —
  `.github/workflows` is admin-owned.
- `landing_truth_probe` extension to the zero-diff path (truth-restore
  LANDED instead of reject) — polish, needs its own probe-design pass.
