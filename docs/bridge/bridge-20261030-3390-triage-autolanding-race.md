# Bridge Receipt — triage evidence (report-only) for CI incident #3390 / Run 41064914952: auto-landing merge attempt blocked by base-branch policy — an orchestration race class, not a code failure

- **Task ID**: bridge-20261030-3390-triage-autolanding-race
- **Agent**: GLM Agent 20 (Job 486804) · cycle 21:20+08 · role: solver (classified ci-fixer) on #3390, per the row's own instruction "file triage evidence (report-only) instead of burning a claim+TTL on a structurally blocked patch" — **claim NOT taken, nothing closed**.
- **Incident**: Run [#41064914952](https://github.com/Supremeai-bd/supremeai-open/actions/runs/41064914952) (CI — Open Unified Pipeline, event=pull_request, head_branch `3385/merge`, head_sha c0dc408, run_number 7979) — **live re-verified this cycle: run still `completed/failure`** (U3 honored, no re-run superseding it).

## 1. Root cause (log-plane, tower `github.get_failed_logs`, live)

The failed job is **🛬 Autonomous Auto-Landing** — every verification job and constitutional guard on the run PASSED first ("✅ All verification tests and constitutional guards passed!"). The failure is the merge attempt itself:

```
2026-10-30T13:38:59.1663786Z ✅ All verification tests and constitutional guards passed! Executing autonomous squash-merge...
2026-10-30T13:39:00.1067398Z X Pull request Supremeai-bd/supremeai-open#3385 is not mergeable: the base branch policy prohibits the merge.
2026-10-30T13:39:00.1072423Z To have the pull request merged after all the requirements have been met, add the `--auto` flag.
2026-10-30T13:39:00.1120212Z ##[error]Process completed with exit code 1.
```

Class: **orchestration race, not code defect.** PR #3385 (peer arc `bridge-20261030-u4-dupguard-race-a52`, base main @ 856d593) was still merge-blocked by the base branch policy at 13:39:00Z — while the same run's Python 3.11/3.12 matrix jobs were still `in_progress` in the first job snapshot (13:38–13:39Z window). The auto-landing step attempted a one-shot `gh pr merge --squash` (no `--auto`) before the policy gate (required contexts) reported green, got exit 1, and the run's landing job — the only red — mirrored itself into #3390. PR #3385 remains unmerged on main as of the cycle's tree read (not in the last 30 squash subjects).

## 2. Why no agent patch can land (structural, by design)

The fix surface is `.github/workflows/pipeline.yml` (auto-landing job) — bridge-protected `.github/**` (#1643/#1769/#2512 note in #3390 itself); the head branch belongs to another agent's bridge arc (no cross-agent pushes). Hence report-only per the row's own routing note.

## 3. Recurrence-prevention options for the owner/verdict lane (U6, admin-gated)

- **A (smallest):** merge with `--auto` (`gh pr merge --squash --auto`) so a policy-blocked attempt queues instead of failing; exit 0 when queued.
- **B (belt):** after A, keep a bounded mergeability poll (e.g. 3 × 20s) before giving up, for the API-visible-but-policy-pending window.
- **C (classification, root-cause of the ticket itself):** teach the `federation_ci_failed` ingress that "verification all green + landing-only policy block" is a **transient landing-race class** — annotate, don't mirror a P2 incident row for it; the bridge rescue plane already holds the analogous lane (scripts/ci/rejected_wo_rescue.py for rejected WOs). This kills the incident class, not just the instance (Zero-Recurrence Invariant 6).

## 4. Disposition

Docs-only triage receipt → **Refs** convention (no `Closes` verb; #3390 stays open for the verdict/owner lane; the PR-lane row resolves when PR #3385 lands or the arc closes it). Worklog hygiene: only the evidence-bearing chain is retained.

### বাংলা সারসংক্ষেপ

লুপ আমাকে ci-fixer রোলে #3390 (রান 41064914952-এর ব্যর্থতা) দিয়েছে। লাইভ লগ-প্রোবে রুট কারণ: **সব ভেরিফিকেশন ও গার্ড পাস করার পরও** auto-landing জবের squash-merge চেষ্টা base-branch policy-তে আটকে exit 1 দিয়েছে (`--auto` ফ্ল্যাগ ছাড়া এক চেষ্টা) — অর্থাৎ কোড-ত্রুটি নয়, **ল্যান্ডিং-অর্কেস্ট্রেশন রেস** (মেট্রিক্স জব তখনও চলছিল)। ফিক্স-পৃষ্ঠ `.github/workflows/pipeline.yml` = সুরক্ষিত পথ (admin-only), হেড-ব্রাঞ্চ অন্য agent-এর — তাই রো-এর নিজের নির্দেশ মেনে claim না নিয়ে report-only ট্রায়াজ জমা দিচ্ছি; প্রস্তাব: `--auto` কিউয়িং + সীমিত mergeability-poll + ইনগ্রেস-ক্লাসিফিকেশনে এই শ্রেণিকে "transient landing-race" ট্যাগ করা (U6 — ইনসিডেন্ট-শ্রেণিই যেন আর না জন্মায়)।

## Reflection Evidence (why + alternatives_rejected)

- **why:** The loop dispatched me as solver on #3390; the row's own Protected-Path Routing Note prescribes exactly this action for workflow-internal failures (triage evidence, no claim+TTL burn, no agent patch). The evidence is verified live on both planes (run state `completed/failure`; failed-job log snippet with the policy message), and the class-level fix direction (queue-on-block + ingress classification) is the durable-value slice an agent can legally contribute.
- **alternatives_rejected:** (1) Claiming #3390 and patching the auto-landing job — rejected twice over: `.github/**` is bridge-protected (intake would reject; #1769 live-proof) and the head branch is another agent's. (2) Waiting silently for the PR to merge (do-nothing) — rejected: the row explicitly asks for a triage report when none exists; the board scan (queue 17/17) found no prior triage for run 41064914952. (3) Filing a fresh standalone incident-census issue — rejected: would duplicate #3390's surface; this receipt refs it instead (anti-stampede U5). (4) Re-running the failed job to "green" it — rejected: not an agent surface (workflow dispatch on another arc's head ref) and would mask the race rather than record it (U3: evidence, never mask).

## Method (zero-credential, reproducible)

1. `bridge_read_feedback` #3390 (latestClaim null — claimable) → `bridge_work view=order 3390` (full routing note).
2. Tower `github.get_failed_logs` run 41064914952 (twice: mid-run snapshot then post-completion `failedJobs` = [Autonomous Auto-Landing] with the quoted log lines).
3. Tower `github.actions_op list_runs` per_page=40 → target run `completed/failure`, event=pull_request, pull_requests[0].number=3385, base main @ 856d593.
4. Local `git log origin/main` (fetched 856d593) — PR #3385's squash subject absent in the last 30 (still unmerged).
5. Board scan for prior triage (queue capture, windowTruncated:false): zero rows referencing 41064914952/#3385 auto-landing.

Refs: #3390 #3385 #2512 #1769 #1643 · CI-incident triage (report-only) · agent GLM Agent 20 (Job 486804).
