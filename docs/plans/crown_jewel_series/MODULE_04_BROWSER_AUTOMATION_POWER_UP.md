---
id: crown-jewel-module-04-browser-automation-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 04: Browser Automation Stack Power-Up (এজেন্টের 'হাত'-কে সৎ, কার্যকর ও পর্যবেক্ষণযোগ্য করা — দ্বৈত রাউটার, ভাঙা takeover ও ফেব্রিকেটেড সাফল্য পর্যুগ করার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Browser Circle (backend/tools/browser/ + backend/browser/ + backend/api/routes/browser/ + backend/api/routes/browser_routes.py + backend/api/routes/session_takeover.py + backend/core/browser_session_manager.py + backend/core/playwright_manager.py + backend/services/scraper/)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৪ — একটি মডিউল (Browser Automation Stack), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main ad1611e (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/tools/browser/playwright_browser_agent.py (PlaywrightBrowserAgent, 689 লাইন — ORPHAN: বাস্তব caller কেবল ভাঙা takeover + মৃত MCP dispatcher; test_playwright_browser_agent.py 861 লাইন)"
  - "backend/core/browser_session_manager.py (L30 allowed_actions = navigate/screenshot/content/extract — click/fill/type বাদ → canonical API-তে সর্বদা 403)"
  - "backend/api/routes/session_takeover.py (L408 agent.get_or_create_session — PlaywrightBrowserAgent-এ এই method অস্তিত্বহীন → AttributeError, grep-verified NOT FOUND)"
  - "backend/api/routes/browser/ (১৫ submodule, 2,349 লাইন — canonical /api/browser, routers.py:21)"
  - "backend/api/routes/browser_routes.py (845 লাইন — দ্বিতীয় /api/browser; ৪ endpoint routers.py:268-এ shadowed)"
  - "backend/core/playwright_manager.py (get_global_browser — semaphore 2-page cap, missions suite-এ টেস্টেড)"
  - "backend/browser/autonomous_browser.py (AutonomousBrowserAgent — hardcoded ৩-ধাপ স্ক্রিপ্ট L93-114, goal অগ্রাহ্য; 'navigate' L132-এ কখনো navigate করে না)"
  - "backend/browser/semantic_dom.py (L90-99 mock-elements fallback) + vision_grounding.py (শুধু image-length পাঠায় → কাল্পনিক coords)"
  - "backend/api/routes/browser_action_registry.py (L194-198 ফেব্রিকেটেড 142ms metrics)"
  - "backend/integrations/browser_use_adapter.py (272 লাইন — flag-gated, 0 caller, DORMANT)"
  - "backend/services/browser/ (aiohttp :8002 microservice — 0 caller, compose-এ নেই, DORMANT)"
  - "backend/core/agents/live/browser_agent.py (BrowserAgent 209 লাইন — LIVE: agent_registry.py:50, scraper routes)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md (ERR-A03/A06 — সৎ-ব্যর্থতা ফিক্স প্রোডাকশন-পথে প্রমাণিত)"
  - "frontend browserService.ts (L35-47 → POST /api/browser/automation/sessions|actions — বাস্তব wired)"
implements:
  - "Canonical API-কে সত্যিই interactive করা — allowed_actions ফিক্সে click/fill/type unlock (আজ 403)"
  - "HITL takeover মেরামত — ভাঙা session-acquire + স্ক্রিনকাস্ট বাস্তব CDP-তে"
  - "৫টি false-assurance surface পর্যুগ — Constitution #5/#13 browser-অঙ্গনে প্রয়োগ"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main ad1611e: browser_session_manager.py L30 sed-verified; session_takeover.py L408 sed-verified + get_or_create_session grep NOT FOUND; playwright_browser_agent.py wc 689; browser_routes.py wc 845; caller-grep সম্পন্ন; autonomous_browser.py L93-114/L132 agent-পাঠ-যাচাইকৃত)"
code_evidence:
  - "backend/core/browser_session_manager.py L30 — allowed_actions = ('navigate','screenshot','content','extract') — click/fill/type নেই; কিন্তু _automation.py:35 ৭টি action advertise করে → প্রতিটি interactive কল 403"
  - "backend/api/routes/session_takeover.py L408 — agent.get_or_create_session(session_name=session_id) — PlaywrightBrowserAgent-এ grep 'def get_or_create_session' = NOT FOUND → HITL takeover জন্মেই মৃত (AttributeError)"
  - "backend/api/routes/routers.py L268 — browser_routes.py-র screenshot/ai-action/security-scan/browse-session endpoint ৪টি shadowed — 845 লাইনের অর্ধেক অদৃশ্য"
  - "backend/api/routes/_surf_actions.py L41-43 — 1×1 PNG mock screenshot; browser_action_registry.py L194-198 — ফেব্রিকেটেড 142ms latency metrics — দুটিই সৎ-পরীক্ষা (ERR-G purge) থেকে রক্ষা পাওয়া মিথ্যা"
  - "backend/browser/semantic_dom.py L90-99 — mock-elements fallback; vision_grounding.py — কেবল image-এর দৈর্ঘ্য পাঠায়, ছবি নয় → VLM-ভিত্তিক coords কাল্পনিক"
  - "backend/browser/autonomous_browser.py L93-114 — hardcoded ৩-ধাপ স্ক্রিপ্ট, ব্যবহারকারীর goal অগ্রাহ্য; L132 'navigate' step কখনো navigation করে না — deep_research.py:262 এই এজেন্টকেই fallback করে"
  - "backend/tools/browser/playwright_browser_agent.py — 689 লাইন; প্রতি-action নতুন browser spin-up; type_text (L685-689) type নয় read করে; url=None হলে fake success (L683)"
  - "backend/integrations/browser_use_adapter.py — 272 লাইন modern browser-use ইঞ্জিন অ্যাডাপ্টার — flag-gated, 0 production caller"
  - "backend/api/routes/browser_routes.py L734-755 — gallery endpoint কিছুই persist করে না — screenshots base64/tmp-তেই মরে; কোনো browser telemetry hook নেই"
  - "backend/services/browser/ + backend/tools/browser/mcp_tools.py + web_fallback_agent.py — তিনটি সম্পূর্ণ dormant surface (0 caller)"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) allowed_actions ফিক্সে _automation action-integration টেস্ট (navigate→click→screenshot চেইন), (২) takeover integration টেস্ট (WS→session acquire→screencast frame), (৩) বিদ্যমান ~2,027 টেস্ট-LOC (test_playwright_browser_agent.py 861, test_playwright_manager.py 319, test_scraper_service.py 301, test_browser_agent.py 219) zero regression, (৪) route-parity meta-test — dual-router merge-এ কোনো OpenAPI path হারাবে না"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "Interactive-সংজ্ঞা: canonical /api/browser-এ click/fill/type 200-উত্তর দেয় (SSRF/policy gate অটুট) — 403-কারণ দূর"
  - "Takeover-সংজ্ঞা: WS সংযোগ → session acquire → বাস্তব screencast ফ্রেম — AttributeError শূন্য"
  - "সত্য-সংজ্ঞা: ৫টি false-assurance surface হয় বাস্তব, নয় honest 501/422 — fabricated উত্তর শূন্য"
  - "Route-parity: dual-router merge-এ OpenAPI path-set অপরিবর্তিত বা স্পষ্ট-নথিভুক্ত deprecation; 721-route zero regression CI প্রমাণ"
