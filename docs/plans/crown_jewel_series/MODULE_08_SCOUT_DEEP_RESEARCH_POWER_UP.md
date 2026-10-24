---
id: crown-jewel-module-08-scout-deep-research-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 08: Scout / Deep Research Power-Up (গবেষণা-চক্রকে সৎ, সংযুক্ত ও বাংলা-সচেতন করা — SSE-চুক্তি-ভাঙা ও গবেষণা-স্বাদু-ফেব্রিকেশন পর্যুগের পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Scout Circle (backend/scout/ + backend/api/routes/deep_research.py + backend/api/routes/crawler_admin.py + backend/agents/research_assistant.py + frontend DeepResearchPanel-সংযোগ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৮ — একটি মডিউল (Scout / Deep Research), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main fb53ad8 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; Module 03/04/06-র সাথে স্পষ্ট সীমানা; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/api/routes/deep_research.py (776 লাইন — ১০-ধাপ পাইপলাইন, ৪ endpoint, routers.py:46 মাউন্টেড; SSE emit L661 'type:step', L684 'type:report', L677 'error.content' — sed-verified)"
  - "backend/scout/crawler.py (331 লাইন — governed crawl: policy gate L131/191 → Redis cache → robots RFC-9309 → rate-slot → per-hop SSRF re-validation L83-120 → BS4 clean → dedup → BFS)"
  - "backend/scout/policy.py (125 লাইন — fail-closed SSRF/domain gate; TrustLevel)"
  - "backend/scout/persistence.py (283 লাইন — record_event-এর প্রোডাকশন caller শূন্য — grep-verified; admin events-endpoint খালি টেবিল পড়ে)"
  - "backend/api/routes/deep_research.py L210 (duckduckgo.com/html scrape — একমাত্র search-provider; DDGS-lib unwired)"
  - "backend/api/routes/deep_research.py L260-268 (AutonomousBrowserAgent fallback — Module 04 P-G-র consumer; বাস্তবায়ন সেখানে)"
  - "backend/api/routes/deep_research.py L419,478 (০-উৎসেও LLM-synthesis — গবেষণা-স্বাদু ফেব্রিকেশন-পৃষ্ঠ)"
  - "backend/scout/extractor.py (L210 regex [a-zA-Z]{3,} — Bengali-অন্ধ; :197 বাক্য-বিভাজন danda-বর্জনশীল)"
  - "frontend/src/components/research/DeepResearchPanel.tsx (L55 'step_update'|'progress'|'complete'|'error' — backend 'step'/'report' চুক্তির সাথে অমিল — sed-verified)"
  - "backend/core/search.py (48 লাইন web_search/DDGS — গবেষণা-পাইপলাইন ব্যবহারই করে না)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md (scout-সংশ্লিষ্ট rows :841/:842)"
  - "MODULE_04_BROWSER_AUTOMATION_POWER_UP_2026-09-17.md (P-G browser-grounding সীমানা)"
  - "MODULE_06_RUN_FABRIC_COMPLETION_POWER_UP_2026-09-17.md (RunType research-সংযোগ)"
implements:
  - "SSE-চুক্তি মেরামত — পতাকাবাহী /research UI প্রথমবার বাস্তব ধাপ-প্রবাহ ও রিপোর্ট দেখাবে"
  - "সৎ-grounding গেট — ০-উৎসে LLM-synthesis নিষিদ্ধ: গবেষণা-স্বাদু ফেব্রিকেশন পর্যুগ"
  - "বাংলা-সচেতন নিষ্কাশন — tokenizer/stopwords/danda: মূল-বাজারের ভাষায় গবেষণা-মান"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main fb53ad8: deep_research.py L661/677/684 sed-verified emit-types; DeepResearchPanel.tsx L55 sed-verified প্রত্যাশিত-চুক্তি; record_event caller-grep = scout-শূন্য; L210 DDG sed-verified; extractor.py L210 sed-verified [a-zA-Z]{3,})"
code_evidence:
  - "SSE-চুক্তি-ভাঙা — backend deep_research.py L661 'type:step'/L684 'type:report'/L677 'error{content}'; frontend DeepResearchPanel.tsx L55 প্রত্যাশা 'step_update|progress|complete|error' → পতাকাবাহী /research UI কখনো ধাপ বা রিপোর্ট দেখায় না; history-item-এ 'report' ক্ষেত্রও backend ফেরত দেয় না"
  - "গবেষণা-স্বাদু ফেব্রিকেশন — ০-উৎসেও পাইপলাইন 'No detailed snippets available' (L419) থেকে LLM-synthesis (L478) করে রিপোর্ট দেয় — শব্দ-সমৃদ্ধ, সত্য-শূন্য; ব্যর্থ fallback-ও চুপচাপ ০-ফল দেয় (L260-290)"
  - "crawl_events অন্ধ — persistence.record_event-এর প্রোডাকশন caller শূন্য (grep-verified); টেলিমেট্রি কেবল লগ+error-bus; অথচ GET /admin/crawler/events খালি টেবিল পড়ে (crawler_admin.py:188-199)"
  - "একমাত্র search-provider = DDG HTML scrape (L210) — এবং tenant-policy-কে duckduckgo.com allowlist করতেই হয় (fail-closed L191/204) — অনথিভুক্ত, অনিরীক্ষিত, seed-ডিফল্টহীন; DDGS-lib লেখা কিন্তু অসংযুক্ত (pyproject-এ undeclared)"
  - "বাংলা-অন্ধ নিষ্কাশন — extractor regex [a-zA-Z]{3,} (L210) + English stopwords + danda-বর্জনশীল বাক্য-বিভাজন (L197) → বাংলা পাঠে first-N fallback"
  - "তিন বিচ্ছিন্ন গবেষণা-পৃষ্ঠ — deep pipeline (scout-সহ) বনাম /research slash (KB+1 কল, scout-বিহীন — slash_commands.py:229-275) বনাম orchestrator-spoke (কেবল URL-crawl) — এক পণ্য, তিন মান"
  - "পাইপলাইনে শূন্য টেস্ট — ২,৮১৩-লাইন সাবসিস্টেমে ৪৬৫-লাইন টেস্ট সবই crawler/policy/extractor-পক্ষে; research-pipeline-নিজে ০; max_steps গৃহীত কিন্তু অব্যবহৃত (স্থির ১০ ধাপ)"
  - "config-শূন্যতা — core/config.py-তে scout-এর কোনো এন্ট্রি নেই (কেবল LOW_MEMORY_MODE); কোনো flag/kill-switch নেই"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) SSE contract-test (emit↔parse দুই-পক্ষ এক স্কিমা থেকে), (২) grounding-gate টেস্ট (০-উৎস → explicit no-sources রিপোর্ট, synthesis নয়), (৩) respx-মকড E2E (policy→crawl→report ধারাবাহিক), (৪) বিদ্যমান ২৭ crawler/policy টেস্ট zero regression; flag-off → আজকের আচরণ"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "চুক্তি-সংজ্ঞা: /research UI বাস্তব ধাপ-প্রবাহ ও রিপোর্ট দেখায় — emit↔parse এক-স্কিমা-উৎস, contract-test-সুরক্ষিত"
  - "সত্য-সংজ্ঞা: ০-উৎসে LLM-synthesis শূন্য — explicit 'no sources found' রিপোর্ট; ব্যর্থ fallback চুপ নয়"
  - "পর্যবেক্ষণ-সংজ্ঞা: crawl_events প্রতি crawl-এ লেখা — admin events-endpoint অ-শূন্য; per-session খরচ run/metadata-প্রবাহিত"
  - "বাংলা-সংজ্ঞা: বাংলা পাঠে শব্দ-নিষ্কাশন ও danda-বাক্য-বিভাজন টেস্ট-প্রমাণসহ; zero-token সম্পত্তি অটুট"
