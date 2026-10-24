---
id: crown-jewel-module-09-dormant-tools-activation-power-up-v1-2026-09-17
title: "Crown Jewel Module Series — Module 09: Dormant Tools সক্রিয়করণ Power-Up (৬,৭৯৫-লাইনের ঘুমন্ত ক্ষমতা-ভাণ্ডারকে সত্য-নীতি-সহ জাগানো — LLM→Tool-পথ খোলা ও অডিট-সত্য করার পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Tools Circle (backend/tools/ + backend/tools/mcp/ + backend/core/mcp_policy.py + backend/core/capability_gateway.py + backend/core/capability_activation.py + scripts/audit_module_wiring.py + backend/api/routes/tools_registry.py)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ৯ — একটি মডিউল (Dormant Tools সক্রিয়করণ), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — fresh main c7d5bb8 (2026-09-17) sed/grep/wc-যাচাইকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; orphan-wiring-master-plan মতবাদ-পুনঃব্যবহার; প্রতিটি ধাপে flag+kill-switch; 721-route surface-এ zero-regression লক্ষ্য"
depends_on:
  - "backend/tools/agent_tools.py (L212 SUPREME_TOOLS = [search_database, check_system_health, execute_python_code] — production consumer শূন্য, grep-verified; execute_python_code-এ DockerSandbox run_secure L185)"
  - "backend/api/routers.py (ALL_ROUTERS registry — e.g. L392-404 diagram/voice_coder/pair/self_planner — ৬ mounted-but-orphan router)"
  - "backend/tools/mcp/mcp_server.py (list_tools L40, call_tool L112, _check_policy L20 → core/mcp_policy.evaluate_tool L164; unknown-tool → ডিফল্ট R3 REQUIRE_APPROVAL L91-92)"
  - "mcp.json (root — কেবল TS control-tower নিবন্ধিত; mcp_neon/mcp_observability/mcp_ide_trio FastMCP apps অনাগম্য)"
  - "backend/core/mcp_policy.py (TOOL_PROVIDER_ACTION 25-entry — নীতি-মানচিত্র)"
  - "backend/core/capability_activation.py (L20 tenant-flags) + backend/core/capability_gateway.py (L98-106 — কেবল ৩ capability)"
  - "backend/api/routes/tools_registry.py (DB-catalog — নীতি/এক্সিকিউশনের সাথে অসংযুক্ত)"
  - "scripts/audit_module_wiring.py (L76-80 stem-regex — ২ blind-spot: dotted-string অদৃশ্য + transitive-reachability নেই → ৬ false-dormant + transitively-dead 'operational')"
  - "backend/tools/learning/rlhf_pipeline.py (L140 'not_implemented' — register §7.1, sed-verified)"
  - "docs/plans/features/orphan_components_wiring_master_plan.md (Phase 0-4 dependency-ordered wiring মতবাদ)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md (§7.1 tools fakes, §8 Class C orphan-surface)"
  - "README.md Constitution #12 (Capability ≠ Permission) + #6 (Policy Before Power)"
  - "backend/tests/tools/ (৩৯ ফাইল — dormant-পিনকৃত চুক্তি)"
implements:
  - "LLM→Tool-পথ খোলা — SUPREME_TOOLS গভর্নড ReAct-লুপে: এজেন্ট প্রথমবার সত্যিই টুল ডাকবে (sandbox+policy-গেটসহ)"
  - "সক্রিয়করণ-পাইপলাইন — catalog+tenant-flag+প্রতি-টুল R0-R6 নীতি: 'Capability ≠ Permission' প্রয়োগে"
  - "অডিট-সত্য — audit-regex সংশোধন + reachability: MODULES_LIST পরিকল্পনার ভিত্তি হওয়ার যোগ্য"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (fresh main c7d5bb8: agent_tools.py L212 grep-verified ০-consumer; mcp.json python-parse = কেবল control-tower; rlhf_pipeline.py L140 sed-verified 'not_implemented'; routers.py registry-লাইন যাচাইকৃত; audit regex L76-80 পাঠ-যাচাই)"
