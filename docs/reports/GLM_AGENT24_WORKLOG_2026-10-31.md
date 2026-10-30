# GLM Agent 24 — Worklog (Job 486817)

> Keep-it-small contract: one file per agent, durable facts only, replaced
> in place (compacted) every cycle. Registered via tower heartbeat
> 2026-10-30T16:26:43Z, slot `agent-24`.

## Durable facts

| Field | Value |
| --- | --- |
| Agent | GLM Agent 24 (GLM/Z.ai, slot agent-24) |
| Job | 486817 |
| First cycle | 2026-10-31, dispatched task-3538 (P0, browser CI red) |

## Cycle 1 (2026-10-31) — task-3538, browser satellite CI red

- **Incident:** #3538 — satellite `supremeai-browser` `ci` failed on main
  (run 41089438563), ~20s red.
- **Root cause (byte-verified repro):** commit 4359f154 added
  `tests/test_webbotauth_probe.py`; its fixture importlib-loads
  `scripts/webbotauth/probe.py`, which imports `cryptography` at module
  level; satellite CI installs only the 8-package pip line +
  requirements.txt — neither carries cryptography (pyproject's declaration
  is not consulted by ci.yml) → ModuleNotFoundError → 9 probe tests ERROR.
- **Fix:** `cryptography==50.0.2` pinned in `browser/requirements.txt`
  (the one agent-writable surface CI pip-installs) — WO #3565, PR #3566
  (fixes #3538). Guard RUNS in CI, no skip-masking; also revives the dead
  `ghost_tower/credential_vault.py` Fernet fallback on Render.
- **U6 guard:** `browser/tests/test_dependency_surface.py` — stdlib-only
  tripwire, scans tests/ + scripts/ top-level imports against CI's real
  install surface — WO #3568, PR #3569. Proven both directions (passes
  post-fix; fails pre-fix with the exact offender line).
- **Verification:** 65/65 files blob-sha-verified against the tower;
  clean CI-equivalent venv: 9 ERRORs pre-fix → 19 passed, 1 skipped
  post-fix; ruff E9/F63/F7/F82 clean; 4-pattern secret scan clean.

## Durable lessons (anti-recurrence)

1. **Tower text-transport artifact:** the tower's file-content payload eats
   `[m` sequences (ANSI-stripping) — `branches: [main]` reads as `ain]`.
   Never verify bracket-bearing content from pasted payload text; compare
   **blob shas** (`git hash-object` vs tower metadata).
2. **pyproject deps ≠ satellite CI deps:** satellite ci.yml installs the
   pip line + requirements.txt only; anything a test plane imports must
   live in requirements.txt or it dies at runtime. The dependency-surface
   guard (PR #3569) now enforces this mechanically.
