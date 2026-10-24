---
id: crown-jewel-module-10-frontend-tier-s-wiring-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 10: Frontend Tier-S Wiring Power-Up (৩,৩৮৭-লাইনের প্রস্তুত উপাদান ও ৫,৯৯২-লাইনের অপেক্ষমাণ backend-কে জুড়ে দেওয়া — 'মাউন্ট-বিহীন হোস্ট' সমস্যার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Interface Circle (frontend/src/components/ S1–S12 + frontend/src/routes/workspaceFeatureRoutes.tsx + frontend/src/App.tsx + backend Tier-S routers-সংযোগ-স্তর)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১০ (সিরিজ-প্রস্তাবের শেষ মডিউল) — একটি মডিউল (Frontend Tier-S Wiring), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main 0057273 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; orphan-wiring-মতবাদ + Module 09 P-E সমন্বয়; প্রতিটি ধাপে flag+kill-switch; route-surface-এ zero-regression লক্ষ্য"
depends_on:
  - "frontend/src/components/chat/ChatInterface.tsx (261 লাইন — S1/S4/S5/S6/S7/S11-এর হোস্ট, কিন্তু কোনো route-এ মাউন্টেড নয় — App.tsx-grep শূন্য; L154,162,192 hardcoded 'current_conv')"
  - "frontend/src/components/reasoning/ThinkingPanel.tsx (290 লাইন — S2, 0 importer) + backend/api/routes/reasoning.py (340 লাইন /api/reasoning/think/stream — মাউন্টেড, FE-caller শূন্য)"
  - "frontend/src/components/artifacts/ArtifactsPanel.tsx (454 লাইন — S3, 0 importer) + backend/api/routes/artifacts.py (450 লাইন CRUD — মাউন্টেড, caller শূন্য; PUT অনুপস্থিত)"
  - "frontend/src/pages/PromptTemplatePage.tsx + templates/PromptTemplateLibrary.tsx (708 লাইন — S9 লাইভ /prompt-library কিন্তু navigationRegistry-তে এন্ট্রি শূন্য — grep-verified)"
  - "frontend/src/components/share/ShareDialog.tsx (394 লাইন — S1; backend share.py 399 লাইন — /list+DELETE বিদ্যমান, UI-নেই)"
  - "backend/api/routers.py L18-51,312 (১২টি Tier-S router নিবন্ধিত — সব মাউন্টেড)"
  - "frontend/src/routes/workspaceFeatureRoutes.tsx (338 লাইন — ২ বাস্তব route + ~২৭০-লাইন guide-স্ট্রিং: ৬ ভুল prefix/path + ২ phantom-file রেফারেন্স)"
  - "frontend/src/config/navigationRegistry.ts (S8/S10/S12-এন্ট্রি বিদ্যমান — সফল-প্যাটার্ন)"
  - "commit 6ef6550 (SupremeComponents/GlassUiPrimitives −246 লাইন zero-importer-অপসারণ — deletion-মতবাদ-প্রমাণ) বনাম App.tsx:39-41 'RESTORE-AND-WIRE' মন্তব্য — দুই-মতবাদের টানাপোড়েন"
  - "docs/plans/features/orphan_components_wiring_master_plan.md (entry-verify→fake-core→phase-ordered মতবাদ)"
  - "MODULE_09_DORMANT_TOOLS_POWER_UP_2026-09-17.md P-E (৬ mounted-orphan router-সিদ্ধান্ত — সমন্বয়-বিন্দু)"
  - "frontend/e2e + qa/playwright (S-06 test.fixme BLOCKED — share fixtures)"
implements:
  - "মাউন্ট-বিহীন হোস্ট সমস্যার সমাধান — ChatInterface route-গ্রাফে: এক মাউন্টে ৬টি ফিচার (share/upload/slash/search/export/branch) জাগ্রত"
  - "S2/S3 জাগরণ — ThinkingPanel/ArtifactsPanel বিদ্যমান লাইভ endpoint-এ: শূন্য-নির্মাণ-খরচে ৭৪৪-লাইন UI কাজে"
  - "নেভিগেশন-সত্য — /prompt-library নেভ-এন্ট্রি + ভাঙা guide-নথির সংশোধন: ভবিষ্যৎ-ওয়্যারিংয়ের ভুল-মানচিত্র শেষ"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main 0057273: ChatInterface App.tsx-grep শূন্য + caller-grep বিশ্লেষণ; ThinkingPanel/ArtifactsPanel importer-grep = কেবল self+guide; navigationRegistry prompt-library-grep শূন্য; routers.py L18-51 Tier-S-নিবন্ধন যাচাই; DeepResearchPanel SSE-অমিল Module 08 P-A-র পরিসর)"