code_evidence:
  - "backend/tools/agent_tools.py L212 — SUPREME_TOOLS (search_database/check_system_health/execute_python_code-DockerSandbox-run_secure L185) — grep: production consumer শূন্য; কোনো ReAct/tool-calling লুপই অস্তিত্বহীন — এজেন্ট আজ কোনো টুল ডাকতে পারে না"
  - "৬ mounted-but-orphan router (১,৫৯৭ লাইন) — comment_thread_ai 413, diagram_to_architecture 330, collaborative_editor 286, self_planner 266, voice_coder 152, ai_pair_programmer 150 — routers.py-registry-তে লাইভ, কিন্তু FE/agent-consumer শূন্য (register §8 Class C)"
  - "mcp.json — কেবল TS control-tower; mcp_neon (363 লাইন, NEON_API_KEY), mcp_observability (146, SENTRY), mcp_ide_trio — সব লেখা কিন্তু অনাগম্য; mcp_client.discover_tools হার্ডকোড web_search/code_generator-ফলব্যাক (L104)"
  - "অডিট-দ্বৈত-অন্ধত্ব — scripts/audit_module_wiring.py L76-80 stem-regex: (১) dotted-string dynamic-mount অদৃশ্য → ৬ false-dormant; (২) transitive-reachability নেই → dormant-caller-নির্ভর টুল 'operational' লেবেল পায় (safe_executor←cot_reasoner ইত্যাদি) — MODULES_LIST.md-র 127/63 বিভাজন দুই-দিকেই অবিশ্বস্ত"
  - "নীতি-মানচিত্র-ছিদ্র — TOOL_PROVIDER_ACTION ২৫-এন্ট্রি; unknown → R3-অনুমোদন; tools_registry DB-catalog নীতি/এক্সিকিউশনের সাথে অসংযুক্ত — catalog-এ থাকা = ডাকা-যাওয়া নয়, কিন্তু সেই সম্পর্ক কোথাও কোডে নেই"
  - "মিথ্যা/ক্ষতিকর অবশেষ — rlhf_pipeline 'not_implemented' (register §7.1); bandwidth_optimizer regex non-ASCII-মোছে → বাংলা-ধ্বংসকারী (dup of context-budget); ensemble_router (৫ম router-প্রজন্ম); stealth_http_client test-only — ~৮০০+ লাইন deletion-প্রার্থী"
  - "env/API-gated সম্পদ — mcp_neon/mcp_observability/video/music/threed/bangla_ai_connector (৮৫৭ লাইন) — key-provisioning অনথিভুক্ত"
test_evidence: "none yet — প্রতিটি Phase-এর execution প্ল্যান সংজ্ঞায়িত করবে; সমষ্টিগত চুক্তি: (১) ReAct-লুপ integration টেস্ট (টুল-কল→policy-gate→sandbox→ফল→বার্তায়), (২) সক্রিয়করণ-পাইপলাইন টেস্ট (R-tier অনুযায়ী অনুমতি/অনুমোদন), (৩) অডিট-টেস্ট (dotted-mount শনাক্ত; transitive-dead চিহ্নিত), (৪) বিদ্যমান backend/tests/tools/ ৩৯-ফাইল চুক্তি zero regression; flag-off → আজকের আচরণ"
acceptance_criteria:
  - "প্রতিটি Phase আলাদা ছোট execution প্ল্যান হিসেবে Gate 0–6 পাস"
  - "Tool-path সংজ্ঞা: এজেন্ট-চ্যাট থেকে SUPREME_TOOLS-এর ≥১ টুল sandbox+policy-gate দিয়ে সফল ডাক — এন্ড-টু-এন্ড প্রমাণ"
  - "পাইপলাইন-সংজ্ঞা: tools_registry-catalog ↔ নীতি-মানচিত্র ↔ tenant-activation ত্রি-সংযোগ; প্রতি টুলের R-tier নথিভুক্ত"
  - "অডিট-সত্য সংজ্ঞা: ৬ false-dormant শোধরানো; transitive-dead চিহ্নিত; MODULES_LIST-রিজেন CI-প্রমাণসহ"
  - "পরিচ্ছন্নতা-সংজ্ঞা: deletion-candidate (~৮০০+ লাইন) স্পষ্ট-নথি + zero-importer-প্রমাণ + archive-ট্যাগ; zero-regression CI প্রমাণ"
test_evidence_note: "Gate 4-এ integration/পাইপলাইন/অডিট টেস্ট; Gate 5-এ live — প্রথম বাস্তব tool-call পর্যবেক্ষণ + admin-events-এ নীতি-সিদ্ধান্ত প্রবাহ; completion claim-এর আগে বাধ্যতামূলক"
risk_and_rollback:
  - "সবচেয়ে বড় ঝুঁকি: tool-execution অপব্যবহার (বিশেষত code-exec) — প্রশমন: DockerSandbox অটুট, R-tier নীতি (code-exec = সর্বোচ্চ অনুমোদন), tenant-flag ডিফল্ট off, audit-log প্রতি কলে, kill-switch"
  - "ReAct-লুপে খরচ-বৃদ্ধি (বহু-ঘূর্ণি LLM-কল) — প্রশমন: ধাপ-সীমা, প্রতি-টুল টোকেন-বাজেট (M03/M06 চুক্তির সাথে), flag default false"
  - "অডিট-সংশোধনে status-কম্পন (MODULES_LIST বদল) — প্রশমন: রিজেন-স্ক্রিপ্ট + পরিবর্তন-নথি; কোনো রানটাইম-পরিবর্তন নয়"
  - "Deletion-এ লুকানো consumer — প্রশমন: zero-importer-প্রমাণ (dotted-string-সচেতন regex-দিয়েই), archive-ট্যাগ, git-history উল্লেখ"
  - "Rollback: প্রতিটি Phase = একক commit revert + flag-off; কোনো schema migration নেই (tools_registry টেবিল বিদ্যমান)"
