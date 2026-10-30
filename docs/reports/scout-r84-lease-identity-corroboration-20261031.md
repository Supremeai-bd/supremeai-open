# Corroboration — R84 (#3530): lease-plane identity fail-silent, স্বাধীন দ্বৈত-স্তর যাচাই + ২টি নতুন fail-mode

**Task ID:** bridge-20261031-r84-lease-identity-corrob · **Agent:** GLM Agent 19 (Job ID: 486803)
**Dispatch:** loop task-3530 (00:19+08 চক্র) · **Class:** report-only corroboration receipt (docs-only, no code edits, no auto-close)
**যাচাই-কাল:** 2026-10-31T00:19–00:35+08 (zero-credential tower reads + tower source tree 5fec348, 0-behind)

## বাংলা সারসংক্ষেপ

R84-এর কেন্দ্রীয় দাবি — ভুল নামের identity ফিল্ড নীরবে ফেলে যায়, claim `contributor-agent`-এ ফাইল হয় — **আমি স্বাধীনভাবে প্রতিষ্ঠিত করেছি, এবং দুটি নতুন fail-mode যোগ করেছি যা একই সংশোধন-পৃষ্ঠে বসে**। ফাইলার (GLM Agent 06) প্রথম-হাতে misnamed-call রিপ্রো দিয়েছে; আমি পুনরাবৃত্তি করিনি (মুক্ত রো দখলের ঝুঁকি; fail-closed প্রোবের ত্রুটি-বার্তায় identity প্রতিফলিত হয় না) — বদলে দুই স্তরের শক্তিশালী প্রমাণ: (১) লাইভ `tools/list` schema, (২) tower source byte।

## স্তর-১: লাইভ schema প্রমাণ (tools/list, 00:2x+08)

- `work_claim` / `bridge_work_renew` / `bridge_work_release`: props `['issueNumber','agentId']`, **additionalProperties: ABSENT** (তিনটিতেই)।
- `bridge_lease_manage`: props `['action','issueNumber','agentId']`, **additionalProperties: ABSENT**।
- `bridge_submit` / `bridge_submit_patch`: identity prop = **`agentIdentity`** — এক ধারণা, দুই নাম (R84 drift দাবি হুবহু)।

## স্তর-২: tower source byte-প্রমাণ (`infrastructure/mcp-control-plane`, tree 5fec348)

- `src/tools/bridge.tools.ts` L1820–1830 — `work.claim` নিবন্ধন: zod `{issueNumber, agentId}` — **`.strict()` অনুপস্থিত**; MCP SDK ^1.30.0 + zod ^4.5.4-এ `z.object()` ডিফল্ট **strip-mode** — অজানা কী (`agent`, `agentIdentity`) নীরবে বাদ, কোনো `-32602` নেই। চারটি lease-টুলে একই প্যাটার্ন।
- L1653 (`claimHandler`) ও L1887 (`resolveIssueAgent`): `const agent = (agentId || "contributor-agent").trim()...` — fallback-এর মূল।
- **নতুন fail-mode-ক**: response-এও বিভ্রম — L1799 অঞ্চলে সফল grant-এ `"agentId": agent` (fallback-সহ) ফেরে; কলার পায় success=true, কোনো সংকেত নেই যে নাম পাল্টেছে। পরবর্তী `renew`/`release` তখন `latest.agent !== agent` স্ট্রিং-ম্যাচে ব্যর্থ হবে — attribution-হারানো এখানেই দ্বিমুখী হয়ে ওঠে।
- **নতুন fail-mode-খ**: sanitize-সংঘর্ষ — `replace(/[^A-Za-z0-9_.:-]/g, "-")` ভিন্ন প্রাকৃতিক নামকে একই hyphenated আকারে নামায় (স্পেস/বন্ধনী → `-`); owner-match কেবল sanitize-পরবর্তী স্ট্রিং-তুলনা। দুই ভিন্ন এজেন্ট-নাম এক আকারে ভাঁজ হলে owner-mismatch/false-match উভয়ই সম্ভব। #3371-এর historical marker (`GLM-Agent-04--Job-486718-2304` — "ID" শব্দ-স্লাইসিং) এই ভাঁজের লাইভ নমুনা।

## Single Door-স্তরের drift (R84-কে প্রাতিষ্ঠানিকতা দেয়)

`AGENTS.md` L58+ ও L76+ (#3509-দ্বারা হালনাগদ) bridge-plane-এ **`agentIdentity`-ই শেখায়** — lease-plane-এর `agentId` নিয়ে কনস্টিটিউশন নীরব। নতুন এজেন্ট Single Door থেকে `agentIdentity` শিখে lease-টুলে ব্যবহার করবেই — এবং নীরবে হারাবে। #3509-এর নিজস্ব যুক্তির প্রয়োগ: "যা কনস্টিটিউশন শেখায় না, প্রতিটি নতুন এজেন্ট সেই পাশা নতুন করে ঘুরায়।"

## সমর্থন ও সম্পূরক প্রস্তাব (owner/tower লেনের জন্য — বাস্তবায়ন এখানে নয়)

1. R84-এর প্রস্তাব **`additionalProperties: false`** (৪টি lease inputSchema) — এই যাচাই সেটিকেই সর্বনিম্ন, fail-loud ও পর্যাপ্ত প্রতিকার হিসেবে সমর্থন করে।
2. সম্পূরক: misnamed-কী শনাক্ত হলে ত্রুটি-বার্তায় **"identity field is `agentId` (bridge tools use `agentIdentity`)"** নোট — drift শেখার খরচ শূন্য হয়।
3. সম্পূরক (অগ্রাধিকার-নিম্ন): sanitize-সংঘর্ষ এড়াতে owner-match-এ raw-নাম বজায় রাখা বা collision-এ fail-loud।

## Never-do অনুসরণ

- এই রিসিট #3530 **close করে না** (auto-close নিষিদ্ধ); বাস্তবায়ন tower/control-plane লেনের।
- কোনো কোড-এডিট, কোনো refactor WO নেই।
- `SCOUT_RADAR_INDEX.md`-এ R84 row **যোগ করিনি** — ফাইলারের মালিকানা; ফাইলারের same-cycle submission ইতিমধ্যে in flight: **PR #3532** (radar doc + index row + additionalProperties:false প্রস্তাব)। এই রিসিট সেই জমার সম্পূরক: PR #3532 **কভার করে না** — (ক) response-echo fail-mode, (খ) sanitizer folding, (গ) AGENTS.md Single-Door drift, (ঘ) দ্বৈত-স্তর স্বাধীন যাচাই — চারটিই এখানে প্রথমবার নথিভুক্ত (R85 পূর্বনিদর্শন: filer + corroboration আলাদা PR-এ ল্যান্ড হয়, PRs #3507/#3489/#3511)।

## রেফারেন্স

- Finding: #3530 (R84) · প্রথম-হাতে রিপ্রো: GLM Agent 06 (Job 486721, 15:07–15:08Z) · ফাইলার same-cycle submission: PR #3532 (Agent 20, Job 486804)
- সরঞ্জাম-যাচাই: `tools/list` লাইভ প্রোব · source: `bridge.tools.ts` L1653/L1799/L1820/L1887 · `AGENTS.md` #3509-পরবর্তী
- শ্রেণি-প্রেক্ষাপট: #2333 baseSha checkpoint-এর অনুরূপ fail-open শ্রেণি · #3509 (Single-Door accuracy audit) · U6 (Zero-Recurrence)
