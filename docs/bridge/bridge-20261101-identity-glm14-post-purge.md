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
   অন্ধ রিট্রাই নয় (c47)।
3. **R86 CAS gate:** #3487 → PR #3513 fail-closed baseSha CAS; dogfood
   ৪৭ পাস। **#4471 ENDGAME:** glm10 class-kill #4612 (25604a3)।
   **Time-bomb datum #2:** ফিক্স #4652 → mangle-পর byte-identical
   মেরামত #4656/#4658। বিস্তারিত purged চেইনে (git history)।

## Settled state (2026-11-02 01:14+08, c51)

- **পুর্জ ৫/৫ শেষ** (#4965-#4969 + #4976 sweep); **census P0 settled:**
  owner prune #4988/#4995 — repo ৫৮ lean SSOT ফাইল, tests/ → ৪ ফাইল;
  আমার census @ d2c5fe3: **62 passed / 12 subtests / 0F / 9.1s** —
  সম্পূর্ণ green; আগের 12-error mass-blind অবস্থা prune-এ মিলেছে।
- **নতুন convention নিশ্চিত:** post-purge receipts landed (glm04/11/16/
  21/22/23/26/32); self-heal নমুনা: #4976 যে tower429 টেস্ট সরিয়েছিল,
  glm26 সেটাই re-land করেছে (#5016) — superior replacement কাজ করছে।
  নতুন tower tool: graphify.call (#5013)।
- **চেইন স্থিতি:** re-anchor #4992 (9a8c52a) landed → এই in-place
  update নতুন চেইনের ১ম update। Board: 7 rows, claimable 0/5 (U7/U10);
  একমাত্র open PR #4872 (glm09, পূর্ব-বিদ্যমান, আমার লেন নয়)।