baseline: "(hypothesis — Phase PR-এ মাপা হবে) আজ: এজেন্ট-প্রবেশ্য টুল = 0 (SUPREME_TOOLS অকার্যকর); MCP-অনাগম্য server = ৩; false-dormant = ৬; transitive-dead-'operational' = ≥৬; catalog↔নীতি-সংযোগ = ০; deletion-প্রার্থী জীবিত = ~৮০০+ লাইন"
measurement_method:
  - "(a) tool-path: এন্ড-টু-এন্ড সফল agent-tool-call গণনা (hard: প্রথম ১টির আগে 'broken')"
  - "(b) নীতি-কভারেজ: R-tier-নথিভুক্ত টুল গণনা / মোট সক্রিয় (লক্ষ্য ১০০%)"
  - "(c) অডিট-সত্য: false-dormant গণনা (লক্ষ্য 0) + transitive-dead-চিহ্নিত গণনা (সব)"
  - "(d) regression: backend/tests/tools/ ৩৯-ফাইল + route-graph meta-tests শূন্য-ব্যর্থতা"
success_threshold: "tool-call → ≥১ এন্ড-টু-এন্ড সফল (hard); নীতি-কভারেজ → ১০০% সক্রিয়-টুলে (hard); false-dormant → 0 (hard); MODULES_LIST-অডিট → CI-প্রমাণসহ পুনঃগণনাযোগ্য (hard); সব সংখ্যা measured-হওয়া পর্যন্ত hypothesis"
plan_lifecycle: "living — Crown Jewel Module Series চক্র ৯-এর প্রস্তাবিত নীলনকশা; single-plan discipline অটুট — কোনো Phase ফাউন্ডার-অনুমোদন-পূর্বে executable নয়"
---

# Crown Jewel Module Series — Module 09: Dormant Tools সক্রিয়করণ Power-Up

**Status:** proposed (ফাউন্ডার রিভিউ অপেক্ষমাণ — Gate 2 পূর্বে executable নয়)
**Owner:** Tools Circle (`backend/tools/` + `backend/tools/mcp/` + `core/mcp_policy.py` + `capability_gateway.py` + `scripts/audit_module_wiring.py`)
**Main anchor:** fresh main `c7d5bb8` (2026-09-17)
**Resource delta:** 0 নতুন dependency / 0 নতুন infra / 0 নতুন CI cost (অডিট-গেট বিদ্যমান CI-স্টেপে) / 0 schema migration / 0 route deletion (deletion-পর্বে নথিভুক্ত ব্যতিক্রম)

## বাংলা সারসংক্ষেপ

আগের আট মডিউল ছিল অঙ্গ-প্রত্যঙ্গ; এই মডিউলটি **গুপ্তধন-গুদাম**: `backend/tools/`-এ ৪৪টি dormant টুল — ৬,৭৯৫ লাইন লেখা, টেস্ট-করা, কিন্তু প্ল্যাটফর্ম যেন তাদের অস্তিত্বই জানে না। সবচেয়ে ধারালো সত্যটি এক লাইনে: **SupremeAI "এজেন্ট-প্ল্যাটফর্ম", অথচ এজেন্ট আজ একটিও টুল ডাকতে পারে না** — `agent_tools.py` L212-র SUPREME_TOOLS (search_database, check_system_health, এমনকি DockerSandbox-নিরাপদ `execute_python_code`) এর production consumer শূন্য; কোনো ReAct/tool-calling লুপই কোডবেজে নেই। গুদামের তালা-ব্যবস্থাও দ্বৈত-অন্ধ: MCP-পক্ষে তিনটি সম্পূর্ণ server (neon/observability/ide_trio) লেখা কিন্তু `mcp.json`-এ অনাগম্য; HTTP-পক্ষে ৬টি router registry-তে মাউন্টেড কিন্তু কোনো FE-consumer নেই (১,৫৯৭ লাইন); আর এ-সব *কোনটা কী* — তার একমাত্র উৎস MODULES_LIST.md — নিজেই অবিশ্বস্ত: audit-regex dotted-string দেখে না (৬টি মিথ্যা-dormant) আর transitive-reachability মাপে না (মৃত-চেইনের যাত্রীরা 'operational' পদক পায়)। তলানিতে আরও: `rlhf_pipeline` 'not_implemented' কিন্তু তালিকায়, `bandwidth_optimizer` regex দিয়ে non-ASCII মুছে ফেলে — অর্থাৎ **বাংলা-ধ্বংসকারী** একটি "টুল" জীবিত।

