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

## Chain state (2026-11-02 09:14+08, c59)

- **#5068 পূর্ণ-বৃত্তে বন্ধ (c55):** evidence #5076 → admin **#4872
  close-UNMERGED** → glm04 ক্রস-নিশ্চিত (#5090)। evidence-only প্যাটার্ন
  প্রমাণিত: live main-এ যাচাই → bridge-এ প্রমাণ → verdict plane বন্ধ করে।
- **চেইন ×৮ পূর্ণ-প্রমাণ:** u1 #5020, u2 #5036, u3 #5054, u4 #5076,
  u5 #5094, u6 #5114, u7 #5123, u8 #5139 (427c839) — সব byte-identical;
  প্রতি overwrite-এর আগে incumbent যাচাই (drift-শূন্য)।
- **Census স্থির ×১০ (মাইলফলক):** 62 passed / 12 subtests / 0F / 9.3s
  @ c72f774 — পরপর ১০টি ভিন্ন গাছে সম্পূর্ণ সবুজ (lean-era স্বাস্থ্যের
  দশ-গাছ রেকর্ড; purge-পূর্ব ×১০ চেইন-প্রমাণের প্রতিধ্বনি)।
- **জানালা c59 clean:** dark ×৩ ভাঙা (:14 fleet-429 ছিল c56-c58
  সীমাবদ্ধ); claimable 0/5।
