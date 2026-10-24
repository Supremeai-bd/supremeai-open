---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:ci_cd_warning_elimination_and_node_upgrade_plan
subject: SupremeAI — Warning Elimination Implementation Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Warning Elimination Implementation Plan

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Target branch:** `main`  
**Purpose:** Remove/fix the warnings observed in the supplied GitHub Actions logs and prevent the same warning classes from returning.

---

## 0. Audit Basis

This plan is based on:

1. The supplied GitHub Actions log archive from 2026-08-28.
2. The current repository configuration/code on `main`.

The log archive contains repeated Node.js 20 deprecation warnings, Node runtime deprecation warnings (`punycode` and `url.parse()`), Poetry `--sync` deprecation, pip-as-root warning, a `dorny/paths-filter` event-payload warning, and one CI summary reporting a failed `Notify on Failure` job despite reporting “Zero Warnings”.

Important distinction:

> Do not hide warnings by suppressing stderr or setting broad ignore flags. Fix the source of each warning, then add regression checks.

---

# 1. Warning Inventory

## W-01 — GitHub Actions Node.js 20 deprecation

### Observed

The supplied logs repeatedly report:

```text
Node 20 is being deprecated.
This workflow is running with Node 24 by default.
```

They also explicitly identify Node-20-backed actions such as:

```text
actions/cache
actions/checkout
docker/build-push-action
docker/login-action
docker/metadata-action
Infisical/secrets-action
dorny/paths-filter
```

### Root cause

The repository deliberately SHA-pins actions, but several pinned SHAs correspond to older major releases whose runtime is Node 20.

Current `ci.yml` includes, among others:

```text
actions/checkout → v4 SHA
actions/cache → v4 SHA
actions/setup-node → v4 SHA
actions/upload-artifact → v4 SHA
dorny/paths-filter → current pinned SHA producing Node-20 warning
```

The custom backend setup action also pins:

```text
actions/cache → v4 SHA
```

GitHub's current guidance is to move actions to Node-24-compatible releases rather than suppressing the warning.

### Fix

Create an **Actions Runtime Upgrade Matrix** before editing:

| Action | Current | Target |
|---|---|---|
| `actions/checkout` | v4 SHA | Node-24-compatible major |
| `actions/cache` | v4 SHA | v5 |
| `actions/setup-node` | v4 SHA | Node-24-compatible major |
| `actions/upload-artifact` | v4 SHA | Node-24-compatible major |
| `actions/download-artifact` | audit all | Node-24-compatible major |
| `dorny/paths-filter` | current SHA | Node-24-compatible release |
| `docker/build-push-action` | current SHA | Node-24-compatible release |
| `docker/login-action` | current SHA | Node-24-compatible release |
| `docker/metadata-action` | current SHA | Node-24-compatible release |
| `Infisical/secrets-action` | current SHA | Node-24-compatible release |
| Other `uses:` actions | audit | Node-24-compatible release |

**Do not blindly change SHA → tag.**

For every upgrade:

1. Identify exact upstream release.
2. Confirm Node runtime.
3. Confirm breaking changes.
4. Pin the exact commit SHA.
5. Keep a version comment next to the SHA.

Example:

```yaml
uses: actions/cache@<EXACT_NODE24_SHA> # v5.x
```

### Important

Do NOT set:

```text
ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true
```

That only suppresses/extends the old runtime and is not the desired long-term fix.

---

# 2. W-02 — `punycode` DeprecationWarning

### Observed

```text
[DEP0040] DeprecationWarning:
The `punycode` module is deprecated.
```

### Root cause

This is emitted by a Node dependency used by one of the GitHub Action runtimes/tools.

The supplied logs show it during backend setup / Docker-related action execution.

### Fix strategy

Do NOT modify application Python code first.

Instead:

1. Upgrade Node-20-backed GitHub Actions to Node-24-compatible versions.
2. Re-run the workflow.
3. If `punycode` remains, identify the emitting package with:
   ```text
   NODE_OPTIONS=--trace-deprecation
   ```
   in a temporary diagnostic run.
