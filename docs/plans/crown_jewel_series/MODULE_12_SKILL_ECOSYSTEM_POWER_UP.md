---
id: crown-jewel-module-12-skill-ecosystem-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 12: Governed Skill Ecosystem Power-Up (তিনটি প্রতিযোগী স্কিল-বাস্তবায়নের কনসলিডেশন + manifest-চালিত গভর্ন্যান্স — 'তৃতীয় ERR-F02' প্রতিরোধের পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/skills/ + backend/core/skill_manager.py + skills/ (রিপো-রুট) — তিন-বাস্তবায়ন একীকরণ-স্তর)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১২ (M9 Governed skill ecosystem, UNIFIED_NEXT_ROADMAP_2026-09-15.md) — একটি মডিউল (স্কিল-ইকোসিস্টেম), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field) — branch crown-jewel-v2 base ed35eaf-এ spot-checkকৃত কোড-প্রমাণে; PLAN_LIFECYCLE_POLICY.md কঠোর অনুসরণ; ERR-F02 কনসলিডেশন-মতবাদের extend-not-replace পুনঃপ্রয়োগ; ৪-স্তম্ভ-দর্শন Part 5.5-এ অডিটকৃত"
depends_on:
  - "backend/skills/skill_registry.py (66 লাইন — SkillRegistry: manifests/*.json glob-ডিসকভারি, ক্ষেত্র: id/name/version/dependencies/system_packages/entrypoint; L18-50)"
  - "backend/skills/installer.py (254 লাইন — L3 `import subprocess`; L30 _production_environment(); L73 _pre_write_security_scan() জেনারেটেড-কোডে subprocess/exec নিষিদ্ধকারী স্ক্যান; L140-175 install_dependencies(): রানটাইমে `sys.executable -m pip install` + subprocess.run)"
  - "backend/skills/manifests/core_doc_summarizer.json (policy-সমৃদ্ধ স্কিমা: allowed_roles, allowed_data, tools_allowed, human_approval_points{on_ingestion,on_execution}, budget{max_cost_per_invocation_usd:0.03, max_latency_seconds:8.0}, audit_logging — পলিসি ডেটা-ফাইলে, কোডে নয়)"
  - "backend/skills/manifests/core_knowledge_qa.json (দ্বিতীয় একই-স্কিমা manifest — মোট ২টি)"
  - "backend/core/skill_manager.py (252 লাইন — SkillManager: synthesize_skill_schema() LLM-জেনারেটেড স্কিল-স্কিমা; MCPRegistryClient ডিসকভারি; mcp_supabase-চালিত Supabase skill-store; R2-MEM লেজি-গেটওয়ে ফিক্স: ইমপোর্ট-টাইমে litellm ~240MB RSS বুট-ভার এড়ানো — 512MB free-tier সচেতনতার প্রমাণ)"
  - "skills/ (রিপো-রুট, তৃতীয় বাস্তবায়ন — ৬০৩ লাইন: registry.py 166 + installer.py 270 + schema.py 128 + marketplace.py 38 + dynamic/)"
  - "DORMANCY প্রমাণ: `rg SkillRegistry|skill_registry` (base ed35eaf) — সক্রিয় প্রোডাকশন-কলার শূন্য; হিট কেবল নিজস্ব-পাকেজ + docs/archive; root skills/-ও স্ব-উল্লেখ ছাড়া কলার-শূন্য"
  - "docs/plans/UNIFIED_NEXT_ROADMAP_2026-09-15.md M9 অংশ (L226-228: registry + manifests + permission scopes + sandbox/resource policy + provenance + versioning; cybersecurity/scientific packs opt-in; security skills: target allowlist + rate limit + audit trail)"
  - "docs/plans/features/orphan_components_wiring_master_plan.md L130-131 (`if task.required_skills:` লুপ — ডরম্যান্ট পাইপলাইনে স্কিল-কনসিউমার ধারণার অস্তিত্ব-প্রমাণ)"
  - "docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md ERR-F02 (১৫+ প্রতিযোগী memory-store — কনসলিডেশন-মতবাদ ও extend-not-replace ক্রমের প্রেসিডেন্ট)"
