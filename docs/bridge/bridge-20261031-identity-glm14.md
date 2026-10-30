# GLM Agent 14 — Worklog (Job ID 486785)

> পোস্ট-আর্কাইভ receipt (পুরনো ইতিহাস supremeai-archive-এ);
> ছোট ফাইল (durable facts only), প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষেপ)

- **R86 root-cause fix ADOPTED:** #3487 → PR #3513 fail-closed baseSha CAS
  gate; প্রতিটি submit dogfood (এ পর্যন্ত ১১টি পাস)।
- **Cycle 6-১১:** AGENTS.md drift fix (#3605→#3612), studio lazy-load
  (#3606→#3610), P0 #3663 (anonymous = global-admin; #3727 fail-closed),
  shape-4 read-plane finding (#3758/#3759), co-obligation reds heal
  (#3820/#3821), #3853+#3858 স্টেল-রান/লেন triage (receipts #3883/#3898;
  **উভয় wild-যাচাই: #3534 MERGED, tracker-class cure #3931 landed**)।
- Registration: GLM Agent 14 / Job 486785; প্রতি সাইকেলে loop-dispatch (U7)।

## Cycle 12 (2026-10-31 07:14+08) — hold ×2 → #3527 protected-lane remedy

- Loop ×3: প্রথম দুই run-এ zero ACTION (auditor/human-eye; board 48/16-gates/
  zero-P0) → hold; তৃতীয়ত dispatch **#3527** (solver; U5 coverage lapsed হওয়ায়)।
- **#3527 remedy 1 (agent-doable half):** fresh সেনসাস — pipeline.yml-এর ১৫টি
  checkout-ই implicit-persist; ১৪টি নিরাপদে flip-যোগ্য (job-লেভেল বিশ্লেষণ:
  `stale_base_guard` push-মুক্ত প্রমাণিত; `satellite-dispatch-and-sync`-এর
  `|| true` fallback push = documented residual)। প্যাচ locally apply করে সব
  যাচাই সবুজ: guard unpersisted 15→1, self-test PASS, pytest 5/5, fast-lint PASS।
- **Protected-lane সীমা (প্রথম-হাতে প্রমাণিত):** `.github/`-এ bridge lane
  automatic write নেয় না (bridge_intake: never auto-applied → admin review);
  #3931-ও workflow নয়, watchdog script-এ সমাধান করেছিল। Apply-ready প্যাচ
  রশিদে জমা: WO #3948/PR #3949 (Refs-only — admin প্রয়োগের আগে বন্ধ নয়,
  #2211)। Closes/`originalIssueNumber` ইচ্ছাকৃত বাদ।
- **Tower diff-parser চুক্তি (নতুন নথি):** unified_diff hunk-only — `index`
  লাইন reject, `diff --git`+`---/+++` আবশ্যক।
- Refs: #3527 · #3518/#3517 (residual family) · #3931 · #3948/#3949 · U5/U8/U10।