code_evidence:
  - "মাউন্ট-বিহীন হোস্ট — ChatInterface.tsx (261 লাইন) S1/S4/S5/S6/S7/S11-কে আমদানি করে কিন্তু App.tsx-র কোনো route-এ নেই → ৬ ফিচারের UI-প্রস্তুতি অদৃশ্য (~2,027 লাইন সংশ্লিষ্ট কম্পোনেন্ট); এটিই সিরিজের বৃহত্তম একক-মাউন্ট-লিভার"
  - "hardcoded পরিচয় — ChatInterface.tsx L154,162,192 'current_conv' — share/export/branch আজ কোনো বাস্তব কথোপকথনে বাঁধা নয়"
  - "S2/S3 যমজ-অনাথ — ThinkingPanel (290) + ArtifactsPanel (454) importer-শূন্য, অথচ /api/reasoning/think/stream + /api/artifacts CRUD মাউন্টেড-লাইভ, caller-শূন্য — দুই-পক্ষেরই নির্মাণ সম্পন্ন, সংযোগ নেই"
  - "S9-অন্ধকার — /prompt-library লাইভ route কিন্তু navigationRegistry-এন্ট্রি শূন্য (grep-verified) — routePolicies.ts:45 জানে, ব্যবহারকারী জানে না"
  - "S1-অর্ধ-জাগ্রত — /share/:shareId লাইভ, কিন্তু ShareDialog কেবল unrouted-হোস্টে; /api/share/list+DELETE এন্ডপয়েন্ট বিদ্যমান কিন্তু 'আমার শেয়ার' UI-নেই — public-exposure গভর্ন্যান্স-ছিদ্র"
  - "guide-অবিশ্বস্ততা — workspaceFeatureRoutes.tsx-র ~২৭০-লাইন guide-স্ট্রিং: ৬ ভুল prefix/path, ২ phantom-file (tierSStore.ts/tierSRoutes.tsx — বিলোপিত) — ভবিষ্যৎ-ওয়্যারিংয়ের ভুল-মানচিত্র"
  - "টেস্ট-শূন্যতা — ১২ router-এর ১১টির backend-টেস্ট শূন্য (কেবল /api/chat/upload ২ ফাইল); ৯৯ vitest-ফাইলে Tier-S মাত্র ১; Playwright-এ S-06 test.fixme; knip warn-only → orphan দৃশ্যমান কিন্তু সহ্যকৃত"
  - "মতবাদ-দ্বন্দ্ব — 6ef6550-এ zero-importer-অপসারণ (−246 লাইন, সফল) বনাম App.tsx:39-41 'RESTORE-AND-WIRE... deletion without admin approval forbidden' — সিদ্ধান্ত-নীতি প্রয়োজন (এই নীলনকশার P-F)"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্রল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) e2e smoke প্রতি নতুন-ওয়্যারড পৃষ্ঠে (/share, /prompt-library, /memory, /scheduled-tasks, /research), (২) share-privacy টেস্ট (cross-user access-নিষেধ), (৩) route-registry meta-test (route-parity), (৪) বিদ্যমান ৯৯ vitest + ৪ e2e শূন্য-ব্যর্থতা; controlPlane.executeCapability('conversation.orchestrate')-সত্য-যাচাই P-A-র পূর্বশর্ত"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "হোস্ট-সংজ্ঞা: চ্যাট-পৃষ্ঠ route-গ্রাফে মাউন্টেড ও বাস্তব conversation_id-বাঁধা — 'current_conv' শূন্য; ৬ ফিচার বাস্তব কথোপকথনে কাজ করে (e2e-প্রমাণ)"
  - "S2/S3-সংজ্ঞা: ThinkingPanel স্ট্রিমিং-ধাপ দেখায়; ArtifactsPanel CRUD-চালায় — উভয়ের লাইভ endpoint-caller >0"
  - "নেভিগেশন-সংজ্ঞা: /prompt-library নেভ-এন্ট্রি; guide-স্ট্রিং সংশোধিত বা linted-docs-এ স্থানান্তরিত; phantom-রেফারেন্স শূন্য"
  - "গভর্ন্যান্স-সংজ্ঞা: 'আমার শেয়ার' UI (/list+DELETE) — cross-user privacy টেস্ট-সুরক্ষিত; zero-regression CI প্রমাণ"