এই নীলনকশা গুদাম-ভাণ্ডারকে crown-jewel স্তম্ভে তোলে ৭ ধাপে: **(A)** LLM→Tool-পথ (গভর্নড ReAct) → **(B)** সক্রিয়করণ-পাইপলাইন (catalog+নীতি+tenant ত্রি-সংযোগ) → **(C)** MCP-অনাগম্যতা শেষ → **(D)** অডিট-সত্য (regex+reachability) → **(E)** false-dormant নিরাময় → **(F)** deletion-sweep (নথি-প্রমাণসহ) → **(G)** প্রথম-ফ্লিট সক্রিয়করণ (top-10 candidates)। **মতবাদ-পুনঃব্যবহার:** repo-র নিজস্ব `orphan_components_wiring_master_plan.md`-র Phase-স্তর-পদ্ধতি এখানেই খাটবে — নতুন দর্শন নয়। **শৃঙ্খলা-বাক্য:** সক্রিয়করণ মানেই অনুমতি নয় — Constitution #12 "Capability ≠ Permission"; প্রতিটি টুল R-tier নীতি ছাড়া জাগবে না।

---

## Part 1 — Competitor Intelligence (established patterns; fresh-dated citations পরবর্তী চক্রে সংগ্রহ হবে — এ চক্রে design-pattern observation হিসেবে labeled)

### ৯.১ Tool-calling লুপ — এজেন্টের হাত-মোড়ানো

- আধুনিক এজেন্ট-প্ল্যাটফর্মের মূল প্রিমিটিভ: LLM→tool-call→ফল→পুনঃপ্রম্পট লুপ, schema-নিবন্ধিত টুলসহ (established pattern)।
- SupremeAI-র সংযোগবিন্দু: SUPREME_TOOLS+DockerSandbox বাস্তব — লুপটিই অস্তিত্বহীন (P-A); এটিই এই মডিউলের একক-সর্বোচ্চ লিভার।

### ৯.২ নীতি-স্তরীয় অনুমতি মতবাদ (R-tiers)

- পরিণত টুল-ব্যবস্থায় প্রতি-টুল ঝুঁকি-স্তর (auto/notify/approve/deny) নীতি-ফাইলে (established pattern)।
- SupremeAI-র সংযোগবিন্দু: mcp_policy-র R0-R6 কাঠামো বিদ্যমান (unknown→R3 ডিফল্ট চৌকস) — মানচিত্র-বিস্তার ও catalog-সংযোগই ঘাটতি (P-B)।

### ৯.৩ সত্য-ইনভেন্টরি মতবাদ

- বড় মোনোরিপো-তে reachability-ভিত্তিক dead-code-অডিট CI-গেট হিসেবে মানক (established pattern)।
- SupremeAI-র সংযোগবিন্দু: audit-স্ক্রিপ্ট বিদ্যমান — দুই blind-spot সংশোধনেই মডিউল-তালিকা পরিকল্পনাযোগ্য (P-D)।

### ৯.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল (fresh main c7d5bb8-verified)

| প্যাটার্ন | যা করে | SupremeAI আজ (c7d5bb8-verified) | গ্যাপ |
|---|---|---|---|
| Tool-calling লুপ | schema-টুল এজেন্ট-প্রবেশ্য | SUPREME_TOOLS লেখা, consumer শূন্য | P-A |
| R-tier নীতি | প্রতি-টুল ঝুঁকি-স্তর | R0-R6 কাঠামো আছে, catalog-অসংযুক্ত | P-B |
| MCP-পরিবেশনা | সব server নিবন্ধিত | ৩ server অনাগম্য | P-C |
| সত্য-ইনভেন্টরি | reachability-অডিট | stem-regex, ২ blind-spot | P-D |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main c7d5bb8, 2026-09-17)