4. Upgrade the specific action/package responsible.
5. Do not add a global warning suppression.

### Acceptance

No:

```text
DEP0040
punycode is deprecated
```

in CI logs.

---

# 3. W-03 — `url.parse()` DeprecationWarning

### Observed

```text
[DEP0169] DeprecationWarning:
url.parse() behavior is not standardized and prone to errors...
Use the WHATWG URL API instead.
```

### Fix strategy

First determine whether this comes from:

```text
repository JavaScript
dependency
GitHub Action
CLI tool
```

Use a trace-enabled diagnostic run.

Search the repository and lockfiles for direct usage:

```text
url.parse(
require('url').parse
from 'url'
```

If application code directly uses it:

```text
url.parse(...)
```

replace with:

```text
new URL(...)
```

where behavior is equivalent.

If a third-party dependency owns the call:

- update that dependency if a compatible release exists;
- do not fork/copy it merely to silence the warning;
- if no safe upgrade exists, document the transitive source and isolate it until upstream fixes it.

### Acceptance

No `DEP0169` from the production/CI toolchain.

---

# 4. W-04 — Poetry `--sync` is deprecated

### Observed

The logs report:

```text
The `--sync` option is deprecated and slated for removal,
use the `poetry sync` command instead.
```

### Current source

`.github/actions/setup-backend/action.yml` contains:

```bash
poetry install --no-root --sync --with dev --dry-run
```

on the cache-hit path.

### Fix

Replace the deprecated command with the modern equivalent while preserving the current intended behavior.

Before changing it, verify the installed Poetry version and command compatibility.

Desired behavior:

```text
cache hit
   ↓
validate/synchronize environment
   ↓
do not unnecessarily reinstall the complete environment
```

Do not simply delete the sync step.

### Also fix the `|| true` issue

Current setup contains commands such as:

```bash
poetry lock --no-update ... || true
```

and:

```bash
... --dry-run ... || true
```

These can hide genuine dependency problems.

After migration:

- preserve non-fatal behavior only where intentionally required;
- otherwise fail the setup job when dependency state is invalid.

### Acceptance

No Poetry deprecation warning and no hidden dependency synchronization failure.

---

# 5. W-05 — `dorny/paths-filter` missing `before` field

### Observed

The supplied logs contain:

```text
##[warning]'before' field is missing in event payload -
changes will be detected from last commit
```

### Current source

`ci.yml` uses:

```yaml
dorny/paths-filter
```

with a `push` + `pull_request` + `workflow_dispatch` workflow.

The `before` field is not universally present on every GitHub event.

### Fix

Do not attempt to manufacture `github.event.before` for events where it does not exist.

Make event handling explicit:

```text
push
    → use push comparison context

pull_request
    → use PR base/head context

workflow_dispatch
    → use explicit force_* inputs
```

The path-filter step should receive the appropriate base/ref context for each event.

### Special case

The current workflow already has:

```text
force_backend
force_frontend
force_infra
```

Preserve these.

### Acceptance

No:

```text
'before' field is missing in event payload
```

warning during:

- push
- pull request
- manual dispatch

---

# 6. W-06 — pip running as root inside Docker

### Observed

GHCR build log:

```text
WARNING: Running pip as the 'root' user can result in broken permissions...
```

### Important assessment

This warning is inside the **Docker image build**, not the GitHub runner itself.

### Fix options

Preferred long-term approach:

```text
Docker build
   ↓
create/use application virtual environment or non-root build user
   ↓
install Python packages there
   ↓
runtime image runs as non-root
```

But do not redesign the Dockerfile solely to remove a harmless build-time warning if it would materially complicate the production image.

### Required audit

Inspect:

```text
Dockerfile
Dockerfile.*
docker-compose*
```

Determine:

- where pip runs;
- whether it installs into system Python;
- whether runtime already uses a non-root user;
- whether the final image is actually non-root.

### Priority

```text
Runtime security > cosmetic build warning
```

If runtime already runs non-root and build isolation is intentional, document the remaining build-time warning rather than introducing fragile complexity.

---

# 7. W-07 — pip version upgrade notice

