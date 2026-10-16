---
id: zero-admin-guide
title: "Zero-Admin Policy — Enforcement Guide & Auto-Merge Checklist (supremeai-open)"
document_role: runbook
status: active
canonical: true
owner: governance
last_verified: 2026-10-16
related_docs:
  - AGENTS.md
  - AGENT_RULES.md
  - docs/GUARDIAN_EVALUATION.md
  - docs/CONTRIBUTING.md
  - docs/AUTONOMY_LOOP_CONTRACT.md
  - docs/INGRESS_SECURITY_POLICY.md
source_issue: 50
source_pr: null
supersedes: []
superseded_by: []
---

# Zero-Admin Policy — Enforcement Guide & Auto-Merge Checklist

This guide documents how `Supremeai-bd/supremeai-open` operates with an admin
manual-effort budget of **≤ 0.01%** ([AGENTS.md §2.1](../AGENTS.md)): why human
manual code merging is eliminated by design, which machine gates actually enforce
that elimination, and the exact checklist a PR submitter follows to achieve 100%
autonomous auto-merge. Every mechanism described here is real and verifiable in
this repository — no aspirational claims.

## 1. What Zero-Admin means (and what it does not)

Zero-Admin is a budget statement: admin manual effort per landed change stays at
or below 0.01% of the work. It is **not** zero-governance. Authority is
redistributed from humans to machine-enforced gates:

- "Gates outrank agent preference" ([AGENTS.md §1.4](../AGENTS.md)).
- Critical behavior is machine-enforced where possible — the fail-closed guard
  list ([AGENT_RULES.md §15](../AGENT_RULES.md)): `GUARD-TEMPLATE` ·
  `GUARD-GROUP` · `GUARD-DUPLICATE` · `GUARD-SEQUENCE` · `GUARD-ADMIN` ·
  `GUARD-SCOPE` · `GUARD-FRESHNESS` · `GUARD-EVIDENCE` · `GUARD-MERGE` ·
  `GUARD-DOC-LINK`.
- "If a guard can be enforced outside the agent, do not rely only on agent
  instructions."

Submission is autonomous by design through three pathways ([AGENTS.md §2.1](../AGENTS.md)):
MCP Control Tower Bridge (zero-credential, `bridge_submit_patch`), public fork +
PR, and ephemeral JIT lease for CLI agents. None of them requires an admin to
touch the change between submission and landing.

## 2. Why human manual merging is eliminated by design

Manual merging is not merely discouraged — the pipeline has no step where a
human approval is required for a gate-clean PR. The Merge Gate
(`.github/workflows/landing.yml`, job `autonomous-auto-landing`) lands changes
through deterministic, fail-closed mechanics:

1. **One candidate PR per run, selected by machine** — the gate resolves the
   target PR itself; agents never "ask for a merge".
2. **Mergeability is never trusted on UNKNOWN.** GitHub computes mergeability
   asynchronously; the gate polls until a decision exists and gives up
   fail-closed if it never resolves — an unknown state can never pass.
3. **Draft PRs are skipped.**
4. **Conflicts hold the landing** (`BLOCKED` comment, non-zero exit).
5. **Every check on the PR head must reach a terminal green state** — the gate
   watches all checks (`gh pr checks --watch --fail-fast`), covering separately
   triggered guard jobs a snapshot could not see while pending.
6. **Fail-honest merge:** the merge exit code gates everything downstream. The
   `LANDED` comment and the bridge dispatch fire only after the squash-merge
   actually succeeded — a failed merge can never produce a fake success signal.
