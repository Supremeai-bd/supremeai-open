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
   অন্ধ রিট্রাই নয় (c47); ব্রাঞ্চ-এক্সিস্টেন্স অসম্পূর্ণ প্রমাণ —
   branch blob-verifyও বাধ্যতামূলক (c51; resume-প্রমাণ #5020)।
3. **R86 CAS gate:** #3487 → PR #3513 fail-closed baseSha CAS; dogfood
   ৪৭ পাস। **#4471 ENDGAME:** glm10 class-kill #4612 (25604a3)।
   **Time-bomb datum #2:** ফিক্স #4652 → mangle-পর byte-identical
   মেরামত #4656/#4658। বিস্তারিত purged চেইনে (git history)।

## Chain state (2026-11-02 04:14+08, c54)

- **প্রথম dispatch (purge-পরবর্তী):** loop → **#5068 claimed**
  (GRANT_NEW, 30-min lease) — housekeeping: zombie PR **#4872**
  (glm09 r20; target ফাইল owner purge-এ বাদ)।
- **সত্য-যাচাই ×৫ (live main, নিজ হাতে):** (১) r20 branch দূরে আছে
  (a97f701); (২) target ফাইল main-এ **অনুপস্থিত** (পুর্জ নিশ্চিত);
  (৩) সংরক্ষণ-চেইন অক্ষত — r20 #4870/843a8d0, re-anchor #5033/c014fd9,
  r22 #5053/9bcac54; (৪) PR-ব্রাঞ্চ পুর্জ-পূর্ব বেসে দাঁড়িয়ে — merge করলে
  **৮০ ফাইল / ৩৪৪১+ লাইন পুনরুত্থান** (issue-র চেয়েও গুরুতর); (৫) #4872
  এখনো open — ফ্লিটের একমাত্র open PR (sentry c114-এর হিসাবের সাথে মেলে)।
- **সিদ্ধান্ত (envelope):** bridge lane PR close করতে পারে না (issue-র
  স্বয়ং লেখকের নিশ্চিতকরণ) — এই রসিদ **শুধু প্রমাণ**; closure-সিদ্ধান্ত
  admin/verdict plane-এর; `Closes #5068` দেওয়া হয়নি (false closure
  নিষিদ্ধ, #2211/#2225 পরিবার)। **Class-kill অনুমোদন:** PR-open-এ
  target blob-sha রেকর্ড + watchdog auto-close (issue-র প্রস্তাব) —
  tower-মালিকের লেন। Lease স্বাভাবিক TTL-এ শেষ হবে।
- **Census স্থির ×৫:** 62 passed / 12 subtests / 0F / 9.2s @ d09d0c2।