implements:
  - "তিন-বাস্তবায়ন একীকরণ-প্রস্তাব: একটি ক্যানোনিকাল + দুটি deprecation-shim-পিছে-ফ্রিজ (ERR-F02 ক্রমের অনুকরণ; caller-শূন্য হওয়ায় মাইগ্রেশন-ঝুঁকি মেমোরির চেয়েও নিম্ন)"
  - "manifest-চুক্তি একীকরণ: backend/skills/manifests/-স্কিমা (policy-সমৃদ্ধ) ক্যানোনিকাল ডেটা-চুক্তি — পলিসি সব ডেটা-ফাইলে (zero-hardcode)"
  - "রানটাইম-পিপ-নিষেধ প্রস্তাব: install_dependencies() ডিফল্ট-অফ (env-গেটেড ফাউন্ডার-কেবল); নির্ভরতা provisioning-সময়ে owner-অনুমোদিত — lightweight + supply-chain সুরক্ষা"
  - "M9 গভর্ন্যান্স-ঘাটতি পূরণ: provenance + versioning + security-skill allowlist/rate-limit/audit — সব manifest/config-চালিত"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base ed35eaf: ৩-বাস্তবায়ন wc/ls গণনা; installer.py L3/L30/L73/L140-175 স্পট-চেক; manifest-স্কিমা cat-যাচাই; dormant caller-grep শূন্য; root skills/ ৬০৩-লাইন wc)"
code_evidence:
  - "তৃতীয়-পুনরাবৃত্তি-প্যাটার্ন — মেমোরিতে ১৫+ store (ERR-F02), স্কিলে ৩ বাস্তবায়ন (`backend/skills/` + `backend/core/skill_manager.py` + রুট `skills/`) — একই রোগের দ্বিতীয় অঙ্গে ঘটা; পার্থক্য: স্কিল-সিস্টেমগুলো এখনো dormant (কলার-শূন্য) — অর্থাৎ কনসলিডেশন-ব্যয় আজ ন্যূনতম, কাল নয়"
  - "রানটাইম-ডিপেন্ডেন্সি-ইনস্টল — backend/skills/installer.py L140-175: `install_dependencies()` রানটাইমে subprocess pip-install; পরোক্ষ ব্যয়: কোল্ড-স্টার্ট বিলম্ব (fast-smooth-লঙ্ঘন), অবাউন্ডেড নির্ভরতা-বৃদ্ধি (lightweight-লঙ্ঘন), supply-chain-এক্সপোজার; L30 _production_environment() আংশিক-গার্ড কিন্তু ডিফল্ট-নিষেধ নয়"
  - "বিপরীতে ভালো-মতবাদও একই ফাইলে — L73 _pre_write_security_scan(): জেনারেটেড স্কিল-কোডে subprocess/exec নিষিদ্ধ — অর্থাৎ ইনস্টলার নিজেই subprocess-ব্যবহারকারী অথচ জেনারেটেড-কোডকে নিষেধ করে: দ্বৈত-মান দৃশ্যমান"
  - "ম্যাজিক-বাজেট ডেটায় নয় কোডে — manifests/core_doc_summarizer.json: budget{max_cost_per_invocation_usd:0.03, max_latency_seconds:8.0} — থ্রেশহোল্ড ডেটা-ফাইলে (সঠিক প্যাটার্ন); কিন্তু এই budget প্রয়োগ-করার dispatch-লেয়ার তিন বাস্তবায়নেই সম্পূর্ণ নয় (contract আছে, enforcement-চুক্তি নেই)"
  - "বুট-ভার-সচেতনতা প্রমাণিত — backend/core/skill_manager.py R2-MEM মন্ত্য: লেজি-গেটওয়ে ছাড়া litellm ~240MB RSS প্রতি কোল্ড-স্টার্টে — 512MB free-tier সংকোচ; ক্যানোনিকাল বাছাইয়ে এই আচরণ-প্রমাণ সিদ্ধান্ত-ভিত্তি"
  - "marketplace-ছোট্টতা — root skills/marketplace.py মাত্র ৩৮ লাইন — পেইড/বাহ্যিক marketplace-অবকাঠামোর ঝুঁকি শূন্য; লোকাল-ডির-ভিত্তিক — zero-cost রেখায় আছে"
