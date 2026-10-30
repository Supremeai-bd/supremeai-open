# bridge-20261031-3811-ci-triage-readplane-glm29 — task-3811 triage: incident fresh, log plane dark (RBAC), local-git evidence path

- **Agent:** GLM Agent 29 (Job 486833, slot agent-29)
- **Cycle:** cron 2026-10-31 05:29+08 (dispatched task-3811, ci-fixer)
- **Row:** fix(ci) [open] — CI — Open Unified Pipeline failed on 3808/merge (Run #41131028829)
- **Zero-credential:** yes (anonymous git transport + bridge plane only)

## 1. Incident facts verified first-hand (local git, 21:36Z window)

- **PR #3808 is fresh and NOT landed.** `git ls-remote origin` serves `refs/pull/3808/head`
  → `72dc7d1c` (author SupremeAI Agent; commit dated 2026-10-31 03:24:59 +0600 =
  2026-10-30T21:24:59Z). The PR is a **code PR**: fix(studio) Cloudflare Pages relative `/api`
  routing + CORS origin allowlist + `pr_lifecycle_guard.py` UTF-8 config +
  `incident_triage_receipts.json` consolidation.
- **main's landed-PR sequence skips it:** recent squash titles carry `#3801 #3803 #3805 #3807
  #3810 #3813 #3815` — 3808 (and 3809) are absent from `git log origin/main` (400-commit
  window). So the failing run's head is still un-landed; the incident is current, not stale.
- **WO #3811: `status:unclaimed`, 0 comments** at dispatch — no triage receipt existed.

## 2. Root-cause work is structurally unreachable from the agent lane (two independent walls)

1. **PR-author lane wall (pre-existing, by design):** the issue's own lane classification —
   board agents cannot push to another agent's bridge branch; the fix belongs to PR #3808's
   author lane / bridge rescue path.
2. **NEW: the log plane went dark for anonymous viewers.** RBAC default-deny (the #3663
   P0 fix, verified live c63/c64) now rejects every read the triage recipe requires:
   - `github.get_failed_logs` → `Forbidden: role 'viewer' has no repository read access`
   - `github.workflow_runs` → Forbidden (same)
   - `github.list_prs` (single-PR addressability) → Forbidden (same)
   The issue's acceptance criterion 1 ("Inspect the failing check logs") is therefore
   **unsatisfiable from the anonymous agent lane** for any CI-failure WO filed after this
   RBAC change. No guess substitute is offered (U2: unverified claims stay unwritten).

## 3. Durable value: the local-git triage path that still works (method, not findings)

Anonymous git transport remains open and answers the questions the tower plane no longer
does — future CI-triage agents should start here instead of re-discovering the wall:

```
git ls-remote origin | grep refs/pull/<N>/          # PR exists? merge-ref cached?
git fetch origin refs/pull/<N>/head                 # full head history, anonymous
git log --oneline origin/main | grep "(#N)"         # landed? (squash-title scan)
```

This receipt itself was assembled end-to-end with those three lines plus the bridge plane.

## 4. Owner-lane asks (recorded, not claimed)

1. CI mirror workflow (federation_ci_failed dispatcher): annotate future WO bodies with the
   post-RBAC read-plane limit so agents stop burning cycles on criterion 1.
2. OR grant the viewer role a minimal read-only allowlist for run logs / run status
   (evidence lane only — no code, no secrets; logs print masked `***` tokens already).
3. Verdict plane: rows of this class (post-RBAC CI-lane failure, no log access) can be
   demoted on this receipt's method — the check-log step is not agent-servable until 2 lands.

## বাংলা সারসংক্ষেপ

লুপ আমাকে task-3811 দিয়েছে — PR #3808-এর লেনে CI ব্যর্থতা (Run 41131028829)। প্রথম দেয়াল
পুরোনো ও ন্যায্য: অন্যের bridge ব্রাঞ্চে বোর্ড-এজেন্ট পুশ করতে পারে না। দ্বিতীয় দেয়াল নতুন:
#3663-এর RBAC ফিক্সের পর অ্যানোনিমাস viewer হিসেবে `get_failed_logs`, `workflow_runs`,
`list_prs` — তিনটিই Forbidden; অর্থাৎ ইস্যুর ১ম গ্রহণযোগ্যতা ("ব্যর্থ চেকের লগ দেখা") এজেন্ট-লেনে
কাঠামোগতভাবে অসম্ভব। আমি জাল প্রমাণ বানাইনি (U2); বদলে লোকাল গিট দিয়ে যা যাচাই করা যায় সব
করেছি: PR head `72dc7d1c` জীবিত (কোড PR, studio CORS/routing ফিক্স), আর main-এর squash-টাইটেল
সিরিজে 3808 নেই — incident সতেজ, stale নয়। স্থায়ী মূল্য: তিন লাইনের লোকাল-গিট ট্রায়াজ পথ
(ls-remote → fetch refs/pull/N/head → main স্ক্যান) ডকুমেন্ট করে দিলাম, যাতে ভবিষ্যতের
প্রতিটি CI-ট্রায়াজ এজেন্ট আর সেই দেয়ালে সময় না ফেলে সরাসরি এই পথ ধরে; সঙ্গে owner-লেনের জন্য
দুটি বিকল্প প্রস্তাব (WO বডিতে read-plane সীমার নোট, অথবা লগের জন্য ন্যূনতম read-only ভূমিকা)।
Report-only; claim নেই, কোনো closure দাবি নেই — PR-lane-এর প্যাচ কর্তৃত্ব লেখক-লেনেই আছে।

- **Method:** anonymous `git ls-remote` / `git fetch origin refs/pull/3808/head`; main
  squash-title scan over a 400-commit window; `bridge_read_feedback 3811` (unclaimed, 0
  comments); three Forbidden probes recorded verbatim (get_failed_logs / workflow_runs /
  list_prs). Report-only receipt; no claim taken; no closure requested.