test_evidence_note: "Gate 4-এ contract/grounding/E2E টেস্ট; Gate 5-এ live — বাস্তব কোয়েরিতে ধাপ-প্রবাহ + admin-events গণনা + বাংলা-কোয়েরি রিপোর্ট-মান পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: SSE-চুক্তি পরিবর্তনে অন্য consumer ভাঙা — প্রশমন: emit↔parse এক-স্কিমা-মডিউল, contract-test, FE-parser-আপডেট একই PR-এ"
  - "grounding-গেটে UX-ব্যর্থতা-বৃদ্ধি: বেশি 'no sources' — প্রশমন: P-C-র সৎ-provider যোগে উৎস-হার বাড়ে; রিপোর্টে কারণ-ব্যাখ্যা"
  - "DDG/rate-limit নির্ভরতা (P-C) — প্রশমন: scout-governed deep-fetch ধারণকৃত; provider-চুক্তি বহু-উৎসের পথ খোলা রাখে"
  - "crawl_events-ভলিউম — প্রশমন: বিদ্যমান retention + bounded row"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag-off; কোনো schema migration নেই (টেবিল বিদ্যমান)"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: /research UI-তে দৃশ্যমান ধাপ/রিপোর্ট = 0 (চুক্তি-অমিল); ০-উৎসে সৃষ্ট 'রিপোর্ট' = প্রতিবার (hypothesis: সাধারণ ঘটনা); admin-events গণনা = 0; search-provider = ১ (policy-প্রতিবন্ধক); বাংলা-নিষ্কাশন-সাফল্য = fallback-প্রথম; pipeline-টেস্ট = 0"
