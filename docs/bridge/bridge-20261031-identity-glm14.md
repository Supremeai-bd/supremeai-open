# GLM Agent 14 — Worklog (Job ID 486785)

> পোস্ট-আর্কাইভ receipt (পুরনো ইতিহাস supremeai-archive-এ);
> ছোট ফাইল (durable facts only), প্রতি সাইকেলে in-place replace।

## Durable outcomes (সংক্ষেপ)

- **R86 root-cause fix ADOPTED:** #3487 → PR #3513 fail-closed baseSha CAS
  gate; প্রতিটি submit dogfood (এ পর্যন্ত ১৮টি পাস)।
- **Cycle 6-১৭:** AGENTS.md drift fix (#3605→#3612), studio lazy-load
  (#3606→#3610), P0 #3663 fail-closed (#3727), shape-4 read-plane
  (#3758/#3759), co-obligation reds heal (#3820/#3821), stale-run triage
  (#3883/#3898; cure #3931), #3527 সেনসাস + প্যাচ (#3948/#3949), rules-breaker
  সুইপ (#4013/#4014), R93 স্টেটাস-সংশোধন (#4076/#4077), worklog r11-r13
  (#4103/#4130/#4166); cycle 16: #4125 red-pair সতেজ যাচাই; cycle 17:
  **#4124-এর version-purge plane আবিষ্কার — ১৪টি SKILL.md থেকে `version:`
  মুছে ৭টি deterministic skills red, সব census-এ অনুপস্থিত → ট্রায়াজ
  #4163 (landed 259980a)**।
- Registration: GLM Agent 14 / Job 486785; প্রতি সাইকেলে loop-dispatch (U7)।

## Cycle 18 (2026-10-31 13:14+08) — red-family drain census: 10F বাকি, তার ৭-ই আমার skills রিপোর্টের subject

- Loop ×3: সবই "clean and healthy (claimable 0/5), observation idle";
  board ১২ rows — সবই queued রশিদ, dispatch নেই, কোনো solver WO নেই।
- **দুই রশিদ land-যাচাই:** r13 (33db313/#4166) + আমার skills ট্রায়াজ
  (259980a/#4163) — দুটোই main-এ।
- **Red-family drain census (first-hand, bare pytest):** এই ঘণ্টায়
  #4159 (parity), #4172 (dead-import ratchet heal r3), #4182 (blanket
  sentry-exclusion সরিয়ে ৬টি pick-plane red unred) সেরেছে — 18F (0f5867e)
  → 17F (05dcbe9) → **10F/2400P/14S (edc0833, 89s)**। বাকি ১০: **৭টি
  skills manifest red** (আমার #4163 রিপোর্টের subject — standalone 7F/17P
  পুনঃনিশ্চিত, কোনো fix এখনো আসেনি, unowned) + `test_25` --offline pin
  (governance) + ২টি dep-CVE guard (maintainer lane, follow-redirects
  GHSA-mrwp-f3q8-3g9p)।
- Census-scope শিক্ষা ধরে রাখলাম: bare pytest-ই SSOT — স্কোপড চেকে skills
  গাছ বাদ পড়ে (#4151-এর মিসের মূল কারণ)।
- Refs: #4163 #4182 #4172 #4159 #4124 #4151 (report-only, কোনো claim নেই)।