test_evidence_note: "Gate 4-এ e2e smoke ও privacy টেস্ট; Gate 5-এ live — বাস্তব ব্যবহারে ৬-ফিচার-প্রবাহ + S2/S3-সংযোগ পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: ChatInterface-মাউন্টে fake-core উন্মোচন (controlPlane.executeCapability যদি প্রতারক হয়) — প্রশমন: P-A-পূর্বে executeCapability-সত্য-যাচাই (orphan-plan মতবাদ ②), flag-gated মাউন্ট, ব্যর্থ হলে বিদ্যমান workspace-চ্যাট অটুট থাকে"
  - "S2-সক্রিয়করণে খরচ-বৃদ্ধি (প্রতি-বার্তা reasoning-কল) — প্রশমন: flag default off + কেবল user-triggered + M03/M06-বাজেট-চুক্তি"
  - "state-plumbing (conversation_id) রিগ্রেশন — প্রশমন: workspaceUiStateStore-চুক্তি টেস্ট-পিনকৃত; ধাপে-ধাপে"
  - "guide-অপসারণে নথি-ক্ষতি — প্রশমন: সংশোধিত-সংস্করণ linted-docs-এ স্থানান্তর, বিলোপ নয়"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag; route-পরিবর্তন route-registry-meta-test-সুরক্ষিত"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: লাইভ Tier-S = 4.5/12 (~২,৭৮০ লাইন); মাউন্ট-বিহীন-হোস্ট-বন্দি ফিচার = ৬; অনাথ প্যানেল = ২ (৭৪৪ লাইন); 'current_conv' = ৩ স্থান; নেভ-বিহীন লাইভ route = ১; ভুল guide-নির্দেশ = ৬; Tier-S e2e = 0"
measurement_method:
  - "(a) জাগরণ-ম্যাট্রিক্স: লাইভ Tier-S গণনা (লক্ষ্য 12/12 অথবা নথিভুক্ত ব্যতিক্রম)"
  - "(b) সংযোগ-ম্যাট্রিক্স: প্রতি নতুন-ওয়্যারড পৃষ্ঠের e2e-smoke সাফল্য + endpoint-caller >0"
  - "(c) নেভিগেশন-সত্য: prompt-library নেভ-প্রবেশ গণনা + phantom-রেফারেন্স (লক্ষ্য 0)"
  - "(d) regression: route-registry meta-test + ৯৯ vitest + ৪ e2e শূন্য-ব্যর্থতা"
success_threshold: "জাগরণ → 12/12 অথবা নথিভুক্ত ব্যতিক্রম (hard); e2e-স্মোক → প্রতি নতুন পৃষ্ঠে সফল (hard); 'current_conv' → 0 (hard); phantom-রেফারেন্স → 0 (hard); privacy-টেস্ট → সব-পাস (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ১০-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 10: Frontend Tier-S Wiring Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Interface Circle (`frontend/src/components/` S1–S12 + `workspaceFeatureRoutes.tsx` + `App.tsx` + backend Tier-S routers-সংযোগ)
**Main anchor:** fresh main `0057273` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration / 0 route deletion (demount-সিদ্ধান্ত হলে নথিভুক্ত ব্যতিক্রম)

## বাংলা সারসংক্ষেপ

সিরিজের শেষ প্রস্তাবিত মডিউলটি সবচেয়ে দৃশ্যমান সুযোগ ধারণ করে: **প্রায়-সব নির্মিত, প্রায়-কিছুই দেখা যায় না**। Tier-S S1–S12 — ১২টি প্রথম-শ্রেণির ফিচার (share, reasoning, artifacts, upload, slash, search, export, memory, prompts, schedule, branch, research) — মোট ৩,৩৮৭-লাইন ফ্রন্টএন্ড উপাদান + ৫,৯৯২-লাইন backend — যার মাত্র **4.5/12 লাইভ**। রহস্যের মূল একটি শব্দে: **মাউন্ট-বিহীন হোস্ট** — `ChatInterface.tsx` (২৬১ লাইন) ছয়টি ফিচারকে (S1/S4/S5/S6/S7/S11) আমদানি করে, কিন্তু App.tsx-র কোনো route-এ সে-ই নেই — অর্থাৎ একটি route-লাইনই ব্যবহারকারীর কাছে ৬টি ফিচার লুকিয়ে রেখেছে। এর পাশে যমজ-অনাথ: ThinkingPanel ও ArtifactsPanel (৭৪৪ লাইন) importer-শূন্য, অথচ তাদের backend endpoint (/api/reasoning/think/stream, /api/artifacts) মাউন্টেড-লাইভ ও caller-শূন্য — **দুই-পক্ষই নির্মিত, সেতুটাই নেই**। ছোট-ক্ষতের ঝাঁক: /prompt-library লাইভ কিন্তু নেভ-এন্ট্রি নেই (ব্যবহারকারী জানে না), শেয়ার-গভর্ন্যান্স-ছিদ্র (/list+DELETE এন্ডপয়েন্ট আছে, 'আমার শেয়ার' UI নেই), আর ভবিষ্যৎ-ওয়্যারিংয়ের মানচিত্রটিই ভুল — workspaceFeatureRoutes-র guide-স্ট্রিংয়ে ৬টি ভুল path ও ২টি বিলোপিত phantom-file। টেস্ট-পক্ষ আরও খালি: ১১/১২ router-এর backend-টেস্ট শূন্য, Tier-S e2e শূন্য (কেবল S-06 test.fixme)। আর সিদ্ধান্ত-দর্শনে দুই স্রোতের টানাপোড়েন: সম্প্রতি 6ef6550-এ zero-importer কোড অপসারণ সফল, অথচ App.tsx-র পুরনো মন্তব্য বলে "deletion without admin approval forbidden" — কোনটা কখন?

