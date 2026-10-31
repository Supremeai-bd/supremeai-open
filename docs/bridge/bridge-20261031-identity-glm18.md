# GLM Agent 18 — Worklog (Job ID 486801)

> ছোট receipt ফাইল (durable facts only), প্রতি সাইকেলে in-place replace;
> পুরনো সাইকেল-বিবরণ মুছে শুধু গুরুত্বপূর্ণ অংশ থাকে (keep-it-small চুক্তি)।

## Durable outcomes (সংক্ষেপ)

- Registration: GLM Agent 18 / Job 486801; প্রতি সাইকেলে loop-dispatch (U7)।
- **r1 LANDED (PR #4224, merge fb26520; WO #4223 bridge:landed)** — প্রথম
  landing; slot z.ai-18 heartbeat রেজিস্ট্রে যুক্ত।

## Cycle 2 (2026-10-31 15:18+08) — no-pick clean-hold; board-drain regime নিশ্চিত; কোনো কোড এডিট নেই

- Loop bare ×১ + rebase ladder: work-start rebase 10 behind সারিয়েছে;
  চক্রের ভেতরে আরও ২ landing এসে loop-start auto-rebase আবার সারিয়েছে
  → pre-push tip 556e3f5 (0 behind)। claimable 0/5 → observation idle;
  zero open P0 blocker; PR-plane dark (github.list_prs roster-এ নেই)।
- **Board-drain regime CORROBORATED (root-cause cure লাইভ)**: GLM 11
  r14-এর integrity-certified খালি বোর্ড ধরে রাখা হয়েছে — 07:22Z ফেচে
  totalOpen=1, একমাত্র row নিজেই GLM 11-এর r14 receipt (#4234, +5 min)।
  আগের ২২-row ghost plane ~15:05+08-এ drain; ০ কমেন্ট সহ পুরনো rows
  (#4083 +295 min পর্যন্ত) সব বন্ধ — ghost-closure অন্ধত্বের সমাধান
  tool-side census ফিক্সে (GLM 11 r13)।
- **Red-census at-tip (full suite): 2 failed, 2234 passed, 13 skipped,
  21 subtests, 67.10s** — CVE-guard pair একমাত্র red (maintainer-lane,
  #4150 routing, agent action নয় U5); passed 2230 → 2234 (নতুন hermetic
  health test #4232 এসেছে, live Render probe সরানো হয়েছে — flake cure)।
- verify-only 9/9 PASS (constitution freshness gate PASS)।
- Sandbox নোট: এই মেশিনে exec-bit আলাদা হওয়ায় rebase-এর আগে
  core.fileMode false না দিলে ৪২১৪-ফাইল phantom mode-diff rebase আটকায়
  — machine-local কনফিগ, repo defect নয়।
- r2 = এই প্যাচ (in-place replace; চক্র ১-এর বিবরণ মুছে ফেলা হয়েছে,
  শুধু landing pointer রাখা হয়েছে)।

## পরের agent-এর জন্য নোট (এই slot)

- ফাইলটি প্রতি সাইকেলে in-place replace + baseSha CAS pin করো (fail-closed
  gate; পুরনো blob sha পুরোনো হলে STALE_BASE_ERROR)।
- Full suite 2F/2234P আশা করো যতক্ষণ না maintainer CVE-guard lane মীমাংসা
  করে; lockfile unilaterally bump নয় (U5/U10)।
- Board এখন খালি-স্বাভাবিক (drain regime): নতুন row = নতুন agent-এর নিজের
  receipt হলে সেটা ghost নয় — per-row taskId যাচাইই work-truth (R94)।
- Receipt prose-এ executable string / flag quote এড়াও (WAF 403)।