test_evidence_note: "Gate 4-এ action-chain ও takeover integration টেস্ট; Gate 5-এ live — বাস্তব ব্রাউজার-সেশনে screenshot artifact-স্থায়িত্ব ও per-action latency পর্যবেক্ষণ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "click/fill/type unlock-এ অপব্যবহার-ঝুঁকি (arbitrary interaction) — প্রশমন: বিদ্যমান SSRF gate + URL-permission/policy/pause স্তর অটুট; per-session grant বিকল্প"
  - "Takeover-এ bandwidth ঝুঁকি (screencast) — প্রশমন: fps/quality cap, বিদ্যমান disconnect-aware WS প্যাটার্ন"
  - "Dual-router merge-এ লুকানো consumer ভাঙা — প্রশমন: আগে uniques-কে canonical-এ port, পরে deprecation-warning, পরিমাপ, অপসারণ সবশেষে"
  - "False-assurance purge-এ frontend ব্যর্থ-UX — প্রশমন: honest 501/422 + explicit error-body চুক্তি; EvolutionForge-ধাঁচ fallback"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag; কোনো schema migration নেই (artifact storage বিদ্যমান objects-API প্যাটার্ন)"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: canonical API-তে সফল interactive action = 0% (সব 403); কার্যকর HITL takeover সেশন = 0; জীবিত false-assurance surface = 5; স্থায়ী screenshot artifact = 0 (সব ক্ষণস্থায়ী); browser-কলের telemetry-কৃত অনুপাত = 0%"