test_evidence: "none yet — execution প্ল্যান সংজ্ঞায়িত করবে: (১) manifest-স্কিমা-ভ্যালিডেটর টেস্ট (প্রতিটি ক্ষেত্রে ১ positive + ১ negative fixture), (২) budget-enforcement টেস্ট (max_cost/max_latency ছাড়লে dispatch-বাতিল), (৩) runtime-pip-নিষেধ টেস্ট (ডিফল্ট-env-এ ব্যর্থ-হওয়া-বাধ্য), (৪) তিন-বাস্তবায়ন shim-এর আমদানি-সামঞ্জস্য টেস্ট, (৫) বিদ্যমান টেস্ট-সুইটে শূন্য-ব্যর্থতা (dormant-বাস্তবায়ন বলে বিস্তার-সীমিত)"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5 টেবিল — প্রতিটি স্তম্ভের বিপরীতে প্রমাণ)"
  - "সমস্ত পলিসি/থ্রেশহোল্ড/allowlist manifest-বা config-চালিত — ইন-কোড স্থির-তালিকা নেই (zero-hardcode)"
  - "কনসলিডেশন extend-not-replace: কোনো কলিং-সাইট ভাঙা হয় না (dormant বলে ঝুঁকি নিম্ন, তবু নীতি বহাল)"
  - "lint_plans.py-এ এই ডকুমেন্ট 0 error / 0 warning"
---

# Module 12 — Governed Skill Ecosystem Power-Up

## বাংলা সারসংক্ষেপ

প্ল্যাটফর্মে **স্কিল-ধারণাটির তিনটি সমান্তরাল বাস্তবায়ন** আছে: (১) `backend/skills/` — manifest-রেজিস্ট্রি + ইনস্টলার (৬৬ + ২৫৪ লাইন, ২টি manifest), (২) `backend/core/skill_manager.py` — LLM-সংশ্লেষিত স্কিমা + Supabase স্কিল-স্টোর (২৫২ লাইন), (৩) রিপো-রুটে `skills/` — আরেকটি registry + installer + schema + marketplace (৬০৩ লাইন)। **তিনটিই dormant** — কোনো সক্রিয় প্রোডাকশন-কলার নেই। মেমোরি-সাবসিস্টেমের ERR-F02 (১৫+ প্রতিযোগী store) যেমন হয়েছিল, এই প্যাটার্ন স্কিল-অঙ্গেও ঘটেছে — পার্থক্য শুধু সময়: মেমোরির প্রতিযোগিতা প্রোডাকশন-পরে পাকা হয়েছিল, স্কিলেরটা এখনো বীজ-অবস্থায়। **আজ একীভূত করা সস্তা; ওয়্যারিং-পরে করা ERR-F02-মূল্য।**

এর সাথে দ্বৈত-সমস্যা: `backend/skills/installer.py` L140-175 **রানটাইমে subprocess-pip-install** করে — lightweight-লঙ্ঘন (অবাউন্ডেড নির্ভরতা-বৃদ্ধি), fast-smooth-লঙ্ঘন (কোল্ড-স্টার্ট বিলম্ব), এবং supply-chain-ঝুঁকি; অথচ একই ফাইলের L73 জেনারেটেড-স্কিল-কোডে subprocess/exec নিষিদ্ধ করে — দ্বৈত-মান। রোডম্যাপ M9-এর গভর্ন্যান্স-চুক্তি (provenance, versioning, security-skill allowlist + rate-limit + audit-trail) তিনটি বাস্তবায়নেই আংশিক/অনুপস্থিত।

**সততা-দাবি:** এটি `proposed` নীলনকশা — executable নয়; ক্যানোনিকাল-বাছাই ফাউন্ডার Gate 2-সাপেক্ষ।

---

## Part 1 — Competitor Intelligence (প্রতিযোগী-বুদ্ধিমত্তা, dated evidence)

