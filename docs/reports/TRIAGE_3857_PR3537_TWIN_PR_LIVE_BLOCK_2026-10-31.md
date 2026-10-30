# Triage receipt for CI tracker #3857 — PR #3537: one red is frozen, one is LIVE (twin PR)

> **Agent:** GLM Agent 08 (Job 486735) · report-only, Refs #3857 #3537 (bare), no
> claim held, no Closes. Family context: frozen-red tracker class documented in
> TRIAGE_3851_PR3639 (landed #3865) and TRIAGE_3854_PR3622 (#3871/#3870); instance
> receipt #3856 → TRIAGE_3856_PR3542 (#3874/#3875). This instance is DIFFERENT:
> half the red is a live semantic failure the rebase remedy cannot fix.

## Half 1 — Loop-Contract Parity Guard red: stale-run artifact

- PR #3537 (`bridge/bridge-20261031-compound-citation-r3-glm12`, head `07d60ca`) changes
  2 code files (`scripts/agents/continuous_agent_loop.py`, `tests/…demotion.py`, +73).
- Merge into current `origin/main` (`22e5a2f`): **clean** (ort auto-merge of the loop.py
  hunk).
- `python3 scripts/agents/check_loop_contract_parity.py` on the merge tree →
  **"✅ Loop-contract parity OK: tiers 1..8, 10 guards, no flag-table copy, SSOT
  pointers present"**, **exit 0**; loop `--verify-only` 8/8 PASS on the same tree.
- Head is **140 commits behind** main, never re-pushed → the tracked red is frozen at
  the run-time base era. Same mechanism as the family receipts.

## Half 2 — Anti-Duplicate PR Guard red: LIVE, and the tracker's remedy is wrong for it

- **PR #3536 is OPEN with the IDENTICAL head branch** (`bridge/bridge-20261031-
  compound-citation-r3-glm12`) and identical changed files — one glm12 submission
  minted **two open PRs** (one WO-titled, one raw-titled), both referencing #2766.
- The guard (`pipeline.yml:344+`, "Verify no competing open PR exists for the same
  issue") is therefore correctly red **today** — a competing PR exists now. Rebase +
  re-push will NOT green it; the twin must land or close first.
- Class evidence it recurs: tracker **#3858** files the same twin-closure problem for
  PR #3534 (`bridge-20261030-3402-twin-closure-r1`).
- **Remedy (author glm12 / admin lane):** close one of the twins (keep the branch that
  carries the newest rebase; the content is identical so closure loses nothing), then
  the survivor's guard goes green on its next run. Filer-lane class note: the intake
  appears to double-open PRs for one submission (WO-mirror + raw) — minting a
  guaranteed Anti-Duplicate red per twin pair; worth an intake-side fix (open one, or
  make the guard twin-aware by head-branch equality).

## Disposition

Tracker disposition = half stale-run (parity) + half live twin-PR blocker (anti-
duplicate). The boilerplate remedy ("rebase onto latest main, fix the failing guards,
re-push") is misleading for this class: rebasing cannot close the twin. No bridge
patch (would add a THIRD copy of the same work — U5 and anti-duplicate). Claim
released/not held. Rollback: revert this receipt; docs-only.

## Verification (3-tier)

1. **Reflection**: receipt is the only new file; findings line-cited (`pipeline.yml:344+`).
2. **Smoke**: merge + parity command quoted with real exit 0; twin-PR identity verified
   via both PR pages (same head branch string, same 2 files).
3. **Tests**: `check_loop_contract_parity.py` PASS line quoted verbatim; the
   anti-duplicate red is reproduced by the live existence of PR #3536 itself.

## Reflection Evidence

- **why:** this tracker looks like the 4th frozen-red instance but is half-live; a
  solver following the boilerplate would rebase, re-push, and stay red, burning the
  author's push window. The increment is the twin-PR identity proof (same head branch
  string) which converts "fix the guard" into "close one PR" — a one-action remedy —
  plus the intake double-open class note with its second instance (#3858).
- **alternatives_rejected:** (1) rebasing and re-pushing myself — foreign bridge
  branch, and it would not green the live half. (2) Closing PR #3536 myself — admin/
  author authority over foreign PRs. (3) A code patch making the guard twin-aware —
  the guard lives in protected `.github/`, admin-only; noted as class recommendation.
  (4) A full duplicate battery receipt — parity half is covered by the family
  receipts; only the twin finding is new.
