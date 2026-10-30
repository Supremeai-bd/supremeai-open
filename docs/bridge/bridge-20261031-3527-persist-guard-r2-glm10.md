# Run Receipt — GLM Agent 10 (Job 486755) — cycle 4: #3527 persist-credentials guard r2

- **Task ID:** `bridge-20261031-3527-persist-guard-r2-glm10`
- **Agent:** GLM Agent 10 (Job 486755) — anonymous zero-credential surface (`?client=GLM-Agent-10`)
- **Lane:** scripts guard extension + report (one code file r2, one report doc, this receipt; zero `.github/` writes, no closure requested)
- **Context note:** the r2 identity worklog (`docs/bridge/bridge-20261030-identity-glm10.md`) was migrated to supremeai-archive by the founder mandate (#3524); this file is the cycle-4 receipt and carries forward only the durable facts.

## Durable facts, cycles 1-3 (from the archived worklog)

1. **#2360 option-C artifact** — sentinel surfacing template + install note → WO #3283 / PR #3284, **merged (e44c8e4b, verified on main 10-31)**.
2. **#2766 U6 zizmor guard** → WO #3351 / PR #3352 (duplicate WO #3353 stranded-by-design — do not act).
3. **R85 = #3478** (MCP Apps SEP-1865 scout lane) + radar XV + index registration; registration turned the R48 freshness guard red→green.

## Cycle 4 (2026-10-31 00:10+08, role-locked auditor)

Loop offered zero clean picks (all open candidates U5-covered); board sweep found **#3527** —
GLM Agent 08's audit finding (`status:unclaimed`, 0 comments): `ops-maintenance.yml` persists
the job GITHUB_TOKEN at 18/23 checkout sites (implicit `persist-credentials: true` default),
11 of those jobs holding write permissions. Shipped the finding's ranked fix #2 — the only
agent-lane leg (fix #1 is owner-lane `.github/`):

- **`scripts/ci/workflow_hardening_census_guard.py` r2** (full-file): per-checkout
  credential-posture resolution (`resolve_checkouts`) with step-body boundary + dash-led
  step-shape handling; new countable classes `implicit_persist_true` / `persist_true_explicit`
  / `persist_dynamic` (fail-closed); `--emit-baseline` for one-command re-baselining; self-test
  6→9 cases.
- **Ground-truth verification:** fetched the live 108,324 B `supremeai/.github/workflows/ops-maintenance.yml`
  (sha `150cd37d`) via tower read plane and ran the r2 census on the exact bytes — reproduces
  the filer's hand count **exactly**: 23 checkout / 5 explicit-false / 18 implicit-true / 0
  explicit-true / 0 dynamic; the filer's five line-number citations (L517/1593/1701/1738/1782)
  each land inside a checkout with-block (re-verified line-by-line).
- **Report:** `docs/reports/R3527_PERSIST_CREDENTIALS_GUARD_R2_2026-10-31.md` (includes the
  owner-lane action list and the one-time re-baseline note for the r2 schema change).

## Verification this cycle

- guard self-test **9/9 PASS** (offline fixtures); `py_compile` PASS; ruff clean on the file.
- loop `--verify-only` **8/8 PASS** (contract `agent-loop-contract/1`).
- U5 anti-stampede before build: tracked-tree scan, origin/main last-200 subjects, 20-row
  queue window — zero #3527 remedy citations anywhere (the filing report itself is the only hit).
- Dual-rebase: work-start and pre-submit both on origin/main, 0 behind.

## Notes for the next agent on this slot

- r2 guard: any r1-era frozen baseline drifts on first r2 run (profile-key schema change) —
  one-time expected SURFACE_DRIFT; re-baseline with `--emit-baseline` + dated evidence.
- Tower `github.read_file` 404s on `supremeai-open:.github/**` but reads
  `supremeai:.github/**` fine — owner-lane workflow truth lives in the private monorepo.
- Sandbox: exec bits drop on rewrite → `chmod +x` before local ruff (git mode stays 100644,
  `core.fileMode false` set in this sandbox clone).

## Reflection Evidence (why + alternatives_rejected)

- **why:** the finding's only agent-lane leg was the machine-tracking one; making the 18
  implicit exposures a baseline-frozen number is the recurrence-killing shape (no new
  implicit-true checkout can land silently), versus another report-only receipt that adds
  zero protection.
- **alternatives_rejected:** duplicate evidence receipt on #3527 (filer's own report already
  counts the sites); writing `supremeai/.github/workflows/ops-maintenance.yml` directly
  (owner-lane); claiming #3527 for closure (owner-lane legs remain open — Refs only);
  editing the archived r2 worklog in its old path (post-#3524 the file is gone from main —
  new receipt file instead).

## Rollback

git revert-safe: revert the guard script to r1 (single tracked file) + delete this receipt
and the R3527 report; no other file depends on them.
