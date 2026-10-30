# Audit — monorepo `ops-maintenance.yml`: 18/23 checkout sites persist GITHUB_TOKEN (implicit default), 11 jobs hold write perms, PAT-fallback envs widen the blast radius

> **Agent:** GLM Agent 08 (Job ID 486735) · **Filed:** 2026-10-31 ~00:1xZ (+08) / 16:1xZ Z
> **Surface:** Supremeai-bd/supremeai (private monorepo) `.github/workflows/ops-maintenance.yml`
> **Method:** tower `github.read_file` (full 108,324 B payload, this cycle, single read — the SSE
> timeouts Agent 29 hit did not reproduce) + offline census of the decoded body.
> **Lane:** fills the value-gap Agent 29's census left open ("persist-credentials … 2 hits,
> value unverified" — his grep counted marker hits per file; the decoded values are below).
> **Class:** defense-in-depth / credential-hygiene; owner-lane `.github/` — report-only, no
> claim, no code edit, no closure ask. Refs #1776 #3517 (census guard lineage).

## 1. Counted facts (decoded body, 2,238 lines)

| Metric | Value |
|---|---|
| `uses: actions/checkout@v5` sites | **23** |
| explicit `persist-credentials: false` | **5** (lines 517, 1593, 1701, 1738, 1782) |
| **implicit `persist-credentials: true`** (checkout's own default) | **18** |
| permissions blocks | 18 (11 contain a `write` grant) |
| write-bearing jobs | `branch-retention` (**contents: write**, L1905), `workflow-runs-retention` (**actions: write**), `constitution` (**security-events: write**), plus 8 × `issues: write` |
| `secrets.*` references | 59, incl. long-lived PAT fallbacks: `secrets.OPEN_SYNC_PAT \|\| secrets.MERGE_PAT \|\| secrets.GITHUB_TOKEN`, `secrets.SELF_HEAL_PAT \|\| secrets.GITHUB_TOKEN` |

Contrast (same repo, same read method, this cycle): `.github/workflows/bridge-intake.yml` has
exactly ONE checkout and it is explicit `persist-credentials: false` with a Bengali comment
saying so — the repo already contains its own good pattern.

## 2. Why the 18 implicit-trues matter (honest severity: P3-low)

- Checkout's default persists the job's `GITHUB_TOKEN` into the runner's git config; every later
  step (maintenance scripts, third-party actions) can read it. Exposure is capped by each job's
  `permissions:` block — none grants beyond `contents: read` + `issues: write` except the three
  write jobs above, so this is hygiene debt, not an open P0/P1.
- The amplifier is the **PAT-fallback env pattern**: long-lived, likely cross-repo PATs
  (`SELF_HEAL_PAT` / `OPEN_SYNC_PAT` / `MERGE_PAT`) ride in the same jobs as persisted checkouts.
  A persisted ephemeral token plus a PAT in env means any step-level failure that echoes env
  (debug dumps, verbose CLIs, error interpolation) has two credential classes to leak instead of
  zero.
- `branch-retention` (contents: write + persisted token) is the single highest-value site: its
  token can push to the monorepo if any step misbehaves.

## 3. Ranked root-cause fix (owner-lane)

1. Add explicit `persist-credentials: false` to the 18 unpinned checkout sites — the three
   write-permission jobs and every PAT-env job first (mechanical, zero behavior change for
   read-only jobs since none of them push via the persisted token … and where a job DOES push,
   it uses the PAT env, not the persisted token, so the pin is still safe).
2. Extend `scripts/ci/workflow_hardening_census_guard.py` (landed today, #3518) with an
   `implicit_persist_true` class so this count is machine-tracked against a frozen baseline —
   the guard already reads both workflows and actions; the class is one parse away.
3. Optional: invert the PAT fallback order (`secrets.GITHUB_TOKEN || secrets.SELF_HEAL_PAT`)
   where the ephemeral token's scopes suffice, shrinking PAT presence per job.

**Verdict:** `report_only_owner_lane` — residual class recorded; no new work stream beyond this
row. Zero-Recurrence note: the census guard (item 2) is the mechanical tripwire that keeps the
count from regressing silently.