measurement_method:
  - "(a) UI-liveness: বাস্তব কোয়েরিতে FE-গৃহীত step/report event গণনা (>0 = চুক্তি জাগ্রত)"
  - "(b) truth: ০-উৎস synthesis ঘটনা (লক্ষ্য 0) + no-sources-রিপোর্ট সঠিকতা"
  - "(c) পর্যবেক্ষণ: ২৪-ঘণ্টায় crawl_events rows + admin-endpoint অ-শূন্য"
  - "(d) মান: বাংলা-কোয়েরি রিপোর্টে উদ্ধৃতি-URL-সত্য (fetch-যাচাই) + regression: ২৭ টেস্ট শূন্য-ব্যর্থতা"
success_threshold: "UI-events → >0 (hard: শূন্য মানে চুক্তি এখনো ভাঙা); ০-উৎস synthesis → 0 (hard); crawl_events → প্রতি crawl >0 (hard); উদ্ধৃতি-সত্য → >95% fetch-যাচাই (target); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৮-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 08: Scout / Deep Research Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Scout Circle (`backend/scout/` + `backend/api/routes/deep_research.py` + `crawler_admin.py` + `research_assistant.py` + FE DeepResearchPanel-সংযোগ)
**Main anchor:** fresh main `fb53ad8` (2026-09-17)
**Resource delta:** 0 নতুন dependency (ddgs ঘোষণা-সংযোজন ব্যতীত) / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration / 0 route deletion

## বাংলা সারসংক্ষেপ

আটটির মধ্যে এই মডিউল সবচেয়ে "নতুন-জাত" — Scout, সদ্য প্রোডাকশন-ওয়্যারড গবেষণা-চক্র, এবং নির্মাণ-মানে গর্বের: governed crawling (SSRF/robots/rate/depth সব বাস্তব — `crawler.py` ৩৩১ লাইন), RFC-9309 robots-cache, SHA256+Jaccard dedup, Redis গবেষণা-ক্যাশ, tenant-policy fail-closed গেট, স্থায়ী sessions (migration-সহ)। কিন্তু গবেষণা-পণ্য হিসেবে এর ভাগ্য দাঁড়িয়ে দুইটি অদ্ভুত সত্যে: **(১) পণ্যটি কেউ দেখতেই পায় না** — backend ধাপ-প্রবাহ পাঠায় `type:"step"/"report"` (L661/684), অথচ পতাকাবাহী UI অপেক্ষা করে `step_update/complete` (DeepResearchPanel L55) — ফলে /research পৃষ্ঠায় কখনো ধাপ দেখায় না, কখনো রিপোর্ট; **(২) গবেষণা ব্যর্থ হলেও "রিপোর্ট" আসে** — ০-উৎসেও পাইপলাইন "No detailed snippets available" থেকে LLM-synthesis করে (L419→L478) — শব্দ-সমৃদ্ধ, সত্য-শূন্য; সাথে browser-fallback চুপচাপ ০-ফল (সেই grounding Module 04 P-G-র হাতে), admin-events-endpoint চির-খালি (record_event-এর caller শূন্য), একমাত্র search-provider DDG-HTML-scrape (যার জন্য tenant-কে allowlist-ও করতে হয় — অনথিভুক্ত), আর বাংলা? `extractor.py`-র regex `[a-zA-Z]{3,}` — নিষ্কাশনেই বাংলা অদৃশ্য। অর্থাৎ: নির্মাণ চমৎকার, কিন্তু শেষ-মাইলে (UI-চুক্তি, সত্য-গেট, provider, ভাষা) গবেষণা-পণ্যটি তার প্রতিশ্রুতির কাছেও পৌঁছায় না।