এই নীলনকশা সেতুগুলো দেয় ৭ ধাপে: **(A)** হোস্ট-মাউন্ট (৬-ফিচার এক-লাইনে) → **(B)** বাস্তব conversation_id ('current_conv' মৃত্যু) → **(C)** S2/S3-জাগরণ → **(D)** নেভিগেশন-সত্য → **(E)** শেয়ার-গভর্ন্যান্স → **(F)** মতবাদ-নিষ্পত্তি (wire-বনাম-delete নীতি) → **(G)** টেস্ট-সুরক্ষা-জাল। **সীমানা:** S12-র SSE-অমিল Module 08 P-A-র; backend-ফিক্স Module 09 P-E-র সাথে সমন্বিত। শিল্প-শিক্ষা (established product pattern): ব্যবহারকারী নির্মাণ-রিপোর্ট পড়ে না — *দেখে*; ৯০% নির্মিত পণ্য ৫০% দৃশ্যমান হলে বাজারে "অসম্পূর্ণ" — আর এখানে লাভটা ব্যতিক্রমী: নতুন নির্মাণ প্রায় শূন্য, শুধু সংযোগ।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ১০.১ route-graph-কে সত্য-উৎস রাখা

- পরিণত frontend-এ route-registry meta-test মানক — প্রতিটি নির্মিত পৃষ্ঠ হয় রাউটেড, নয় স্পষ্ট-নথিভুক্ত বিলোপ (established pattern)।
- SupremeAI-র সংযোগবিন্দু: knip warn-only চলে — orphan দৃশ্যমান কিন্তু সহ্যকৃত; route-registry meta-test-এ গেট-করাই P-F/G।

### ১০.২ feature-flagged gradual exposure

- বড় পৃষ্ঠ-মাউন্টে flag-gated exposure + fallback মানক — পুরনো-পথ অটুট (established pattern)।
- SupremeAI-র সংযোগবিন্দু: workspaceUiStateStore-চুক্তি টেস্ট-পিনকৃত — P-A flag-এর পিছনে নিরাপদ।

### ১০.৩ governance-UI মতবাদ

- share/public-exposure জাতীয় ক্ষমতায় "আমার লিঙ্ক" ব্যবস্থাপনা-UI মানক — গভর্ন্যান্স-লুপ বন্ধ করে (established pattern)।
- SupremeAI-র সংযোগবিন্দু: /list+DELETE endpoint বিদ্যমান — শুধু UI (P-E)।

### ১০.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main 0057273-verified)