| বিদ্যমান | বিষয় | এই নীলনকশার সাথে সম্পর্ক |
|---|---|---|
| `docs/plans/features/orphan_components_wiring_master_plan.md` | orphan-wiring মতবাদ (Phase 0-4) | পুনঃব্যবহৃত — এই নীলনকশা তার tools-পক্ষের প্রয়োগ; নতুন দর্শন নয় |
| `MODULE_06_RUN_FABRIC_COMPLETION_POWER_UP_2026-09-17.md` | run_scope | সম্পূরক — tool-call গুলো run-প্রবাহিত (terminal-agent-fleet বিশেষত) |
| `MODULE_05_SELF_EVOLUTION_POWER_UP_2026-09-17.md` | skill_metrics | সম্পূরক — tool-call-ফল fitness/LearningStore-ফিডের নতুন উৎস (flag-gated, ভবিষ্যৎ-সংযোগ) |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` §7.1/§8 | tools fakes + Class C | P-E/P-F সরাসরি নিরাময় — alignment |
| MODULE_02 | kernel single-door | সম্পূরক — ভবিষ্যতে tool-dispatch kernel-দরজায়; এখানে registry-স্তর মাত্র |
| frontend workspaceFeatureRoutes guide | Tier-S wiring | সম্পূরক — Module 10-র পরিসর; ৬ mounted-orphan router-এর FE-consumer সেখানেই প্রার্থী |

**গ্রেপ-যাচাই:** fresh main c7d5bb8-এ কোনো বিদ্যমান ডকুমেন্ট ReAct-লুপ, tools-সক্রিয়করণ-পাইপলাইন, MCP-নিবন্ধন-সিঁড়ি বা audit-regex-সংশোধনের execution-নীলনকশা দেয় না — সম্পূর্ণ unclaimed (`docs/plans/` recursive grep, 2026-09-17)।

---

## Part 2 — Six-Field Complete Plan

### ২.১ কী আছে (কোড-যাচাইকৃত)

1. **তিন পৃষ্ঠের registry-কাঠামো:** HTTP (routers.py ALL_ROUTERS+register_all_routers), MCP (mcp_server list/call+policy-gate+audit), agent-registry (8 agent auto-registered) — সব লাইভ কাঠামো।
2. **SUPREME_TOOLS+DockerSandbox:** ৩ বাস্তব টুল, code-exec sandboxed (run_secure) — টেস্ট-পিনকৃত।
3. **নীতি-ইঞ্জিন:** mcp_policy R0-R6 + TOOL_PROVIDER_ACTION (২৫ এন্ট্রি) + unknown→R3; mcp_audit।
4. **Tenant-স্তর:** capability_activation flags; capability_gateway (৩ capability সংযুক্ত)।
5. **DB-catalog:** tools_registry টেবিল + admin RBAC route।
6. **সম্পদ-ভাণ্ডার:** ৪৪ dormant = ৬,৭৯৫ লাইন (৬ false-dormant ১,৫৯৭ + বাস্তব-অসংযুক্ত ২৭ = ৪,১০৭ + env-gated ৬ = ৮৫৭ + সৎ-stub ১৬১ + shim ৭৩)।
7. **টেস্ট-রক্ষা:** backend/tests/tools/ ৩৯ ফাইল — activation-প্রার্থীদের চুক্তি পিনকৃত।

### ২.২ কী নেই (কোড-যাচাইকৃত অনুপস্থিতি)

1. **LLM→Tool-লুপ** — SUPREME_TOOLS-এর কোনো consumer/ReAct-লুপ নেই; এজেন্ট টুল-শূন্য।
2. **ত্রি-সংযোগ** — catalog↔নীতি↔tenant-activation একে অপরকে চেনে না।
3. **MCP-অনাগম্যতা** — ৩ server mcp.json-বহির্ভূত; discover_tools হার্ডকোড-ফলব্যাক।
4. **অডিট-সত্য** — ২ blind-spot; MODULES_LIST দুই-দিকেই অবিশ্বস্ত।
5. **পরিচ্ছন্নতা-সিদ্ধান্ত** — ~৮০০+ লাইন deletion-প্রার্থী (বাংলা-ধ্বংসকারী bandwidth_optimizer সহ) অনথিভুক্ত।
6. **key-provisioning-নথি** — ৬ env-gated সম্পদের চালু-পথ অজানা।

### ২.৩ কী করতে হবে (গুপ্তধন-জাগরণের ৭ ধাপ)

```text
P-A: LLM→Tool-পথ           → গভর্নড ReAct-লুপ (chat-orchestrator-সংযুক্ত): SUPREME_TOOLS
                              + policy-gate + DockerSandbox + ধাপ/টোকেন-সীমা (flag default false)
P-B: সক্রিয়করণ-পাইপলাইন    → catalog ↔ R-tier-মানচিত্র ↔ tenant-flag ত্রি-সংযোগ + নথি
P-C: MCP-অনাগম্যতা শেষ      → mcp.json-এ neon/observability/ide_trio + policy-map-এন্ট্রি
                              + discover_tools-হার্ডকোড শেষ (key-provisioning-নথিসহ)
P-D: অডিট-সত্য              → audit-regex dotted-string-সচেতন + transitive-reachability
                              + CI-গেট (MODULES_LIST-রিজেন-যাচাই)
P-E: false-dormant নিরাময়  → ৬ mounted-orphan router: FE/agent-consumer প্রার্থী-নথি অথবা
                              honest demount (Module 10-সহযোগিতায়)
P-F: deletion-sweep         → ~৮০০+ লাইন: zero-importer-প্রমাণ + archive-ট্যাগ + নথি
                              (bandwidth_optimizer/rlhf/ensemble_router/stealth_http_client ইত্যাদি)
P-G: প্রথম-ফ্লিট সক্রিয়করণ   → top-10 candidates-এর ৩টি (cot_reasoner, headless_agent_registry
                              +parallel_executor, mcp_observability) flag-gated জাগরণ