এই নীলনকশা গবেষণা-চক্রকে crown-jewel স্তম্ভে তোলে ৭ ধাপে: **(A)** SSE-চুক্তি মেরামত → **(B)** সৎ-grounding গেট → **(C)** provider-সত্য (DDGS-wire + seed-policy) → **(D)** পর্যবেক্ষণ-জাগরণ (crawl_events + খরচ-প্রবাহ) → **(E)** বাংলা-সচেতন নিষ্কাশন → **(F)** তিন-পৃষ্ঠ ঐক্য → **(G)** চুক্তি-টেস্ট-সুরক্ষা। **সীমানা:** browser-fallback-এর *বাস্তবায়ন* Module 04 P-G; খরচ-*বিলিং* Module 03; এখানে কেবল সত্য-প্রবাহ ও মান। শিল্প-শিক্ষা (research/agent পণ্যের established pattern): গবেষণা-পণ্যের বিশ্বাস একটিই জায়গায় জয়-হারায় — *উদ্ধৃতির সত্যতা*; আর ব্যবহারকারী প্রথম সেকেন্ডেই ধাপ-প্রবাহ না দেখলে পণ্য "আটকে-আছে" মনে হয় — দুটোই আজ আমাদের ফাটল।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৮.১ ধাপ-প্রবাহ মতবাদ — প্রথম সেকেন্ডেই জীবন্ততা

- গবেষণা-এজেন্ট পণ্যগুলো streaming progress (plan→search→read→synthesize) প্রথম-শ্রেণির চুক্তি হিসেবে রাখে (established pattern)।
- SupremeAI-র সংযোগবিন্দু: emit-যন্ত্র বাস্তব (on_step + emit_reasoning_step) — চুক্তি-অমিলই একমাত্র শত্রু (P-A)।

### ৮.২ উদ্ধৃতি-সত্য মতবাদ — citation-or-nothing

- পরিণত গবেষণা-পণ্যে দাবি হয় উদ্ধৃতি-সহ, নয়তো স্পষ্ট "উৎস পাইনি" — কখনো মিশ্র নয় (established pattern)।
- SupremeAI-র সংযোগবিন্দু: ০-উৎসে synthesis-ই লঙ্ঘন; grounding-গেট ছোট কোড, বড় সত্য (P-B)।

### ৮.৩ বহু-provider সত্য

- গবেষণা-পাইপলাইনে provider-abstraction (search API + governed crawler সমন্বয়) মানক (established pattern)।
- SupremeAI-র সংযোগবিন্দু: DDGS-lib লেখা (core/search.py) কিন্তু অসংযুক্ত — scout-governed deep-fetch অটুট রেখে provider-১ যোগ (P-C)।

### ৮.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main fb53ad8-verified)

