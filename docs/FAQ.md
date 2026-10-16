---
id: faq
title: "Operational FAQ — Validation Errors & Autonomous-Landing Troubleshooting (supremeai-open)"
document_role: guide
status: active
canonical: true
owner: auditor
last_verified: 2026-10-16
governing_issue: 23
related_docs:
  - docs/AGENT_PORTAL_SPEC.md
  - docs/ZERO_ADMIN_GUIDE.md
  - AGENT_RULES.md
  - docs/AGENT_LOOP_SPEC.md
---

# Operational FAQ — Troubleshooting Validation Errors

> Every entry below is a **real, observed failure class** on this repository's board — symptom → root cause → exact fix. The Zero-Admin premise (see [`docs/ZERO_ADMIN_GUIDE.md`](./ZERO_ADMIN_GUIDE.md)) is that you never need an admin to resolve any of these.

## Q1. CI failed with "Branch '…' violates the naming convention"

**Symptom:** 🌿 Branch Naming Guard fails.
**Cause:** branch name outside the constitutional pattern.
**Fix:** rename locally and push as a **new fast-forward** branch (never force):

```sh
git branch -m feat/my-old-name feat/my-task-42-slug   # allowed prefixes:
# feat/ fix/ docs/ chore/ test/ refactor/ perf/ bridge/ group/
# contributor/ hotfix/ release/ agent/
git push origin feat/my-task-42-slug                   # open the PR from the new branch
```

Bot branches (`dependabot/*`, `github-actions/*`, `copilot/*`) are auto-allowed.

## Q2. 🔗 Issue Reference Guard failed

**Cause:** the PR title/body contains no `#<issue-number>` reference.
**Fix:** edit the PR description (or title) to reference the governing issue — e.g. `Closes #42`. Best practice: `Closes #<n>` in **both** title and body (see Q8 for why both).

## Q3. 👥 Anti-Duplicate PR Guard failed — "competing duplicate PR"

**Cause:** another open PR already targets the same issue (U4: one issue = one open PR, anywhere in the federation — including bridge work orders).
**Fix:** do **not** open a second PR. If the existing PR is green — let it land. If it is failing or stale (>2 h), you may follow up on that branch or review it; only supersede it by explicitly closing the old PR first.

## Q4. 🧱 Boundary Sanitization Guard failed — "not an approved public surface"

**Cause:** a new file/directory is outside the approved public registry (`scripts/ci/boundary_sanitization_guard.py` is the SSOT).
**Fix:** move the file under an approved surface, or — when the governing issue explicitly requires a new surface (e.g. a new top-level `tests/` dir) — expand the registry in the same PR, referencing the governing issue (the guard's own docstring prescribes this). Never ship private-context content on the public boundary.

## Q5. ⏳ Stale-Base Guard failed — "Branch is stale: main advanced N commit(s)"

**Cause:** `main` moved after your branch was cut (fast-moving federation — normal).
**Fix:** rebase or merge-sync onto the latest `origin/main`, then push **fast-forward**:

```sh
git fetch origin main
git merge origin main        # or: git rebase origin/main
git push origin <branch>     # plain push; fast-forward
```

**Never `--force`:** force-pushes are rejected server-side (pre-receive hook) and locally by the pre-push guard (see Q6). If your local branch has rewritten history (e.g. after a local rebase), reproduce the same content as a fast-forward: check out the remote head, merge `origin/main`, resolve, push.

## Q6. `git push` declined with "pre-receive hook declined"

**Cause:** server-side Zero-Force-Push protection (docs/INGRESS_SECURITY_POLICY.md) rejected a non-fast-forward update — typically a force-push or history rewrite.
**Fix:** rebuild forward. Recipe that always works (used on PR #290):

```sh
git checkout -b sync <remote-branch-head-sha>
git merge origin/main                  # resolve conflicts with the final intended content
git add -A && git commit               # merge commit = fast-forward for the remote
git push origin sync:<your-branch>     # NO --force needed
```

## Q7. My PR merged but the task issue stayed open

**Cause:** GitHub processes `Closes #N` only from the **final squash commit message** (#165 doctrine). If the keyword was only in branch commits (not the PR title/body), the old gate behavior could drop it.
**Fix (prevention):** put `Closes #<n>` in the **PR title and/or body** — the gate preserves the description into the squash message. **Fix (recovery):** close the issue manually with landing evidence (merge SHA + verification summary), and note the miss so the body-builder is repaired.

## Q8. Tower test suite skipped with "missing required env [ … ]" — is that a failure?

**No — it is a documented PASS.** Suites wrapped by `scripts/test-runner.ts` with a required-env argument (e.g. `GITHUB_TOKEN`, `MCP_ADMIN_KEY`, `SUPREMEAI_SIDECAR_TESTS`) skip cleanly with exit 0 when the env is absent (#116 doctrine: never silently dead, always a documented skip). CI runs the same skip. Do not add fake credentials to "make them run" — offline determinism is the design.

## Q9. Which Tower suites run in CI, and which need live services?

`npm run test:tower-ci` (33+ steps) is the credentials-free chain that runs in CI — it is a superset of the offline-provable `test:unit` surface (PR #290 folded the remaining offline-green suites in; repaired the dead `test:account-chain` reference that used to break the unit chain). Suites requiring live endpoints/credentials skip with documented reasons. If `npm run test:unit` fails on your machine, run it under a clean env first (`env -i PATH="$PATH" HOME="$HOME" npm run test:unit`) — stray local env vars are the most common false failure.

## Q10. The PR shows `mergeable_state: unknown` / check-runs list looks empty — is it stuck?

**Usually event-visibility lag, not a stuck gate.** The gate may land via the webhook/dispatch path even while the checks API briefly shows nothing for the head SHA. Ground truth = the PR's `merged` field and the squash commit on `main`. If genuinely stuck: push any fast-forward sync commit to re-fire events (see Q5 recipe).

## Q11. My branch disappeared right after the PR merged

**Expected behavior:** the Command Router deletes the PR head branch post-merge and verifies task-issue closure autonomously. Nothing to recover — the work is on `main` (squash commit).

## Q12. Secret Scanning flagged my commit

**Fix:** remove the credential from the change, **rotate it at the provider** (a pushed secret is compromised regardless of cleanup), then push forward (fast-forward). Never add secrets to `.gitleaksignore` — that file exists for verified false positives only.

## Q13. Where do I run the "3-Tier Verification Contract"?

```sh
python scripts/agents/continuous_agent_loop.py --verify-only
```

Eight evidence tiers: Python compile, JSON parse + api-schemas deep validation, YAML/OpenAPI safe-load, fail-honest binary guard, task-contract fail-closed, group-registry guard, envelope determinism, machine-path isolation. Tier-count SSOT: `docs/AGENT_LOOP_SPEC.md` §4.

## Related Documents

- [docs/AGENT_PORTAL_SPEC.md](./AGENT_PORTAL_SPEC.md) — architecture spec this FAQ belongs to
- [docs/ZERO_ADMIN_GUIDE.md](./ZERO_ADMIN_GUIDE.md) — the autonomous-landing handbook + submitter checklist
- [AGENT_RULES.md](../AGENT_RULES.md) — policy contracts (U4 anti-duplicate, U8/U165 keyword doctrine, U10 authority)
- [docs/AGENT_LOOP_SPEC.md](./AGENT_LOOP_SPEC.md) — envelope, tiers, guard registry
- [docs/INGRESS_SECURITY_POLICY.md](./INGRESS_SECURITY_POLICY.md) — push/merge enforcement surfaces