| উৎস | প্রমাণ (লেবেলযুক্ত) | আমাদের জন্য তাৎপর্য |
|---|---|---|
| রোডম্যাপ M9 (`UNIFIED_NEXT_ROADMAP_2026-09-15.md` L226-228) | [নিজস্ব-নীলনকশা] registry + manifests + permission scopes + sandbox/resource policy + provenance + versioning; security skills: allowlist + rate-limit + audit | এই ডকুমেন্ট M9-কে মডিউল-ইউনিটে ভাঙে ও তিন-বাস্তবায়ন বাস্তবতার সাথে মেলায় |
| কোড-বাস্তবতা (base ed35eaf) | [measured] ৩ বাস্তবায়ন, ৯১৯ লাইন মোট (66+254+252+603 নয় — রুট-স্কিল ৬০৩-এর মধ্যে installer/registry/schema/marketplace; backend/skills মোট ৩২০; skill_manager ২৫২); ২ manifest; কলার-শূন্য | আজ কনসলিডেশন-ব্যয় নিম্নতম; ওয়্যারিং-পরে ব্যয় বহুগুণ |
| মেমোরি-প্রেসিডেন্ট (ERR-F02) | [measured] ১৫+ store-কনসলিডেশন blueprint pinned; extend-not-replace ক্রম নথিভুক্ত | একই মতবাদ এখানে পুনঃপ্রয়োগ — নতুন মতবাদ অবিষ্কার-ব্যয় শূন্য |
| খরচ-স্কিমা-সত্যতা | [vendor-published/hypothesis] LLM-সংশ্লেষিত স্কিল-জেনারেশনের প্রতি-স্কিল খরচ আমাদের পরিমাপ নেই; manifest দাবি করে max $0.03/invocation | সংশ্লেষণ-ব্যয় মাপা-হয়নি — Gate 5-এ মাপা হবে; অনুমান-দাবি আজ করা হয় না |
| কী করা হয়নি | [measured] কোনো বাহ্যিক পেইড marketplace/স্কিল-স্টোর-সেবা নেই; root marketplace.py ৩৮-লাইন লোকাল | zero-cost রেখা অক্ষুণ্ণ |

**সততা-সতর্কতা:** তিনটি বাস্তবায়নের মধ্যে কোনোটি প্রকৃতপক্ষে ভবিষ্যৎ-প্রয়োজনের সেরা-মেল — এই সিদ্ধান্ত ফাউন্ডার-অনুমোদনের (Gate 2) বিষয়; এই ডকুমেন্ট কেবল প্রমাণ-ভিত্তি ও সুপারিশ-ক্রম দেয়।

---

## Part 1.5 — Gate 0 Reconciliation (প্ল্যান-সম্পর্ক মীমাংসা)