### Observed

```text
[notice] A new release of pip is available
24.0 -> 26.2.1
```

### Fix

This is a **notice**, not a correctness warning.

Do not blindly upgrade pip globally just to make the log quiet.

Instead:

1. Determine the supported pip version for the Python version and dependency lock.
2. Pin/update the CI build-tool version intentionally.
3. Validate Poetry/setuptools/wheel compatibility.
4. Update Docker and CI consistently if required.

### Acceptance

Either:

- no stale pip notice because the build environment intentionally uses the selected version; or
- the notice is accepted/documented as non-actionable.

Do not create an endless “latest pip” dependency.

---

# 8. W-08 — CI reports “Zero Warnings” but `Notify on Failure` failed

### Observed

The Smart Pipeline Summary says:

```text
🧹 Zero Warnings
```

but also:

```text
🚨 Notify on Failure | 🔴 ❌
Fix failing job: Notify on Failure - blocking deployment
```

### This is NOT a warning cleanup task only.

It is a CI correctness issue.

### Fix

Inspect the actual `Notify on Failure` job and its dependency/condition.

Determine:

```text
Why did it fail?
Was the failure intentional?
Did it fail because another job failed?
Did the summary parser misclassify the run?
```

The summary generator must distinguish:

```text
warnings = 0
errors = 0
failed jobs = 1
```

from:

```text
warnings = 0
failed jobs = 0
```

### Required rule

A summary saying:

```text
Zero Warnings
```

must never be interpreted as:

```text
CI is clean
```

unless all required jobs are successful.

---

# 9. W-09 — Warning scanner false confidence

The supplied summary reports “Zero Warnings” even though raw logs contain Node/Poetry warnings.

This indicates the log scanner may be:

- scanning only selected job output;
- stripping warning lines;
- scanning before post-job output;
- treating known warnings as ignored;
- or failing to aggregate all job logs.

### Fix

Update the warning scanner to classify:

```text
ERROR
FAILURE
WARNING
DEPRECATION
NOTICE
```

and output:

```text
Critical failures
Warnings
Deprecated dependencies
Informational notices
Ignored known warnings
```

with explicit counts.

### Required behavior

If raw logs contain:

```text
##[warning]
DeprecationWarning
deprecated
```

the summary must report them unless an explicit allowlist entry exists.

---

# 10. Repository-wide GitHub Actions Audit

Before fixing individual workflows, inventory every:

```yaml
uses:
```

under:

```text
.github/workflows/
.github/actions/
```

Build a table:

| Workflow | Action | Current SHA | Release | Runtime | Target | Reason |
|---|---|---|---|---|---|---|

Include:

- checkout
- cache
- setup-python
- setup-node
- upload/download artifact
- pnpm setup
- Docker actions
- Infisical
- Trivy
- TruffleHog
- paths-filter
- any third-party actions

### Rule

Every action must be:

```text
exact SHA pinned
+
known release
+
known runtime
+
reviewed before upgrade
```

---

# 11. Do Not Break Supply-Chain Hardening

The repository intentionally uses full SHA pinning.

Therefore:

### DO

```text
v4 SHA
 ↓
find v5 exact commit
 ↓
verify upstream release
 ↓
pin new SHA
 ↓
comment version
```

### DO NOT

```text
SHA
 ↓
@v5
```

just to eliminate warnings.

The warning fix must not reduce supply-chain security.

---

# 12. Phase-by-Phase Implementation Order

## Phase 1 — GitHub Actions runtime modernization

- [ ] Inventory every `uses:`
- [ ] Identify Node-20-backed actions
- [ ] Upgrade to Node-24-compatible releases
- [ ] Pin exact SHAs
- [ ] Preserve least-privilege permissions
- [ ] Validate all workflow inputs
- [ ] Run CI

## Phase 2 — Event/pipeline warnings

- [ ] Fix `dorny/paths-filter` `before` handling
- [ ] Test push
- [ ] Test PR
- [ ] Test workflow_dispatch
- [ ] Preserve force flags

## Phase 3 — Python/Poetry warnings