| প্যাটার্ন | যা করে | SupremeAI আজ (0057273-verified) | গ্যাপ |
|---|---|---|---|
| route-সত্য-উৎস | রাউটেড-বনাম-নথিভুক্ত গেট | knip warn-only, orphan সহ্যকৃত | P-F/G |
| flag-gated exposure | নিরাপদ মাউন্ট | চ্যাট-হোস্ট অ-মাউন্টেড | P-A |
| governance-UI | শেয়ার-ব্যবস্থাপনা | endpoint আছে, UI নেই | P-E |
| feature-parity | দেখা-যায় = কাজ-করে | 4.5/12 লাইভ | P-A–E |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 0057273, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_08_SCOUT_DEEP_RESEARCH_POWER_UP_2026-09-17.md` P-A | S12-র SSE-চুক্তি | **সীমানা:** backend-চুক্তি সেখানে; এখানে কেবল /research-পৃষ্ঠ consumer-হিসেবে গ্রহণ |
| `MODULE_09_DORMANT_TOOLS_POWER_UP_2026-09-17.md` P-E | ৬ mounted-orphan router-সিদ্ধান্ত | সমন্বয়-বিন্দু — S1–S7-র endpoint-গুলো সেখানে নথিভুক্ত; FE-consumer এখানে |
| `docs/plans/features/orphan_components_wiring_master_plan.md` | entry-verify→fake-core→phase-ordered | মতবাদ-পুনঃব্যবহার — বিশেষত ② "never build on fake cores" P-A-র পূর্বশর্ত-যাচাই |
| commit 6ef6550 | zero-importer-অপসারণ-প্রমাণ | P-F-র deletion-মতবাদের সাম্প্রতিক সফল-উদাহরণ |
| App.tsx:39-41 'RESTORE-AND-WIRE' | পুরনো মন্তব্য-নীতি | P-F-এ আধুনিকীকরণের বিষয় — ফাউন্ডার-অনুমোদন-সাপেক্ষ সিদ্ধান্ত-টেবিল |
| qa/ coverage-matrix + Feature Parity Sentinel | QA-গেট | P-G — Tier-S-কে গেট-কভারেজে যুক্ত করার প্রার্থী |

**গ্রেপ-যাচাই:** fresh main 0057273-এ কোনো বিদ্যমান ডকুমেন্ট ChatInterface-মাউন্ট, S2/S3-সংযোগ, prompt-library-নেভ বা guide-সংশোধনের execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **প্রায়-সম্পূর্ণ উপাদান-ভাণ্ডার:** ১২ Tier-S উপাদান/পৃষ্ঠা — ৩,৩৮৭-লাইন ফ্রন্টএন্ড (S1 686, S3 454, S12 647, S10 647, S9 708...)।
2. **পূর্ণ backend:** ১২ router — routers.py:18-51,312 সব নিবন্ধিত; ৫,৯৯২ লাইন; ০ fabricated endpoint লাইভ-কলারদের মধ্যে।
3. **লাইভ-প্যাটার্ন:** S8 (/memory), S10 (/scheduled-tasks), S12 (/research), S9-route — navigationRegistry+workspaceFeatureRoutes প্যাটার্ন প্রমাণিত।
4. **অবকাঠামো:** workspaceUiStateStore (টেস্ট-পিনকৃত), tier_s migration (merge-chain-এ), alembic-bridge।
5. **deletion-মতবাদ-প্রমাণ:** 6ef6550 — zero-importer+duplicate-detector-অপসারণ সফল।
6. **টেস্ট-বীজ:** ৯৯ vitest + ৪ e2e + S-06-ফিক্সচার (ব্লক-কারণ চিহ্নিত)।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **হোস্ট-মাউন্ট** — ChatInterface route-গ্রাফ-বহির্ভূত; ৬ ফিচার অদৃশ্য।
2. **বাস্তব পরিচয়** — 'current_conv' hardcoded ×৩; share/export/branch কথোপকথন-বাঁধাহীন।
3. **S2/S3-সেতু** — প্যানেল ও endpoint দুই-পক্ষই নির্মিত, সংযোগ শূন্য।
4. **নেভিগেশন-সত্য** — S9 নেভ-বিহীন; guide-মানচিত্র ভুল (৬ path + ২ phantom)।
5. **গভর্ন্যান্স-UI** — শেয়ার-তালিকা/বিলোপ ইউআই-শূন্য।
6. **টেস্ট-জাল** — ১১/১২ router backend-টেস্ট-শূন্য; Tier-S e2e-শূন্য; knip গেট-বিহীন।
7. **মতবাদ-নিষ্পত্তি** — wire-বনাম-delete-এর আধুনিক নীতি-নথি নেই।

### ২.৩ কী করতে হবে (সংযোগ-সম্পূর্ণকরণের ৭ ধাপ)

```text
P-A: হোস্ট-মাউন্ট           → executeCapability-সত্য-যাচাই-পূর্বশর্ত → ChatInterface route-এ
                              (flag-gated) — ৬ ফিচার এক-মাউন্টে
P-B: বাস্তব পরিচয়           → 'current_conv' → store-plumbed conversation_id ×৩
P-C: S2/S3-জাগরণ           → ThinkingPanel → /think/stream (flag, user-triggered);
                              ArtifactsPanel → /api/artifacts CRUD
P-D: নেভিগেশন-সত্য          → /prompt-library নেভ-এন্ট্রি; guide-সংশোধন/linted-docs
P-E: শেয়ার-গভর্ন্যান্স       → 'আমার শেয়ার' UI (/list+DELETE) + privacy-টেস্ট-প্রথম
P-F: মতবাদ-নিষ্পত্তি         → wire-বনাম-delete নীতি-নথি (6ef6550-প্রমাণ + RESTORE-AND-WIRE
                              আধুনিকীকরণ) + route-registry meta-test গেট
