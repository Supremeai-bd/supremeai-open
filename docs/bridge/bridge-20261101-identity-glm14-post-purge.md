# GLM Agent 14 (Job ID 486785) — Post-Purge Re-anchor

> প্রতিষ্ঠাতা-পুর্জ #4965 (Batch 1/5: 308 ফাইল) পূর্ববর্তী চেইন সরিয়েছে
> (r11-r42, `bridge-20261031-identity-glm14.md`)। মালিক-পক্ষের hygiene
> হিসেবে গৃহীত — পুনরুদ্ধার চাইনি। লেন নতুন তারিখ-ধারী পথে ন্যূনতম
> আকারে পুনরারম্ভ (GLM 19/22/32 প্রেসিডেন্ট); পূর্ণ ইতিহাস git-এ।

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

## Post-purge state (2026-11-02 00:14+08)

- Purge-ওয়েভ (#4965-67, #4973/#4974/#4976) মাঝপথে; census mass-blind
  ছিল (81d95bd-এ ১২ collection error → 5bddb5d-এ ৪); heal প্রতীক্ষিত।
- এই ফাইল থেকে নতুন চেইন; প্রতি সাইকেলে in-place replace।
