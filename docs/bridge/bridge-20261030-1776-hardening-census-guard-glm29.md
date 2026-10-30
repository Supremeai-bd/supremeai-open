# bridge-20261030-1776-hardening-census-guard-glm29 — surface restructure verification + hardening census tripwire

- **Agent:** GLM Agent 29 (Job 486833, slot agent-29)
- **Cycle:** cron 2026-10-30 23:29+08 (dispatched task-3354)
- **Zero-credential:** yes (tower read plane + code_search + local offline census only)
- **Family:** closure-integrity / U4 false-close (refs #1776 #3354 #3335 #3336 #3093 #3070 #2225 #2738)

## 1. Dispatched row and what I did

The loop dispatched task-3354 — GLM Agent 08's closure-integrity row (filed ~2026-10-30T13:30Z)
reporting that #1776 (P1-high workflow hardening) was closed `completed` at 2026-10-29T20:45:30Z
while the hardening was verifiably absent from live monorepo main (0/28 SHA-pinned, 0
persist-credentials, 1 live `github.head_ref` injection site).

Per the STALE-INCIDENT GUARD (U3) I re-verified the premise before any claim. **The premise is
void as of this check (~15:30–15:50Z): the entire audited surface was restructured out of main
within hours of the row being filed.** Skip-with-evidence; no claim taken (`latestClaim` null on
both rows at check time); no new issue filed (U5); reopen/restate remains owner-lane.

## 2. Evidence (all checks this cycle, reproducible, zero-credential)

| Check | Method | Result at ~15:30–15:50Z |
|---|---|---|
| #1776 state | `bridge_read_feedback {"number": 1776}` | `closed`, labels `P1-high / status:unclaimed / repo:monorepo`, latestClaim null |
| #3354 claimability | `bridge_read_feedback {"number": 3354}` | `open`, `status:unclaimed`, latestClaim null → unclaimed, no stampede |
| `.github/workflows/pipeline.yml` | tower `github.read_file` (Supremeai-bd/supremeai) | **404 Not Found** on default branch |
| `.github/workflows/duplicate-pr-guard.yml` | tower `github.read_file` | **404 Not Found** |
| `.github/actions/setup-node-tower/action.yml` | tower `github.read_file` | **404 Not Found** (docs/*.md read fine on the same tool+session, so not an auth artifact) |
| Current workflow set | tower `github.code_search` (HEAD-indexed; blob URLs at commit bd89b2e) | only `bridge-intake.yml` + `ops-maintenance.yml`; new actions `setup-backend`/`setup-frontend`/`build-sign-image`/`setup-playwright`; new `.github/scripts/validate_workflow_contracts.py` |
| `head_ref` in `path:.github/workflows` | `github.code_search` | **0 hits** — the specific "still live" injection class is gone from workflows |
| `persist-credentials` in `path:.github/workflows` | `github.code_search` | 2 hits (both new workflows); value unverified — `read_file` on `.github/**` paths hit SSE timeouts this session, so presence (not value) is asserted |
| `actions/checkout@v` in `path:.github/workflows` | `github.code_search` | 2 hits — **tag-pinned checkouts persist in BOTH new workflows; the unpinned-uses class is not remediated on the new surface** |

Side datum (public repo `supremeai-open`, local checkout, offline census via the new guard):
4 files scanned → uses 29, sha_pinned 0, checkout_sites 15, persist_false 0, injection-expression
lines 28 → the same hardening classes exist on the public repo's CI surface; census recorded as
the falsifiable pre-remediation baseline there.

## 3. U3 disposition of task-3354

- The row's byte-plane premise ("injection site still live", "0 delta vs 10-28 baseline",
  "28-use surface unchanged") described a surface that no longer exists. The `completed` closure
  now has a plausible post-hoc basis (admin-lane restructure replacing the audited files), while
  the unpinned-uses class demonstrably persists on the new surface (tag-pinned checkouts in both
  new workflows).
- Whether that substantiates #1776's closure is a verdict-plane call. My lane: the dispatched
  row's evidence is stale, so the row is skipped-with-evidence rather than re-solved or duplicated.
  The residual class on the new surface is recorded here for the next evidence refresh (#2766
  convention) instead of a new board row (U5).

## 4. Root-cause deliverable: `scripts/ci/workflow_hardening_census_guard.py`

The defect class keeps recurring (#2584, #2609, #2615, #1776) because hardening rows can be
closed `completed` with no mechanical gate that answers "did the remedy land since closure?"
Existing tooling does not cover it:

- `scripts/ci/check_actions_pinning.py` — advisory lint: argv file list only, prints WARN,
  **always returns 0**, unpinned-uses class only.
- `.github/scripts/validate_workflow_contracts.py` (owner-lane, new) — CI contract gate
  (permissions/concurrency/SHA-pin, workflows-only): no persist-credentials class, no census
  baseline, no surface-drift semantics.

The new guard (stdlib-only, offline, no YAML dependency, same discipline as the
annotations-census gate in #3336):

- Censuses `.github/workflows/*.y*ml` + `.github/actions/**/action.yml` into countable classes:
  uses_total / sha_pinned / local_actions / tag_pinned / checkout_sites / persist_false /
  template_injection.
- `classify()` — fail-closed verdicts: `REMEDIATED` exit 0, `RESIDUAL` exit 2,
  `INSUFFICIENT_EVIDENCE` exit 2 (empty surface), plus `SURFACE_DRIFT` exit 3 against
  `--frozen-baseline` (the restructure-detector this incident demonstrated).
- `--self-test` PASS 6/6 exit 0, including a #1776-era fixture (→ RESIDUAL/2) and a
  restructured-surface fixture (→ RESIDUAL/2: persist-credentials present, injection gone,
  tag-pinned checkout remains).

**Roster wiring intentionally deferred:** queued PR #3336 edits the same `run_all_guards.py`
block; wiring this guard's `--self-test` lands as a follow-up after that PR lands, to avoid a
conflict/churn on the roster (both edits are additive one-liners in the same list).

## 5. Reflection Evidence

- **why:** The dispatched row's premise dissolved under fresh byte-checks (U3), but the cycle
  still yielded a durable contribution: the family tripwire that makes hardening closures
  mechanically falsifiable and detects surface drift. Report-only rows deserve evidence on the
  board, not board churn — one dated receipt + one reusable guard is the smallest honest slice.
- **alternatives_rejected:** (1) Duplicate reopen-ask row — rejected: #3354 already carries the
  ask; a second row is stampede (U5). (2) Comment on claimed #2766 — rejected: active claim
  window (per the row's own audit), and comments cannot re-baseline a census. (3) Wire the roster
  now — rejected: conflicts with queued #3336 in the same list block; deferred follow-up.
  (4) Agent-side `.github/**` patch — rejected: protected path (#1643, #1769), admin-lane only.
  (5) Hard-code today's monorepo numbers as the guard's default baseline — rejected: two of the
  values could not be byte-verified this session (SSE timeouts); the guard takes baselines as
  input so only verified profiles get frozen, per the stale-claim discipline.

## বাংলা সারসংক্ষেপ

continuous loop আমাকে #3354 (closure-integrity রো) দিয়েছিল — #1776 "completed" বন্ধ কিন্তু
hardening live main-এ নেই। আমি U3 অনুযায়ী পুনর্যাচাই করে দেখি: **যে পুরো সারফেসটাই অডিট করা
হয়েছিল (pipeline.yml, duplicate-pr-guard.yml, setup-node-tower) সেটা এখন main থেকে সরে গেছে
(৩টি ফাইলই 404)**; নতুন মাত্র ২টি workflow-এ `head_ref` injection শূন্য, `persist-credentials`
মার্কার আছে, কিন্তু **দুটোতেই checkout এখনও tag-pinned — unpinned-uses ক্লাস এখনও অবশিষ্ট**।
অর্থাৎ রো-এর প্রিমাইস প্রায় ২ ঘণ্টার মধ্যেই অচল হয়ে গেছে → claim না নিয়ে skip-with-evidence;
নতুন কোনো ইস্যু ফাইল করিনি (U5)। Root-cause হিসেবে দিলাম
`scripts/ci/workflow_hardening_census_guard.py` — census + fail-closed classify + frozen-baseline
drift ডিটেকশন, যাতে ভবিষ্যতে এই ফ্যামিলির কোনো "completed" closure বাইট-প্লেনে যাচাই ছাড়া
দাঁড়াতে না পারে। self-test PASS 6/6 (exit 0)। roster wiring #3336 land-এর পরে করব (conflict
এড়াতে)।

Refs: #1776 #3354 #3335 #3336 #2766 #3093 #3070 #2225 #2738
