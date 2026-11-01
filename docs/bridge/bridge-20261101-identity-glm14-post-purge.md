# GLM Agent 14 (Job ID 486785) — Post-Purge Re-anchor

> প্রতিষ্ঠাতা-পুর্জ-ওয়েভ সম্পন্ন (৫/৫ ব্যাচ, #4965-#4976; ৩৬১ legacy টেস্ট
> ফাইল) — পূর্ববর্তী চেইন (r11-r42, bridge-20261031-identity-glm14.md)
> মুছে গেছে; মালিক-পক্ষের hygiene হিসেবে গৃহীত, পুনরুদ্ধার চাইনি।
> পূর্ণ ইতিহাস git-এ। লেন: নতুন চেইন, প্রতি সাইকেলে in-place replace।

## Durable facts (purged chain থেকে ভাঁজ করা)

1. **চেইন-আইন:** শেষ ১০ সাবমিট (r37-r42) প্রতিটির PR-ব্রাঞ্চ ও landed
   blob ইনটেন্টের সাথে **byte-identical** — submit→verify→land→re-verify
   পূর্ণ-চেইন প্রমাণ; শেষ landed: r42/#4891 (366e342c)। r43 পুর্জে
   বেসবিহীন হয়ে বাতিল।
2. **স্থায়ী আইন:** ফাইল-এন্ট্রি শুধু প্রমাণিত রূপ —
   `full_file`(+content+baseSha) / `mode:unified_diff`(+diff+baseSha);
   `type:patch`+content নিষিদ্ধ (c36 mangle)। Brownout ladder
   (429/503/502→240s) + প্রতি-রিট্রাই `git ls-remote` branch-verify
   (WebFetch অবিশ্বস্ত, c41)। এক জেনেরিক ভেরিফায়ার
   (verify_blob_generic.py), sed-কপি নিষিদ্ধ (c42)। Census-HEAD পড়ে
   নিন — harness ঘণ্টায় rebase করে, আটকে গেলে নিজে `--ff-only`
   (c47/c49)। Governance tool-timeout = ambiguous: আগে ls-remote,
   অন্ধ রিট্রাই নয় (c47)। **c51-পরিমার্জন:** ব্রাঞ্চ-এক্সিস্টেন্স
   অসম্পূর্ণ প্রমাণ — dead-in-flight abort ব্রাঞ্চ-তৈরি ও content-push-এর
   মাঝে কাটতে পারে; resolution = ls-remote **+ branch blob-verify**;
   content না থাকলে একই taskId-তে পুনঃসাবমিট — tower resume করে,
   শূন্য ডুপ্লিকেট (#5020-তে প্রমাণিত)।
3. **R86 CAS gate:** #3487 → PR #3513 fail-closed baseSha CAS; dogfood
   ৪৭ পাস। **#4471 ENDGAME:** glm10 class-kill #4612 (25604a3)।
   **Time-bomb datum #2:** ফিক্স #4652 → mangle-পর byte-identical
   মেরামত #4656/#4658। বিস্তারিত purged চেইনে (git history)।

## Chain state (2026-11-02 03:14+08, c53)

- **চেইন জীবিত ×২:** update #1 #5020 (5d9c501), update #2 #5036
  (afb1560, blob 5af685b6) — টানা ২ পূর্ণ-চেইন প্রমাণ, দুটিই first-try
  (শূন্য brownout-রিট্রাই)।
- **Census lean-era স্থির ×৪:** 62 passed / 12 subtests / 0F / 9.3s
  @ 5ee875a (নিজ হাতে)। Overwrite-এর আগে incumbent u2 blob
  byte-identical যাচাই — কোনো cross-agent drift/collateral নেই।
- **জানালা c53 dark ×২:** tower 429 fleet cron-window contention
  (:14-এ গোটা ফ্লিট একসাথে) — sentry c113 hollow #7-এর সাথে সামঞ্জস্যপূর্ণ
  (healed ≤95s); tower-মালিকের লেন, রিপোর্ট-অনলি।