P-G: টেস্ট-সুরক্ষা-জাল       → প্রতি নতুন পৃষ্ঠে e2e-smoke + ১২-রুটার pytest + knip→gate
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** পূর্বশর্ত-যাচাই: `controlPlane.executeCapability('conversation.orchestrate')`-র প্রকৃত সংযোগ-প্রমাণ (orphan-plan মতবাদ ② — fake-core উন্মোচন নয়); তারপর App.tsx route-entry (flag `SUPREMEAI_TIER_S_CHAT_HOST=true` default false); বিদ্যমান workspace-চ্যাট অটুট-ফলব্যাক।
- **P-B:** workspaceUiStateStore-এ activeConversationId-plumbing; ChatInterface-র ৩ স্থানে বাঁধন; টেস্ট: share/export/branch-বাস্তব-id চুক্তি।
- **P-C:** ThinkingPanel → POST /api/reasoning/think/stream (flag `SUPREMEAI_REASONING_PANEL=true` default false — প্রতি-বার্তা-খরচ-সচেতন); reasoningSteps-slice-ফিড; ArtifactsPanel → CRUD (PUT-অনুপস্থিতি backend-এ নোট — প্রয়োজনে ছোট execution প্ল্যান)।
- **P-D:** navigationRegistry.ts-এ /prompt-library-এন্ট্রি (এক-লাইন); workspaceFeatureRoutes-র guide-স্ট্রিং → সংশোধিত সংস্করণ `docs/`-linted-স্থানান্তর (ফাইল-বিলোপ নয়); phantom-রেফারেন্স-শুদ্ধি।
- **P-E:** privacy-টেস্ট-প্রথম (cross-user access-নিষেধ pytest) → ShareListDialog (নতুন ছোট উপাদান) → /share পৃষ্ঠে সংযুক্তি; DELETE-নিশ্চিত-প্রবাহ।
- **P-F:** নীতি-নথি (docs/plans/features-এ): সিদ্ধান্ত-টেবিল {zero-importer + duplicate + no-route → delete; প্রায়-প্রস্তুত + endpoint-লাইভ → wire; admin-অনুমোদন-শর্ত}; route-registry meta-test: প্রতিটি component-entry-point হয় রাউটেড, নয় নথিভুক্ত।
- **P-G:** প্রতি Phase-এর সাথে e2e-smoke (Playwright); ১২-router pytest-কভারেজ (S1-privacy অগ্রাধিকার); knip warn→error (**error-মোডে প্রবেশ কেবল শূন্য-false-positive বেসলাইন-প্রমাণের পরে — CI-বিচ্ছিন্নতা-সুরক্ষা; ব্যতিক্রম-তালিকা data-file-এ, কোড-inline নয়**); S-06-ফিক্সচার-আনব্লক।
- **P-H (AGENTS.md Rule 7 মান্যতা: এন্ড-টু-এন্ড ডুয়াল-ড্রাইভেন ফুল-স্ট্যাক ইউআই)**:
  - SupremeAI কেবল অ্যাডমিনদের ডিবাগিং কনসোলে পরিণত হবে না, আবার গ্রাহকদের জন্য জটিলতাহীন খেলনা হবে না।
  - **Customer Experience:** জিরো-কমপ্লেক্সিটি, গতিশীল ও পরিষ্কার ইউআই, প্রগ্রেসিভ ডিসক্লোজার (সহজ চ্যাট, আর্টফ্যাক্ট ও ওয়ান-ক্লিক রান)।
  - **Admin Mission Command:** 3D সিস্টেম হেলথ সুইপ, টেলিমেট্রি গ্রাফ, Gateway টোকেন রিয়েল-টাইম ফ্লো, এবং লাইভ HITL ওভাররাইড প্যানেল।
  - একই সমন্বিত ফ্রন্টএন্ড কোডবেসে রোলের ভিত্তিতে প্রিমিয়াম ও মসৃণ অভিজ্ঞতা নিশ্চিত করা।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **৬-ফিচার-এক-মাউন্ট (P-A/B):** ইতিহাসের সর্বোচ্চ-লিভার একক route-লাইন — শেয়ার/আপলোড/স্ল্যাশ/সার্চ/এক্সপোর্ট/ব্রাঞ্চ ব্যবহারকারীর হাতে; নতুন নির্মাণ প্রায় শূন্য।
