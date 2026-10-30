# Scout census — pipeline.yml least-privilege permissions gap (11 read-only jobs inherit workflow-level write)

**Task ID:** bridge-20261031-scout-perms-census-glm28 · **Agent:** GLM Agent 28 (Job ID: 486832)
**Dispatch:** continuous loop, 2026-10-31 06:28+08 চক্র · **Class:** report-only scout census (docs-only, no code edits, no auto-close)
**যাচাই-কাল:** 2026-10-31T06:3x–06:5x+08 · **Evidence base:** main tip `7c7e293` (0-behind worktree census, reproducible greps below)

## বাংলা সারসংক্ষেপ

`.github/workflows/pipeline.yml`-এর টপ-লেভেল `permissions` ব্লক তিনটি `write` স্কোপ দেয় (`contents`, `pull-requests`, `issues`)। ২২টি job-এর মধ্যে মাত্র ৪টি নিজের `permissions` ঘোষণা করে; বাকি ১৮টি উত্তরাধিকারসূত্রে পূর্ণ write টোকেন পায়। এর মধ্যে **১১টি job কাঠামোগতভাবে সম্পূর্ণ read-only** (কোনো `gh` write, `git push` বা dispatch POST নেই) — অথচ PR-gate-এ ফর্ক-শাখা থেকে চলা প্রতিটি guard job এই টোকেন ধারণ করে। সংশোধন এক ব্লকের diff: টপ-লেভেল read-only করা + ৭টি measured writer job-এ per-job elevation। একই diff-ে ৪ লাইনে ৪টি job-এর অনুপস্থিত `timeout-minutes`-ও যোগ করা যায় (#3386 — ci-failed, কখনো জমেনি)।

## Level 1 — the workflow-wide grant (L68–71, tip 7c7e293)

```yaml
permissions:
  contents: write
  pull-requests: write
  issues: write
```

Only 4 of 22 jobs declare their own `permissions:` block: `federation-ci-mirror`, `bridge-intake-instant`, `claim-guard`, `agent-loop`. The other 18 inherit the full write triple.

## Level 2 — measured per-job census (write-op grep per job block)

Method: for each job block, grep `gh pr|gh issue` (comment/edit/close/merge/create), `git push`, `POST /repos/**/dispatches`, `issues.create|createComment|addLabels`, `--request POST|PATCH|PUT`.

**A — strictly read-only, inherits full write (11 jobs — the finding):**

| job | write ops found |
|---|---|
| satellite-board-audit | none |
| branch-naming-guard | none |
| issue-reference-guard | none |
| tower-verification-guard | none |
| duplicate-pr-guard | none |
| boundary_sanitization_guard | none |
| loop_contract_parity_guard | none |
| ingress_hook_guard | none |
| stale_base_guard | none |
| fast-lint-syntax-preflight | none |
| studio-verification | none |

**B — genuinely writes, inherits broad (7 jobs — legit, should declare per-job):**
`test-matrix`, `secrets-scan`, `mcp-tower`, `sdk-typescript` (each POSTs `repos/Supremeai-bd/supremeai-open/dispatches` → `contents: write` needed for the GITHUB_TOKEN fallback), `knowledge-sharing-guard` (`gh pr edit` → `pull-requests: write`), `auto-landing` (PR landing ops), `satellite-dispatch-and-sync` (`git push`).

**C — already compliant (4 jobs):** per-job `permissions:` declared — the correct convention already exists in this same file; it was never extended.

## Level 3 — blast radius (why this is more than hygiene)

1. **Fork-PR surface**: the `pull_request` triggers run these guards on every PR — the repo's primary external-contribution path. Any step gone wrong in a guard (script injection, substituted action, dependency slip) holds a token able to write commits, edit/close issues, and post/edit PRs on the public repo.
2. **Measured injection overlap**: `stale_base_guard` interpolates `${{ github.event.pull_request.base.sha }}` and `${{ github.event.pull_request.head.sha }}` directly into `run:` shell; `knowledge-sharing-guard` interpolates `github.event.pull_request.number` into `gh pr edit --body`. These are exactly the job class GitHub's security-hardening guidance says must run with the narrowest token.
3. **Root cause**: one generous top-level block instead of deny-by-default + per-job elevation. The 4 compliant jobs prove the intended pattern; it simply was never extended to the whole file.

## Fix contract (small, zero-behavior-change)

1. Top-level → deny-by-default: `contents: read`, `pull-requests: read`, `issues: read`.
2. Per-job elevation, matching measured need: `test-matrix` / `secrets-scan` / `mcp-tower` / `sdk-typescript` / `satellite-dispatch-and-sync` → `{ contents: write }`; `knowledge-sharing-guard` → `{ pull-requests: write, contents: read }`; `auto-landing` → `{ pull-requests: write, contents: write }` (it lands PRs); the 4 compliant jobs stay as-is; the 11 read-only jobs need **no change** (they inherit read-only).
3. Token-chain note: the four dispatch jobs use `secrets.OPEN_SYNC_PAT || MERGE_PAT || OPEN_DISPATCH_TOKEN || GITHUB_TOKEN` — per-job elevation only tightens the GITHUB_TOKEN fallback; PAT behavior unchanged.
4. **Recurrence guard (U6)**: wire a mechanical check into the existing guard family that fails any job holding workflow-level write without a measured write-op or its own `permissions:` block (zizmor `workflow-permissions` audit, the #1776/#2793 hardening lineage) — so new jobs cannot silently regress.

## Adjacent gap, same file (noted here, do not file duplicate)

`test-matrix`, `secrets-scan`, `mcp-tower`, `sdk-typescript` still have **no `timeout-minutes`** (18 of 22 jobs have it). Filed once as #3386 — claimed, released after 7 minutes, then closed `ci-failed`; **never landed** (live census today shows the 4 jobs still bare). If a solver takes this census, the 4 missing timeouts are a 4-line piggyback in the same diff.

## Boundary

`.github/workflows/pipeline.yml` lives in this open repo — fully inside the agent envelope; the remedy needs no private plane. Verification ladder for a solver: YAML parse, per-job permission assertions (the new recurrence guard's own tests), and a green matrix run.
