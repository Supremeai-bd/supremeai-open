# Audit corroboration — #3354's #1776 closed-'completed' finding reproduces on both planes (independent second-agent pass, tree 6726949)

- **Lane:** #3354 (audit:finding, report-only — reopen ask for the owner/verdict lane) · **Agent:** GLM Agent 19 (Job ID 486803), continuous loop dispatch 2026-10-30T13:19+08, atomic claim `GRANT_NEW` 13:27:58Z
- **Subject:** #1776 (P1-high, admin-lane workflow hardening) is closed with `state_reason: "completed"` while the hardening it demands is byte-absent from live main. Filed by GLM Agent 08 (Job 486735) at ~13:30Z; this pass is the independent re-verification the audit lane expects before an owner acts on the reopen ask.
- **Mode:** zero-credential, report-only, docs-only payload, no close verbs (U4) — the reopen decision stays with the owner.

## 1. Verdict summary

Every load-bearing premise of #3354 reproduces on independent tooling ~12 minutes after filing. Closure plane: two tower JSON reads (`bridge.work_order`, `bridge_read_feedback`, 13:42Z) both return `state: closed`, `stateReason: completed` — matching the filer's 13:30Z REST probe byte-for-byte on the two fields that matter. Byte plane: all four hardening classes are still absent on tree `6726949` (0/29 SHA-pinned `uses:`, 0 `persist-credentials`, the `head_ref` shell interpolation live at `pipeline.yml:364` — the filer's exact "r2 :364" line — and the setup-node-tower action unchanged). One vantage artifact is reported honestly in §3: a single HTML page-read at 13:39Z returned "open" and is outweighed by three machine reads.

## 2. Byte-plane re-check (local `git` on fetched `origin/main` @ 6726949, 13:37–13:41Z)

| Check | #1776 remedy (per #3354) | Filer @13:30Z | This pass @13:37Z | Verdict |
|---|---|---|---|---|
| SHA-pinned `uses:` (`uses: .*@[0-9a-f]{40}`) | 27 pins | 0 (of 28 `uses:`) | **0** (of 29 `uses:`) | corroborated (total-count drift 28→29 does not touch the conclusion) |
| `persist-credentials: false` on checkouts | 15 sites | 0 | **0** | corroborated |
| inline `${{ github.head_ref }}` shell interpolation (duplicate-pr-guard) | de-inject | 1 site, live (`:364`) | **1 site, live — `.github/workflows/pipeline.yml:364`** | corroborated, same line |
| `.github/actions/setup-node-tower/action.yml` | harden | 1,474 B, 1 tag-pinned `uses:`, 0 persist-credentials | **1,480 B incl. trailing newline, 1 `uses:` (setup-node@v5), 0 persist-credentials** | corroborated (6-byte delta = newline counting; profile identical) |

Scanner-plane corroboration on main re-confirmed: `docs/bridge/bridge-20261030-r1776-zizmor-refresh-glm25.md` present on `6726949` (GLM Agent 25's r2 receipt, identical 60-finding profile, "Refs #2766 no close"). One item is honestly NOT verifiable from this runtime: commit `f5ef7a5` (PR #3341) predates the shallow clone's history window — no claim is made about it either way.

## 3. Closure plane (machine reads) and one vantage artifact

| Read | Tool / vantage | Time (Z) | Result |
|---|---|---|---|
| Filer's probe | GitHub REST, GLM Agent 08 | ~13:30 | `closed` / `completed` / `closed_at 2026-10-29T20:45:30Z` == cycle-46 claim-release second |
| This pass ×1 | Tower `bridge.work_order {1776}` | 13:42 | **`state: closed`, `stateReason: completed`** |
| This pass ×2 | Tower `bridge_read_feedback {1776}` | 13:42 | **`state: closed`**, labels `P1-high, status:unclaimed, repo:monorepo` |
| This pass ×3 | HTML page read | 13:39 | "open", no closure events — **outlier**: one LLM page-parse vs three machine JSON reads; the page's own event list ends at the claim release, which under `closed_at == that second` is the stale-render signature, and it is reported here rather than suppressed |

Three machine reads across two independent credentials-free planes agree with the filer; the HTML parse is recorded as a vantage artifact, not evidence. The `closed_at == claim-release-second` signature stands: the P1 closed at the moment its lease released, not when a patch merged — and `completed` (not `not_planned`) asserts a remedy the byte plane cannot find.

## 4. Disposition

The reopen ask in #3354 is **supported and now two-agent-corroborated**: the owner/verdict lane should either reopen #1776 (the hardening is pending; the fresh numbers are in #3354's table, this §2, and the zizmor r2 receipt) or re-label the closure honestly (e.g. moved/superseded with a target lane). This receipt closes nothing: docs-only keep-open contract, `Refs` only. The `status:claimed` marker on #3354 releases immediately after submission; the row stays with its owner.

## 5. Dedup and provenance

- Serves #3354 directly (its audit-lane contract invites exactly this independent pass). Cross-refs without duplicating: #1776 (subject), #2766 (evidence-refresh row, served by the zizmor r2 receipt), #2516/#2100 (verdict-plane context), `bridge-20261030-receipt-wo-pick-exclusion` (this agent's parallel loop-fix lane — unrelated surface).
- Provenance: local `git grep`/`git cat-file` on fetched `origin/main` 6726949 (13:37–13:41Z); tower `bridge.work_order` + `bridge_read_feedback` JSON reads (13:42Z); one HTML read (13:39Z, reported as outlier); no writes, no tool executions, no protected-path access.

## বাংলা TL;DR

লুপ আমাকে #3354 দিয়েছিল — তার premise: P1 #1776 "completed" হিসেবে বন্ধ, অথচ হার্ডেনিং main-এ নেই। আমি স্বাধীনভাবে দুই প্লেনেই যাচাই করলাম: (১) byte-plane — tree 6726949-এ SHA-pin 0/29, persist-credentials 0, head_ref injection pipeline.yml:364-এ জীবিত (ফাইলারের সাথে লাইন-পর্যন্ত মিল), setup-node-tower action অপরিবর্তিত; (২) closure-plane — tower-এর দুটি JSON রিডই বলছে closed/completed, ফাইলারের REST probe-এর সাথে হুবহু। একটি HTML পেজ-পাঠ "open" বলেছিল — তিনটি machine read-এর বিপরীতে সেটি vantage-artifact হিসেবে সৎভাবে নথিভুক্ত। ফলে reopen ask এখন দুই-এজেন্ট-সমর্থিত; সিদ্ধান্ত মালিকের। এই রিসিট কিছুই বন্ধ করে না।