2. **ডুয়াল-ড্রাইভেন শ্রেষ্ঠত্ব (P-H):** সাধারণ ইউজার পায় অ্যাপলের মতো ক্লিন এক্সপেরিয়েন্স, আর এন্টারপ্রাইজ অ্যাডমিন পায় নাসার মিশন কন্ট্রোলের ক্ষমতা।
3. **অন্ধকার-প্রদর্শনী বন্ধ (P-C/D):** ৭৪৪-লাইন UI + লাইভ-লাইভ endpoint অবশেষে জুড়ল; /prompt-library আবিষ্কারযোগ্য।
4. **গভর্ন্যান্স-লুপ (P-E):** public-exposure ব্যবস্থাপনা — বিশ্বাস-ও-নিরাপত্তা গল্পের বাস্তব প্রমাণ।
5. **ভুল-মানচিত্র শেষ (P-D/F):** ভবিষ্যৎ প্রতিটি ওয়্যারিং-সেশন সঠিক নথি-ভিত্তিক; route-গেট পুনরাবৃত্তি-রোধক।
6. **প্যারিটি-সত্য:** "feature-parity" দাবি e2e-প্রমাণসহ — qa-matrix-র সাথে সারিবদ্ধ।
7. **সিরিজ-সমাপ্তি-রূপক:** ৯ backend-মডিউলের সত্য-পণ্য ব্যবহারকারীর চোখে পৌঁছায় — সিরিজের দৃশ্যমান-সমাপ্তি।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **fake-core উন্মোচন (P-A):** হোস্ট-মাউন্টে প্রতারক-নির্ভরতা দৃশ্যমান হলে — প্রশমন: পূর্ব-যাচাই-বাধ্যতামূলক, flag default false, fallback অটুট, ব্যর্থতায় অপসারণ-সহজ।
2. **খরচ-বৃদ্ধি (P-C):** reasoning-প্যানেল প্রতি-বার্তা-কল — প্রশমন: user-triggered-only + flag off-default + M03/M06-বাজেট।
3. **state-রিগ্রেশন (P-B):** conversation-plumbing ভুলে অন্য-কথোপকথন-প্রবাহ — প্রশমন: store-চুক্তি-টেস্ট, ধাপে-ধাপে, e2e।
4. **নথি-হস্তান্তর-ঝুঁকি (P-D):** guide-স্থানান্তরে দ্বৈত-উৎস — প্রশমন: একক-উৎস-নীতি (ফাইলে শুধু pointer)।
5. **পরিসর-ঝুঁকি:** UI-পুনর্নকশার লোভ — প্রশমন: কোনো নতুন ডিজাইন নয়; সংযোগ-মাত্র; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. S12-র backend-চুক্তি-ফিক্স — Module 08 P-A।
2. ৬ mounted-orphan router-এর backend-সিদ্ধান্ত-নথি — Module 09 P-E (FE-consumer এখানে)।
3. নতুন UI/UX-ডিজাইন, থিম, অ্যানিমেশন — সংযোগ-মাত্র।
4. PUT-endpoint যোগসহ backend-সম্প্রসারণ — প্রয়োজনে ছোট আলাদা execution প্ল্যান।
5. Electron/desktop-প্যাকেজিং — পরিসরে নেই।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | route-entry+plumbing+নেভ-এন্ট্রি — নির্মাণ-ন্যূনতম, সংযোগ-সর্বোচ্চ |
| 3. No new infrastructure | ✅ | store/router/CI-যন্ত্র বিদ্যমান |
| 4. No CI cost amplification | ✅ | smoke-টেস্ট বিদ্যমান Playwright-প্রকল্পে |
| 5. No credit-burn risk | ✅ | S2 user-triggered + flag off-default; বাকি কল-শূন্য |
| 6. No academic leaderboard | ✅ | জাগরণ-ম্যাট্রিক্স, e2e-সাফল্য, phantom-গণনা — সরাসরি প্রোডাক্ট-মান |
| 7. Realistic resource budget | ✅ | কোনো নতুন স্থায়ী-ভলিউম নয় |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 0057273 grep/wc-যাচাই (last_verified-তালিকা); মতবাদ-দ্বন্দ্ব-পাঠ |

