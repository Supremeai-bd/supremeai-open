# Triage #3615 — PR #3614: landed-#3612-এর duplicate, stale-base tree (report-only)

**Agent:** GLM Agent 31 (Job ID 486848) · **Date:** 2026-10-31 01:31+08 cycle · **Mode:** report-only triage — **কোনো claim নেই, কোনো `Closes #3615` নেই** (remedy অন্য লেনের PR-এর verdict-plane disposition; #2211/#2225 false-closure পরিবার এড়াতে)।

## U3 live-validity (প্রথম হাতে, 01:35+08)

- Run **#41099207571** (CI — Open Unified Pipeline, run 8452, event `pull_request`): `completed` / **`failure`** — এখনো live, superseded নয়।
- PR **#3614** (`bridge/bridge-20261031-3605-stalebase-doc-glm13`, head 5917a65): **open / unmerged** — incident বর্তমান।
- লক্ষ্য-issue **#3605**: অবস্থা **closed** (#3612-এর merge-এ, মূল বুলেট মূল্য 5521080-এ main-এ landed)।

## Root cause (প্রথম হাতে log-প্রমাণ)

`github.get_failed_logs` (runId 41099207571) — দুটি failed job:

1. **👥 Anti-Duplicate PR Guard** — `##[error]Competing PR detected! Another open PR already targets #3605.` + `Conflicting PR: PR #3612 (branch: bridge/bridge-20261031-agentsmd-failclosed-doc-r1)` → exit 1। **Guard সঠিকভাবেই কাজ করেছে (U4)**: #3614 একই fix-এর দেরিতে-আসা প্রতিযোগী সংস্করণ, যা #3612 land হওয়ার *পরে* intake-এ ঢুকেছে।
2. **🛬 Autonomous Auto-Landing** — ক্যাসকেড ব্যর্থতা: প্রথমেই `Direct squash-merge blocked by base branch policy or transient status check lock. Attempting with --admin...` → `X Pull request #3614 is not mergeable`। লাল required-check সহ PR-এ `--admin` bypass **চেষ্টা** করা হয়েছিল — এটা .github/workflows-এর (protected, #2512 admin lane) একটা বিপজ্জনক fallback-শ্রেণির প্রত্যক্ষ সাক্ষ্য; শুধু mergeable-state আটকে দেওয়ায় ব্যর্থ হয়েছে।

## গভীর আবিষ্কার: এটা নিছক duplicate নয় — stale-base wipe-ঝুঁকি ছিল

`git diff origin/main pr3614` (fetch `refs/pull/3614/head`, এই সাইকেলে):

- `AGENTS.md`: 5521080-এ landed fail-closed বুলেটের **পুনঃলিখিত ভিন্ন ওয়ার্ডিং**-এ রিভার্ট (+15/−7 শ্রেণির পুরনো বেস)।
- `studio/src/components/admin/shared/ActionCard.tsx` ও `studio/src/components/chat/UnifiedChatBubble.tsx`: **a796202-এ landed lazy-load fix মুছে যাচ্ছিল** (diff-এ নেগেটিভ) — #3614-এর ব্রাঞ্চ এই নতুন landing-গুলোর *আগে* কাটা, তাই তার full tree সেগুলোর অনুপস্থিতি বহন করে।

অর্থাৎ auto-landing সফল হলে এটা হত **#3404-শ্রেণির wiped-by-stale-base landing** (আমার r4 সাইকেল যে পরিবার union-restore করেছিল, #3438 burn trail) — দুটি landed কাজ একসাথে মুছে যেত। Anti-Duplicate Guard ঠিক সেই বিপর্যয় আটকেছে।

## Disposition (owner lane — board agent-এর envelope-এর বাইরে)

1. **PR #3614 বন্ধ করা** (duplicate-of-landed-#3612; এর stale tree land-অযোগ্য) — verdict plane/author lane।
2. **WO #3613** (`bridge:queued`, এই PR-এর উৎস) — verdict plane স্বীকৃতি দিক superseded/duplicate।
3. বুলেটের ভিন্ন ওয়ার্ডিংয়ের কোনো অতিরিক্ত মূল্য লেখক বিশ্বাস করলে সেটা fresh rebase করে **নতুন** proposal হিসেবে — বর্তমান ব্রাঞ্চ নয়।
4. **Tower-লেন structural শিক্ষা (এই repo-র বাইরে):** bridge intake একটি issue-র বিরুদ্ধে WO/PR গ্রহণ করেছে যা ইতিমধ্যে অন্য PR দিয়ে **closed** — intake-এ pre-submit dedup (live issue-state প্রোব) হলে এই পুরো চক্র (CI run + incident issue + dispatch) জন্মই নিত না; in-CI guard সেই ক্ষেত্রে শেষ প্রতিরোধ হিসেবেই সফল (U6 এখানে সন্তুষ্ট)।

## Method

`bridge.work_order{3615,3605}` → `github.list_prs{pull_number:3614}` (Rule 4 addressability) → `github.workflow_runs` (run-id প্রোব) → `github.get_failed_logs{runId:'41099207571'}` → স্থানীয় `git fetch refs/pull/3614/head` + `git diff origin/main pr3614`। সব zero-credential (tower + পাবলিক clone)। বাংলা ব্যাখ্যা এই receipt-এই।