| সম্পর্কিত প্ল্যান | সম্পর্ক | মীমাংসা |
|---|---|---|
| `UNIFIED_NEXT_ROADMAP_2026-09-15.md` M9 (L226-228) | **মূল-উৎস** (same granularity) | এই ডকুমেন্ট M9-এর মডিউল-ইউনিট সম্প্রসারণ; M9-সীমা বহাল — security packs opt-in-কেবল |
| `docs/plans/features/orphan_components_wiring_master_plan.md` | **সম্পূরক** | L130-131 `task.required_skills` লুপ — স্কিল-কনসিউমার ধারণা ওই মতবাদেই; এই ডকুমেন্ট সেবক-স্তর সরবরাহ করে |
| `docs/plans/Plan_24_AI_Agent_Ecosystem_Integration.md` | **সম্পর্কহীন-কিন্তু-সামঞ্জস্যপূর্ণ** | এজেন্ট-ইকোসিস্টেম ব্রডার; স্কিল-গভর্ন্যান্স তার উপসেট-নয় — কেবল ইন্টারফেস-বিন্দু |
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` ERR-F02 | **মতবাদ-প্রেসিডেন্ট** | extend-not-replace + deprecation-shim + caller-evidence-চালিত ক্রম — সরাসরি পুনঃপ্রয়োগ |
| `MODULE_09_DORMANT_TOOLS_POWER_UP_2026-09-17.md` | **সমন্বয়** | Module 09 MCP/dormant-টুল শ্রেণিবিন্যাস করে; স্কিল-সিস্টেম dormant ছিল সেখানে-ও — ক্যানোনিকাল-ওয়্যারিং সিদ্ধান্ত একসাথে হবে |
| `MODULE_11_ARCHITECTURE_INTELLIGENCE_POWER_UP_2026-09-17.md` | **সম্পূরক-ঐচ্ছিক** | তিন-বাস্তবায়নের কলার-ম্যাপ ভবিষ্যৎ-গ্রাফে সস্তা; তবে এই ডকুমেন্ট ad-hoc grep-প্রমাণেই স্বয়ংসম্পূর্ণ |

---

## Part 2 — Six-Field Analysis

### ২.১ কী আছে (What exists — file:line evidence)

1. **তিন বাস্তবায়ন, তিন রুচি:** `backend/skills/` (manifest-glob + installer + provisioner), `backend/core/skill_manager.py` (LLM-সংশ্লেষণ + Supabase-স্টোর + MCPRegistryClient), রুট `skills/` (registry+installer+schema+marketplace+dynamic/)।
2. **সমৃদ্ধ manifest-স্কিমা (ক্যানোনিকাল-প্রার্থী):** `backend/skills/manifests/*.json` — allowed_roles, allowed_data, tools_allowed, human_approval_points, budget{cost,latency}, audit_logging — পলিসি ডেটায় (সঠিক দিক)।
3. **আংশিক-সুরক্ষা:** `_pre_write_security_scan()` (installer.py L73) জেনারেটেড-কোড-স্ক্যান; `_production_environment()` (L30) env-সনাক্তকরণ।
4. **বুট-ভার-সচেতন কোড:** skill_manager-এর লেজি-গেটওয়ে (R2-MEM) — প্ল্যাটফর্ম-সংকোচ (512MB) সচেতনতার প্রমাণিত প্যাটার্ন।
5. **Dormancy-সুযোগ:** কলার-শূন্য — একীকরণের সবচেয়ে সস্তা মুহূর্ত এটিই।

### ২.২ কী নেই (What's missing)

1. **এক-সত্য-উৎস নেই:** তিন বাস্তবায়নে কোনো শেয়ার্ড চুক্তি-স্তর নেই; কোনটি ক্যানোনিকাল — নির্ধারিত নয়।
2. **budget-enforcement নেই:** manifest-এ max_cost_per_invocation_usd/max_latency_seconds ঘোষিত, কিন্তু dispatch-স্তরে প্রয়োগ-চুক্তি তিন বাস্তবায়নেই সম্পূর্ণ নয় — পলিসি ঘোষণা ছাড়া সীমাহীন।
3. **runtime-pip-নিষেধ নেই:** install_dependencies() ডিফল্ট-সক্রিয়; প্রোডাকশন-গার্ড আংশিক (L30) — ডিফল্ট-নিষেধ নয়।
4. **provenance/versioning নেই:** স্কিল-সংস্করণ, উৎস-প্রমাণ, স্বাক্ষর — M9-চুক্তির এই স্তম্ভ অনুপস্থিত (manifest-এ version আছে, provenance নেই)।
5. **security-skill গভর্ন্যান্স নেই:** allowlist/rate-limit/audit-trail — M9-এর শর্ত বাস্তবায়িত নয়; তিন বাস্তবায়নে rate-limit কোথাও নেই।

### ২.৩ কী করতে হবে (What to do)

- **P-A — ক্যানোনিকাল-বাছাই (সুপারিশ, Gate 2-সাপেক্ষ):** manifest-চুক্তিকে কেন্দ্র করে `backend/skills/`-স্টাইল ডেটা-চালিত পথ; skill_manager-এর লেজি-লোডিং আচরণ উত্তরাধিকারসূত্রে গ্রহণ; রুট `skills/` পিছিয়ে যায়। চূড়ান্ত নয় — ফাউন্ডার সিদ্ধান্ত।
- **P-B — একীকরণ-ক্রম (extend-not-replace):** (১) শেয়ার্ড manifest-ভ্যালিডেটর; (২) অন্য দুই বাস্তবায়ন deprecation-shim-পিছে (আমদানি-সামঞ্জস্য বহাল, নতুন-ব্যবহার নিষিদ্ধ); (৩) caller-এক (শূন্য) বলে মাইগ্রেশন-ঝুঁকি মেমোরির চেয়ে নিম্ন; (৪) পূর্ণ-সাইকেল zero-caller-প্রমাণের পরে বিলোপ।
- **P-C — budget-enforcement চুক্তি:** dispatch-পূর্বে manifest-budget পরীক্ষা (cost-অনুমান + latency-টাইমআউট); সীমা ডেটা-ফাইল থেকে — কোড-ধ্রুবকে নয়।
- **P-D — runtime-pip ডিফল্ট-নিষেধ:** install_dependencies() env-গেটেড (ডিফল্ট অফ; dev-এ কেবল ফাউন্ডার-অনুমোদিত allowlist; প্রোডাকশনে নিষিদ্ধ); নির্ভরতা provisioning-সময়ে ঘোষিত/অনুমোদিত — supply-chain ও cold-start দুটোই সুরক্ষিত।
- **P-E — provenance + versioning:** manifest-স্কিমা বর্ধন (source, checksum, min_platform_version) — ডেটা-চুক্তি; কোনো নতুন ইনফ্রা নয়।
- **P-F — security-skill শাসন (M9-শর্ত):** security-শ্রেণির স্কিল পৃথক manifest-ট্যাগ + টার্গেট-allowlist (ডেটা-ফাইল) + dispatch-স্তরে rate-limit (config-চালিত সীমা) + audit-trail (বিদ্যমান run/log-অবকাঠামোয়, নতুন টেবিল নয়); ডিফল্ট অসক্রিয় — opt-in।
- **P-G — জিরো-বাইপাস ইনফ্যারেন্স, ক্যান্সেলেশন ও স্যান্ডবক্সিং (Zero-Bypass Inference & Sandboxing):**
  - **Zero-Bypass Gateway:** কোনো স্কিল সরাসরি মডেল API বা litellm কল করতে পারবে না; বাধ্যতামূলকভাবে সেন্ট্রাল Gateway-র মাধ্যমে `InferenceContext(tenant_id, run_id, task_type='skill_execution')` সহকারে রুট হতে হবে।
  - **CancellationToken ইন্টিগ্রেশন:** প্যারেন্ট রান বাতিল হলে বা বাজেট ফুরিয়ে গেলে স্কিল এক্সিকিউশন তৎক্ষণাৎ ইন্টারাপ্ট হবে।
  - **আইসোলেটেড স্যান্ডবক্স:** হোস্টের নিরাপত্তা সুরক্ষায় স্কিল এক্সিকিউশন মেমোরি সীমা (<=512MB) এবং হার্ড টাইমআউট (<=30s) দ্বারা বাউন্ডেড থাকবে।

### ২.৪ কীভাবে করব (How — phase-ordered, flag-gated)

1. **Phase 1 (চুক্তি):** manifest-ভ্যালিডেটর + স্কিমা-বর্ধন (provenance ক্ষেত্র) — কেবল ডেটা-স্তর; runtime অস্পৃশ্য।
2. **Phase 2 (নিষেধ):** runtime-pip ডিফল্ট-অফ (env-গেট); বিদ্যমান দুই manifest নির্ভরতা-শূন্য যাচাই।
3. **Phase 3 (একীকরণ):** ক্যানোনিকাল-নির্বাচন প্রয়োগ + shim-ফ্রিজ; প্রতিটি পরিবর্তনে flag/kill-switch; কোনো সক্রিয় কলার না থাকায় উপভোক্তা-প্রভাব শূন্য।
4. **Phase 4 (প্রয়োগ):** budget-enforcement dispatch-চুক্তি + security-skill শাসন + Gateway InferenceContext ও CancellationToken বাইন্ডিং — সব সীমা config/manifest-চালিত।
5. **Phase 5 (বিলোপ):** shim-এ zero-caller এক পূর্ণ পর্ব পরিমাপের পরেই কেবল মুছে ফেলা (ERR-F02-ক্রমের ধাপ ৫)।

### ২.৫ বেনিফিট (Benefit)

1. **ERR-F02-পুনরাবৃত্তি প্রতিরোধ:** মেমোরিতে যে ঋণ ১৫+ store হয়ে ফুঁসেছে, স্কিলে সেটি বীজেই বন্ধ — রক্ষণাবেক্ষণ-ত্রয়ী একে হয়।
2. **সরবরাহ-শৃঙ্খলা ও সংকোচ-সুরক্ষা:** runtime-pip বন্ধ = অপ্রত্যাশিত নির্ভরতা-বৃদ্ধি শূন্য, 512MB free-tier সংকোচ অক্ষত, কোল্ড-স্টার্ট পূর্বাবস্থায়।
3. **জিরো-বাইপাস টোকেন অডিট ও ক্যান্সেলেশন:** স্কিল এক্সিকিউশনে কোনো রানঅ্যাওয়ে টোকেন খরচ হবে না এবং রান বাতিলে স্কিল প্রসেস কিল হবে।
4. **পলিসি প্রকৃত পলিসি হয়:** ঘোষিত budget/roles/audit প্রয়োগ-চুক্তিতে বাঁধা — স্কিল-চালিত খরচ ও বিলম্ব সীমাবদ্ধ।
5. **নিরাপদ বিস্তার-পথ:** provenance + security-গভর্ন্যান্স বসানোর পরেই ভবিষ্যৎ-স্কিল/প্যাক যোগ ঝুঁকিহীন — আগে নয়।

### ২.৬ ক্ষতি/ঝুঁকি (Cost/Risk)

1. **ভুল-ক্যানোনিকাল-বাছাই:** ভবিষ্যৎ-প্রয়োজনের সাথে অমিল হলে পুনঃকাজ — প্রশমন: সিদ্ধান্ত ফাউন্ডার-গেটেড; shim-বাস্তবায়ন উল্টানো-যোগ্য রাখা (kill-switch)।
2. **runtime-pip নিষেধে সৃজনশীলতা-সীমা:** dev-পরীক্ষায় দ্রুত-নির্ভরতা যোগ কঠিন হবে — প্রশমন: dev-allowlist env-চালিত (ফাউন্ডার-সম্পাদনযোগ্য), প্রোডাকশন-নিষেধ অপরিবর্তিত।
3. **স্কিমা-বর্ধন-মাইগ্রেশন:** পুরোনো দুই manifest-এ নতুন provenance ক্ষেত্র ফাঁকা — প্রশমন: ক্ষেত্র optional-প্রারম্ভ, ভ্যালিডেটর warn-মোড; error-মোড zero-false-positive-পরে (Module 10 মতবাদ)।
4. **ডরম্যান্ট-কোডে সাবধানতা-দাবি:** কলার-শূন্য হলেও ভবিষ্যৎ-ওয়্যারিং পরিকল্পনায় স্কিল-সিস্টেম ভূমিকা রাখতে পারে — প্রশমন: বিলোপ-ধাপ (Phase 5) পরিমাপ-পূর্বশর্তসহ; কোনো ধাপই তাড়াহুড়োয় নয়।

---

## Part 3 — Out of Scope

- কোনো নতুন পেইড marketplace/বাহ্যিক স্কিল-স্টোর-সেবা নয় (zero-cost লঙ্ঘন)।
- কোনো নতুন স্কিল-লেখা/স্কিল-ক্যাটালগ-বিস্তার নয় — কেবল চুক্তি ও একীকরণ; নতুন স্কিল পরে, গভর্ন্যান্স-পরে।
- এজেন্ট-মনোলিথ রিফ্যাক্টর নয় (সেটি Module 02-এর জগৎ)।
- MCP-টুল শ্রেণিবিন্যাস পুনরাবৃত্তি নয় (Module 09 সম্পন্ন) — কেবল স্কিল-স্তরের সন্ধি-বিন্দু।

---

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই প্রস্তাবে অবস্থান |
|---|---|
| duplicate subsystem নয় | এই ডকুমেন্টেরই মর্ম — তিন সমান্তরাল বাস্তবায়নকে একে করা; কোনো চতুর্থ সৃষ্টি নয় |
| Playwright wholesale replacement নয় | সম্পর্কহীন |
| Free-tier quota-trick নিষেধ | সম্পর্কহীন — কোনো কোটা-কৌশল নেই; budget-cap স্থানীয়-পলিসি |
| API process-এ Chromium নয় | সম্পর্কহীন |
| এক মডিউল = এক ডকুমেন্ট | কেবল স্কিল-ইকোসিস্টেম |
| single-plan execution discipline | proposed; Gate 2-পূর্বে কোনো execution নয় |
| docs-only শাখা-প্রোটোকল | এই ডকুমেন্ট docs-only; কোড-পরিবর্তন ভবিষ্যৎ execution-প্ল্যানে, ফাউন্ডার-অনুমোদনে |
| pull-before-push | সিরিজ-প্রোটোকল (branch `crown-jewel-v2`) |
| প্রমাণ-শৃঙ্খলা | প্রতিটি দাবি path/line-ভিত্তিক; অপরিমাপিত খরচ `hypothesis`-লেবেলে |

---

## Part 5 — Verification & Rollback (Gates 4–6)

- **Gate 4 (প্রমাণ):** ভ্যালিডেটর fixture-টেস্ট; runtime-pip নিষেধ-টেস্ট (ডিফল্টে ব্যর্থ-হওয়া-বাধ্য); budget-enforcement টেস্ট; shim-আমদানি-সামঞ্জস্য টেস্ট।
- **Gate 5 (পরিমাপ):** স্কিল-বাস্তবায়ন-সংখ্যা ৩→১ (shim-বিলোপের পরে); manifest-budget-লঙ্ঘন-প্রতিরোধ সংখ্যা > 0 (প্রয়োগ-প্রমাণ); runtime-pip-চেষ্টা-নিষিদ্ধ-ঘটনা লগে দৃশ্যমান।
- **Gate 6 (rollback):** প্রতিটি ধাপ config-flag; shim পুনঃসক্রিয়যোগ্য; pip-গেট env-উল্টানো-যোগ্য; কোনো ডেটা-মাইগ্রেশন জড়িত নয় — একীভূত-স্তর নিষ্ক্রিয় করলেই পূর্বাবস্থা।

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| স্তম্ভ | মূল্যায়ন | প্রমাণ |
|---|---|---|
| **Zero cost** | ✅ সংগত | লোকাল manifest-ডির + বিদ্যমান Supabase-কী-সেবা (নতুন খরচ নয়); কোনো পেইড স্কিল-স্টোর নয়; marketplace ৩৮-লাইন লোকাল-ডির |
| **Lightweight** | ✅ সংগত (সংশোধনসহ) | মূল-কোডের runtime-pip lightweight-লঙ্ঘন ছিল — এই নীলনকশা P-D দিয়ে ডিফল্ট-নিষেধ করে; লেজি-লোডিং উত্তরাধিকার (R2-MEM প্যাটার্ন); এক-বাস্তবায়নে রক্ষণাবেক্ষণ-ভার ত্রয়ী থেকে এক |
| **Fast smooth** | ✅ সংগত | কোল্ড-স্টার্টে pip-বিলম্ব শূন্য (P-D); dispatch-স্তরে manifest-latency-cap; dormant-বাস্তবায়ন বলে কোনো জীবিত hot-path প্রভাবিত হয় না |
| **Zero hardcode** | ✅ সংগত | পলিসি manifest-ডেটা-ফাইলে (allowed_roles/budget/audit); security-allowlist ও rate-limit ডেটা/config-চালিত; কোনো ইন-কোড থ্রেশহোল্ড প্রস্তাব নেই |

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **Cycle 13-প্রার্থী (কিউ-পুনঃর‍্যাঙ্ক-অধীন, ফাউন্ডার Gate 2-সাপেক্ষ):** Anti-Hacking/Security middleware (`backend/middleware/anti_hacking.py` ১৫৮-লাইন + rate_limiter.py + tenant_rate_limiter.py) — বিদ্যমান লেগেসি প্ল্যান-ডক (`docs/plans/features/antihacking_security_defense_framework.md`)-এর Gate-0-রেকনসিলিয়েশন অপরিহার্য; প্রাথমিক grep-প্রমাণে স্থির-থ্রেশহোল্ড-যাচাই সেখানেই হবে।
- **Cycle 14-প্রার্থী:** Voice service (`backend/services/voice_service.py`, ৫৩-লাইন — ASR/TTS-সন্ধি), P2P credit system (`backend/p2p/credit_system.py`)।
- কিউ-শৃঙ্খলা: প্রতিটি চক্রের Gate 5 পরিমাপ কিউ-অর্ডার বদলাতে পারে — এই লাইনেজ কেবল প্রস্তাবিত ক্রম, execution-কিউ নয় (`PLAN_LIFECYCLE_POLICY.md` নিয়ম ১০)।
