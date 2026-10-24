---
id: crown-jewel-module-15-security-organ-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 15: Security Organ Deep Power-Up (গভীর সুরক্ষা-অঙ্গ: ৯,৫৫৫-লাইনের অঙ্গে অর্ধেক ডরম্যান্ট, লাইভ-গেট দুটি টেস্ট-বিহীন, ডিসেপশন-ফিডব্যাক লুপ বিচ্ছিন্ন — ৩য়-পক্ষ বুদ্ধিমত্তা-সমৃদ্ধ পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/core/autonoguard_engine.py + backend/core/security/** — গভীর সুরক্ষা-অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১৫ — একটি মডিউল (গভীর সুরক্ষা-অঙ্গ), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); নতুন চুক্তি অনুযায়ী Part 1 এখন গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (OWASP GenAI Top-10 2025, NeMo Guardrails, Llama Prompt Guard 2, Microsoft Spotlighting, garak/PyRIT, TruffleHog, Semgrep, Infisical, least-agency, API-deception) — প্রতিটি ধারণা চার-স্তম্ভ-ফিল্টারে ছাঁকা; branch crown-jewel-v2 base 678e817-এ spot-checkকৃত কোড-প্রমাণ"
depends_on:
  - "অঙ্গ-আকার: backend/core/security/** = ৯,৫৫৫+ লাইন (২০+ ফাইল) + backend/core/autonoguard_engine.py ৪৮০ লাইন — তবে wiring-সত্য: (a) সক্রিয় ~১১টি ইউনিট (autonoguard middleware-পথে, auth_middleware, api_key_middleware, origin_validator, honeypot, rbac, tool_gateway, ast_scanner, ssrf, ws_auth, vault-গুলো), (b) ইমপোর্ট-কিন্তু-নিষ্ক্রিয় ২টি (facade-এর scanner/behavioral অর্ধেক + behavioral_analyzer.py ৪০৬ লাইন — record_user_behavior-এর শূন্য production কলার), (c) সম্পূর্ণ dormant ৮টি (prompt_firewall.py ২৪৭, injections/sql_prevention.py ৭৫৯, audit/security_auditor.py ৭৮২, audit/compliance_bot.py ৫৭৪, scanning/secret_scanner.py ৪৫৯, security/rate_limiter.py ১৯৪, api_key_limiter.py ৪৩, optimized_behavioral_analyzer.py ২৬০)"
  - "মাউন্ট-প্রমাণ: backend/core/app_builder.py L119-123 + L424-433 — AuthMiddleware, APIKeyAuth, OriginValidator, HoneypotMiddleware, AutonoGuardMiddleware সব মাউন্টেড; autonoguard শুধু SENSITIVE_OPS প্রিফিক্সে প্রতি-রিকোয়েস্ট (autonoguard_engine.py L37-48: ১০টি লিটারেল পাথ)"
  - "হট-পাথ বাস্তবতা: প্রতিটি রিকোয়েস্টে ~৬-৯টি Redis রাউন্ড-ট্রিপ ৪টি ওভারল্যাপিং লিমিটার-স্তর জুড়ে (auth revocation + api-key sliding-window + RequestValidation zset ×2 + honeypot rules-cache) — fast-smooth ঝুঁকি একক মডিউলে নয়, পুনরাবৃত্তিতে"
  - "SEC-003 ঝুলন্ত-বাস্তবতা: branch-এর backend/core/security/__init__.py L321-323-এ এখনো docstring-এ লিটারেল 'is_admin=True' — origin/main-এর 15c50db এটি reword করেছে কিন্তু branch 1-commit পিছিয়ে; পরবর্তী sync-এ মিলবে (pull-before-push প্রোটোকল)"
  - "টেস্ট-উল্টোপাল্টা: লাইভ-এনফোর্সড দুটি গেটের শূন্য টেস্ট — scanning/ast_scanner.py (sandbox pre-exec gate!) ও protection/honeypot.py (মাউন্টেড!); বিপরীতে dormant sql_prevention.py-র সেরা টেস্ট-কভারেজ — টেস্ট-শক্তি ভুল জায়গায়"
  - "false-assurance জরিপ: /admin-api/security-scan (backend/api/routes/admin_dashboard/endpoints_security.py L16-60) মাত্র ৩টি ইনলাইন চেক দেখায় যখন ২,৫০০+ লাইনের বাস্তব স্ক্যানার (security_auditor+secret_scanner+enhanced_ast_scanner) শূন্য-কলার; autonoguard_engine.py L335-336 নিজেই বাংলা কমেন্টে 'optimistic verification' স্বীকার করে; api_key_middleware.py L177-183 latency_ms=0.0 ফেব্রিকেটেড মেট্রিক"
  - "ত্রিমুখী ডুপ্লিকেট: ৩টি AST স্ক্যানার (scanning/ast_scanner লাইভ / enhanced_ast_scanner ৩৫৩ লাইন facade-only 'ML-based' নাম কিন্তু কোনো ML নেই / core/ast_security_scanner ২৩১ লাইন immune-shim লাইভ); ২টি behavioral analyzer (একটি inert, একটি শূন্য-ইমপোর্টার); ৩টি vault-চেইন (secret_vault=Infisical-client / security_vault=Fernet fail-fast / secure_credential_store=Fernet কিন্তু ব্যর্থতায় plaintext ফেরত) — দুটি ভিন্ন env-key-chain (ENCRYPTION_KEYS বনাম BROWSER_CREDENTIALS_ENCRYPTION_KEY); security_vault.py L25-এ self-OR টাইপো get('ENCRYPTION_KEY') or get('ENCRYPTION_KEY')"
  - "বাংলা-প্যারিটি ফাঁক: সব blocklist ইংরেজি-একমাত্রিক (prompt_firewall L23-54-এর ১৮ প্যাটার্ন, telegram_security.py L70-88) — বাংলা jailbreak স্থানীয় fast-path পেরোন্যাস; guardian_ai.py-তে মাত্র ১টি বাংলা প্যাটার্ন L235-242; ভুল-পজিটিভ বিপরীত-ঝুঁকি: guardian_ai.py L428 'on\\w+\\s*=' → 'phone='/once=' আটকায়; middleware/security.py L52 অ্যাপস্ট্রফি/হ্যাশ SQL-প্যাটার্ন → সাধারণ query-string 400"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): OWASP GenAI Top-10 2025 (LLM01 prompt injection, LLM02 sensitive-disclosure, LLM06 excessive agency) genai.owasp.org; NVIDIA NeMo Guardrails (Apache-2.0) rails-as-config; Meta Llama Prompt Guard 2 22M (huggingface.co); Microsoft Spotlighting (arXiv 2403.14720); NVIDIA garak + Microsoft PyRIT; TruffleHog OSS; Semgrep CE; Infisical (MIT); Auth0 least-agency (2025-10-27); Nordic APIs API-honeypot (2025-03-13)"
implements:
  - "গভীর সুরক্ষা-অঙ্গের wiring-সত্য-মানচিত্র: (a)/(b)/(c) শ্রেণি-টেবিল — 'security theater' বনাম প্রকৃত-প্রতিরক্ষা পৃথকীকরণ (Module 13-এর middleware-স্তরের সম্প্রসারণ, পুনরাবৃত্তি নয়)"
  - "ডিসেপশন-ফিডব্যাক লুপ (অস্বাভাবিক-চিন্তার কেন্দ্র): মাউন্টেড honeypot+autonoguard-এর ব্লক-ইভেন্ট → record_user_behavior-এ ফিড → inert behavioral_analyzer জাগরণ — দুটি অর্ধ-মৃত মডিউল এক জীবন্ত অভিযোজিত প্রতিরক্ষায়, শূন্য নতুন অবকাঠামো"
  - "rails-as-data: NeMo Guardrails-এর ৫-রেল ট্যাক্সোনমি (input/output/dialog/retrieval/execution) প্যাটার্নে একক security_policy.yml — SENSITIVE_OPS, honeypot signatures, prompt-patterns, governance-lists সব ডেটা-ফাইলে; বাংলা-প্যারিটি-প্যাক একই ফাইলে চড়ে"
  - "OWASP LLM Top-10 → মডিউল-ম্যাপিং টেবিল (ডেটা-ফাইল): LLM01→prompt_firewall+rails; LLM02→guardian PII+vault; LLM03→Module-12 skill-provenance; LLM06→tool_gateway least-agency allowlist — প্রতিটি ফাঁক ট্র্যাকড-রো"
  - "env-aware fail-policy সুইপ (V5.1 মতবাদ-সম্প্রসারণ): api_key_limiter fail-open→env-aware; secure_credential_store plaintext-fallback→production-এ raise; guardian AI-scan fail-open→loud-log"
  - "AST-স্ক্যানার একীকরণ (ERR-F02 extend-not-replace): ৩→১ ক্যানোনিকাল + deprecation-shim; rate-limit একীকরণ: ৪→১ কর্তৃত্ব (dormant কিন্তু superior security/rate_limiter-এর Lua/env-aware ডিজাইন শোষণ) — হট-পাথ Redis রাউন্ড-ট্রিপ হ্রাস"
  - "প্রত্যাখ্যান-সিদ্ধান্ত-নথি (anti-cargo-cult): Llama Prompt Guard 2 22M নেয়া হবে না — 512MB বাজেট + arXiv (2026-02-15) প্রমাণ agentic tool-injection শ্রেণিবদ্ধকরণে এর সীমাবদ্ধতা; বিনিময়ে regex+LLM-judge হাইব্রিডই সঠিক পথ"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 678e817: autonoguard_engine L37-48+L335, app_builder L119-123/L424-433, security/__init__ L321-323, guardian_ai L428+L235-242, middleware/security L52, endpoints_security L16-60, honeypot-mount, ৯,৫৫৫-লাইন wc-census; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "অর্ধেক-অঙ্গ-নিদ্রা — ৯,৫৫৫ লাইনের মধ্যে ~২,৮৬৮ লাইন (prompt_firewall ২৪৭ + sql_prevention ৭৫৯ + security_auditor ৭৮২ + compliance_bot ৫৭৪ + secret_scanner ৪৫৯ + api_key_limiter ৪৩) শূন্য production কলার — লেখা হয়েছিল, কেউ জাগায়নি; ERR-F02-প্যাটার্ন আগে থেকেই গজিয়েছে"
  - "লাইভ-গেট-বিহীন-টেস্ট — প্রতি রিকোয়েস্টে যে দুটি গেট সত্যিই চলে (honeypot signature-scan, sandbox-পূর্ব ast_scanner) সেগুলোর একটিও টেস্ট-ফাইল নেই; অথচ ডরম্যান্ট sql_prevention-এর টেস্ট সবচেয়ে ভালো — assurance উল্টে আছে"
  - "বিচ্ছিন্ন-নার্ভাস-সিস্টেম — behavioral_analyzer.py (৪০৬ লাইন, alert+recommended_action সহ) ইন্টিগ্রেটেড কিন্তু record_user_behavior-এর শূন্য কলার → ইভেন্ট-ইনফিউজ শূন্য; একই সময়ে honeypot ও autonoguard প্রতিদিন বাস্তব আক্রমণকারী দেখে কিন্তু কেউ শেখে না — ডেটা-প্রবাহের শূন্য-খরচ সংযোগ অফুরন্ত"
  - "৪-স্তর লিমিটার-অতিরিক্ত — security/rate_limiter (dormant, কিন্তু সেরা ডিজাইন: env-চালিত সীমা + Lua-atomic + env-aware fail), core/rate_limit, middleware/rate_limiter, middleware/security-ব্যাকআপ — প্রতি-রিকোয়েস্ট ~৬-৯ Redis রাউন্ড-ট্রিপ; একীকরণে ফ্রি-টিয়ার latency সরাসরি লাভ"
  - "৩য়-পক্ষ-ফিল্টার-শৃঙ্খলা — প্রতিটি ধার-করা ধারণা গৃহীত হয়েছে 'প্যাটার্ন হিসেবে, নির্ভরতা নয়' নীতিতে: NeMo-র config-ট্যাক্সোনমি হ্যাঁ, NeMo-লাইব্রেরি নয় (হেভি); PromptGuard-মডেল নয় (RAM+agentic-blind); garak/PyRIT শুধু nightly-রিপোর্ট-প্রস্তাব (ফাউন্ডার-গেটেড, zero-false-positive পূর্বশর্ত — Module 10/11 মতবাদ)"
test_evidence: "বিদ্যমান-ভিত্তি: autonoguard engine+middleware, auth_middleware, rbac, ws_auth, tool_gateway, ssrf, vault-ত্রয়ী টেস্টেড; প্রস্তাব-ভিত্তি: honeypot + ast_scanner টেস্ট-ফাইল (P-G), rails-loader টেস্ট (P-B), ডিসেপশন-লুপ ইভেন্ট-প্রবাহ টেস্ট (P-C), fail-policy দুই-মুখ টেস্ট (P-D); সব execution-স্তরে ফাউন্ডার-অনুমোদন-পরবর্তী"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5 টেবিল)"
  - "নতুন কোনো পেইড-সার্ভিস বা হেভি-নির্ভরতা নয়; ৩য়-পক্ষ ধারণা শুধু প্যাটার্ন-হিসেবে (512MB বাজেট-সংগত)"
  - "সব পলিসি-তালিকা/থ্রেশহোল্ড ডেটা-ফাইল+env-চালিত (P-B); কোনো hot-path latency-যোগ নয়; extend-not-replace (shim-বাধ্যতামূলক)"
  - "লিন্ট-শৃঙ্খলা: lint_plans.py 0 error / 0 warning; কোনো নতুন CI-গেট এই ডকে তৈরি হয় না (garak-nightly শুধু ফাউন্ডার-গেটেড প্রস্তাব)"
---

# Module 15 — Security Organ Deep Power-Up (গভীর সুরক্ষা-অঙ্গ)

## বাংলা সারসংক্ষেপ

সুরক্ষা-অঙ্গ হলো প্রকল্পের সবচেয়ে বড় অথচ সবচেয়ে অসম-জাগ্রত অঙ্গ: **৯,৫৫৫+ লাইনের মধ্যে ~১১টি ইউনিট সক্রিয়, ২টি অর্ধ-নিদ্রা, ৮টি সম্পূর্ণ ঘুমন্ত**। সবচেয়ে চমৎকার অদৃষ্ট-বিড়ম্বনা — যে দুটি গেট প্রতিদিন সত্যিই চলে (honeypot, sandbox-পূর্ব AST-স্ক্যান) সেগুলোর কোনো টেস্ট নেই; আর যেগুলোর টেস্ট সবচেয়ে ভালো (sql_prevention) সেগুলো কখনো চলেই না। এই নীলনকশার কেন্দ্রে **তিনটি অস্বাভাবিক চিন্তা**: (১) **ডিসেপশন-ফিডব্যাক লুপ** — honeypot/autonoguard প্রতিদিন বাস্তব আক্রমণকারী দেখে, আর behavioral_analyzer সজীব-নিদ্রায়; দুজনকে এক তারে জুড়লেই শূন্য-খরচে একটি অভিযোজিত প্রতিরক্ষা-সিস্টেম; (২) **rails-as-data** — NeMo Guardrails-এর স্থাপত্য-দর্শন ধার করা হবে লাইব্রেরি নয়: একক security_policy.yml-এ ৫-রেল, যেখানে বাংলা-প্যারিটি-প্যাক ও OWASP-ম্যাপিং একই জায়গায় বাস করবে; (৩) **anti-cargo-cult প্রত্যাখ্যান-নথি** — বাজারে যা জনপ্রিয় (Prompt Guard মডেল, ভারী guardrail-লাইব্রেরি) তা 512MB ফ্রি-টিয়ার-বাস্তবতা ও arXiv-প্রমাণে স্বচ্ছভাবে প্রত্যাখ্যান করা। ফলাফল: হট-পাথ Redis রাউন্ড-ট্রিপ হ্রাস, ৩টি AST-স্ক্যানার→১, ৪টি লিমিটার→১ কর্তৃত্ব, এবং অ্যাডমিন-প্যানেলের খেলনা-স্ক্যান → বাস্তব-স্ক্যান।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

> নতুন সিরিজ-চুক্তি: প্রতিটি চক্রে বাইরের জগৎ থেকে যা শেখা যায় তার গভীর-সমীক্ষা; প্রতিটি ধারণা **চার-স্তম্ভ-ফিল্টারে** (zero cost / lightweight / fast smooth / zero hardcode) ছাঁকা — "গ্রহণ" মানে প্যাটার্ন-ধার, "প্রত্যাখ্যান" মানে কারণ-সহ নথিভুক্ত।

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **OWASP GenAI Top-10 2025** (genai.owasp.org) | LLM01 prompt-injection, LLM02 sensitive-disclosure, LLM06 excessive-agency ইত্যাদির ক্যানোনিকাল শ্রেণিবিন্যাস | একক `owasp_llm_mapping` ডেটা-ফাইলে প্রতিটি আমাদের সুরক্ষা-ইউনিট ↔ OWASP-ID ম্যাপ; ফাঁক = ট্র্যাকড-রো (P-B-এর অংশ) | zero-cost ✓; hardcode-মুক্ত (ডেটা-ফাইল) ✓ |
| **NeMo Guardrails** (NVIDIA, Apache-2.0) | rails-as-config: input/output/dialog/retrieval/execution ৫-রেল সব config-ফাইলে | security_policy.yml-এ একই ৫-রেল ট্যাক্সোনমি; আমাদের বিক্ষিপ্ত তালিকার সব এক ছাদের নিচে (P-B) | লাইব্রেরি-প্রত্যাখ্যান (হেভি), প্যাটার্ন-গ্রহণ ✓ |
| **Microsoft Spotlighting** (arXiv 2403.14720, 2024-03) | অবিশ্বস্ত-কনটেন্টে delimiting/datamarking/encoding — indirect prompt-injection প্রতিরোধে প্রমাণিত, ন্যূনতম overhead | scout/deep-research + auto_rag_injector-এর ইনজেক্টেড কনটেন্টে মার্কার-প্রোটোকল — prompt-template-স্তরের পরিবর্তন, শূন্য অবকাঠামো (Module 07/08 boundary-নোট) | zero-cost ✓; hot-path-শূন্য ✓ |
| **garak + PyRIT** (NVIDIA/MSR, ওপেন-সোর্স) | LLM vulnerability-scan প্রোব-স্যুট — red-team-কে CI-র রাতে চালানো | architecture-nightly-প্যাটার্নে (Module 11) founder-gated **report-only** লাল-দল-রাত্রি; গেট নয়, আয়না (P-H) | zero-false-positive পূর্বশর্ত; founder-gated ✓ |
| **TruffleHog OSS / gitleaks** | battle-tested secret-scanning | আমাদের dormant secret_scanner.py (৪৫৯ লাইন)-এর নিয়তি-সিদ্ধান্তে তুলনা-ভিত্তি — platform-specific স্ক্যান রাখা হলে সাধারণ-প্যাটার্ন তাদের মত ডেটা-ফাইলে | devDep-only, রানটাইম-বাইরে ✓ |
| **Semgrep CE** | rules-as-YAML — AST-নিয়মও ডেটা-ফাইলে | ৩-কপি AST-স্ক্যানারের নিয়মগুলো data-file-এ; ক্যানোনিকাল স্ক্যানার লোড করবে (P-E) | নির্ভরতা নয়, ফরম্যাট-ধার ✓ |
| **Infisical (MIT)** | self-hostable secrets-প্ল্যাটফর্ম | আমাদের secret_vault.py **ইতিমধ্যেই** Infisical-client — পছন্দটি সংরক্ষণযোগ্য; env-override-চেইন নথিভুক্ত হবে (P-F) | ইতোমধ্যে-অর্থায়িত; নতুন-খরচ-শূন্য ✓ |
| **Auth0 least-agency** (2025-10-27) + OWASP LLM06 | "least privilege"-এর এজেন্টি-রূপ: প্রতি-এজেন্ট টুল-allowlist, deny-by-default | tool_gateway-এর RISK_LEVELS→role ম্যাপিংকে per-agent allowlist ডেটা-ফাইলে বিস্তার (P-B রেল-৫) | ডেটা-ফাইল-চালিত ✓ |
| **Nordic APIs API-honeypot** (2025-03-13) + awesome-honeypots | deception-কে ইন্টেলিজেন্স-উৎস বানানো: ব্লক-ইভেন্ট = ফ্রি আক্রমণকারী-টেলিমেট্রি | **ডিসেপশন-ফিডব্যাক লুপ** (P-C): honeypot/autonoguard ব্লক → record_user_behavior → behavioral_analyzer জাগরণ | zero-cost ✓; hot-path-শূন্য (async feed) ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ — anti-cargo-cult অধ্যায়)

| বিকল্প | কেন নয় |
|---|---|
| **Llama Prompt Guard 2 22M** (Meta, ফ্রি-ওয়েট) | 512MB ফ্রি-টিয়ারে ~৯০MB+ মডেল-রেসিডেন্সি ঝুঁকি; আরও নির্ণায়ক — arXiv (2026-02-15) প্রমাণ: PromptGuard-2/LlamaGuard শ্রেণিবদ্ধকারীরা **agentic tool-injection** মূল্যায়নে স্থাপত্যগতভাবে অক্ষম — আমাদের প্রকৃত ঝুঁকি-স্থান tool_gateway; বিকল্প: বিদ্যমান regex fast-path + LLM-judge হাইব্রিড |
| **NeMo Guardrails লাইব্রেরি-ব্যবহার** | নির্ভরতা-ওজন + কিছু রেলে LLM-কল-প্রয়োজন (latency+খরচ); আমাদের রেল-লজিক সাধারণ regex/ডেটা-চালিত — লাইব্রেরির প্রয়োজনই নেই |
| **পেইড WAF/ম্যানেজড-গার্ডরেল (Lakera ইত্যাদি)** | zero-cost স্তম্ভ-লঙ্ঘন; তদুপরি আমাদের হট-পাথ ইতিমধ্যে রেডিস-স্পর্শী — বাহ্যিক-কল-যোগ অগ্রহণযোগ্য |
| **নিজস্ব সাধারণ secret-scanner-বিস্তার** | TruffleHog/gitleaks-এর সাথে প্রতিযোগিতা নয় — আমাদের মূল্য platform-specific প্যাটার্নে সীমাবদ্ধ থাকা |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

বাজারের guardrail-স্ট্যাক মডেল-আগে-রাখে (classifier সামনে); আমাদের সবচেয়ে বড় সম্পদ তা **নয়** — আমাদেরটা **অবস্থান-আগে-রাখে** (SENSITIVE_OPS প্রিফিক্স-গেটিং + tool-risk-tiering + honeypot-deception)। এই ভিন্নতাকেই পুঁজি করা হবে: যেখানে প্রতিযোগীরা classifier-কে পাল্লা দেয়, আমরা **শেখা-লুপ** দিয়ে জিতব — প্রতিটি ব্লক-ইভেন্ট পরের ব্লককে স্মার্ট করবে (P-C), চিরন্তন মডেল-আপডেটের খরচ-ছাড়া।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| `docs/plans/features/risk_remediation_and_hardening_execution_plan_bn.md` (১,৩২৪ লাইন) | active / evidence_state: unverified | **supersede নয়** — ওটা fix-execution-তালিকা, এটা অঙ্গ-সত্য-মানচিত্র। §১০ P1 "MCP/tool-execution policy-gateway বাধ্যতামূলক" ← আমাদের tool_gateway (a)-স্ট্যাটাস দ্বারা শক্তিশালী; §১ P0 secret-ঝুঁকি ← আমাদের vault-ত্রয়ী+key-chain-দ্বৈততা আবিষ্কার (P-F) দ্বারা পুনঃস্থানাঙ্কিত হবে |
| `docs/plans/features/production_hardening_and_p1_p2_roadmap_2026_09_11.md` (৬১ লাইন) | active / partial / canonical: candidate | এর P1/P2 সুরক্ষা-আইটেমগুলো এই মডিউলের P-A…P-H সারিতে পুনঃস্থানাঙ্ক (re-anchor); বিরোধ নেই, ক্রম-নির্দেশ |
| `docs/plans/features/antihacking_security_defense_framework.md` | historical | Module 13-এ ইতোমধ্যে Gate-0 সমাপ্ত — পুনরাবৃত্তি নয় |
| Module 13 (এই সিরিজ) | published | **boundary**: middleware/anti_hacking.py + middleware/rate_limiter*.py এ মডিউলে পুনঃ-অডিট নয়; Module 13-এর "autonoguard IS wired" এক-লাইন নোটই এখানে পূর্ণ-গভীরতায় সম্প্রসারিত |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **সক্রিয় কঙ্কাল (a-শ্রেণি, ~১১ ইউনিট)**: app_builder L119-123/L424-433-এ AuthMiddleware, APIKeyAuth, OriginValidator, HoneypotMiddleware, AutonoGuardMiddleware মাউন্টেড; rbac ১৭-ফাইলে; tool_gateway agent_action+mcp+orchestrator-এ; ast_scanner sandbox-পূর্ব; ssrf browser+scout-এ (৩০০s DNS-cache); ws_auth ৬ WS-রুটে; vault-ত্রয়ী বিতরণ-চলমান
- **চলন্ত ভালো প্যাটার্ন**: V5.1 env-aware fail-policy (admin fail-closed/dev fail-open+loud-log); honeypot 418+TTL-block; fail-open-গুলোতে bounded বা loud-log অভ্যাস ক্রমবর্ধমান; secret_vault-এ env-override-অগ্রাধিকার + ৭ HARD_REQUIRED প্রোড-ফেইল-ক্লোজড
- **dormant-কিন্তু-সেরা-ডিজাইন**: security/rate_limiter.py — env-চালিত সীমা + Lua-atomic + env-aware fail: একীকরণের ইঞ্জিন-হৃদয় হবে (P-F)
- **গভীরতার সম্পদ**: guardian_ai-র BD-phone/NID PII-regex; prompt_firewall-এর \u0980-\u09FF সচেতনতা; cryptographic_ledger HITL-ব্যবহৃত

### ২.২ কী নেই

- **~২,৮৬৮ লাইনের নিদ্রা-ব্লক** — ৬ dormant ইউনিটের শূন্য production কলার (উপরের depends_on)
- **লাইভ-গেটের টেস্ট** — honeypot + ast_scanner শূন্য-টেস্টেড অথচ এনফোর্সড
- **সংযুক্ত নার্ভাস-সিস্টেম** — behavioral_analyzer-এ ইভেন্ট-ইনফিউজ শূন্য; ডিসেপশন-ডেটা নষ্ট হয়
- **একক পলিসি-উৎস** — ১৪+ জায়গায় ইন-কোড তালিকা/থ্রেশহোল্ড (SENSITIVE_OPS, honeypot-signatures, SQL/XSS ২২ regex, RISK_LEVELS, retention 30d ইত্যাদি)
- **বাংলা-প্যারিটি** — blocklist ইংরেজি-একমাত্রিক; ভুল-পজিটিভ দ্বৈত (`on\w+=`, অ্যাপস্ট্রফি-৪০০)
- **OWASP-ম্যাপিং** — কোনো ক্যানোনিকাল শ্রেণিবিন্যাসে ইউনিট-ম্যাপ নেই
- **সত্য-অ্যাডমিন-স্ক্যান** — খেলনা ৩-চেক বনাম ২,৫০০+ লাইন বাস্তব-স্ক্যানার-বেকার

### ২.৩ কী করতে হবে

আটটি প্রস্তাব (সবই ফাউন্ডার-রিভিউযোগ্য; বাধ্যতামূলক-ক্রম P-G প্রথম — লাইভ-গেটের নিরাপত্তা-জাল আগে):

- **P-G (প্রথম, ঝুঁকি-অবনম)**: লাইভ-অনটেস্টেড গেট দুটিতে টেস্ট — ASTSandboxScanner + HoneypotMiddleware; টেস্ট-ছাড়া অন্য কোনো P শুরু নয়
- **P-A**: `/admin-api/security-scan` truth-label — ব্যাকগ্রাউন্ড-টাস্কে বাস্তব SecurityAuditor+SecretHunter (on-demand, hot-path-বাইরে); খেলনা ৩-চেক অপসারণ বা উপ-সেট হিসেবে শোষণ
- **P-B**: security_policy.yml — NeMo-ট্যাক্সোনমিতে ৫-রেল; SENSITIVE_OPS/honeypot-signatures/prompt-patterns/governance-lists/RISK_LEVELS সব ডেটায়; env-override পূর্ব-প্যাটার্নে (prompt_blocked_patterns config_fields L332); একই ফাইলে owasp_llm_mapping + বাংলা-প্যারিটি-প্যাক
- **P-C**: ডিসেপশন-ফিডব্যাক লুপ — honeypot-block/autonoguard-OTP-fail → async record_user_behavior; behavioral_analyzer-এর alert সাবস্ক্রাইবযোগ্য; hot-path-বাইরে, বাউন্ডেড-কিউ
- **P-D**: env-aware fail-policy সুইপ — api_key_limiter (এখন দ্বিমুখ fail-open), secure_credential_store plaintext-fallback→production-raise, guardian AI-scan fail-open loud-log — V5.1 নীতি-প্যাটার্নে
- **P-E**: AST ৩→১ — ক্যানোনিকাল scanning/ast_scanner + নিয়ম-ডেটা-ফাইল; enhanced_ ও core/ast_security_scanner shim-এ (ERR-F02: zero-caller-প্রমাণ-পূর্ব অপসারণ নয়)
- **P-F**: rate-limit ৪→১ কর্তৃত্ব + vault/key-chain ৩→১ নথি + security_vault L25 self-OR টাইপো-ফিক্স; dormant-কিন্তু-superior security/rate_limiter ডিজাইন শোষণ — হট-পাথ Redis রাউন্ড-ট্রিপ উল্লেখযোগ্য হ্রাস
- **P-H**: লাল-দল-রাত্রি **প্রস্তাব** (garak-প্যাটার্ন, report-only, founder-gated, zero-false-positive প্রমাণ-পূর্ব — এই ডক কোনো workflow তৈরি করে না)
- **P-I (Zero-Bypass CI এনফোর্সমেন্ট ও টেন্যান্ট বাউন্ডারি অডিট)**:
  - CI-তে একটি স্ট্যাটিক গেট যা নিশ্চিত করবে কোনো সাবসিস্টেম সরাসরি প্রোভাইডার ক্লায়েন্ট কল করছে না (Module 03 জিরো-বাইপাস বাউন্ডারি)।
  - ডাটাবেজ এবং ভেক্টর কোয়েরিতে বাধ্যতামূলক RLS ও টেন্যান্ট আইসোলেশন স্কোপ যাচাই (`tenant_id` ফিল্টারিং অডিট)।

### ২.৪ কীভাবে করব

প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2 পরবর্তী); সাধারণ-ক্রম P-G→P-D→P-B→P-A→P-C→P-E→P-F→P-I→P-H; প্রতিটিতে: টেস্ট-আগে, env-নামকরণ V5.1-সংগত, shim+deprecation-নোট, baseline-N র‍্যাচেট (নতুন ইন-কোড পলিসি-লিটারেল = fail, পুরনো N-তালিকাভুক্ত); P-C-তে bounded-queue+ltrim-অভ্যাস (B-11-প্যাটার্ন); P-B-তে YAML-লোড-fail→last-known-good+loud-log (fail-safe-ডেটা)

### ২.৫ বেনিফিট

- সুরক্ষা-দাবি ↔ সুরক্ষা-বাস্তব একরেখায় (false-assurance ৮টি → পরিমাপযোগ্য)
- প্ল্যাটফর্ম-ব্যাপী টেন্যান্ট আইসোলেশন ও জিরো-বাইপাস কঠোরভাবে সুরক্ষিত (P-I)
- হট-পাথ রাউন্ড-ট্রিপ হ্রাস → fast-smooth সরাসরি লাভ (ফ্রি-টিয়ারে পরিমাপযোগ্য p95)
- প্রতি-আক্রমণকারী-শেখা (P-C) — মডেল-কেনা-ছাড়া অভিযোজিত-প্রতিরক্ষা: প্রতিযোগীদের সাথে ভিন্ন-পথ
- বাংলা-জেইলব্রেক-প্যারিটি — স্থানীয়-ভাষার আক্রমণও একই জালে
- অ্যাডমিন-প্যানেল বাস্তব-তথ্য দেখাবে — সিদ্ধান্ত-মানের প্যানেল

### ২.৬ ক্ষতি/ঝুঁকি

- P-C-তে ভুল-জাগরণ: behavioral অশ্রাব্য-অ্যালার্ট → ডিফল্ট alert-only + থ্রেশহোল্ড-ডেটা-ফাইলে (মাউন্ট-সিদ্ধান্ত Module-13-সংগত)
- P-B-তে ভুল-মাইগ্রেশন: একটি তালিকা বাদ-পড়লে গেট-অন্ধ → শুরুতেই dual-read (কোড-ডিফল্ট + ফাইল-ওভাররাইড) + parity-টেস্ট
- P-E/P-F-এ ERR-F02-পুনরাবৃত্তি-ঝুঁকি → shim-অবধারিত, zero-caller-প্রমাণ-পূর্ব অপসারণ
- টেস্ট-সংযোজনে CI-সময়-বৃদ্ধি → এককালীন, warn-only শুরু (Module-10 knip মতবাদ)

## Part 3 — Out of Scope

- middleware/anti_hacking.py + middleware/rate_limiter*.py পুনঃ-অডিট (Module 13)
- LLM-judge-মডেল নির্বাচন / LLM Gateway-অভ্যন্তর (Module 03)
- voice/p2p সত্য-সেমান্টিকস (Module 14); skill-runtime-pip (Module 12)
- কোনো নতুন workflow/CI-গেট তৈরি (P-H শুধু প্রস্তাব-লিপি)
- Infisical-স্ব-হোস্ট-মাইগ্রেশন — বর্তমান client-পথ অটুট

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active (P-G প্রথম) |
| Evidence-first | প্রতিটি দাবি file:line; ৩য়-পক্ষ দাবি তারিখ-চিহ্নিত URL-উৎস |
| Extend-not-replace | P-E/P-F shim-বাধ্যতামূলক; ERR-F02 মতবাদ |
| Founder gates | মাউন্ট/enforcement-পরিবর্তন সব Gate 2-পরবর্তী |
| Zero-false-positive | যেকোনো ভবিষ্যৎ-গেট warn-only→প্রমাণ→গেট |
| Branch discipline | docs-only এই ডক; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-G টেস্ট-সবুজ; P-B parity-টেস্ট (পুরনো-আচরণ = নতুন-আচরণ); P-C ইভেন্ট-প্রবাহ ইন্টিগ্রেশন-টেস্ট; P-D দুই-মুখ fail-টেস্ট
- **Gate 5 (measurement)**: হট-পাথ Redis-কমান্ড/রিকোয়েস্ট (৬-৯ → লক্ষ্য ≤৪); admin-scan-রিপোর্টে বাস্তব-ফাইন্ডিং-গণনা; P-C-র প্রতি-সপ্তাহ-শেখা-ইভেন্ট
- **Gate 6 (rollback)**: প্রতিটি P-র এক-ফাইল-রোলব্যাক (ডেটা-ফাইল/শিম-নিরপেক্ষ); P-C kill-switch env; P-B last-known-good-লোডার

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-G টেস্ট-জাল | ✓ CI-সময়-মাত্র | ✓ | ✓ ঝুঁকি-অবনম | n/a |
| P-A truth-label | ✓ বিদ্যমান-স্ক্যানার | ✓ on-demand | ✓ hot-path-বাইরে | ✓ থ্রেশহোল্ড-ডেটা |
| P-B rails-as-data | ✓ | ✓ YAML-লোড | ✓ দ্বৈত-পাঠে-অপরিবর্তিত | ✓✓ মূল-উদ্দেশ্য |
| P-C ডিসেপশন-লুপ | ✓ শূন্য-নতুন-অবকাঠামো | ✓ bounded-কিউ | ✓ async, hot-path-বাইরে | ✓ থ্রেশহোল্ড-ডেটা |
| P-D fail-policy | ✓ | ✓ | ✓ fail-পথে-ন্যূনতম | ✓ env-চালিত |
| P-E AST ৩→১ | ✓ | ✓ কম-কোড | ✓ | ✓ নিয়ম-ডেটা |
| P-F লিমিটার/vault একীকরণ | ✓ | ✓ | ✓✓ রাউন্ড-ট্রিপ-লাভ | ✓ env-সীমা |
| P-H লাল-দল-রাত্রি | ✓ ওপেন-সোর্স | ✓ report-only | ✓ nightly-বাইরে | ✓ প্রস্তাব-স্তর |
| PromptGuard-২ প্রত্যাখ্যান | ✓✓ RAM-সংরক্ষণ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: প্রতিটি প্রস্তাব publish-পূর্বে চার-স্তম্ভে ছাঁকা; ৩য়-পক্ষ ধারণাগুলো "নির্ভরতা নয়, প্যাটার্ন" চুক্তিতে; প্রত্যাখ্যানগুলোও কারণ-নথিভুক্ত — ভবিষ্যৎ-চক্রে পুনঃ-পরীক্ষাযোগ্য।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ১৬-প্রার্থী**: Billing/Metering Gateway (`backend/api/routes/billing*` + usage-meters) — ৩য়-পক্ষ গবেষণা-প্রস্তুতি: LiteLLM spend-tracking প্যাটার্ন, OpenTelemetry-মিটারিং, token-pricing-ডেটা-ফাইল পদ্ধতি (পেইড-বিকল্প প্রত্যাখ্যান-কারণসহ)
- **চক্র ১৭-প্রার্থী**: HITL/Approval চেইন (hitl_ledger + approval_manager — approval_manager নিজস্ব `_audit`-ইনলাইন চালায়, canonical log_security_event নয়) — ৩য়-পক্ষ: LangGraph interrupt-প্যাটার্ন, Humanloop-স্টাইল review-loop (প্যাটার্ন-হিসেবে)
- কিউ-পুনঃর‍্যাঙ্ক: Gate 5 পরিমাপে; simulated-class governance script (zero-false-positive পূর্বশর্তে) স্থগিত-প্রার্থী