```

### ২.৪ কীভাবে করব (ফাইল-স্তরের দিক-নির্দেশ, প্রতিটি Phase আলাদা execution প্ল্যান)

- **P-A (LLM→Tool-পথ, স্যান্ডবক্স আইসোলেশন ও জিরো-বাইপাস বাউন্ডারি):**
  - নতুন পাতলা tool-calling-লুপ মডিউল (core-এ) — schema (SUPREME_TOOLS-সুসংগত) → policy-gate (mcp_policy পুনঃব্যবহার) → executor (DockerSandbox/DB-agent) → ফল-প্রম্পট।
  - **Zero-Bypass Binding:** কোনো টুল যদি অভ্যন্তরীণভাবে এলএলএম কল ব্যবহার করে (যেমন কোড এক্সপ্লেনেশন বা এসকিউএল জেনারেশন), তবে তা অবশ্যই Module 03 LLM Gateway-র `InferenceContext(task_type='tool_execution')` দিয়ে যেতে হবে।
  - **বাউন্ডেড এক্সিকিউশন টাইমআউট ও স্যান্ডবক্স লিমিট:** ইনফিনিট লুপ ও মেমোরি ক্র্যাশ ঠেকাতে প্রতি টুলে কঠোর টাইমআউট (ডিফল্ট ১৫ সেকেন্ড) এবং ডকার/WASM স্যান্ডবক্স মেমোরি কোটা প্রয়োগ।
  - **স্ট্রাকচার্ড এরর রিটার্ন:** টুল ব্যর্থ হলে আনহ্যান্ডেলড ক্র্যাশ বা ফেক সাকসেসের বদলে স্ট্রাকচার্ড এরর ডিকশনারি (`{"status": "error", "error_type": "...", "message": "..."}`) রিটার্ন করা।
  - ধাপ-সীমা ও প্রতি-সেশন টোকেন-বাজেট (env/config-পঠিত); flag `SUPREMEAI_AGENT_TOOLS=true` (default false)।
- **P-B:** tools_registry-catalog-এ R-tier কলাম-মান (বিদ্যমান টেবিল); capability_activation-tenant-flags সাথে যুদ্ধ; প্রতি টুলের এন্ট্রি = {tier, tenant-default, audit}; নথি: সক্রিয়করণ-রানবুক।
- **P-C:** mcp.json-এ ৩ server-নিবন্ধন (env-উপস্থিতি-শর্তায়িত) — **দর্শন-সংগতি শ্রেণিবিভাগ (এই পাস):** ide_trio = স্থানীয়/zero-cost → সাধারণ নিবন্ধনযোগ্য; neon (NEON_API_KEY) ও observability (SENTRY) = **তৃতীয়-পক্ষ key-নির্ভর পরিষেবা → নিবন্ধন-এন্ট্রি লিখিত হলেও default-off + ফাউন্ডার-সিদ্ধান্ত-গেটেড** (zero-cost দর্শন: key-অনুপস্থিতিতে আচরণ অপরিবর্তিত; কোনো নতুন খরচ-পথ নয়); mcp_client.discover_tools-ফলব্যাক → বাস্তব discovery (**ফলব্যাক-সংশোধন key-নির্ভর server ছাড়াই সম্পূর্ণ কাজ করবে**); runbook: key-provisioning (Part 3-5 অনুযায়ী সিদ্ধান্ত ফাউন্ডারের)।
- **P-D:** audit_module_wiring.py — dotted-string-প্যাটার্ন যোগ + AST/entrypoint-reachability; CI-তে রিজেন-যাচাই (warn→gate ধাপে — **gate-পর্বে প্রবেশ কেবল শূন্য-false-positive drift-প্রমাণের পরে**, lint_plans-র Stage-2 চুক্তি-অনুরূপ — CI-বিচ্ছিন্নতা-সুরক্ষা); MODULES_LIST রিজেন + পরিবর্তন-নথি।
- **P-E:** ৬ router-এর প্রতিটির সিদ্ধান্ত-নথি (FE-consumer প্রার্থী হলে Module 10-র সাথে সমন্বয়; নয়তো honest demount — routers.py-থেকে, deprecation-নোটসহ)।
- **P-F:** deletion-candidate প্রত্যেকের zero-importer-প্রমাণ (P-D-র সংশোধিত audit দিয়েই) → অপসারণ + git-history-নোট; বাংলা-ধ্বংসকারী bandwidth_optimizer অগ্রাধিকার।
- **P-G:** flag-gated জাগরণ — cot_reasoner (deterministic-reasoning tool হিসেবে P-A-লুপে), headless_agent_registry+parallel_executor (admin-route + M06 run_scope), mcp_observability (self-healing-উৎস — **দর্শন-সংগতি সংশোধন: revival key-বিহীন-প্রথম — উৎস স্থানীয় error_event_bus/telemetry, SENTRY-সংযোগ optional env-শর্তায়িত; key-অনুপস্থিতিতেও সম্পূর্ণ কার্যকর**) — প্রতিটি আলাদা PR, আলাদা রোলব্যাক।

### ২.৫ বেনিফিট (সবই hypothesis — Gate 5-এ measured হবে)

1. **প্ল্যাটফর্ম-প্রতিশ্রুতি সত্য (P-A):** "এজেন্ট টুল ব্যবহার করে" প্রথমবার প্রোডাকশন-সত্য — এজেন্ট-বিভাগের সবচেয়ে বড় ব্যবধান বন্ধ।
2. **নিরাপদ স্যান্ডবক্স ও জিরো-বাইপাস (P-A):** টুলের অপব্যবহার, ইনফিনিট লুপ এবং আনট্রেসড টোকেন খরচ বন্ধ।
3. **৬,৭৯৫-লাইন সম্পদের ROI:** লেখা-টেস্টকৃত ক্ষমতা ব্যবহারকারীর কাছে পৌঁছায় — নতুন উন্নয়ন-ব্যয় ছাড়াই ফিচার-প্রবৃদ্ধি।
4. **নিরাপত্তা-মডেল প্রমাণ (P-B/A):** R-tier+tenant+audit = শিল্প-মান নীতি-গল্প; বিক্রয়/অডিট-প্রস্তুত।
5. **পরিকল্পনা-ভিত্তি সত্য (P-D):** MODULES_LIST প্রথমবার বিশ্বাসযোগ্য — সব ভবিষ্যৎ-চক্রের র‍্যাঙ্ক-কিউ সঠিক।
6. **পরিচ্ছন্নতা (P-F):** ~৮০০+ লাইন মৃত/ক্ষতিকর অপসারণ — রক্ষণ-বোঝা হ্রাস, বাংলা-সুরক্ষা।

### ২.৬ ক্ষতি/ঝুঁকি (সৎ, প্রশমন সহ)

1. **টুল-অপব্যবহার:** code-exec/DB-কোয়েরি — প্রশমন: sandbox অটুট, R-tier, tenant-default off, প্রতি-কল audit, kill-switch, ধাপ/টোকেন-সীমা।
2. **খরচ-বৃদ্ধি (P-A):** বহু-ঘূর্ণি লুপ — প্রশমন: ধাপ-সীমা, টোকেন-বাজেট, flag default false, পরিমাপ-গেট।
3. **অডিট-কম্পন (P-D):** status-বদলে অন্য-নথি-অসামঞ্জস্য — প্রশমন: রিজেন+পরিবর্তন-নথি; রানটাইম-অপরিবর্তিত।
4. **Deletion-অবশ্যম্ভাবী-লোভ:** প্রয়োজনীয় কিছু কাটার ঝুঁকি — প্রশমন: zero-importer-প্রমাণ-বাধ্যতামূলক, archive-ট্যাগ, বিতর্কিত-ক্ষেত্রে অপসারণ নয় নথি।
5. **পরিসর-ঝুঁকি:** "সক্রিয়করণ" নামে ৪৪-টুল একসাথে জাগানোর লোভ — প্রশমন: কেবল ৩টি P-G-তে; বাকি প্রতিটি আলাদা execution প্ল্যান; প্রতিটি Phase Gate 0–6।

---

## Part 3 — Explicit Out-of-Scope

1. ৪৪-এর মধ্যে ৩টি ব্যতীত সব dormant-টুলের সক্রিয়করণ — প্রতিটি ভবিষ্যৎ-পাইপলাইন-প্রার্থী।
2. নতুন টুল-লেখা/নতুন sandbox-যন্ত্র — বিদ্যমান DockerSandbox পুনঃব্যবহার।
3. ৬ mounted-orphan router-এর FE-নির্মাণ — Module 10-র পরিসর (সমন্বয়-নথি মাত্র)।
4. kernel-দরজায় tool-dispatch-মাইগ্রেশন — Module 02 P-A-র পরবর্তী ধাপ।
5. key-ক্রয়/সরবরাহ — কেবল runbook; সিদ্ধান্ত ফাউন্ডারের।
6. সমান্তরাল multi-plan execution — একসময়ে একটাই Phase active।

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | প্রতিটি Phase আলাদা proposed execution; একসময়ে একটাই active |
| 2. Small change to existing code | ✅ | লুপ-মডিউল পাতলা-নতুন; বাকি সব বিদ্যমান ফাইলে সংযোগ |
| 3. No new infrastructure | ✅ | sandbox/policy/catalog/audit সব বিদ্যমান |
| 4. No CI cost amplification | ✅ | অডিট-গেট বিদ্যমান CI-স্টেপে; টেস্ট বিদ্যমান স্যুটে |
| 5. No credit-burn risk | ✅ | লুপ flag default false; ধাপ/টোকেন-সীমা কাঠামোগত |
| 6. No academic leaderboard | ✅ | tool-call-liveness, নীতি-কভারেজ, অডিট-সত্য — সরাসরি প্রোডাক্ট-মান |
| 7. Realistic resource budget | ✅ | ৩-টুল জাগরণ; sandbox-সময়সীমা বিদ্যমান |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main c7d5bb8 sed/grep-যাচাই (last_verified-তালিকা); মতবাদ-পুনঃব্যবহার-পাঠ |

| Constitution ধারা | প্রভাব |
|---|---|
| #3 Reuse Before Creation | ✅ ৬,৭৯৫-লাইন সম্পদ পুনঃব্যবহারই এই নীলনকশার মূল-সূত্র |
| #6 Policy Before Power | ✅ কোনো টুল R-tier ছাড়া জাগবে না |
| #12 Capability ≠ Permission | ✅ ত্রি-সংযোগ-পাইপলাইনের মূল-বাক্য |
| #13 No Silent Failure | ✅ rlhf 'not_implemented' সিদ্ধান্তে; audit-অন্ধত্ব শেষ |
| #5 Verify Before Trust | ✅ MODULES_LIST CI-যাচাইকৃত; tool-call প্রমাণসহ |

---

## Part 5 — Verification & Acceptance (Gates 4–6) + Rollback

- **Gate 4 (প্রতি Phase):** backend/tests/tools/ ৩৯-ফাইল শূন্য-ব্যর্থতা; P-A ReAct-লুপ integration টেস্ট (gate→sandbox→ফল); P-B ত্রি-সংযোগ টেস্ট; P-D অডিট-টেস্ট (dotted-mount শনাক্ত); P-F প্রতি অপসারণে route-graph meta-test।
- **Gate 5 (live):** প্রথম বাস্তব agent-tool-call পর্যবেক্ষণ (audit-log-প্রমাণ); admin-এ R-tier প্রবাহ; MODULES_LIST-রিজেন প্রমাণ; deletion-নথি-পর্যালোচনা।
- **Gate 6:** প্রতিটি Phase নিজস্ব execution প্ল্যানে complete; এই নীলনকশা complete যখন acceptance_criteria-র পাঁচটি সংজ্ঞা সবই evidence-সহ সত্য।
- **Rollback:** প্রতিটি Phase = একক commit revert + flag-off; লুপ/নিবন্ধন flag-gated; deletion-আর্কাইভ git-history-পুনরুদ্ধারযোগ্য।

---

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Pass, 2026-09-17, branch `crown-jewel-v2`)

| দর্শন | রায় | ভিত্তি |
|---|---|---|
| Zero cost | ⚠️ ছিল → ✅ **সংশোধিত** | P-C-র ৩ MCP server-এ neon/SENTRY key-নির্ভর তৃতীয়-পক্ষ পরিষেবা — এখন শ্রেণিবিভাগ: ide_trio সাধারণ, key-নির্ভররা default-off ফাউন্ডার-গেটেড; P-G-র mcp_observability key-বিহীন-প্রথম (স্থানীয় error_event_bus উৎস); আউট-অব-স্কোপ-5 (key-ক্রয় ফাউন্ডারের) অটুট |
| Lightweight | ✅ সংগত | পাতলা লুপ + বিদ্যমান DockerSandbox/mcp_policy পুনঃব্যবহার; নতুন sandbox/টুল-লেখা নয় |
| Fast & smooth | ✅ সংগত | flag default false → হট-পথ অপরিবর্তিত; P-D CI-gate শূন্য-false-positive-পরে (CI ভাঙবে না) |
| Zero hardcode | ⚠️ ছিল → ✅ **সংশোধিত** | P-A-র ধাপ-সীমা/টোকেন-বাজেট env/config-পঠিত (§২.৪ সংশোধিত) |

মূল-যন্ত্রপাতি spot-check (base `ed35eaf`): `backend/tools/agent_tools.py` L212 SUPREME_TOOLS অটুট; `backend/tools/mcp/`-তে mcp_ide_trio.py ইত্যাদি বিদ্যমান (P-C প্রাসঙ্গিক)।

স্কোপ-সততা: proposal-দর্শন অডিট + মূল-যন্ত্রপাতি spot-check; সম্পূর্ণ line-ref re-verification নয়।

---

## Part 6 — পরবর্তী চক্র লাইনেজ (reference-only; candidate list ≠ execution queue)

- **চক্র ১–৮ (প্রকাশিত):** Module 01 Memory → 02 Orchestration → 03 LLM Gateway → 04 Browser → 05 Self-Evolution → 06 Run Fabric → 07 Context Engine → 08 Scout।
- **চক্র ১০ (কিউতে):** Module 10 — Frontend Tier-S Wiring (`frontend/` S1–S12) — সিরিজের শেষ প্রস্তাবিত চক্র; P-E-র ৬ mounted-orphan router-এর FE-consumer-সিদ্ধান্ত এখানেই পূর্ণ হবে।
- সূচি ও কিউ-পুনঃর‍্যাঙ্ক: `crown_jewel_series/README.md`।