7. **Squash semantics preserve issue auto-close (#220):** the squash subject is
   derived from the live PR title and the body from the PR body, so `Closes #N`
   keywords survive landing and close the issue without admin bookkeeping.
8. **Bridge dispatch continues in the same run** (job `bridge-dispatch`): a
   public merge is automatically ported into the private pipeline
   (Public-First SSOT, [AGENTS.md §2.3](../AGENTS.md)) — no human porting step
   exists, which is also why duplicate PRs on the private repo are forbidden
   (Zero-Duplicate mandate, [AGENTS.md §2.3.5](../AGENTS.md)).

The residual admin surface — the honest ≤ 0.01% — is reserved for what machines
must not decide alone: `ADMIN_DECISION`-gated architectural/policy choices
([AGENT_RULES.md §6](../AGENT_RULES.md)), protected-path review outcomes
(`bridge:admin-review`), and safety stops ([AGENTS.md §1](../AGENTS.md)). These
are decision *inputs*, not merge labor: they gate *what may land*, not *how a
gate-clean PR lands*.

## 3. CI Guardian — autonomous verification criteria

### 3.1 Public pipeline guard jobs (`.github/workflows/pipeline.yml`)

| Guard | What it enforces | Fail behavior |
|---|---|---|
| Branch Naming Guard | Head branch matches `^(feat\|fix\|docs\|chore\|test\|refactor\|perf\|bridge\|group\|contributor\|hotfix\|release\|agent)/.+` (bot branches auto-allowed) | fail-closed (`guard-exempt` label is the admin escape hatch) |
| Issue Reference Guard | PR title or body references `#N` | fail-closed |
| Anti-Duplicate PR Guard | No competing open PR for the same issue (U4, one issue = at most one open PR) | fail-closed |
| Boundary Sanitization Guard (#107) | No proprietary paths/content; public boundary holds (`scripts/ci/boundary_sanitization_guard.py`) | fail-closed |
| Loop-Contract Parity Guard (#118) | Agent-loop code == contract SPEC invariants | fail-closed |
| Test Matrix | Python 3.10–3.13 matrix green | fail-closed |
| Secrets Scan | No credential-shaped content (documentation can leak too) | fail-closed |
| MCP Tower | TypeScript typecheck + test suites green | fail-closed |
| Agent Loop (cron) | Continuous dispatcher runs on schedule; findings land as issues | scheduled |

### 3.2 Guardian evaluation contract (verdict derivation)

The CI Guardian evaluates one PR per head SHA and derives its verdict
deterministically. The normative rules live in
[docs/GUARDIAN_EVALUATION.md](./GUARDIAN_EVALUATION.md) (schema:
`api-schemas/guardian-evaluation.schema.json`); summarized:

| Category | Weight |
|---|---|
| `template_adherence` — PR body follows the task contract; `Closes #N` rides in the commit message (squash doctrine, AGENT_RULES U8) | 20 |
| `scope_boundary` — diff stays inside declared Touching Files; protected paths untouched | 25 |
| `test_evidence` — 3-tier verification present and reproducible | 30 |
| `security_scan` — secret scanning and boundary checks clean | 25 |

Weights sum to 100; the autonomous-merge score floor is **80**. Verdicts derive
in strict order — first rule wins:

1. **REJECT** — `security_scan` fail, or `scope_boundary` fail touching
   protected paths, or a duplicate-PR collision (U4). Never healable
   automatically; start a clean submission.
2. **HOLD** — any category `fail`, or score below threshold. Emits
   `healing_instructions` (one concrete, mostly automatable step per failed
   criterion).
3. **PASS** — otherwise.

`merge_eligibility.eligible = (verdict == PASS) AND (score.overall >= 80) AND (no security_scan fail at any status)`.

### 3.3 Bridge intake gates (Pathway 1)

Zero-credential submissions pass the same philosophy on intake
([AGENTS.md §8](../AGENTS.md), [docs/CONTRIBUTING.md §7](./CONTRIBUTING.md)):
task-id format → dedup → diff caps (≤ 200 KB, ≤ 30 files) → secret-pattern scan
→ forbidden-path check — all fail-closed; the intake rejects rather than
sanitizes. Clean orders become a PR through the full constitutional gate chain
above; status is reported back on the work-order issue
(`bridge:in-gates` / `bridge:landed` / `bridge:rejected` / `bridge:admin-review`).

## 4. Auto-merge checklist — achieving 100% autonomous landing

Each item maps to a real gate. A PR that satisfies all of them needs no human
action between `git push` (or `bridge_submit_patch`) and the `LANDED` comment.

**Pre-flight (before writing code):**

- [ ] Issue is claimable (open, no active claim/hold; implicit claimable
      lifecycle — #219) and matches your capability (U3 validity).
- [ ] **No competing PR exists** for this issue anywhere in the federation
      (U4; machine-enforced by the Anti-Duplicate PR Guard).
- [ ] Base is fresh (U5): re-poll `main` and open PRs at start.
- [ ] The issue's declared Touching Files are known and sufficient for the fix.

**Submission:**

- [ ] Branch named `<type>/<slug>` with an allowed prefix
      (`feat/ fix/ docs/ chore/ test/ refactor/ perf/ bridge/ group/
      contributor/ hotfix/ release/ agent/`).
- [ ] PR title or body references the issue (`Refs #N` / `Closes #N`).
- [ ] PR body follows the task-contract template: `## Summary`, issue claim,
      **Test Evidence** section with the exact verification commands and their
      output (GUARD-EVIDENCE).
- [ ] `Closes #N` rides in the **commit message** (squash doctrine — the PR
      body copy is belt-and-suspenders; a body-only keyword leaves the issue
      open after landing, AGENT_RULES U8).
- [ ] Diff stays strictly inside the declared Touching Files; protected paths
      (`.github/`, `docs/ledger/`, `docs/master_docs/`, `prisma/`,
      credential/key/env patterns) untouched (GUARD-SCOPE).
- [ ] Bridge lane: total diff ≤ 200 KB, ≤ 30 files, summary length kept
      title-safe.
- [ ] No secrets or credential-shaped literals — including inside
      documentation and test fixtures.
- [ ] Local verification green before pushing: reflection check
      (`git diff --stat` matches declared scope), boot smoke, relevant test
      suite — for agent-loop work, `continuous_agent_loop.py --verify-only`.
- [ ] Board-freshness re-check at completion (#4177) recorded in the handoff.

**Post-submission:**

- [ ] Watch the Merge Gate's PR comment: `LANDED ✓` or `BLOCKED` with the
      reason.
- [ ] On **HOLD**: read `healing_instructions` and fix every `automatable: true`
      item; push (a new head SHA re-runs the full evaluation — U5 freshness,
      never force-push).
- [ ] On **REJECT**: do not patch the rejected head; submit a clean, corrected
      PR (and yield to any PR that already covers the issue — U4).
- [ ] Never push stale work or force-push (Zero-Force-Push doctrine,
      [docs/INGRESS_SECURITY_POLICY.md](./INGRESS_SECURITY_POLICY.md)).

A PR that passes every gate lands autonomously; the issue auto-closes from the
squash commit message; the bridge dispatch ports the landed work to the private
pipeline. **Zero admin touches.**

## 5. Failure taxonomy — what holds a landing and how it heals

| Symptom | Gate that fired | Healing path |
|---|---|---|
| Branch rejected | Branch Naming Guard | Rename branch (new PR) with allowed prefix |
| "must reference an issue number" | Issue Reference Guard | Add `Refs #N` / `Closes #N` to title or body |
| Competing PR detected | Anti-Duplicate PR Guard (U4) | Yield to the existing PR; contribute on its branch only if abandoned |
| Proprietary path/content | Boundary Sanitization Guard | Remove the path/content; private-only work never lands publicly |
| Secret flagged | Secrets Scan / bridge intake | Remove the literal; re-run locally before resubmitting |
| Scope drift | Guardian `scope_boundary` (REJECT if protected) | Shrink diff back to Touching Files |
| Missing/weak evidence | Guardian `test_evidence` (HOLD) | Add reproducible Test Evidence, push new head SHA |
| Merge conflicts | Merge Gate `BLOCKED` | Rebase on fresh `main`, push |
| Checks flaky/red | Merge Gate watch (fail-closed) | Fix root cause; never bypass the gate (U6) |

## Related Documents

- [AGENTS.md](../AGENTS.md) — agent entrypoint; §2.1 Zero-Admin policy + pathways
- [AGENT_RULES.md](../AGENT_RULES.md) — U-rules; §15 fail-closed guard list
- [docs/GUARDIAN_EVALUATION.md](./GUARDIAN_EVALUATION.md) — normative Guardian verdict rules
- [docs/CONTRIBUTING.md](./CONTRIBUTING.md) — submission paths, caps, protected paths
- [docs/AUTONOMY_LOOP_CONTRACT.md](./AUTONOMY_LOOP_CONTRACT.md) — the continuous loop contract
- [docs/INGRESS_SECURITY_POLICY.md](./INGRESS_SECURITY_POLICY.md) — Zero-Force-Push and ingress policy
