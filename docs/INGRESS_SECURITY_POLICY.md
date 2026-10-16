# Ingress Security Policy — Zero-Force-Push, Stale-Base Rejection & Public-First Ingress

```yaml
id: ingress-security-policy
title: Zero-Force-Push, Stale-Base Rejection and Public-First Ingress policy
document_role: policy
status: active
canonical: true
owner: agent-orchestration
last_verified: 2026-10-15
related_docs:
  - AGENTS.md
  - AGENT_RULES.md
  - docs/CONTRIBUTING.md
  - docs/OPS_ACTIONS_QUOTA_RUNBOOK.md
source_issue: "https://github.com/Supremeai-bd/supremeai-open/issues/161"
```

## Related Documents

- [`AGENTS.md`](../AGENTS.md) — agent entrypoint (§2.1 submission pathways, §8 bridge lane).
- [`AGENT_RULES.md`](../AGENT_RULES.md) — universal rules (U4 anti-duplicate, U5 freshness, U6 safety).
- [`docs/CONTRIBUTING.md`](./CONTRIBUTING.md) — contributor onboarding and protected paths.
- [`docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`](./OPS_ACTIONS_QUOTA_RUNBOOK.md) — Actions budget context.

---

## Purpose

This document codifies the **Zero-Force-Push, Stale-Base Rejection and
Public-First Ingress Security Policy** for the SupremeAI federation
(issue #161). It exists because the defect class it eliminates is
recurring and structural: stale or rewritten history landing on `main`
silently reverts recent fixes, reintroduces resolved bugs, and destroys
commit provenance. Rule U6/P6 require machine-enforced prevention at the
root cause, not agent-side vigilance.

The authoritative enforcement is **server-side** (GitHub branch
protection + CI guards). This policy adds a local poka-yoke layer so the
defect class is stopped at the earliest possible stage — the developer's
or agent's own terminal, before anything leaves the machine.

## 1. Zero-Force-Push Mandate (Git History Immutability)

- Force pushes (`git push --force`, `git push --force-with-lease`) and
  branch deletions on `main` are strictly forbidden across
  `Supremeai-bd/supremeai-open` and `Supremeai-bd/supremeai`.
- Commit provenance is immutable: a pushed commit must remain reachable
  from the same branch tip forever. History rewrites invalidate every
  audit, ledger and evidence trail built on that history.
- Required server-side settings (admin applies, agents must never
  attempt to bypass):

| Setting | Value |
|---|---|
| `allow_force_pushes` | `false` |
| `allow_deletions` | `false` |
| enforcement | branch protection on `main` (both repositories) |

## 2. Stale-Base Rejection & Main-Sync Mandate (Anti-Stale Code Guard)

- Any PR or contribution built on an outdated commit (behind
  `origin/main`) is automatically blocked.
- Why: landing a stale branch silently overwrites recent commits,
  reintroduces previously resolved bugs, and creates hidden regressions.
- Enforcement layers:
  - **Branch protection strict mode:** `required_status_checks.strict: true`
    ("Require branch to be up to date before merging") on `main`.
  - **CI stale-base guard** (see §5.3): fails closed when
    `git rev-list --count HEAD..origin/main > 0` for a PR head.
  - **Board-Freshness Rule (#4177):** agents are constitutionally required
    to re-poll and re-sync with `main` before declaring tasks complete
    (AGENT_RULES U5/U7).
- Local rejection message instructs the exact repair:
  `git fetch <remote> main && git rebase <remote>/main`.

## 3. Public-First Ingress Policy (Single Front Door)

- All contributions touching public-facing surfaces originate exclusively
  on `Supremeai-bd/supremeai-open` and land in `Supremeai-bd/supremeai`
  via the automated Bridge pipeline.
- Governed surfaces:
  - MCP Control Tower & tools (`infrastructure/mcp-control-plane/`)
  - Public schemas & OpenAPI specs (`api-schemas/`)
  - Integration examples & SDK clients (`examples/`)
  - Governance documents and agent rules (`AGENTS.md`, `AGENT_RULES.md`, `docs/`)
- Benefit: maximum use of the free public Actions runtime while preserving
  the private monorepo's 2,000 min/mo budget (see the quota runbook).

## 4. Direct-Push Prohibition

- Direct terminal pushes to `main` are prohibited for autonomous agents on
  **both** repositories. On `supremeai-open` this is the standing
  "agents never write main" rule (AGENTS.md §8.1); on `supremeai` it
  extends to human developers as well.
- Private-only emergency caveat: changes touching proprietary core code
  that does not exist on `supremeai-open` (e.g. `backend/`, live
  infrastructure secrets) are developed on an internal feature branch and
  merged via internal PR. Direct unvetted pushes to `main` remain
  forbidden under all circumstances.

## 5. Enforcement Tooling

### 5.1 Server-side (authoritative) — admin applies

GitHub branch protection on `main` of both repositories:

```
allow_force_pushes: false
allow_deletions: false
required_status_checks:
  strict: true          # stale-base rejection at merge time
```

This is the only enforcement agents cannot bypass; everything local is a
poka-yoke in front of it.

### 5.2 Local pre-push hook (delivered in this task)

`.githooks/pre-push` — dependency-free POSIX sh (git + sh only). It
rejects, fail-closed, for remotes of the federation core repos:

1. branch deletions of `main`;
2. direct pushes to `main` (landing authority = constitutional gates);
3. history rewrites (non-fast-forward updates — i.e. any push that would
   require `--force`);
4. stale branches (`origin/main` advanced past the branch's merge-base).

Honest degradation is built in: if the remote URL is not a federation
core repo the guard is not applicable; if `origin/main` cannot be
resolved offline the freshness check is skipped with the CI guard
remaining authoritative; if the remote tip object is not present locally
the ancestry check is skipped (the server-side protection remains the
barrier). It never blocks what it cannot verify — it also never claims
verification it did not do (U2).

The hook file is committed executable (git mode `100755`); git silently
skips a non-executable hook, so the executable bit is part of the policy
surface and is asserted in CI by the 🛡️ Ingress Hook Guard job (below).

Install (one line, per clone):

```sh
git config core.hooksPath .githooks
```

Deliberate admin bypass — the only escape hatch, chosen explicitly by
the human hand and visible in shell history:

```sh
git push --no-verify
```

### 5.3 CI guards (APPLIED — `.github/workflows/pipeline.yml`)

The guard below was originally delivered as a ready-to-apply artifact
inside this document because `.github/` was a protected path for the
zero-credential bridge lane, and it targeted `open-guards.yml`, which
has since been removed (guards consolidated into `pipeline.yml` — see
#214/#242). It is now applied verbatim as the ⏳ **Stale-Base Guard**
job in `.github/workflows/pipeline.yml` (event-context, PR-only), with
two operational deltas: `actions/checkout` runs with `fetch-depth: 0`
(full history, so fetching the base/head SHAs cannot fail on a shallow
clone) and a 3-minute job timeout. A sibling 🛡️ **Ingress Hook Guard**
job asserts the §5.2 hook surface in CI: executable bit (git silently
skips a non-executable hook), `bash -n` syntax gate, and the hook's own
5-scenario offline `--self-test` — the issue's 3-tier boot smoke and
hook test suite, now continuously enforced.

```yaml
  stale_base_guard:
    name: "⏳ Stale-Base Guard (#161)"
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - name: Checkout repository (full history for merge-base arithmetic)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Reject PR branches built behind main (docs/INGRESS_SECURITY_POLICY.md §5.3)
        run: |
          BASE="${{ github.event.pull_request.base.sha }}"
          HEAD_SHA="${{ github.event.pull_request.head.sha }}"
          git fetch --no-tags origin "+$BASE:refs/tmp-base" "+$HEAD_SHA:refs/tmp-head"
          BEHIND="$(git rev-list --count refs/tmp-head..refs/tmp-base)"
          if [ "$BEHIND" -gt 0 ]; then
            echo "::error::Branch is stale: main advanced $BEHIND commit(s) past the merge-base. Rebase onto latest origin/main before submission."
            exit 1
          fi
```

### 5.4 Constitutional cross-reference (delivered)

The one-line pointer from AGENT_RULES.md **U6** to this policy was
declared as part of issue #161 and initially deferred because PR #169
(issue #155) was touching the same constitutional files (U4
anti-duplicate doctrine). #169 has merged, and the pointer is now in
place under U6 — Safety & Permissions. All sections of this policy are
self-contained here.

## 6. U9 Similar-Problem Sweep

`similar found: 4 | fixed in-task: 3 | filed follow-up: 0 (deferred cross-ref delivered in this update)`

| Surface | Status |
|---|---|
| Local pushes (both repos) | fixed in-task — `.githooks/pre-push` (§5.2), executable bit enforced in CI |
| PR head freshness at CI time | fixed in-task — ⏳ Stale-Base Guard applied in `.github/workflows/pipeline.yml` (§5.3) |
| Hook regressions at CI time | fixed in-task — 🛡️ Ingress Hook Guard (exec bit + `bash -n` + `--self-test`) in `pipeline.yml` (§5.3) |
| Merge-time strictness | already enforced upstream — Merge Gate polls mergeability and never passes UNKNOWN (PR #166); `strict: true` branch protection closes the same class server-side (§5.1) |
| Constitutional cross-ref | delivered — AGENT_RULES.md U6 pointer (§5.4) |

## 7. Verification Evidence

1. **Reflection check:** `git grep -n "Stale-Base Rejection" docs/ AGENTS.md`
   → matches this document (§2 heading).
2. **Guard self-test** (`sh .githooks/pre-push --self-test`, offline
   sandbox, guard-the-guard fixtures):

   ```
   PASS fresh-branch-accepted
   PASS stale-branch-rejected
   PASS force-push-rejected
   PASS direct-main-rejected
   PASS main-deletion-rejected
   PASS unrelated-remote-accepted
   ```

3. **End-to-end through real `git push`** (hook installed via
   `core.hooksPath`, sandbox remote shaped as a federation URL):

   | Scenario | Invocation | Result |
   |---|---|---|
   | advanced `main` | `git push origin main` | REJECTED (ingress banner) |
   | fresh feature branch | `git push origin feature-x` | accepted |
   | stale branch | `git push origin stale-b` | REJECTED ("main advanced 1 commit") |
   | rewritten branch | `git push --force origin force-b` | REJECTED (history-rewrite banner) |
   | admin escape hatch | `git push --force --no-verify` | accepted (deliberate) |
   | deletion of `main` | `git push origin --delete main` | REJECTED (deletion banner) |

   Note: a plain (non-force) non-fast-forward push is already refused by
   git itself client-side before hooks run; the hook adds the explicit
   policy message for the `--force` case, which is the case that would
   otherwise land.

4. **Approved-surface registry expansion** (`scripts/ci/boundary_sanitization_guard.py`):
   `.githooks/` added to `APPROVED_TOP_LEVEL_DIRS` per the guard's own
   documented approval process ("edit APPROVED_* below via a PR that
   references the governing issue"). Verified: guard self-test 19/19
   fixture assertions pass (miss=0, false-positive=0); full-tree
   `--check` scans 199 files with 0 violations; `py_compile` clean.

5. **Boundary sanitization:** no protected paths touched
   (`.githooks/`, `docs/`, `scripts/ci/` are outside the protected set); no
   value-shaped credential patterns in any submitted file.
