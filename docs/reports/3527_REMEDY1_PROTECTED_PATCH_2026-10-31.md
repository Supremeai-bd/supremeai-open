# #3527 remedy 1 — apply-ready verified patch for the protected lane (persist-credentials: false, 14/15 sites)

> **Agent:** GLM Agent 14 (Job ID 486785) · **Cycle:** 2026-10-31 07:14+08 (third pick) · **Dispatch:** `continuous_agent_loop.py` → #3527 (solver)
> **Lane:** report-only evidence for the admin/HITL lane — the bridge client gate rejects automatic writes to protected paths (first-hand error: *"Bridge lane does not accept automatic writes to protected paths"*; `bridge_intake.py` L894: protected paths are **never auto-applied** → admin-review). Refs #3527 #3518 #3517 #1776.

## What is ready (verified first-hand, apply as-is)

A 26-insertion unified diff adding explicit `persist-credentials: false` to **14 of 15** checkout sites in `.github/workflows/pipeline.yml` (blob `9f408ca8` at `f1b2168` — re-verify CAS before apply). Per-site safety census (fresh, mechanical):

| Class | Sites | Decision |
|---|---|---|
| Non-push jobs (guards, matrix, scan, mirror, intake, sdk, studio, agent-loop) | 12 | **flip** — read/API-only; `gh`/API callers use `secrets.GITHUB_TOKEN`, not the credential helper |
| `stale_base_guard` | 1 | **flip** — inspected: only `git fetch` + `gh pr view` (no push; crude "pushy" match was a false positive) |
| `bridge-intake-instant`, `agent-loop`, `federation-ci-mirror` (issues/contents write via API+PAT env) | (in 12 above) | flip — writes go through PAT env / API, persistence irrelevant |
| `satellite-dispatch-and-sync` | 1 | **KEEP implicit (documented residual)** — its `git push origin main \|\| true` fallback can rely on the persisted default token when `BRIDGE_PUSH_TOKEN` is unset; flipping risks the landing pipeline |

Verification at authoring time: YAML parse OK; `workflow_hardening_census_guard.py --check` → `persist_false=14`, `unpersisted_checkouts=1` (was 0/15); guard `--self-test` PASS; `pytest tests/test_workflow_hardening_census_guard.py` 5/5 (offline fixtures); Fast Lint `--step1-syntax` PASS.

The exact diff (26 lines, 14 sites) was payload-ready in this cycle's submission attempt; reproduce with one line per site — insert after each `uses: actions/checkout@v5` line (except the satellite-dispatch one):

```yaml
        with:
          persist-credentials: false
```

(the `stale_base_guard` site already has a `with:` block — add `persist-credentials: false` as its first child, before `fetch-depth: 0`)

## Why this lane ends at the admin

The ranked fix list of #3527: remedy 2 (census guard + tripwire) landed earlier via my prior receipt; remedy 1 is this patch — mechanically complete, but `.github/` is a protected path (AGENTS.md `protectedPathsToAdminReview`; bridge intake: admin-review hold). #3931's precedent confirms the pattern: its CI fix landed in `scripts/ci/federation_ci_watchdog.py`, not the workflow. Optional remedy 3 (PAT fallback order inversion) stays owner-lane as filed.

## Never-do

- No claim of closure: the issue stays open until the admin applies the patch (false-closure #2211 family — receipt is Refs-only).
- No forcing the diff through other lanes (full_file on protected path would be rejected identically).
- No flipping the 15th site without an explicit admin decision on the degraded push fallback.

---

**বাংলা (GLM Agent 14):** #3527-এর র‍্যাঙ্কড ফিক্সের শেষ agent-doable অর্ধেক আমি প্রস্তুত করেছি — ১৪/১৫ checkout সাইটে `persist-credentials: false`, প্রতিটি সাইটের job-লেভেল নিরাপত্তা বিশ্লেষণসহ, সব যাচাই সবুজ। কিন্তু `.github/` protected path — bridge lane automatic write নেয় না (প্রথম-হাতে ত্রুটি প্রমাণিত), তাই প্যাচটি admin lane-এর জন্য apply-ready অবস্থায় জমা হলো। ১৫তম সাইট ইচ্ছাকৃত residual (degraded push fallback)। ইস্যুটি খোলা থাকবে যতক্ষণ না admin প্যাচ প্রয়োগ করে — মিথ্যা closure নয়।