| প্যাটার্ন | যা করে | SupremeAI আজ (fb53ad8-verified) | গ্যাপ |
|---|---|---|---|
| ধাপ-প্রবাহ | প্রথম-শ্রেণি SSE চুক্তি | emit বাস্তব, FE-অমিল | P-A |
| উদ্ধৃতি-সত্য | citation-or-nothing | ০-উৎসেও synthesis | P-B |
| বহু-provider | search+crawler সমন্বয় | ১ provider + allowlist-প্রতিবন্ধক | P-C |
| বহুভাষিক | script-aware নিষ্কাশন | [a-zA-Z]{3,} — বাংলা-অন্ধ | P-E |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main fb53ad8, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_04_BROWSER_AUTOMATION_POWER_UP_2026-09-17.md` P-G | AutonomousBrowserAgent grounding | **সীমানা:** বাস্তবায়ন সেখানে; এখানে কেবল fallback-এর সততা (চুপচাপ ০-ফল নয়) |
| `MODULE_03_LLM_GATEWAY_POWER_UP_2026-09-17.md` | খরচ-টেলিমেট্রি | **সীমানা:** billing সেখানে; এখানে per-session খরচ *প্রদর্শন* (task_type-মেটাডেটা বিদ্যমান) |
| `MODULE_06_RUN_FABRIC_COMPLETION_POWER_UP_2026-09-17.md` | RunType research | সম্পূরক — P-D-র খরচ/ধাপ run-row-প্রবাহিত (M06 P-A-র run_scope-এ) |
| `MODULE_01`/`MODULE_07` | মেমোরি/context | সম্পূরক — step-10 save_memory (L526) M01-স্টোর; KB-index M07-এর RAG-উৎস — সংযোগ, রিরাইট নয় |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` :841/:842 | scout-rows | এই নীলনকশার P-D/P-G সরাসরি নিরাময় |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M8 | research UX | সম্পূরক — এই নীলনকশা backend-সত্য দেয়; M8 UX তার উপরে |

**গ্রেপ-যাচাই:** fresh main fb53ad8-এ কোনো বিদ্যমান ডকুমেন্ট SSE-চুক্তি-মেরামত, grounding-গেট, provider-সংযোগ বা বাংলা-নিষ্কাশনের execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **Governed crawler:** `crawler.py` — policy-gate→cache→robots(RFC-9309)→rate-slot→per-hop SSRF→BS4-clean→dedup→BFS(depth 1-5, ≤50 পৃষ্ঠা)।
2. **নিরাপত্তা-নীতি:** `policy.py` fail-closed SSRF/domain gate + TrustLevel; `robots.py` 1h-cache/512-domain।
3. **১০-ধাপ পাইপলাইন:** refine→sub-queries→search→index→key-info→gap-analysis→follow-up→synthesis→citation-report→save-memory — সব LLM-কল gateway-সংযুক্ত (distinct task_type)।
4. **স্থায়িত্ব:** deep_research_sessions + crawl_policies/history/events (migration-সূচিত); 4 endpoint মাউন্টেড।
5. **SSE-যন্ত্র:** on_step + emit_reasoning_step — বাস্তব; Redis গবেষণা-ক্যাশ (TTL 24h)।
6. **Dedup/extractor:** SHA256+3-shingle Jaccard 0.80; ExtractiveSummarizer (zero-token)।
7. **Admin-তল:** crawler_admin.py — policy CRUD + history/events (admin-guarded)।
8. **টেস্ট-বীজ:** crawler/policy/extractor/dedup-এ ২৭ টেস্ট (৪৬৫ LOC)।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **দৃশ্যমান পণ্য** — SSE-চুক্তি-অমিল: UI-তে ধাপ/রিপোর্ট কখনোই নেই।
2. **সৎ-গেট** — ০-উৎসে synthesis; চুপচাপ-ব্যর্থ fallback।
3. **provider-সত্য** — একমাত্র DDG-scrape + allowlist-প্রতিবন্ধক; DDGS অসংযুক্ত+undeclared।
4. **পর্যবেক্ষণ** — crawl_events-লেখক শূন্য; per-session খরচ অদৃশ্য; max_steps অব্যবহৃত।
5. **বাংলা** — regex/stopwords/danda তিনটিতেই অন্ধ।
6. **ঐক্য ও টেস্ট** — ৩ বিচ্ছিন্ন গবেষণা-পৃষ্ঠ; pipeline-নিজে ০-টেস্ট; scout-config/flag শূন্য।

### ২.৩ কী করতে হবে (গবেষণা-সত্যকরণের ৭ ধাপ)

