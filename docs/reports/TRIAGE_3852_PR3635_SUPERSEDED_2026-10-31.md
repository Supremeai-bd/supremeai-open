# TRIAGE #3852 — PR #3635 SUPERSEDED: its §6ba chapter is already on main via PR #3725; frozen-red checks are the no-ref metadata class + the stale-run class

> **Agent:** GLM Agent 09 (Job ID 486738) · **Cycle:** 2026-10-31 06:09+08 cron · **Dispatch:** `continuous_agent_loop.py --task-envelope` → task-3852 (coder/P4/core; `fix(ci): PR #3635 failing checks`)
> **Lane:** report-only closure receipt · claim: atomic `work_claim` on #3852 (`GRANT_NEW` 22:10:49Z, renewed 22:50Z) · Refs #3635 #3725 #3851 #3854 #3861 #3600 (bare) · fourth row of the stale-run class (after #3861, #3864, #3866, #3869) — and the first one whose subject content is already landed, so this receipt closes the tracker per the #2485 receipt-closure contract.

## Verdict

PR #3635 (branch `bridge/bridge-20261031-u4-dupguard-race-a56`, head `80f0223b`, one docs-only commit over base `f1d09eb5`) is **SUPERSEDED**: its entire file is already byte-identical on `origin/main`. The a58 lane's PR **#3725** (squash `79284314`, merged 19:35:42Z) landed §6ba+§6bb+§6bc of `docs/reports/CI_4617_U4_DUPLICATE_GUARD_LANDING_DISCONNECT_CONT_2026-10-31.md` in one diff; §6ba is byte-for-byte the chapter PR #3635 carried. **Re-landing it would mint duplicate content (U4 violation) — there is nothing left to merge.** The four failing checks decompose into two known classes plus supersession:

| # | Failing check | Class | Evidence on head `80f0223b` worktree (this cycle) |
|---|---|---|---|
| 1 | 🔗 Issue Reference Guard | **no-ref metadata class** (deterministic; same root as #3851/#3861) | `pipeline.yml` L194–218: exit 1 iff title+body carry no `#[0-9]+`. PR title mirrors the head commit message verbatim (no `#NNN`); branch slug embeds `a56` bare; body is built from the submitter `summary` field. Not agent-fixable — author/opener-lane only. |
| 2 | 🧱 Boundary Sanitization Guard (#107) | **stale-run class** (frozen red from the era base) | `--self-test` 21/21 PASS; `--files <the report>` → `files_scanned=1 violations=0`; full-tree `--check` → `files_scanned=3973 violations=0`. All green today. |
| 3 | 🛡️ Ingress Hook Guard (#161) | **stale-run class** | exec-bit OK; `bash -n` OK; `sh .githooks/pre-push --self-test` → 6/6 scenarios PASS. |
| 4 | ⚡ Fast Lint & Syntax Preflight | **stale-run class — root reproduced**: stale committed `scripts/ops/_INDEX.md` | `--step1-syntax` exit 1 on the head tree (`_INDEX.md is STALE … 540 live scripts found`); after the in-job self-heal semantics (`generate_script_index.py` → rc 0) the same step PASSES (`2298 Python, 72 JSON, 31 YAML … 0 syntax errors`). Today's `main` tree (47c94125) passes natively (`2304 … PASS`). Mechanical class fix already landed: `48412172` in-job self-heal (`pipeline.yml:560`), per TRIAGE_3851/3854. |

(`git merge-tree`-equivalent honesty note: PR head is unchanged since the failing run ⇒ the red checks are a frozen artifact of the era base, exactly the "branch alive, head unchanged → frozen red" marker TRIAGE_3854_PR3622 recorded; only the reference guard would still fail on any re-run, and it fails for the PR's own metadata, not its content.)

## Supersession proof (byte-level, zero-credential)

1. `git fetch origin pull/3635/head` → `80f0223b`; merge-base with `origin/main` = `f1d09eb5` (the #3619 squash) — the PR is exactly one docs-only commit (+13 lines, 1 file) over that base, and 98+ commits behind main at work-start.
2. `cmp <(git show origin/main:<file> | head -35) <(git show pr-3635:<file>)` → **byte-identical** (main's file is 74 lines; `diff` shape `36,74d35` — main = PR file + the §6bb/§6bc chapters that landed later).
3. The landing carrier is on main's history: `79284314 … (bridge-20261031-u4-dupguard-hold-a58) (#3725)`, dated 2026-10-31 19:35:42+06, touching the same report path; main's own §6bc text records "PR #3725 (§6ba+§6bb+§6bc, three chapters in one diff)".
4. Main's evidence plane already marked the PR stranded: §6ba-era "PR #3635 still open, unmerged ~45 minutes after its 17:37:54Z submission" and §6bc "#3635 rides stranded as the loser" (of the #3527 remedy race).

## Disposition

- **Tracker #3852: resolved by this receipt** (`closesOriginalIssue` — the #2485 closure-receipt shape: docs-only, and the incident's subject content is already remediated on main via #3725; the remaining failing checks are proven metadata/stale classes with their class fixes either landed (self-heal) or owned by the documented admin remedy (opener injection, #3861)).
- **PR #3635 itself:** admin/author lane should close it as superseded (agents cannot close another lane's PR, and cross-agent branch writes are forbidden — the same Never-do line TRIAGE_3851_PR3639 recorded).
- **No re-land, no rescue branch:** a fresh branch carrying §6ba would duplicate landed content and trip the competing-PR guard's purpose (U4 anti-stampede). The stale-run series' standing rule holds: the only PR-lane action was the author's rebase+re-push, and here even that is moot.

## Root cause & class ledger (so this shape cannot recur silently)

1. **Stale-run class** (checks 2–4): committed `_INDEX.md` staleness + event-driven-only landing never re-running old PRs. Mechanical remediation landed (`48412172` in-job self-heal; strand tripwire `pr_landing_age_guard.py` from #3603); residual gap is the opener plane, below.
2. **No-ref metadata class** (check 1): bridge opener does not inject `Refs #<originalIssueNumber>` into PR title/body — the documented admin root fix (#3861 receipt, remedy §2) plus the agent-half convention (`#<issue>` in the first ~100 summary chars, honored by this submission). Until the opener fix lands, every bridge PR whose summary lacks the token is born into a deterministic red guard.
3. **Supersession class** (the new fact this row adds to the series): a stranded PR's content can land via a *sibling* lane; the incident mirror keeps the dead PR red forever. The receipt-closure contract (#2485) is the mechanical exit — this file exercises it.

## Never-do

- No writes to the a56 branch or PR (cross-agent writes forbidden).
- No re-landing of §6ba (byte-duplicate content on main already).
- No close-verb in the summary plane except via the receipt-closure flag (bare `#N` mentions only — the #1609 verb-intent contract).
