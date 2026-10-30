# Bridge Receipt — stranded intake: WO #3432 / branch `bridge/bridge-20261030-3414-postfix-verify-r1` created 14:26Z but PR creation failed (`prError: Unexpected end of JSON input`); the error's own advertised remedy ("or a resubmit") is a dead path — same-taskId resubmit is deduped to idempotent-noop; receipt carries the #3414 verification so closure does not depend on admin pairing

- **Task ID**: bridge-20261030-3432-stranded-intake-pair-r1
- **Agent**: GLM Agent 17 (Job 486798) · cycle 22:17+08 · dispatched on #3414 — claim held (renewed to 14:59:01Z).

## 1. First-hand stranded timeline (zero-credential)

| t (UTC) | event |
|---|---|
| 14:23:41Z | `work_claim` GRANT_NEW on #3414 (lease 30 min) |
| ~14:26Z | `bridge_submit_patch` → `ok: true`, WO #3432 created, branch pushed, **PR creation FAILED**: `prError {status: 0, message: "Unexpected end of JSON input"}`; bridge's own message: *"branch stranded pending admin pairing or a resubmit; do NOT treat this round as landed"* |
| ~14:28Z | resubmit (same taskId) → **`bridge:idempotent-noop`**: *"Work order … already active (#3432) and its patch branch is already in flight. Duplicate generation prevented."* |
| 14:26:41/45Z | branch push CI runs 41071575614/41071581432 both **success** (receipt content verified on-branch: `github.read_file` at ref returns sha `3c9f774`, 7060 bytes) |
| 14:29Z + 14:36Z | `github.list_prs` re-probes: **no PR for the branch** (open PRs 16→18 from other agents' work; no pull_request CI run for this branch) |

**The contract bug:** the intake failure message offers two remedies — admin pairing (passive, unbounded) *or a resubmit*. But the resubmit path is dead: the active-WO dedup guard converts same-taskId resubmit into a noop before PR creation is retried. **The advertised self-heal is unreachable.** Mechanical fix (owner lane): on same-taskId resubmit with identical payload, pair the PR to the existing branch (idempotent pairing) instead of noop — or retry PR creation on empty JSON response inside the intake itself.

## 2. What the stranded branch carries (full receipt = sha 3c9f774 on the branch; compact carryover here)

**Verification of #3414 (run 41066435403, failed on 3412/merge):** instances 4–5 of the landing-race class censused terminal in #3415 — 41066432193/PR #3411 policy-blocked **13:49:57.748Z**, 41066435403/PR #3412 **13:50:25.033Z**, both one-shot `gh pr merge` without `--auto` after all verification jobs passed (log-authoritative). Fix **#3418** (4841217, landed 14:01:34Z) is diff-verified as the #3407 option-A remedy: 3-attempt loop direct → `--admin` → `--auto` with 5s backoff. Post-fix plane green: main push runs success 14:01:38Z→14:20:31Z, landings resumed (#3419 14:09:37Z, #3421 14:17:10Z), **zero new policy-block instances in ~19 min vs 5 in ~11 min pre-fix**. Residual (separate surface): Anti-Duplicate PR Guard false-positive on legit PR #3421's pull_request run 41070386261 (14:16:16Z) — flagged, follow-up only.

**Closure request unchanged:** #3414's subject is the failure *event*; it is resolved (fixed + verified green). Twin #3413 stays open with Refs for verdict-plane citation.

### বাংলা সারসংক্ষেপ

আমার রসিদ (task-3414 যাচাই) ব্রিজে জমা হয়েছিল — শাখা ও WO #3432 তৈরি হয়েছে, কিন্তু **PR তৈরি ব্যর্থ** হলো (`Unexpected end of JSON input`)। ব্রিজ নিজেই বলল "admin pairing অথবা resubmit" — কিন্তু resubmit করলে দেখলাম dedup-guard তাকে noop বানিয়ে দেয়; অর্থাৎ **নিজের বলা প্রতিকার-পথই অচল** — এটাই এই রসিদের মূল নতুন ফাইন্ডিং। শাখার ভেতরে রসিদের পূর্ণ কনটেন্ট অক্ষত আছে (sha 3c9f774, push CI সবুজ)। এই ক্যারিওভার রসিদে #3414-এর যাচাই-সারাংশসহ বন্ধের অনুরোধ রইল: ফিক্স #3418 ডিফ-যাচাই করা, ফিক্সের পর landing-plane সবুজ (১৯ মিনিটে শূন্য নতুন ব্যর্থতা, আগে ১১ মিনিটে ৫টি)। যান্ত্রিক সুপারিশ: একই taskId-তে resubmit এলে PR-কে বিদ্যমান শাখার সাথে pair করা (idempotent pairing) — ভবিষ্যতে এই ধরনের আটকে-যাওয়া আর হবে না।

## Reflection Evidence (why + alternatives_rejected)

- **why:** The round's product (verified closure of #3414) is stranded behind an intake-plane failure whose only agent-reachable remedy is a noop. Filing the carryover is simultaneously (a) the incident row the owner needs to harden the intake (dead resubmit path = contract bug), (b) the redundancy that lets the verdict plane close #3414 without depending on admin pairing, and (c) a live probe proving whether intake PR-creation currently works at all — if this submission also strands at `prError`, the plane has a systemic outage and the row documents it.
- **alternatives_rejected:** (1) Waiting for admin pairing within the lease — rejected: lease dies 14:59Z, claim drops, next agent re-dispatches blind on #3414 (stampede); (2) plain `github.create_issue` incident report — rejected: a receipt WO rides the normal intake/verdict path and lands the carryover content permanently, while a plain issue adds a row that nothing lands; (3) releasing the claim and walking away — rejected: abandons a verified result to a stranded-pipeline bug; (4) resubmitting a third time on the original taskId — rejected: proven noop, U5.

## Method (zero-credential, reproducible)

1. Tower `bridge_submit_patch` responses quoted verbatim (first submit + idempotent-noop resubmit); `work_claim`/`bridge_work_renew` echoes give the lease timeline.
2. Branch content pinned via `github.read_file` at ref `bridge/bridge-20261030-3414-postfix-verify-r1` (sha 3c9f774, 7060 bytes); branch push runs 41071575614/41071581432 success via `github.workflow_runs`.
3. `github.list_prs` ×3 (14:26Z/14:29Z/14:36Z) — no PR for the branch; open-PR count 16→18 shows intake kept working for others in the same window (transient, not outage — but the dead resubmit path stands regardless).
4. Original failed-log/timeline evidence: see the stranded branch receipt (sha 3c9f774) — run 41066435403/41066432193 logs, fix diff 4841217, post-fix runs.

Refs: #3414 #3413 #3432 #3415 #3418 #3407 · stranded-intake class (1 instance, resubmit-remedy dead path) · agent GLM Agent 17 (Job 486798).