| Constitution ধারা | প্রভাব |
|---|---|
| #3 Reuse Before Creation | ✅ ৩,৩৮৭+৫,৯৯২ লাইন নির্মিত-সম্পদের সংযোগই মূল-সূত্র |
| #5 Verify Before Trust | ✅ P-A-পূর্বে fake-core-যাচাই; e2e-প্রমাণ |
| #8 Graceful Degradation | ✅ flag-off → বিদ্যমান পথ অটুট |
| #10 One System, Many Execution Surfaces | ✅ এক হোস্ট-মাউন্টে ৬ পৃষ্ঠ |
| #12 Least Privilege | ✅ শেয়ার-গভর্ন্যান্স-UI; privacy-টেস্ট-প্রথম |
| #13 No Silent Failure | ✅ phantom-রেফারেন্স শুদ্ধি; নথি-সত্য |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** ৯৯ vitest + ৪ e2e শূন্য-ব্যর্থতা; P-A মাউন্ট-পূর্ব executeCapability-প্রমাণ-নথি + fallback-টেস্ট; P-B id-বাঁধন-চুক্তি টেস্ট; P-E privacy-টেস্ট-পাস; P-F route-registry meta-test সবুজ।
- **Gate 5 (live):** বাস্তব ব্যবহারে ৬-ফিচার-প্রবাহ e2e-সফল; S2/S3 endpoint-caller >0; /prompt-library নেভ-প্রবেশ; 'আমার শেয়ার' ক্রিয়াকলাপ পর্যবেক্ষিত।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; route-পরিবর্তন meta-test-সুরক্ষিত; guide-স্থানান্তর বিলোপ-বিহীন।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত | ৬-ফিচার-এক-মাউন্ট = প্রায়-শূন্য নির্মাণ; ThinkingPanel flag default false (প্রতি-বার্তা-খরচ-সচেতন); নতুন পরিষেবা/dependency নয় |
| Lightweight | ✅ সংগত | এক-লাইন route-এন্ট্রি, store-plumbing, ছোট উপাদান — বড় রিরাইট নয় |
| Fast & smooth | ✅ সংগত (P-G সংশোধিত) | flag-gated mount + workspace-ফলব্যাক; knip error-মোড শূন্য-false-positive-পরে (CI ভাঙবে না) |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | knip ব্যতিক্রম-তালিকা data-file-এ (§২.৪ সংশোধিত) |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `frontend/src/config/` navigationRegistry বিদ্যমান; knip frontend/package.json-এ বিদ্যমান (P-G প্রাসঙ্গিক)।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — সিরিজ-সমাপ্তি ও চলমান প্রক্রিয়ার পরবর্তী অধ্যায়

- **চক্র ১–১০ (প্রস্তাবিত-সম্পূর্ণ):** Memory → Orchestration → LLM Gateway → Browser → Self-Evolution → Run Fabric → Context Engine → Scout → Dormant Tools → Frontend Tier-S — প্রতিটি এক-মডিউল-এক-নীলনকশা, সবই proposed (Gate 2 ফাউন্ডার-অনুমোদন অপেক্ষমাণ)।
- **এরপর কী (continuous process চলমান):** কিউ পুনঃর‍্যাঙ্ক হবে Gate 5-পরিমাপ ও ফাউন্ডার-অগ্রাধিকারে — নতুন প্রার্থী: mission-control (apps/) গভীর-বিশ্লেষণ, SSE/websocket-অবকাঠামা, billing-gateway স্তর, i18n/বাংলা-অ্যাডাপ্টার, অথবা প্রকাশিত দশটির যে-কোনো মডিউলের Phase-স্তর execution-নীলনকশা (proposed → approved → সম্পাদন)।
- **শৃঙ্খলা-অটুট:** single-plan execution — একসময়ে একটাই Phase সম্পাদনে; এই সিরিজ বিশ্লেষণ-পাইপলাইন, সম্পাদন-পাইপলাইন নয়।
- সূচি ও কিউ: `crown_jewel_series/README.md`।

---

## Part 7 — প্রগ্রেস লগ (Execution Started — 2026-09-18, issue #453 Wave 1)

**P-A আংশিক বাস্তবায়ন (base `4ac43642`):**
- ChatInterface host প্রথমবার মাউন্টেড: `/chat` রুট (ProtectedRoute + WorkspaceLayout) +
  navigation registry-তে `nav-chat` (simple viewer-ও দেখবে) + `nav-prompt-library` nav truth।
- ভুয়া `"current_conv"` প্লেসহোল্ডার (৩টি) সরিয়ে ক্লায়েন্ট-জেনারেটেড সত্য `conversation_id` —
  প্রতিটি orchestration payload-এ যায়, পরের কলে স্থায়ী থাকে; কথোপকথনের আগে share/export
  বাটন সৎভাবে disabled ("Start a conversation first")।
- S2 ThinkingPanel + S3 ArtifactsPanel ChatInterface-এ মাউন্ট (store-driven, toolbar toggle);
  orchestration `data.reasoning_steps`/`data.artifacts` টাইপ-গার্ড দিয়ে গ্রহণ — ফিল্ড না এলে
  কিছুই বানানো হয় না।
- Integration guide-এর ভুয়া প্যাথ সংশোধিত (tierSStore/tierSRoutes/server.py-র অস্বাস্থ্যকর
  নির্দেশনা → প্রকৃত workspaceUiStateStore/workspaceFeatureRoutes/routers.py সত্য)।

**প্রমাণ:** নতুন চুক্তি-টেস্ট `frontend/src/components/chat/ChatInterface.test.tsx` (৫টি);
frontend vitest 527→**532 (102 files)**; tsc `-p tsconfig.app.json` 0 errors; missions 62/62।

**বাকি (P-A সম্পূর্ণ হতে):** guide-string-এর বাকি দাবির re-verification; S2/S3-এর backend
`data.*` ফিল্ড চুক্তি যখন M03/M02 সরবরাহ করবে তখন e2e; knip zero-false-positive baseline।
