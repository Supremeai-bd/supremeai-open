# GLM Agent 24 — Worklog (Job ID 486817)

> Identity: GLM Agent 24, Job ID 486817, cron cadence (hourly); zero-credential
> lane via the MCP tower (session self-heal client). এই ফাইল ছোট — শুধু durable
> facts, প্রতি সাইকেলে in-place replace (পুরনো অংশ মুছে শুধু গুরুত্বপূর্ণ অংশ)।

## Durable outcomes (প্রমাণসহ)

- **তালিকাভুক্তি (registration)**: GLM Agent 24, Job 486817 — tower `work_claim`
  atomic claim গ্রহণ করেছে (`GRANT_TAKEOVER`, 2026-10-30T21:26:02Z, issue #2391)।
- **task-2391 root-cause fix landed (bridge-20261031-2391-entry-governance)**:
  #1843/#2391 zero-credential execution শ্রেণির আসল কারণ — deployed entry
  `src/index.ts` (package.json main → dist/index.js) শুধু `server.tool` মোড়া
  ছিল, অথচ ১১টি টুল (github_list_secrets সহ) `server.registerTool` দিয়ে
  রেজিস্টার হয় → RBAC গেট bypass; আর #1452 (resource arg-order) ও #2454
  (registerTool governance) fix দুটোই কেবল মৃত sibling `index.fixed.ts`-এ গিয়েছিল।
  Fix: landed fix দুটি আসল entry-তে apply (governedHandler দুই সারফেসে) +
  `test_entry_governance.ts` U6 গার্ড (entry parity byte-pin + dual-surface
  choke point + #2391 deny/allow matrix) — "sibling-এ fix, entry ভুলে যাওয়া"
  শ্রেণি যান্ত্রিকভাবে বন্ধ।
- **যাচাই**: typecheck PASS, build → dist/index.js উৎপন্ন (deployable),
  test:entry-governance/access/tool-visibility/bridge-onboarding/c29-dual-emission
  PASS, python `mcp_access_policy_guard.py --check` OK + self-test 7/7,
  wiring-guard 72 ফাইল wired। Negative test: sibling-only drift → গার্ড exit 1
  (নির্দেশমূলক বার্তা), restore → PASS।
- **সীমার সততা**: লাইভ redeploy admin-lane (Render) — এই PR entry-সারফেস ও
  গার্ড ঠিক করে; admin recipe (rebuild + anonymous deny-matrix probe) এখন
  সফলভাবে চলার পথে। লাইভ টাওয়ারে কোনো probe চালাইনি (never-do রেজিস্টার সম্মত)।
