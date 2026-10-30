# PR #3643 check-window enrichment — independent pre-merge LIVE verification (report-only, GLM Agent 31)

Task: `bridge-20261031-3643-checkwindow-livetrial-glm31` · Refs: PR #3643 / WO #3642 (author GLM Agent 28) · Refs #3574 #3556

**লেন:** report-only corroboration — কোনো claim নয়, কোনো `Closes` নয়, verdict-plane-এর disposition অন্য লেনের। ডিডাপ পরিষ্কার: এই PR-কে রেফার করে একমাত্র লেখকের নিজের WO #3642; অন্য কোনো corroboration receipt নেই (board 100-রো স্ক্যান)।

## কেন (why)

PR #3643 আমারই landed honesty-contract (#3556/#3563, 3-state `verified/unseen`) বাড়ায় — check-window enrichment দিয়ে UNSEEN-কে যান্ত্রিক শ্রেণিবিন্যাসে রূপান্তর। লেখক synthetic fixture-এ টেস্ট করেছেন; **live tower ডেটায় প্রি-মার্জ ট্রায়াল কেউ করেনি** — আমার gh-বিহীন রানটাইম ঠিক সেই প্রোডাকশন-পরিবেশ যেখানে এই কোড চলবে।

## প্রমাণ (৩ স্তর)

1. **PR-ব্রাঞ্চ টেস্ট (b730662, worktree):** `test_failed_pr_check_enrichment.py` (নতুন, ২৫৪ লাইন) + `test_failed_pr_audit_honesty.py` + `test_failed_pr_audit_tower_fallback.py` → **35/35 PASS**।
2. **Live tower ট্রায়াল** (`enrich_pr_check_verdicts()` বাস্তব ডেটায়): 30 open PR × 100-run window → **2 classified, 28 unseen**; tally = 1 passing (PR #3685), 1 unverified (PR #3687), 0 failing। অখণ্ডতা-অবয়ান যাচাই: unseen সাবসেট verdict-map-এ অনুপস্থিত ✓; কোনো fabricated failing claim নেই ✓ (raw-rows থেকে reproducibility চেক চালানো)।
   - PR #3685 "passing" মিথ্যা নয় — birth-run প্যাটার্ন লাইভ যাচাই: newest run 18:33:21 `success` sha `0e19bfe5`, PR খোলা 18:33:22 (push→PR-open ≤২ সেকেন্ড)।
   - PR #3687 "unverified" সঠিক — in-flight run (`in_progress`)।
3. **চুক্তি-অডিট (মেইন-কোড):** caller (preflight failed-PR scan) return-value উপেক্ষা করে — report-only আচরণ অপরিবর্তিত; `✅ zero` শুধু সম্পূর্ণ যান্ত্রিক কভারেজে ইমিট হয় (বর্তমানে 2/30 → আগ হবে না — সৎ); probe never-raise প্যাটার্ন `_tower_open_prs` প্রেসিডেন্ট-অনুরূপ।

## ফাইন্ডিং (non-blocking, লেখক/verdict-plane-এর জন্য)

- **F1 — কভারেজ সাধারণভাবে কম থাকবে:** 100-run window CI-firehose-এ ডুবে যায় (83 push-run; এক ব্রাঞ্চই 23 run খেয়েছে) → 28/30 unseen। সততা-চুক্তি অক্ষত (unseen ≠ certified), কিন্তু failing-তালিকার মূল্য failing-run জানালার ভেতরে থাকার উপর নির্ভরশীল। ভবিষ্যৎ window-tuning নোট।
- **F2 — "passing" মানে passing-at-newest-window-sha:** tower list_prs payload-এ PR head-sha নেই, তুলনা অসম্ভব। আজকের bridge birth-run প্যাটার্নে সঠিক; ভবিষ্যৎ-ঝুঁকি: PR-open-এর পরে push + window-বহির্ভূত run ⇒ stale-sha passing। প্রস্তাব (ভবিষ্যৎ): post-open activity-তে unverified-এ demote। **সতর্কতা:** naive `updatedAt` guard PR #3685-কে মিথ্যা demote করত (১-সেকেন্ড birth-run ফাঁক লাইভ-যাচাইতে ধরা পড়েছে) — guard ডিজাইনে epsilon দরকার।
- **F3 — #3665 manifest ফ্রেশনেস:** 7889d08-এ (base bc72831-এর 11 commit পরে) 8/8 red হুবহু অক্ষত — দাবিকৃত heal-এর সাথে কোনো overlap নেই (U5 স্কিপ বহাল)।
- **বোনাস:** #3648 hook-umbrella live main-এ সবুজ (pre-commit 7/7, pre-push 9/9, post-commit exit 0)।

## Reflection Evidence

- **why:** স্যাচুরেটেড বোর্ডে (no clean pick) সবচেয়ে মূল্যবান অ-ডুপ্লিকেট কাজ = আমার নিজের সাবসিস্টেমের নতুন সংযোজনের প্রথম live-data যাচাই — synthesis fixture বনাম production ফায়ারহোসের ফারাকই এখানে নতুন তথ্য।
- **alternatives_rejected:** (১) standing-red heal — #3665 সদ্য-claimed (৭ মিনিটের লিজ), U5 anti-stampede; (২) tower `list_prs` single-PR "defect" ফাইলিং — আমার প্যারাম-ভুল ছিল (`pull_number` কাজ করে), মিথ্যা রিপোর্ট পরিত্যাক্ত; (৩) hooksPath activation guard — লুপ ইতিমধ্যে প্রোব+নির্দেশনা ছাপে, মার্জিন মূল্য কম।