measurement_method:
  - "(a) interactive-liveness: /api/browser/automation/actions-এ click/fill/type সাফল্য-হার (লক্ষ্য >95% বৈধ সেশনে)"
  - "(b) takeover-liveness: ২৪-ঘণ্টায় সফল takeover সেশন গণনা (hard threshold: AttributeError শূন্য)"
  - "(c) truth-গণনা: জীবিত fabricated surface সংখ্যা (লক্ষ্য 0), স্থায়ী artifact গণনা (>0 প্রতি সক্রিয় সেশনে)"
  - "(d) regression: OpenAPI path-parity + বিদ্যমান browser টেস্ট-স্যুট শূন্য-ব্যর্থতা"
success_threshold: "interactive success → >95% বৈধ সেশনে (target); takeover AttributeError → 0 (hard); fabricated surfaces → 0 (hard); path-parity → 100% (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৪-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 04: Browser Automation Stack Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Browser Circle (`backend/tools/browser/` + `backend/browser/` + `backend/api/routes/browser*` + `backend/core/browser_session_manager.py` + `backend/core/playwright_manager.py`)
**Main anchor:** fresh main `ad1611e` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost / 0 schema migration / 0 route deletion (merge-পর্বে deprecation-ব্যতীত)

## বাংলা সারসংক্ষেপ

মেমোরি স্মৃতি, orchestration মেরুদণ্ড, gateway হৃৎপিণ্ড হলে — **browser stack হলো এজেন্টের হাত**: ওয়েবে দেখা, চাপা, লেখা, তোলা। এই হাত আশ্চর্য অবস্থায়: *আঙুলের গোড়ায় প্রচুর শক্তি, কিন্তু কবজি তিন জায়গায় ভাঙা*। শক্তির পাশ দেখুন: stealth/anti-bot বাস্তব (UA+WebGL+canvas spoof, bezier human-input — `browser_stealth.py`), proxy-rotation বাস্তব (ProxyManager+proxy_list.json), এনক্রিপ্টেড cookie/session persistence বাস্তব, credential vault+audit বাস্তব, SSRF-গেট বাস্তব, সীমিত-সমান্তরালতা বাস্তব (session semaphore + 2-page cap — `playwright_manager.py`)। কিন্তু কবজি: **(১)** canonical API-তে click/fill/type সর্বদা **403** — `browser_session_manager.py` L30-র allowed_actions-এ এই তিনটি নেই, অথচ `_automation.py` ৭টি action advertise করে — অর্থাৎ interactive browser-পণ্য কাগজে-কলেমে; **(২)** HITL takeover **জন্মেই মৃত** — `session_takeover.py` L408 এমন method ডাকে (`get_or_create_session`) যা `PlaywrightBrowserAgent`-এ অস্তিত্বহীন (grep NOT FOUND); **(৩)** দুই ভাই-রাউটার — canonical `/api/browser` (2,349 লাইন) আর `browser_routes.py` (845 লাইন) — দ্বিতীয়টির ৪ endpoint প্রথমটির কাছে shadowed। তার উপর ৫টি false-assurance surface জীবিত: 1×1 PNG mock screenshot, ফেব্রিকেটেড 142ms metrics, semantic-DOM mock-elements, ছবি-ছাড়া vision-coords, আর goal-অগ্রাহ্য hardcoded autonomous লুপ — যেটা deep-research-এর fallback। সবচেয়ে কষ্টের: 689-লাইনের পতাকাবাহী `PlaywrightBrowserAgent` নিজেই অনাথ — প্রতি-action নতুন browser, type-এর বদলে read, url-শূন্যে fake success।

