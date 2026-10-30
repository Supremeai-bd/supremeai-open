# R3527 — implicit persist-credentials machine-tracking: workflow_hardening_census_guard r2

- **Agent:** GLM Agent 10 (Job ID 486755)
- **Cycle:** cron 2026-10-31 00:10+08
- **Lane:** scripts-only guard extension (cohesive slice: 1 script r2 + this report; zero `.github/` edits, zero closure ask)
- **Refs:** #3527 (audit finding, `status:unclaimed` at dispatch), #3518 (r1 guard landing), #1776 (hardening family)

## What this cycle shipped

#3527's ranked fix #2: extend `scripts/ci/workflow_hardening_census_guard.py` with the
`implicit_persist_true` class + frozen-baseline tracking, so the 18 implicitly-persisting
checkout sites the filer counted by hand in `ops-maintenance.yml` become a machine-tracked
number (Zero-Recurrence tripwire). r1 could only count explicit `persist-credentials: false`
occurrences with a global regex — the dangerous default (`actions/checkout` persists the job
GITHUB_TOKEN into runner git config unless told otherwise) was invisible as a first-class
countable class.

## Guard changes (r2, full-file replace of the r1 script)

1. **`resolve_checkouts()` — per-checkout credential-posture resolution** (with-block-aware
   line scan, stdlib-only, offline): for each `uses:` step invoking actions/checkout, the
   step's own body is scanned for a `persist-credentials` key. Step base column resolves the
   enclosing list-item dash (including the `- name:` step-opening shape, where the dash is on
   a different line than `uses:`). Values classify fail-closed:
   `false` → persisted-off; `true` → `persist_true_explicit`; any expression or non-boolean
   → `persist_dynamic` (counted as NOT persisted); **no key → `implicit_persist_true`**.
2. **New profile keys:** `persist_true_explicit`, `persist_dynamic`, `implicit_persist_true`
   (`persist_false` keeps its name but now means checkout-sites-persisted-off — r1's
   non-checkout `persist-credentials: false` sites no longer pollute the count).
3. **`--emit-baseline PATH`** — one-command frozen-baseline generation for the owner lane
   (`--frozen-baseline` drift mode already exits 3; every new profile key participates in the
   drift diff automatically).
4. **Self-test grew r1's 6 cases to 9:** r2-mixed-postures (5 checkouts: 1 explicit-false with
   comment suffix, 1 explicit-true, 1 `${{ matrix.persist }}` dynamic, 2 implicit — including
   a bare `- uses:` step and a fetch-depth-only step), r2-step-body-boundary (a following
   step's `persist-credentials: false` must not leak into the previous checkout's posture),
   r2-all-off (2 persisted-off checkouts classify REMEDIATED on the persist axis).

## Verification (this cycle, reproducible, zero-credential)

| Check | Method | Result |
|---|---|---|
| Self-test | `python3 scripts/ci/workflow_hardening_census_guard.py --self-test` | **PASS 9/9** (0 failures) |
| Ground-truth vs filer's hand count | tower `github.read_file` fetched the live 108,324 B `supremeai/.github/workflows/ops-maintenance.yml` (2,237 lines, sha `150cd37d`); ran the r2 `census_text()` on the exact bytes | `checkout_sites=23, persist_false=5, persist_true_explicit=0, persist_dynamic=0, implicit_persist_true=18` — **exactly** the filer's 23/5/18 (their 5 explicit-false line numbers L517/1593/1701/1738/1782 all land inside checkout with-blocks; re-verified line-by-line) |
| Surface verdict on the live file | `classify(profile, 1)` | RESIDUAL/2 (tag_pinned 47, unpersisted 18) — consistent with the finding's honest P3-low framing |
| Two parser bugs caught by the self-test before landing | dev-loop | (a) step base column wrong when the dash is on `- name:`; (b) value regex anchored `$`, breaking on comment suffixes and `${{ }}` — both now fixed and pinned by cases 7–8 |

## Owner-lane actions that remain open (from #3527 — not my lane)

1. Add explicit `persist-credentials: false` to the 18 unpinned checkout sites in
   `supremeai/.github/workflows/ops-maintenance.yml` (write-perms + PAT-env jobs first).
2. After that lands, re-baseline once: `python3 scripts/ci/workflow_hardening_census_guard.py
   --check --root . --emit-baseline <dated-baseline>.json` — from then on any new
   implicitly-persisting checkout is a `SURFACE_DRIFT` (exit 3).
3. Optional: invert PAT fallback order where ephemeral scopes suffice.

Note for the operator: r2's profile-key schema change (`persist_false` semantics narrowed,
three keys added) makes any r1-era frozen baseline drift on the first r2 run — a one-time,
expected `SURFACE_DRIFT`; regenerate the baseline with dated evidence as above.

## Honest envelope

Report + script lane; no claim on #3527 taken beyond the loop claim lease
(`contributor-agent`, idempotent), no closure requested (`Refs #3527`) — the issue stays open
until the owner-lane edits land. Zero `.github/` writes; zero credentials touched; the 108 KB
fixture was fetched read-only and never committed.
