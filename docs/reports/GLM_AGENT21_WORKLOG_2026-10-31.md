# GLM Agent 21 — Worklog (Job 486808)

> Keep-it-small contract: one file, durable facts only, replaced in place
> (compacted) every cycle. Slot `agent-21`, zero-credential lane via MCP tower.

## Durable facts

| Field | Value |
| --- | --- |
| Agent | GLM Agent 21 (GLM/Z.ai, slot agent-21) |
| Job | 486808 |
| Cycles | 3 (2026-10-30 ×2, 2026-10-31) |

## Durable outcomes (প্রমাণসহ)

- **Cycle 1 (10-30 18:21+08) — #2395 per_page ভেরিফিকেশন:** ক্লেইমের পর লাইভ
  প্রোবে per_page সেমান্টিক্স সঠিক প্রমাণিত; কিন্তু ডিসপ্যাচের ৩ মিনিটের মধ্যেই
  PR #3158 একই disposition ল্যান্ড করেছিল (ডুপ্লিকেট-রেস)। লোকাল এডিট বর্জন
  (ট্রি e0c742b-এ byte-identical, guard সবুজ) → পাওয়ার-শূন্য noop রিসিপ্ট
  PR #3183 (মার্জ d0a70ab) — WO #3182 অটো-ক্লোজের সরাসরি সাক্ষী (ড্রেনেজ
  মেকানিজম কাজ করছে)। শিক্ষা: Anti-Stampede GUARD-এ হেরে গেলে কখনো রি-ট্রাই নয়।
- **Cycle 2 (10-30 19:21+08) — #2529 অডিট r+1:** তিনটি ফাইন্ডিংয়ের প্রতিটি
  লাইভ রি-প্রোব (#2511/#2522/#2352 ক্লোজড; Nightly run 41033596302 সবুজ;
  ড্রেনেজ সাইকেল-১ সাক্ষী) — সব রেমিডি প্রোটেক্টেড/কোর-সাইড, এনভেলপে কোনো
  অবশিষ্ট কাজ নেই → evidence-only রিসিপ্ট PR #3234 (STALE-INCIDENT GUARD
  অনুযায়ী রি-সলভড ইনসিডেন্ট রি-মেক নয়)।
- **Cycle 3 (10-31 05:21+08) — ecosystem-scout, R90 রাডার:** বিশ্ব-স্ক্যানে
  **GitHub Agentic Workflows (gh aw / github/gh-aw)** ফাইন্ডিং — CI-ব্যর্থতা
  ট্রায়াজ ক্লাস (একই রাতে #3785-এ ৬টি, #3811-এ ৪+ রিসিপ্ট WO) এর CI Doctor
  রেডিমেড ওয়ার্কফ্লো যান্ত্রিকভাবে সমাধান করে (রিপিট-ফেইলারে নয়েজ নয়,
  update-in-place); WO #3846 + PR #3847 (verdict adapt, admin options A/B/C)।
  একই চেঞ্জে লেজার-মেরামত: invariant-G পিন-ড্রিফট (live main-এ RED: pin 87 ≠
  pointer 89) কো-অ্যাডভান্সে বহন + baseline গার্ডের নিজ `--baseline`-এ
  যান্ত্রিক রিজেন (R88-রিপোর্ট ghost floor-এন্ট্রি ড্রপ)।

## Durable lessons (U6)

- **pass-26 ক্লাস ৫ম পুনরাবৃত্তি, প্রথম-হাতে ধরা:** R89 ফ্রি-ভেরিফাইড হওয়ার
  পরও সাবমিটের আগে fresh queue ক্যাপচারে পিয়ারের issue-side কনজাম্পশন
  (landing 0d32b24) ধরা পড়েছে → first-registration-wins ইয়েল্ড, লেন R90-এ
  পুনঃগ্রহণ। সাবমিট-পূর্ব শেষ মুহূর্তের ফ্রেশ ক্যাপচারই একমাত্র নির্ভরযোগ্য
  প্লেন — পুরনো ক্যাপচার মিথ্যা-সবুজ দেয়।
- **unified_diff ইনগ্রেস:** tower পার্সার hunk-only — git header
  (`diff --git`/`index`/mode লাইন) বাদ দিয়ে `---` থেকে শুরু করতে হয়;
  `"mode": "unified_diff"` প্রতি-ফাইলে ঘোষণা আবশ্যক; summary ≤1000 অক্ষর।
- **false-null ফাঁদ (AGENTS.md Rule 4):** PR-মার্জ যাচাই সবসময়
  `pull_number` অ্যাড্রেসেবিলিটি বা `git log`-এ, list-mode snake_case-এ নয়।
- **viewer লেন ১৮ টুল:** `github.create_issue` নেই — scout-এর defining WO
  bridge_submit-এর অটো-ফাইলই চূড়ান্ত আর্টিফ্যাক্ট।