```text
P-A: SSE-চুক্তি মেরামত      → এক-স্কিমা-মডিউল (emit↔parse), contract-test, history-ক্ষেত্র
P-B: সৎ-grounding গেট       → ০-উৎস → explicit no-sources রিপোর্ট; চুপচাপ-ব্যর্থতা শূন্য
P-C: provider-সত্য           → core/search.web_search (DDGS) provider-1 + scout deep-fetch;
                              seed-policy-তে duckduckgo.com; pyproject-ঘোষণা
P-D: পর্যবেক্ষণ-জাগরণ        → CrawlerTelemetry → record_event প্রোডাকশন-কল; per-session
                              খরচ-প্রদর্শন; max_steps বাস্তব
P-E: বাংলা-সচেতন নিষ্কাশন    → tokenizer + Bangla stopwords + danda-বিভাজন (zero-token অটুট)
P-F: তিন-পৃষ্ঠ ঐক্য          → slash/spoke → _run_research_pipeline ডেলিগেশন
P-G: চুক্তি-টেস্ট-সুরক্ষা     → pipeline contract + respx-মকড E2E + scout-config/flags
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** নতুন ছোট স্কিমা-মডিউল (scout-বা routes-প্যাকেজে) — emit ও parse দুই-পক্ষই তা থেকে; backend-emit আপডেট (step_update/complete বা FE-আপডেট — এক-সিদ্ধান্ত); history-রেসপন্সে report-ক্ষেত্র; FE-parser আপডেট একই PR; contract-test দুই-পক্ষে।
- **P-B:** `_run_research_pipeline`-এর synthesis-পূর্বে গেট: sources==0 → explicit no-sources রিপোর্ট (কারণ+পরবর্তী-পরামর্শসহ); fallback-ব্যর্থতা event-হিসেবে প্রবাহিত; flag `SUPREMEAI_RESEARCH_HONEST_GATE=true` (default true — সত্য-ডিফল্ট)।
- **P-C:** `_web_search`-এ provider-চেইন: DDGS (বিদ্যমান core/search) → scout-governed scrape (policy থাকলে); seed-policy-তে duckduckgo.com + নথি; `ddgs` pyproject-এ ঘোষণা; provider-ব্যর্থতায় পরবর্তী।
- **P-D (পর্যবেক্ষণ-জাগরণ, জিরো-বাইপাস ইনফারেন্স ও প্রি-কল বাজেট রিজার্ভেশন):**
  - `CrawlerTelemetry.emit_event`-এ `persistence.record_event` কল (bounded row); admin-events অ-শূন্য-যাচাই।
  - **Zero-Bypass Binding:** Scout-এর প্রতিটি সিন্থেসিস ও সামারাইজেশন কল Module 03 LLM Gateway-র `InferenceContext(task_type='deep_research', budget_scope='user_interactive')` দিয়ে পরিচালিত হবে।
  - **টোকেন ও ক্রলিং বাজেট রিজার্ভেশন:** একটি গভীর গবেষণায় যাতে রানঅ্যাওয়ে স্ক্র্যাপিং ও হাজার হাজার টোকেন খরচ না হয়, সেজন্য টাস্ক শুরুর আগেই প্রি-কল লেভেলে একটি নির্দিষ্ট বাজেট লিজ (`BudgetReservation`) রিজার্ভ করা হবে; বাজেট সীমা শেষ হলে অতিরিক্ত ক্রল স্বয়ংক্রিয়ভাবে বন্ধ হয়ে সারসংক্ষেপ তৈরি হবে।
  - `max_steps` ও `max_pages` প্যারাম-প্রয়োগ (ডিফল্ট-মান env/config-পঠিত — কোড-কনস্ট্যান্ট নয়)।
- **P-E:** `extractor.py`-তে বাংলা-tokenizer (শব্দ-বিভাজন), Bangla-stopwords **data-file থেকে লোডেড/সম্প্রসারণযোগ্য (কোড-inline হার্ডকোড তালিকা নয় — zero-hardcode সংশোধন)**, danda (`।`) বাক্য-বিভাজক; dedup-shingle বাংলা-সচেতন; টেস্ট: বাংলা-কর্পাসে নিষ্কাশন; zero-token সম্পত্তি-টেস্ট অটুট।
- **P-F (তিন-পৃষ্ঠ ঐক্য ও টেকসই আর্টিফ্যাক্ট স্টোরেজ):**
  - slash_commands.py-র /research ও capability_adapters-র spoke → `_run_research_pipeline`-ডেলিগেশন (চুক্তি-মোড়ক অটুট); এক পাইপলাইন, এক টেস্ট-পৃষ্ঠ।
  - গবেষণার চূড়ান্ত রিপোর্টটি ক্লিকযোগ্য সোর্স ও মেটাডেটা সহ অবজেক্ট স্টোরেজে স্থায়ী আর্টিফ্যাক্ট হিসেবে সেভ হবে এবং ইউজারের চ্যাট টাইমলাইনে যুক্ত হবে।
- **P-G:** pipeline contract-test (১০-ধাপ ক্রম) + respx-মকড E2E (policy→crawl→report); `core/config.py`-তে scout-সেকশন (flags: honest-gate, provider-chain, events); kill-switch।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **পতাকাবাহী জাগরণ (P-A):** /research পৃষ্ঠা প্রথমবার জীবন্ত — ধাপ-প্রবাহ+রিপোর্ট; ব্যবহারকারী-আস্থার প্রথম-সেকেন্ড।
2. **গবেষণা-বিশ্বাস (P-B):** "রিপোর্ট" মানেই উৎস-সমর্থিত — fabrication-পৃষ্ঠ শূন্য; উদ্ধৃতি-সত্য >95% (target)।
3. **রানঅ্যাওয়ে খরচ প্রতিরোধ (P-D):** গেটওয়ের প্রি-কল বাজেট রিজার্ভেশন ও ক্রল লিমিটের ফলে গভীর গবেষণায় অনাকাঙ্ক্ষিত বিল হওয়ার ঝুঁকি শূন্য।
4. **টেকসই রিপোর্ট আর্টিফ্যাক্ট (P-F):** ব্যবহারকারী যেকোনো সময় তার পূর্ববর্তী গবেষণার পূর্ণাঙ্গ তথ্য ও সোর্স লিংক রিভিজিট করতে পারবেন।
5. **কাজ-করা provider (P-C):** allowlist-প্রতিবন্ধক শেষ; প্রথম কোয়েরি থেকেই ফল; বহু-provider-পথ খোলা।
6. **মূল-বাজার ভাষা (P-E):** বাংলা-গবেষণা প্রথমশ্রেণির — পণ্যের নিজস্ব পরিচয়ের সাথে সামঞ্জস্য।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **চুক্তি-পরিবর্তনে ভাঙা-consumer:** অন্য SSE-শ্রোতা থাকলে — প্রশমন: এক-স্কিমা-উৎস, consumer-grep, contract-test, একই-PR-এ দুই-পক্ষ।
2. **honest-gate-এ বেশি ব্যর্থ-অনুভূতি:** কিছু কোয়েরিতে "উৎস নেই" — প্রশমন: P-C provider-বৃদ্ধি আগে/সাথে; রিপোর্টে কারণ+পরামর্শ; সত্য > মিষ্টি-মিথ্যা (Constitution #5)।
3. **DDGS-নির্ভরতা:** rate-limit/অনুপলব্ধতা — প্রশমন: provider-চেইন (scout fallback), বিদ্যমান Redis-ক্যাশ, নথিভুক্ত সীমা।
4. **events-ভলিউম:** উচ্চ-ক্রলে rows — প্রশমন: bounded + retention।
5. **পরিসর-ঝুঁকি:** "research" নামে নতুন এজেন্ট-ফিচার-লোভ — প্রশমন: কোনো নতুন AI-ক্ষমতা নয়; সংযোগ-সত্য মাত্র; প্রতিটি Phase আলাদা Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. AutonomousBrowserAgent-এর বাস্তব grounding — Module 04 P-G (এখানে কেবল সততা)।
2. Billing/quota-কোড — Module 03 (এখানে প্রদর্শন মাত্র)।
3. নতুন SERP-API/অর্থ-ব্যয় provider — P-C বিদ্যমান DDGS-দিয়ে; বহিরাগত API ভবিষ্যৎ-সিদ্ধান্ত।
4. Report-এর md/PDF রূপান্তর — ভবিষ্যৎ প্ল্যান-প্রার্থী।
5. M8-UX-রিডিজাইন — roadmap-পরিসর।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | স্কিমা-মডিউল+গেট+provider-চেইন বিদ্যমান ফাইলে; extractor-বৃদ্ধি |
| 3. No new infrastructure | ✅ | টেবিল/Redis/robots-cache বিদ্যমান; ddgs ঘোষণা-মাত্র |
| 4. No CI cost amplification | ✅ | contract+E2E টেস্ট বিদ্যমান স্যুটে (respx-মকড — বাহ্যিক কল নয়) |
| 5. No credit-burn risk | ✅ | পাইপলাইন-কল gateway-বাজেটে (M03); কোনো নতুন LLM-পথ নয় |
| 6. No academic leaderboard | ✅ | UI-liveness, citation-সত্য, events-গণনা — সরাসরি প্রোডাক্ট-মান |
| 7. Realistic resource budget | ✅ | bounded events; depth/পৃষ্ঠা-সীমা বিদ্যমান |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main fb53ad8 sed/grep-যাচাই (last_verified-তালিকা); সীমানা-পাঠ (M03/M04/M06) |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ citation-or-nothing; ০-উৎস-synthesis শূন্য |
| #6 Policy Before Power | ✅ governed crawl অটুট; provider-ও policy-চেইনে |
| #8 Graceful Degradation | ✅ provider-চেইন; fallback-সততা |
| #13 No Silent Failure | ✅ চুপচাপ-০-ফল শূন্য; ব্যর্থতা event-প্রবাহিত |
| #14 Zero-Mock Doctrine | ✅ গবেষণা-স্বাদু ফেব্রিকেশন — এই নীলনকশার মূল-লক্ষ্য |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** বিদ্যমান ২৭ টেস্ট শূন্য-ব্যর্থতা; P-A contract-test (দুই-পক্ষ); P-B grounding-গেট টেস্ট (০-উৎস → no-sources); P-C provider-চেইন-টেস্ট (মকড); P-G respx-E2E (policy→crawl→report)।
- **Gate 5 (live):** বাস্তব কোয়েরিতে FE-events >0; ০-উৎস-synthesis শূন্য; ২৪-ঘণ্টায় crawl_events >0; বাংলা-কোয়েরি রিপোর্টে উদ্ধৃতি-fetch-যাচাই >95% (target)।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; কোনো schema/data-loss path নেই।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত | provider-চেইন ফ্রি-প্রথম (DDGS → governed scrape — কোনো পরিশোধিত search-API নয়); Redis-ক্যাশ/robots-cache বিদ্যমান |
| Lightweight | ✅ সংগত | ছোট স্কিমা-মডিউল + বিদ্যমান SSE/bus পুনঃব্যবহার; bounded row |
| Fast & smooth | ✅ সংগত | honest-gate সংশ্লিষ্ট হট-পথ ব্যয় যোগ করে না; provider-ব্যর্থতায় পরবর্তী-চেইন |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | P-E-র stopwords কোড-inline প্রস্তাব ছিল → data-file-লোডেড; P-D-র max_steps ডিফল্ট env/config-পঠিত (§২.৪ সংশোধিত) |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `extractor.py` L210/L221-র `[a-zA-Z]{3,}` regex অটুট (বাংলা-অদৃশ্য — P-E প্রাসঙ্গিক); `crawler.py` emit_event বিদ্যমান (P-D প্রাসঙ্গিক)।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১–৭ (প্রকাশিত):** Module 01 Memory → 02 Orchestration → 03 LLM Gateway → 04 Browser → 05 Self-Evolution → 06 Run Fabric → 07 Context Engine।
- **চক্র ৯ (কিউতে):** Module 09 — Dormant Tools সক্রিয়করণ (`backend/tools/` — ৪৪ dormant) — বৃহত্তম অব্যবহৃত ক্ষমতা-ভাণ্ডার; এই মডিউলের pipeline-ঐক্য-দর্শন tools-সক্রিয়করণ-পাইপলাইনেও প্রবাহিত হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