এই নীলনকশা হাতটিকে crown-jewel স্তম্ভে তোলে ৭ ধাপে: **(A)** allowed_actions ফিক্স → **(B)** takeover মেরামত + বাস্তব CDP screencast → **(C)** এক canonical /api/browser → **(D)** false-assurance purge → **(E)** artifact pipeline → **(F)** observability parity → **(G)** আধুনিক ইঞ্জিন-grounding ও অনাথ retirement। প্রতিযোগীরা (Playwright ইকোসিস্টেম, browser-use, Skyvern-ধাঁচ) প্রমাণ করেছে জয় এখানেই: সৎ session, সত্য artifact, জবাবদিহি প্রতি-action-এ — আর SupremeAI-র সৌভাগ্য: বাহু-শক্তি ইতিমধ্যেই নির্মিত; কাজটি *কবজি-মেরামত* — নতুন হাত বসানো নয়।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৪.১ Playwright ইকোসিস্টেম — এক session, পূর্ণ জীবনচক্র

- Playwright-এর মতবাদ: এক session/context জুড়ে navigation→interaction→artifact→cleanup — প্রতিটি ধাপ পরিমাপযোগ্য (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `playwright_manager.py`-র global-session + cleanup ঠিক এই মতবাদে — খালি জায়গা: `PlaywrightBrowserAgent`-এর প্রতি-action spin-up এই সুবিধা নষ্ট করে (P-G)।

### ৪.২ browser-use — LLM-native action vocabulary

- browser-use-ধাঁচ ইঞ্জিন DOM-সচেতন LLM interaction জনপ্রিয় করেছে — goal→actions সরাসরি (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `browser_use_adapter.py` (272 লাইন) ইতিমধ্যেই লেখা — কিন্তু 0 caller; P-G-তে flag-gated enable।

### ৪.৩ Skyvern-ধাঁচ — vision+DOM সংযুক্ত grounding

- আধুনিক browser-এজেন্টরা ছবি+DOM একসাথে দেখে grounding করে (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `vision_grounding.py` কাঠামো আছে কিন্তু ছবি পাঠায় না (শুধু length) — মিথ্যা coords; P-D-তে সৎ বা মেরামত।

### ৪.৪ HITL-স্ক্রিনকাস্ট মতবাদ — মানুষ যখন চাকা ধরে

- উন্নত agent-প্ল্যাটফর্মগুলো live-view + intervention দেয় — CDP screencast মানক উপায় (established vendor pattern)।
- SupremeAI-র সংযোগবিন্দু: `session_takeover.py`-র ScreencastStreamer কাঠামো আছে, কিন্তু session-acquireই ভাঙা (L408) — P-B-র মেরামত-বিন্দু।

### ৪.৫ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main ad1611e-verified)

| প্রতিযোগী | যা করে | SupremeAI আজ (ad1611e-verified) | গ্যাপ |
|---|---|---|---|
| Playwright | session-জুড়ে পূর্ণ চক্র | manager-মতবাদ আছে; এজেন্ট প্রতি-action spin-up করে | P-G |
| browser-use | LLM-native actions | adapter লেখা, 0 caller | P-G |
| Skyvern-ধাঁচ | vision+DOM grounding | vision কাঠামো আছে, ছবি পাঠায় না | P-D |
| HITL-screencast | live-view+intervention | কাঠামো আছে, acquire ভাঙা | P-B |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main ad1611e, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `MODULE_01_MEMORY_POWER_UP_2026-09-17.md` | মেমোরি একীকরণ | সম্পূরক — `browsing_memory.py` (100 লাইন, লাইভ) মেমোরি-একীকরণের পরে ঐতিহাসিক-ব্রাউজিং রিকলে যুক্ত হতে পারে (এখানে out-of-scope) |
| `MODULE_02_ORCHESTRATION_CORE_POWER_UP_2026-09-17.md` | Kernel single-door | সম্পূরক — browser-tool dispatch kernel-দরজা দিয়ে গেলে policy-gate অভিন্ন হবে; এই মডিউল browser-নিজস্ব স্তর মাত্র |
| `MODULE_03_LLM_GATEWAY_POWER_UP_2026-09-17.md` | Inference-spine সত্য-উপাত্ত | সম্পূরক — P-F observability প্যাটার্ন Module 03-র telemetry-মতবাদ অনুসরণ করবে |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` ERR-A03/A06 | সৎ-ব্যর্থতা ফিক্স | ইতোমধ্যে মেরামতকৃত — এই নীলনকশা সেই মতবাদকে বাকি ৫ surface-এ বাড়ায় (P-D) — alignment |
| `docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md` M4 Browser | রোডম্যাপ অবস্থান | সম্পূরক — M4-এর পূর্বশর্ত (সৎ session+artifact) এই নীলনকশাই গড়ে |
| `backend/services/scraper/` microservice | স্ক্র্যাপিং :8082 | ভিন্ন উপ-স্তর (লাইভ, compose-wired) — এই নীলনকশা তাকে অটুট রাখে; interactive-browser স্তর আলাদা |

**গ্রেপ-যাচাই:** fresh main ad1611e-এ কোনো বিদ্যমান ডকুমেন্ট allowed_actions-unlock, takeover-মেরামত, dual-/api/browser merge বা browser false-assurance purge-এর execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **Canonical API:** `backend/api/routes/browser/` — ১৫ submodule, 2,349 লাইন, 69 browser-OpenAPI path; ফ্রন্টএন্ড `browserService.ts` L35-47 বাস্তব wired।
2. **Session-manager চুক্তি:** `browser_session_manager.py` — create/get/pause/resume/URL-permission; `playwright_manager.py` — global browser + 2-page semaphore + cleanup।
3. **Stealth বাহু:** `browser_stealth.py` (177 লাইন — UA/webdriver/WebGL/canvas spoof) + `human_behavior.py` (bezier input) + ProxyManager rotation।
4. **নিরাপত্তা-স্তর:** SSRF gate, encrypted cookie/session store, credential vault+audit, policy/pause।
5. **এজেন্ট-স্তর:** `core/agents/live/browser_agent.py` (209 লাইন — agent_registry.py:50 থেকে লাইভ; recipe-based, SSRF-aware, WebScraper fallback)।
6. **গবেষণা-সংযোগ:** `deep_research.py:262` → AutonomousBrowserAgent fallback; scraper microservice (compose-wired :8082, 301-লাইন টেস্ট)।
7. **টেস্ট-সম্পদ:** ~2,027 LOC — agent contract, cookie-encryption/rotation, cleanup-on-failure, manager-ক্ষমতা সব পিনকৃত।
8. **আধুনিক-ইঞ্জিন বীজ:** `browser_use_adapter.py` (272 লাইন) লেখা কিন্তু অসংযুক্ত।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **Interactive বাস্তবতা** — allowed_actions-এ click/fill/type নেই → advertise-কৃত actions সর্বদা 403।
2. **জীবন্ত HITL takeover** — `get_or_create_session` অস্তিত্বহীন → AttributeError; screencast কাঠামো অচল।
3. **এক দরজা** — দুই /api/browser রাউটার; ৪ endpoint shadowed; 845 লাইনের অর্ধেক অদৃশ্য।
4. **সৎ ৫-surface** — 1×1 PNG, fake 142ms metrics, mock DOM elements, ছবি-ছাড়া vision, hardcoded autonomous লুপ।
5. **Artifact স্থায়িত্ব** — screenshots base64/tmp-তে মরে; gallery endpoint কিছু persist করে না।
6. **পর্যবেক্ষণযোগ্যতা** — browser-action-এ 0 telemetry/event hook; per-action latency/cost অপরিমিত।
7. **স্বাস্থ্যকর এজেন্ট-কেন্দ্র** — পতাকাবাহী agent অনাথ + প্রতি-action spin-up + type-বিকলতা + fake-success; PDF/downloads/tabs/চৌকস-wait অনুপস্থিত।

### ২.৩ কী করতে হবে (browser-হাত সৎ-সক্রিয়করণের ৭ ধাপ)

```text
P-A: allowed_actions ফিক্স        → click/fill/type unlock (SSRF/policy অটুট) — interactive বাস্তব
P-B: Takeover মেরামত             → session_manager-সংযুক্ত acquire + বাস্তব CDP startScreencast
P-C: এক canonical /api/browser   → uniques port → deprecation → shadowed retirement
P-D: False-assurance purge (৫)   → বাস্তব অথবা honest 501/422 — fabricated শূন্য
P-E: Artifact pipeline           → screenshots → objects-API + chat-timeline স্থায়িত্ব
P-F: Observability parity        → per-action event+latency → error-bus/telemetry
P-G: ইঞ্জিন-grounding + retirement → autonomous agent বাস্তব session; browser_use flag-gated;
                                     PlaywrightBrowserAgent সংযোজন-সংশোধন; dormant surfaces সিদ্ধান্ত
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A:** `browser_session_manager.py` default allowed_actions-এ click/fill/type যোগ (অথবা per-session grant API); `_automation.py`-র advertise-set-এর সাথে সম্পূর্ণ মিল; SSRF gate + URL-permission অপরিবর্তিত; integration টেস্ট: navigate→click→fill→screenshot চেইন।
- **P-B:** `session_takeover.py` L408 acquire-কে `session_manager`-সংযুক্ত করা (PlaywrightBrowserAgent-এ নতুন পাতলা method — বিদ্যমান manager-ডেলিগেশন); screencast `Page.startScreencast` CDP-তে (fps/quality cap — **cap-মান env-পঠিত, কোড-কনস্ট্যান্ট নয়**; per-session opt-in, default off); WS চুক্তি অপরিবর্তিত।
- **P-C:** ধাপ ১: `browser_routes.py`-র ৪ shadowed-unique endpoint-এর কার্যক্রম canonical package-এ port; ধাপ ২: পুরনো path-এ deprecation-warning; ধাপ ৩: route-parity meta-test-সহ retirement — OpenAPI path-set প্রমাণসহ।
- **P-D:** ৫ surface-এর প্রতিটিতে দুই-সমাপ্তির একটি: বাস্তব বাস্তবায়ন (যেমন vision-এ প্রকৃত image bytes পাঠানো) অথবা honest 501/422 + explicit error-body; `browser_action_registry`-র mock /test endpoint flag-গেটেড বা অপসারিত।
- **P-E:** screenshots → বিদ্যমান objects-API প্যাটার্নে স্থায়ী সংরক্ষণ + gallery endpoint বাস্তব + chat-timeline-এ সংযুক্তি; storage-quota guard।
- **P-F (Observability ও জিরো-বাইপাস ইনফারেন্স বাউন্ডারি):**
  - প্রতি browser-action-এ event (session_id/action/latency/সাফল্য) → বিদ্যমান error_event_bus + telemetry-মতবাদ (Module 03 প্যাটার্ন)।
  - **Zero-Bypass Rule:** ব্রাউজার এজেন্ট কোনোভাবেই সরাসরি কোনো এআই প্রোভাইডার কল করতে পারবে না; ভিশন বা অ্যাকশন ডিসিশনের প্রতিটি কল Module 03-এর ক্যানোনিকাল `InferenceContext(tenant_id, run_id, task_type='browser_vision')`-এর মাধ্যমে গেটওয়ে বাজেট গার্ড পেরিয়ে এক্সিকিউট হতে হবে।
- **P-G (ইঞ্জিন-গ্রাউন্ডিং, স্যান্ডবক্স আইসোলেশন ও রিমোট টেলিপোর্ট সিঙ্ক):**
  - `AutonomousBrowserAgent.achieve` → বাস্তব session (playwright_manager) + goal-ভিত্তিক ধাপ (ধাপ/টোকেন-বাজেট সীমা env-চালিত; সীমা-শেষে honest ব্যর্থতা)।
  - **ক্লাউড স্যান্ডবক্স আইসোলেশন:** ব্রাউজার প্রসেসগুলো কনটেইনারের মেমোরি ক্র্যাশ (OOM) এড়াতে স্ট্রিক্ট মেমোরি লিমিট (Max 1GB per session) ও পেজ কনকারেন্সি সেমাফোর দিয়ে আইসোলেটেড থাকবে।
  - **Supreme Teleport ইন্টিগ্রেশন:** ব্যবহারকারী চাইলে `SUPREME_TELEPORT` রিমোট কন্ট্রোল আর্কিটেকচারের মাধ্যমে মোবাইল বা দূরবর্তী ডিভাইস থেকে সরাসরি লাইভ ব্রাউজার সেশন দেখতে ও টেকওভার করতে পারবেন।
  - `PlaywrightBrowserAgent`-এর type_text/read/fake-success সংশোধন; `mcp_tools`/`web_fallback_agent`/`services/browser` — wire অথবা delete সিদ্ধান্ত।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **পণ্য-প্রতিশ্রুতি সত্য:** "এজেন্ট ব্রাউজ করতে পারে" দাবি প্রথমবার প্রোডাকশন-সত্য — interactive API 0% → কার্যকর।
2. **HITL ও রিমোট টেলিপোর্ট স্তম্ভ (P-B/G):** মানুষ-হস্তক্ষেপ live-view সহ বাস্তব — মোবাইল বা দূরবর্তী যেকোনো ডিভাইস থেকে ব্রাউজার কন্ট্রোল প্ল্যাটফর্মের অন্যতম প্রধান আকর্ষণ।
3. **জিরো-বাইপাস খরচ নিরাপত্তা (P-F):** ব্রাউজারের ভিশন মডেল কলগুলো গেটওয়ের বাজেট রিজার্ভেশনের আওতায় থাকায় ব্রাউজার লুপে রানঅ্যাওয়ে কস্টের ঝুঁকি শূন্য।
4. **গবেষণা-মান বৃদ্ধি:** deep-research fallback hardcoded লুপ থেকে goal-ভিত্তিক হলে Scout-চক্রের ফল-মান বাড়ে (Module 08-র সাথে সিনার্জি)।
4. **আস্থা-পুনরুদ্ধার (P-D):** ৫ মিথ্যা-surface শূন্য — Constitution #5/#13 browser-অঙ্গনে সত্য; ERR-পরিবারের ধারাবাহিকতা।
5. **দৃশ্যমান মূল্য (P-E/F):** স্থায়ী artifact + per-action জবাবদিহি — ব্যবহারকারী দেখবে "এজেন্ট কী করল, কোথায় থামল"।
6. **রক্ষণ-বোঝা হ্রাস (P-C/G):** ~900+ লাইন dormant/shadowed surface-এর সিদ্ধান্ত-স্পষ্টতা।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **Interactive unlock-এ অপব্যবহার:** arbitrary click/fill = বিপজ্জনক শক্তি — প্রশমন: SSRF+permission+pause স্তর অটুট, per-session grant বিকল্প, audit-log বাধ্যতামূলক।
2. **Screencast ব্যান্ডউইথ/গোপনীয়তা:** স্ক্রিনে সংবেদনশীল তথ্য প্রবাহ — প্রশমন: fps/quality cap, per-session opt-in, বিদ্যমান এনক্রিপ্টেড-চ্যানেল।
3. **Router-merge ভাঙা-consumer:** লুকানো caller — প্রশমন: port-প্রথম, warning-পর্ব, path-parity meta-test, retirement সবশেষে।
4. **Purge-এ ফিচার-হ্রাস-অনুভূতি:** কিছু UI হঠাৎ honest-error দেখাবে — প্রশমন: প্রতিটির সাথে fallback-UX ও নথি; কোনো চুপচাপ মিথ্যা নয়।
5. **পরিসর-ঝুঁকি:** browser-refactor-এর ঘুরপথে নতুন ফিচার-লোভ (PDF/downloads ইত্যাদি) — প্রশমন: সেগুলো P-G-র পরে আলাদা execution প্ল্যানের প্রার্থী; এই নীলনকশায় নয়।

---

## Part 3 — Explicit Out-of-Scope

1. PDF/downloads/tabs/evaluate-এর পূর্ণ বাস্তবায়ন — P-G-পরবর্তী আলাদা execution প্ল্যানের প্রার্থী।
2. `browsing_memory`-র Module 01-স্টোরে সংযোগ — মেমোরি-চক্রের পরিসর।
3. নতুন browser-ইঞ্জিন/dependency আমদানি (শুধু বিদ্যমান browser_use adapter flag-gated enable)।
4. scraper microservice-এর পরিবর্তন — ভিন্ন উপ-স্তর, অটুট থাকবে।
5. Frontend browser-UI রিডিজাইন — কেবল artifact/timeline-সংযুক্তি প্রয়োজনে।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | allowed_actions-এক-লাইন; acquire-ডেলিগেশন; port+warning; নতুন কোড কেবল টেস্টে |
| 3. No new infrastructure | ✅ | playwright/objects-API/error-bus বিদ্যমান; নতুন service/DB নয় |
| 4. No CI cost amplification | ✅ | integration টেস্ট বিদ্যমান স্যুটে; নতুন শাখা নয় |
| 5. No credit-burn risk | ✅ | browser-action LLM-বিহীন; vision-মেরামতে বিদ্যমান VLM-সীমা |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট-ক্ষমতা: liveness, artifact-স্থায়িত্ব, truth-গণনা |
| 7. Realistic resource budget | ✅ | 2-page semaphore অটুট; artifact-quota guard |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main ad1611e sed/grep/wc-যাচাই (last_verified-তালিকা); register-উৎস স্পষ্ট |

| Constitution ধারা | প্রভাব |
|---|---|
| #5 Verify Before Trust | ✅ ৫ মিথ্যা-surface পর্যুগ; action-chain integration টেস্ট |
| #6 Policy Before Power | ✅ unlock-ও policy-gate-এর পরেই; permission/pause অটুট |
| #8 Graceful Degradation | ✅ WebScraper-fallback অটুট; purge-এ honest-error চুক্তি |
| #10 One System, Many Execution Surfaces | ✅ দুই /api/browser → এক canonical |
| #13 No Silent Failure | ✅ AttributeError→বাস্তব মেরামত; fake-success→exception/honest-501 |
| #14 Zero-Mock Doctrine | ✅ 1×1 PNG/fake-metrics/mock-DOM — সব zero-mock লক্ষ্যে |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** বিদ্যমান browser টেস্ট-স্যুট (~2,027 LOC) শূন্য-ব্যর্থতা; P-A action-chain integration টেস্ট; P-B takeover WS-integration টেস্ট (acquire→frame); P-C route-parity meta-test; P-D প্রতিটি surface-এ honest-উত্তর টেস্ট।
- **Gate 5 (live):** বাস্তব সেশনে interactive সাফল্য-হার >95% (target); ২৪-ঘণ্টায় সফল takeover >0 হলে ব্যবহৃত; স্থায়ী artifact গণনা >0; fabricated-উত্তর শূন্য; per-action latency প্রকাশিত।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; কোনো schema/data-loss path নেই; router-retirement শেষ ও সবচেয়ে সাবধান ধাপ — revert-পথ git revert একক commit।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ✅ সংগত (P-G শক্তিশালী) | কোনো নতুন ইঞ্জিন/পরিশোধিত পরিষেবা নয় — বিদ্যমান browser_use adapter flag-gated; P-G-র autonomous ধাপে env-চালিত ধাপ/টোকেন-বাজেট সীমা সংযোজন |
| Lightweight | ✅ সংগত | বিদ্যমান session_manager/error_event_bus/objects-API পুনঃব্যবহার; ~900+ লাইন dormant/shadowed surface-এর wire-অথবা-delete |
| Fast & smooth | ✅ সংগত (P-B সংশোধিত) | screencast default-off + per-session opt-in; হট-পথে কোনো নতুন বাধা নয়; P-C route-parity meta-test সহ ধাপে ধাপে |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | P-B-র fps/quality cap আগে স্থির-ধারণা ছিল — এখন env-পঠিত; P-G-র বাজেট-সীমাও env-চালিত (§২.৪ সংশোধিত) |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `backend/core/browser_session_manager.py` L30 allowed_actions tuple-এ navigate/screenshot/content/extract — click/fill/type অনুপস্থিত (P-A প্রাসঙ্গিক); `backend/api/routes/session_takeover.py` বিদ্যমান (P-B প্রাসঙ্গিক)।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১–৩ (প্রকাশিত):** Module 01 Memory → Module 02 Orchestration → Module 03 LLM Gateway।
- **চক্র ৫ (কিউতে):** Module 05 — Self-Evolution & Learning Loop (`backend/core/self_evolution/` + `backend/core/learning/` + `backend/adaptive_engine/` + `backend/evolution/`) — "Universal Self-Learning" প্রতিশ্রুতির কেন্দ্র; এই মডিউলের P-F observability-মতবাদ learning-লুপের উপাত্ত-ভিত্তিও মজবুত করবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