- [ ] Replace deprecated `poetry install --sync`
- [ ] Use `poetry sync` where appropriate
- [ ] Remove unnecessary `|| true`
- [ ] Validate Poetry lock behavior
- [ ] Test cache-hit path
- [ ] Test cache-miss path

## Phase 4 — Node dependency deprecations

- [ ] Trace `punycode`
- [ ] Trace `url.parse`
- [ ] Upgrade responsible dependency/action
- [ ] Avoid broad warning suppression
- [ ] Re-run CI

## Phase 5 — Docker build warning

- [ ] Inspect pip installation layer
- [ ] Verify runtime user
- [ ] Decide whether root pip is acceptable during build
- [ ] If safe, migrate build install to isolated/non-root environment
- [ ] Rebuild image
- [ ] Test runtime permissions

## Phase 6 — CI summary correctness

- [ ] Fix Notify-on-Failure job
- [ ] Fix warning scanner aggregation
- [ ] Ensure all job logs are considered
- [ ] Separate warnings/errors/notices
- [ ] Ensure “Zero Warnings” cannot hide failed jobs

---

# 13. Required Regression Tests

## GitHub Actions

- [ ] push → clean
- [ ] pull_request → clean
- [ ] workflow_dispatch → clean
- [ ] forced backend → works
- [ ] forced frontend → works
- [ ] forced infra → works

## Dependency setup

- [ ] cache hit
- [ ] cache miss
- [ ] Poetry lock unchanged
- [ ] Poetry lock changed
- [ ] dependency installation failure correctly fails CI

## Docker

- [ ] image builds
- [ ] application starts
- [ ] runtime user is correct
- [ ] Python packages import correctly
- [ ] no permission regression

## Summary

- [ ] warning present → reported
- [ ] deprecation present → reported
- [ ] failed job → reported
- [ ] warnings=0 + failure=1 → NOT clean
- [ ] warnings=0 + failure=0 → clean

---

# 14. Definition of Done

The warning cleanup is complete only when:

```text
[ ] Node 20 deprecation warnings are gone
[ ] punycode warning is gone or its transitive source is documented and upstream-fixed
[ ] url.parse warning is gone or its transitive source is documented and upstream-fixed
[ ] Poetry --sync warning is gone
[ ] paths-filter 'before' warning is gone
[ ] pip root warning is either fixed or explicitly accepted after security audit
[ ] pip version notice is intentionally handled
[ ] Notify on Failure is healthy
[ ] Smart Pipeline Summary accurately reports warnings/errors
[ ] every GitHub Action remains SHA-pinned
[ ] all workflows pass on push
[ ] all workflows pass on PR
[ ] manual dispatch paths pass
[ ] Docker build passes
[ ] no production behavior regression
```

---

# 15. Final Architecture Rule

Do not optimize for:

> “Make GitHub Actions log green.”

Optimize for:

> **“Every warning has a known owner, known root cause, and intentional resolution.”**

The final state should be:

```text
Raw logs
   ↓
No unexpected warnings
   ↓
No hidden failures
   ↓
Accurate summary
   ↓
SHA-pinned Node-24-compatible Actions
   ↓
Deterministic Poetry setup
   ↓
Secure Docker build
   ↓
Production-safe CI
```

---

## Priority

### P0 — Fix immediately

1. Node 20-backed Actions
2. `dorny/paths-filter` event warning
3. Poetry `--sync` deprecation
4. `Notify on Failure` false/real failure
5. CI warning scanner accuracy

### P1

6. `punycode`
7. `url.parse`
8. Docker pip-root warning/security review

### P2

9. pip version notice
10. Further workflow/action modernization

---

## Agent Safety Rules

The implementation agent MUST:

- inspect current files before editing;
- preserve full-SHA action pinning;
- never replace SHA pins with floating tags;
- never suppress warnings globally;
- never delete a failing check just to make CI green;
- never add paid infrastructure;
- never change production runtime behavior without a test;
- update one warning class at a time;
- run the relevant workflow/test after each phase;
- produce a before/after warning inventory;
- stop if a proposed dependency upgrade introduces a breaking change.
