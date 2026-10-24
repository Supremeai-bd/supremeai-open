---
id: crown-jewel-module-19-i18n-bengali-adapter-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 19: i18n & Bengali-First Adapter Power-Up (i18n ও বাংলা-অ্যাডাপ্টার: সংস্কৃতিতে বাংলা-প্রথম, মেশিনারিতে ইংরেজি-প্রথম — ভাষা-কর-হ্রাস মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (frontend/src/i18n/ + backend ভাষা-পথ — বাংলা-অ্যাডাপ্টার অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ১৯ — একটি মডিউল (i18n/বাংলা-অ্যাডাপ্টার), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (ICU MessageFormat/MF2, UAX-15 NFC, ভাষা-কর গবেষণা — ACL, OFL ফন্ট self-host); branch crown-jewel-v2 base 33815131-এ spot-checkকৃত কোড-প্রমাণ"
depends_on:
  - "নির্মিত-কিন্তু-অপরিহিত স্ট্যাক: frontend/src/i18n/ ৩১৬ লাইন (I18nProvider/config/translations/useI18n) — translations.ts ২২৪ লাইন en/bn/es/zh × ~৪০ কী; কিন্তু App.tsx-এ হার্ডকোডেড locale='en'; সুইচার-UI (dashboard/Header.tsx L31-41) dead — components/dashboard/ শূন্য বাহ্যিক-ইমপোর্টার; মাউন্টেড core/Header-এ কোনো locale-UI নেই; t()-গ্রাহক শূন্য (শুধু টেস্ট)"
  - "লিখিত-কখনো-অপঠিত অগ্রাধিকার: I18nProvider L7,29 localStorage supreme_lang → POST /api/preferences preferred_language (preferences.py L38-68 _EXTENDED_KEYS গ্রহণ করে, সংরক্ষণ করে) — কিন্তু read-দিক শূন্য: কোনো LLM/chat-পথ পড়ে না; Accept-Language সমঝোতা অনুপস্থিত; index.html L2 স্থায়ী lang='en' — locale-পরিবর্তনে আর হয় না"
  - "৪টি প্রতিদ্বন্দ্বী বাংলা-মডেল-ম্যাপ: core/llm/advanced_model_router.py L63-77 BENGALI_KEYWORDS ১৭ inline + L404-443 bengali→model_multilingual (লাইভ, gateway completion.py L127-130) / engine/smart_router.py L25,34-36 bengali→models['chat'] / core/language_router.py (dormant) bengali→deepseek / services/llm/providers.py L668-704 BengaliNormalizer (লাইভ, llm_router L275,403-408, ১০+ এজেন্ট-ইমপোর্টার) — যার normalize() সম্পূর্ণ prompt লোয়ারকেস করে + ১২-এন্ট্রি BANGLISH_MAP; 'ki khobor' দুই-শব্দ-কী কখনোই ম্যাচ করতে পারে না; ইংরেজি 'ami' শব্দ নীরবে আমি হয়ে যায়"
  - "বাংলা-অন্ধ বাজেট-গণিত: core/llm/token_budget.py L80-91 estimate_tokens — কেবল CJK 2.0 রেশিও; \u0980-\u09ff অনুপস্থিত → বাংলা ~৪ অক্ষর/টোকেনে ~২× আন্ডার-এস্টিমেট → gateway can_fit/বাজেট-সিদ্ধান্ত ভুল (Module 07 split-estimator লাইন-স্তরে পুনঃযাচাইকৃত); সচেতন-যমজ context_engine/budget.py L55-59 (1.3×); L115-127 truncate sentence-regex [.!?\n] — বাংলা দাঁড়ি । (U+0964) অদৃশ্য → 'coherent' truncation মধ্য-অক্ষরে কঠিন-কাটে (conjunct/vowel-sign ভাঙে — দৃশ্যমান বর্জ্য)"
  - "NFC-শূন্যতা: unicodedata গ্রেপ = শূন্য (pyerrorfix vocab ব্যতীত) — core/embeddings.py L132 cache-key কাঁচা-টেক্সট f'{text}:{dim}'; NFC/NFD/ZWNJ-জুক্ত-বিকল্প = নীরব cache-miss, dedup-miss, search-miss; chat_search L66-75 lower()-substring — বাংলা রূপভেদ/বানান-বিকল্পে মিস"
  - "নিরাপত্তা-প্যারিটি-ফাঁক পুনঃযাচাইকৃত: guardian_ai.py L235-243 একমাত্র ১টি বাংলা ইনজেকশন-প্যাটার্ন বনাম ~৮ ইংরেজি; telegram_security.py L70-85 ৫ regex ইংরেজি-একমাত্রিক (বাংলা grep-শূন্য)"
  - "ধ্বংসাত্মক-পথ: tools/bandwidth_optimizer.py L17 re.sub(r'[^\x00-\x7F]+','',prompt) — বাংলা ১০০% বিলোপ (dormant, Module 09 পুনঃযাচাইকৃত); tools/localization/bangla_nlp.py L22-35 বিপরীত-চিত্র — মিশ্র-টেক্সট থেকে সব Latin ছাঁটে; ১৭-শব্দ stopword-তালিকা agents/domain/bangla_nlp_agent.py L27-এ ~৩০-শব্দ দ্বিতীয় তালিকায় ডুপ্লিকেট — দুটোই zero-prod-caller; api/routes/skills.py L104-107 _SLUG_RE [a-z0-9] — বাংলা blueprint-নাম ডিজাইনগতভাবে প্রত্যাখ্যাত"
  - "PDF-টোফু: api/routes/chat_export.py L136-217 reportlab getSampleStyleSheet() (Helvetica/WinAnsi) — রেপো-ব্যাপী কোনো TTFont/registerFont নেই, কোনো ফন্ট-অ্যাসেট নেই (.ttf/.woff2 grep-শূন্য) → বাংলা কথোপকথন-এক্সপোর্ট ফাঁকা রেন্ডার; Markdown/docx UTF-8-নিরাপদ"
  - "ফন্ট-অর্ধ-নির্মিত: index.css L1 Hind Siliguri (Google-CDN) + .font-bengali L489-490 — কিন্তু ক্লাসের শূন্য ব্যবহার; বেস-স্ট্যাকে বাংলা-কভারেজ নেই → সিস্টেম-ফলব্যাক, যন্ত্রভেদে অসামঞ্জস্য; ২৫২ frontend-ফাইলে বাংলা-লিপি (মূলত কমেন্ট, কিন্তু user-facing স্ট্রিং inline-মিশ্র EN+BN — Module 18-প্যাটার্ন অ্যাপ-ব্যাপী); admin.bn.json ১০৪ লাইন (~১০০ BN কী) design-tokens-এ শূন্য-রেফারেন্স অনাথ; scripts/advanced_analysis/bengali_i18n_completeness_checker.py ভাঙা (REPO_ROOT parent.parent → scripts/ রেজলভ) — কখনোই চলে না"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): ICU MessageFormat + MessageFormat 2 (unicode-org.github.io; locize 2026-07-04 — MF2 নতুন Unicode স্ট্যান্ডার্ড 2025-সালে Final Candidate); UAX #15 NFC (unicode.org 2025-07-30); ভাষা-কর — ACL Anthology (O Ahia, cited 205+): ইন্ডিক নন-ল্যাটিন লিপিতে ইংরেজির তুলনায় ~৫× টোকেন-ব্যয়; arXiv 2025-07-31: বাংলা ইনপুট উল্লেখযোগ্য বৃহত্তর টোকেন-গণনা উৎপাদন করে; gwfh.mranftl.com — Google-ফন্ট self-host woff2 (OFL)"
implements:
  - "ভাষা-কর-হ্রাস মতবাদ (অস্বাভাবিক-চিন্তার কেন্দ্র): বাংলা ব্যবহারকারী ইতিমধ্যে ~৫× টোকেন-ব্যয় দেয় (শিল্প-গবেষণা); আমাদের মেশিনারি সেই কর আরও বাড়ায় (বাংলা-অন্ধ বাজেট → ভুল-ট্রাংকেশন; ৪-ম্যাপ-বিভ্রান্তি; NFC-মিস-রিসেট) — এই নীলনকশা কর-হ্রাস: সৎ-গণিত + এক-ক্যাটালগ + NFC-একতা"
  - "catalog-first: প্রতি-পৃষ্ঠতল bn.json+en.json ডেটা-ফাইল (translations.ts + admin.bn.json + ২৫২-ফাইল inline + telegram-স্ট্রিং একত্র; ৩ অনাথ-অ্যাসেট অবসর) — লোডার ~৩০ লাইন, কোনো i18n-লাইব্রেরি নয় (zero-dep বহাল)"
  - "একক bengali_text.py স্ক্রিপ্ট-ইউটিল (P-D): NFC পাস O(n), \u0980-\u09ff সনাক্তকরণ, বাংলা-সচেতন টোকেন-রেশিও, দাঁড়ি-সচেতন অক্ষর-নিরাপদ truncation — token_budget/context_engine/embeddings/chat_search গ্রাহক; Module 07 split-estimator অবসান"
  - "প্যারিটি-রেলস ডেটা-ফাইল (P-E): বাংলা ইনজেকশন-প্যাটার্ন (guardian_ai+telegram_security) + stopword ২→১ + Banglish-ম্যাপ + ৪→১ বাংলা-মডেল-ম্যাপ — এক YAML/JSON; Module 15 P-B প্রেসিডেন্ট"
  - "অগ্রাধিকার-লুপ বন্ধ (P-C): preferred_language chat/SSE-পথে পাঠ → এক system-directive ব্লক ('respond in the user's language') — লিখিত-অপঠিত অবসান"
  - "প্রত্যাখ্যান-নথি (anti-cargo-cult): react-i18next/next-intl/i18next নয় (৩১৬-লাইন নিজস্ব স্ট্যাকই যথেষ্ট — লাইব্রেরি-যোগ = বোঝা); messageformat-runtime নয় (ICU-সিনট্যাক্স কেবল ভবিষ্যৎ-সংগত-ফরম্যাটে); বাংলা-LoRA-প্রশিক্ষণ এই ডকের পরিসরে নয়"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 33815131: i18n-স্ট্যাক ৩১৬ লাইন পূর্ণপাঠ, token_budget L80-91/L115-127, providers L668-704, ৪-ম্যাপ তুলনা, embeddings L132, chat_export L136-217, index.css L1/L489, unicodedata grep, ২৫২-ফাইল বাংলা-গণনা; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "লিখিত-অপঠিত-অগ্রাধিকার — ব্যবহারকারী ভাষা-বেছে localStorage+API-তে সংরক্ষণ হয়, কিন্তু একটিও গ্রাহক নেই: পুরো লুপ অর্ধেক খোলা — সুইচার দেখা যায় না (dead-কম্পোনেন্টে), বেছে নিলেও কোনো আচরণ বদলায় না"
  - "৪-ম্যাপ-অসংগতির ব্যবহারিক-মূল্য — একই বাংলা প্রশ্ন কোন রাউটারে পড়ল তায় ভিন্ন মডেল: advanced_router→multilingual, smart_router→chat, language_router→deepseek; ফল = অনির্দেশ্য গুণ/ব্যয়; P-E-এর এক-ম্যাপ-ডেটা-ফাইলই নিরাময়"
  - "BengaliNormalizer-এর নীরব-ক্ষতি — লাইভ পথে (llm_router L275,403-408) সম্পূর্ণ prompt লোয়ারকেস: ইংরেজি কোড/নাম/সংবেদনশীল-টোকেনও ছোট-হাতের হয়; দ্বিভাষিক প্রম্পটে অনুবাদ-প্রতারণা ('ami'→আমি) — normalize-এর পরিসর সংকুচিত হওয়া উচিত (শুধু সনাক্তকরণ, রূপান্তর নয়)"
  - "ভাষা-করের সংখ্যা — বাজেট-আন্ডার-এস্টিমেট ~২× মানে: বাংলা ব্যবহারকারীর বাজেট দ্বিগুণ-দ্রুত শেষ হয় আর truncation মাঝ-অক্ষরে তার পাঠ্য ভাঙে — ভাষা-করের উপর জরিমানা; P-D-এর সৎ-রেশিও (~৪ অক্ষর/টোকেন, env-সামঞ্জস্য) এই জরিমানা বন্ধ করে"
  - "শূন্য-নতুন-ফন্ট-ব্যয় — Hind Siliguri OFL; self-host woff2 (gwfh-প্যাটার্ন) = CSP-র fonts.gstatic নির্ভরতা অবসান + cold-start-এ ফন্ট-স্থিতি; PDF-এর TTFont-এমবেড একই অ্যাসেট পুনঃব্যবহার"
test_evidence: "বিদ্যমান: ২৩ backend-টেস্ট-ফাইল বাংলা-স্পর্শী (test_language_router 'আজকের আবহাওয়া'→bengali; context_engine 1.3×; bengali_ocr_converter 195L বাস্তব-টুল; multilingual_tts); frontend useTranslation ক্যাটালগ-কী টেস্ট; শূন্য-টেস্ট: provider-মাউন্ট/স্থায়িত্ব প্রবাহ, preferred_language→AI-আচরণ, BengaliNormalizer পার্শ্ব-প্রতিক্রিয়া, PDF বাংলা-রেন্ডার, নিরাপত্তা-প্যারিটি; প্রস্তাব-টেস্ট: NFC-সমতা (বিকল্প-ফর্ম এক-কী), দাঁড়ি-ট্রাংকেশন অক্ষর-সম্পূর্ণতা, এক-ম্যাপ-নির্ধারণতা, ক্যাটালগ-সম্পূর্ণতা চেকার"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5)"
  - "কোনো নতুন i18n-লাইব্রেরি নয় (৩১৬-লাইন নিজস্ব স্ট্যাক বহাল); কোনো পেইড-সার্ভিস নয়; ফন্ট OFL self-host"
  - "সব ক্যাটালগ/প্যাটার্ন/ম্যাপ/রেশিও ডেটা-ফাইল+env (zero-hardcode); NFC O(n) — কোনো hot-path উল্লেখযোগ্য লেটেন্সি-যোগ নয়"
  - "BengaliNormalizer-এর রূপান্তর-আচরণ সংকুচিত-সংশোধন (রূপান্তর-নয়-সনাক্তকরণ); লিন্ট 0 error / 0 warning (সিরিজ)"
---

# Module 19 — i18n & Bengali-First Adapter Power-Up (i18n ও বাংলা-অ্যাডাপ্টার)

## বাংলা সারসংক্ষেপ

প্রকল্পটি **সংস্কৃতিতে বাংলা-প্রথম, মেশিনারিতে ইংরেজি-প্রথম**: ডকুমেন্ট-কর্পাস, ফাউন্ডার-কৌশল, UI-স্ট্রিং বাংলায় স্যাঁতসেঁতে — অথচ i18n-লুপ অর্ধেক খোলা (সুইচার-আনমাউন্টেড, `preferred_language` লিখিত-কখনো-অপঠিত, LLM-পথে শূন্য ভাষা-নির্দেশ), **৪টি প্রতিদ্বন্দ্বী বাংলা-মডেল-ম্যাপ** তিন রাউটারে অসংগত, লাইভ `BengaliNormalizer` সম্পূর্ণ prompt লোয়ারকেস করে, বাজেট-এস্টিমেটর বাংলায় ~২× আন্ডার-মাপে, truncation দাঁড়ি-অন্ধ হয়ে মধ্য-অক্ষরে ভাঙে, PDF বাংলায় টোফু, NFC-শূন্যতায় cache/search নীরব-মিস। শিল্প-গবেষণার সংখ্যা এখানে দাঁত: ইন্ডিক নন-ল্যাটিন লিপিতে ইংরেজির তুলনায় **~৫× টোকেন-ব্যয়** (ভাষা-কর)। মতবাদ: **কর-হ্রাস** — সৎ-গণিত (P-D), এক-ক্যাটালগ (P-A), NFC-একতা, এক-ম্যাপ (P-E); সব zero-dep, OFL-ফন্ট self-host-সহ। বাংলা-প্রথম পরিচয় এখানেই মেশিনারিতে রূপ নেবে।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **ICU MessageFormat / MF2** (unicode-org.github.io; locize 2026-07-04 — MF2 নতুন Unicode স্ট্যান্ডার্ড, 2025-এ Final Candidate) | `{count, plural, one{…} other{…}}` — ভাষা-নিয়ম স্ট্রিং-ভিতরে | ক্যাটালগ-কী-মান ভবিষ্যৎ-সংগত: flat JSON-এ ICU-শৈলী স্ট্রিং লেখা যাবে, রানটাইম সরল-প্রতিস্থাপন শুরুতে (plural-শাখা বাংলায় সরল: bn-এ কেবল one/other CLDR-শ্রেণি) | runtime-নির্ভরতা-প্রত্যাখ্যান, ফরম্যাট-ধার ✓ |
| **UAX #15 NFC** (unicode.org, 2025-07-30) | canonical-equivalence নিশ্চিত করতে নিয়মিত-ফর্মে স্বাভাবিকীকরণ; নিরাপত্তা-উপকার (বিকল্প-উপস্থাপন হ্রাস) | P-D: এক NFC পাস bengali_text.py-তে — embeddings cache-key, dedup, search-মিল এক-ফর্মে; ZWJ/ZWNJ-জুক্ত বানান-বিকল্প এক-ফর্মে | O(n), stdlib-শুধু ✓✓ |
| **ভাষা-কর গবেষণা** (ACL Anthology — O Ahia, cited 205+; arXiv 2025-07-31 বাংলা-বিশেষ) | ইন্ডিক নন-ল্যাটিন লিপি ~৫× টোকেন-ব্যয়; বাংলা ইনপুট উল্লেখযোগ্য বৃহত্তর টোকেন-গণনা | P-D-এর সংখ্যা-ভিত্তি: বাংলা-সচেতন টোকেন-রেশিও env-চালিত (ডিফল্ট ~৪ অক্ষর/টোকেন-ঘরানা, বাস্তব-মাপে ক্যালিব্রেট); বাজেট-সত্য = কর-স্বচ্ছতা | গণিত-সংশোধন খরচ-শূন্য ✓ |
| **Google-ফন্ট self-host** (gwfh.mranftl.com; Noto/Hind Siliguri OFL) | woff2 + CSS-snip; CDN-নির্ভরতা অবসান | P-F: Hind Siliguri self-host (বিদ্যমান index.css পছন্দের বহাল) + PDF TTFont একই TTF; CSP থেকে fonts.gstatic বাদ-পথ | OFL-মুক্ত, ~২০০KB এককালীন ✓ |
| **CLDR bn-লোকেল** (ICU-পরিবার) | সংখ্যা (লক্ষ/কোটি-দলীকরণ), তারিখ-ফরম্যাট | P-H/চক্র-সম্প্রসারণ-নোট: frontend Intl.NumberFormat('bn-BD') — ব্রাউজার-নিজস্ব API, শূন্য-নির্ভরতা | stdlib/browser-API ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন নয় |
|---|---|
| **react-i18next / next-intl / i18next-আদান** | ৩১৬-লাইন নিজস্ব-স্ট্যাক ইতোমধ্যে বিদ্যমান-টেস্টেড; লাইব্রেরি-যোগ = বান্ডল-বৃদ্ধি + ডাবল-স্ট্যাক-বিভ্রান্তি; অনুপস্থিতটা মাউন্ট-ইচ্ছাশক্তি, কোড নয় |
| **messageformat-runtime-আদান** | MF2-শেষ-প্রার্থী-পর্যায়; বাংলার plural-কাঠামো সরল (one/other); flat-catalog + সরল-প্রতিস্থাপনই যথেষ্ট; ভবিষ্যৎ-স্থানান্তর-পথ খোলা রাখা হবে (ICU-শৈলী স্ট্রিং) |
| **বাংলা-LoRA-প্রশিক্ষণ-প্রবাহ** (config/ml/bengali_lora.yaml-সংযোগ) | এই ডকের পরিসর-বাইরে (GPU/সময়-ব্যয়); ডেটা-ফাইল-প্যারিটি ও রাউটিং-সত্যই প্রথম-লাভ |
| **সব-কিছুর-এক-বিশাল-ক্যাটালগ-মনোলিথ** | প্রতি-পৃষ্ঠতল-ফাইল-ছোট-রাখা (fetch-বৃদ্ধি নয়); monorepo-প্যাকেজ-সীমায় |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

শিল্পের i18n "সব-ভাষায়-সব-কিছু" মানসিকতা — বিশাল ক্যাটালগ, ভারী রানটাইম। আমাদের ভিন্ন-পথ: **বাংলা-গভীরতা, ইংরেজি-ভিত্তি** — দুই ভাষা সম্পূর্ণ-সমান-গভীর (নিরাপত্তা-প্যাটার্ন, বাজেট-গণিত, search-মিল পর্যন্ত), তৃতীয়-ভাষা প্রয়োজনে LLM-নিজেই (কোড-আসলে নেই — es/zh-কী অনাথ)। "ভাষা-কর" দৃষ্টিতে: প্রতিযোগীরা বহু-ভাষার প্রস্তাশনা দেখায়, আমরা বাংলা ব্যবহারকারীর প্রকৃত-ব্যয় কমাই — বাজেট-সত্য, NFC-মিল, অক্ষর-সম্পূর্ণ truncation দিয়ে। এটাই ফাউন্ডারের L6 Bengali Adapter Track-এর মেশিনারি-রূপ।

## Part 1.5 — Gate 0 Reconciliation

| লেগেসি-ডক | স্ট্যাটাস | সিদ্ধান্ত |
|---|---|---|
| docs/plans/HEAD_OF_PLANNING_STRATEGIC_LEVERAGE_2026-09-16.md | active | **Lever L6 Bengali Adapter Track** (B5 battlefield, eval-set v1 200-500 আইটেম, L6.2 BengaliNormalizer-অডিট) — ফাউন্ডার-স্তরের কৌশল বিদ্যমান; এই নীলনকশা তার module-level নীলনকশা; L6.2-অডিট এখানে সম্পাদিত (P-D/P-E প্রমাণ) |
| config/ml/bengali_lora.yaml | নথি-অ্যাসেট | LoRA-রেসিপি পরিসর-বাইরে; উল্লেখ-নোট |
| Module 07/09/15/18 (সিরিজ) | published | boundary: split-estimator/bandwidth_optimizer/প্যারিটি-ফাঁক/telegram-স্ট্রিং শুধু লাইন-স্তরে পুনঃযাচাই — পূর্ণ-অঙ্গ-অডিট সেখানেই; এখানকার P-D/P-E তাদের সংশোধন-পথের ভাগ বহন করে |
| i18n/localization-সমর্পিত-প্ল্যান | অনুপস্থিত | **greenfield** — docs/plans-এ কোনো ডেডিকেটেড i18n-প্ল্যান নেই |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **নির্মিত স্ট্যাক**: frontend/src/i18n ৩১৬ লাইন (Provider/config/translations/hook) + localStorage-স্থায়িত্ব + API-সংরক্ষণ-পথ (preferences.py গ্রহণকারী)
- **সচেতন-যমজ**: context_engine/budget.py 1.3× বাংলা-সচেতন গণিত (টেস্টেড) — P-D-এর বীজ
- **বাস্তব বাংলা-টুল**: bengali_ocr_converter.py 195 লাইন (Vision-hint প্রবাহ, টেস্টেড); multilingual_tts; ২৩ বাংলা-স্পর্শী টেস্ট-ফাইল
- **ফন্ট-বীজ**: Hind Siliguri ইতোমধ্যে নির্বাচিত (index.css L1) + .font-bengali ক্লাস-খোলস; admin.bn.json ~১০০ BN কী (অব্যবহৃত-কিন্তু-লেখা)
- **UTF-8-স্বাস্থ্য**: mojibake-শূন্য; ensure_ascii=False সুশৃঙ্খল; ERR-M03 force_utf8_streams সেন্টিনেল-টেস্টেড

### ২.২ কী নেই

- **লুপ-সংযোগ**: সুইচার-মাউন্ট, locale-সম্মান, document.lang-সিঙ্ক, Accept-Language — সব অনুপস্থিত; preferred_language-র শূন্য গ্রাহক
- **এক-ক্যাটালগ**: ৩ অনাথ-অ্যাসেট + ২৫২-ফাইল inline-মিশ্র; t()-গ্রাহক শূন্য
- **এক-ম্যাপ**: ৪ বাংলা-মডেল-ম্যাপ ৩ রাউটারে অসংগত; BANGLISH_MAP/BENGALI_KEYWORDS inline
- **সৎ-বাজেট**: বাংলা-অন্ধ estimate_tokens; দাঁড়ি-অন্ধ truncation; NFC-শূন্য
- **PDF-বাংলা**: TTFont-শূন্য → টোফু; ফন্ট-অ্যাসেট-শূন্য (CDN-নির্ভর)
- **প্যারিটি**: নিরাপত্তা-প্যাটার্ন ১-বনাম-৮; stopword দ্বৈত
- **পরিমাপ**: bengali_i18n_completeness_checker ভাঙা (REPO_ROOT) — কখনোই চলে না

### ২.৩ কী করতে হবে

আটটি প্রস্তাব (ক্রম ভিত্তি→লুপ→সত্য; সব ফাউন্ডার-রিভিউযোগ্য):

- **P-D (ভিত্তি)**: একক bengali_text.py — NFC পাস + স্ক্রিপ্ট-সনাক্তকরণ + বাংলা-সচেতন টোকেন-রেশিও (env-চালিত, বাস্তব-মাপে ক্যালিব্রেটযোগ্য) + দাঁড়ি-সচেতন অক্ষর-নিরাপদ truncation; গ্রাহক: token_budget, context_engine, embeddings cache-key, chat_search — Module 07 split-estimator অবসান
- **P-A**: catalog-first — প্রতি-পৃষ্ঠতল bn.json/en.json; translations.ts + admin.bn.json + inline-স্ট্রিং + telegram-স্ট্রিং একত্র; ৩ অনাথ অবসর; zero-dep লোডার
- **P-B**: লুপ-মাউন্ট — সুইচার মাউন্টেড header-এ; সংরক্ষিত-locale সম্মান; document.lang + html lang সিঙ্ক
- **P-C**: অগ্রাধিকার-লুপ-বন্ধ — preferred_language chat/SSE-পথে পাঠ → system-directive (user's-language); Module 15 P-B শেপ
- **P-E**: প্যারিটি-রেলস — বাংলা ইনজেকশন-প্যাটার্ন + stopword ২→১ + Banglish-ম্যাপ + ৪→১ বাংলা-মডেল-ম্যাপ (ডেটা-ফাইল); BengaliNormalizer-রূপান্তর-আচরণ সংকুচিত (সনাক্তকরণ-হ্যাঁ, নীরব-লোয়ারকেস/শব্দ-বদল নয়)
- **P-F**: ফন্ট-স্থায়িত্ব — OFL self-host woff2 (Hind Siliguri) + PDF TTFont-এমবেড (chat_export) — একই অ্যাসেট দুই গ্রাহক; CSP-র fonts.gstatic বাদ-পথ
- **P-G**: পরিমাপ-সত্য — bengali_i18n_completeness_checker REPO_ROOT-সংশোধন; founder-gated CI-রিপোর্ট (warn-প্রথম, zero-false-positive পূর্বশর্ত)
- **P-H**: dormant-ফাঁদ-নিয়তি — bandwidth_optimizer-এর ASCII-বিলোপ-লাইন অপসারণ (zero-caller-প্রমাণসহ); BengaliNLP stopword-দ্বৈততা মিলন; LanguageRouter fold-বা-wire সিদ্ধান্ত; es/zh-অনাথ-কী নিয়তি (অবসর-প্রস্তাব)
- **P-I**: গেটওয়ে-ইন্টিগ্রেটেড বাংলা টোকেন বাজেট ও মাল্টি-মডেল ক্যালিব্রেশন (Gateway Bengali Token Budgeting):
  - Module 03 LLM Gateway-র সাথে ইন্টিগ্রেশন: বাংলা ইউনিকোড অক্ষরের জন্য (`\u0980-\u09ff`) মডেল-নির্দিষ্ট সঠিক টোকেন রেশিও নির্ধারণ, যাতে প্রাক-কল `BudgetReservation` লিজ সঠিকভাবে টোকেন ব্লক করতে পারে।
  - দাঁড়ি (`।`) ও যুক্তাক্ষর-সচেতন ট্রাংকেশন: টোকেন ট্রাংকেশনে কোনো যুক্তাক্ষর বা শব্দ মাঝখান থেকে না কেটে বাক্য-পর্যায়ে মার্জিত সমাপ্তি নিশ্চিত করা।

### ২.৪ কীভাবে করব

ক্রম P-D→P-A→P-B→P-C→P-E→P-F→P-G→P-H→P-I; প্রতিটি P = আলাদা ছোট execution-প্ল্যান (Gate 2-পরবর্তী); P-D-তে parity-টেস্ট (পুরনো-ক্যালকুলাস-বনাম-নতুন বাংলা-ক্ষেত্রে), NFC-সমতা-টেস্ট (NFC/NFD/ZWNJ-বিকল্প এক-ফল); P-A-তে ক্যাটালগ-সম্পূর্ণতা-চেক P-G-র চেকার-সহ; P-E-তে dual-read স্থানান্তর (ERR-F02); রেশিও-ক্যালিব্রেশন বাস্তব-টোকেনাইজার-মাপে (পরিমাপ-নথি); সব env V5.1-সংগত

### ২.৫ বেনিফিট

- বাংলা ব্যবহারকারীর প্রকৃত-ব্যয় হ্রাস: বাজেট-সত্য (~২×-ভুল অবসান) + অক্ষর-সম্পূর্ণ truncation + NFC-মিল-পুনরুদ্ধার (cache/search হিট)
- গেটওয়ে ইন্টিগ্রেশনে নিখুঁত প্রি-কল রিজার্ভেশন: বাংলা প্রম্পটে কোনো বাজেট ঘাটতি বা ওভার-বিলিং হবে না।
- নিরাপত্তা-প্যারিটি: বাংলা ইনজেকশন আর ইংরেজির সম-জালে
- অনির্দেশ্য-মডেল-গুণ অবসান (৪→১ ম্যাপ) — খরচ-পূর্বানুমেয়তা
- বাংলা-প্রথম পরিচয় মেশিনারিতে প্রমাণিত: সুইচার-কার্যকর, প্রেফারেন্স-সম্মানিত, PDF-পঠনযোগ্য
- ফন্ট-স্থিতি cold-start-সহনশীল (CDN-মুক্ত); zero-dep বহাল

### ২.৬ ক্ষতি/ঝুঁকি

- রেশিও-ক্যালিব্রেশন-ভুল → env-চালিত + বাস্তব-মাপ-নথি + রক্ষণশীল-ডিফল্ট
- NFC-প্রয়োগে ক্যাশ-অবৈধকরণ-ঝলক → স্থানান্তরে দ্বৈত-মিল (কাঁচা+NFC) এক-পিরিয়ড
- P-E-তে ম্যাপ-স্থানান্তর-ভুল → parity-টেস্ট + dual-read; BengaliNormalizer-সংকোচনে আচরণ-পরিবর্তন-সচেতনতা → পরিবর্তন-নোট+টেস্ট
- ক্যাটালগ-স্থানান্তরে স্ট্রিং-মিস → চেকার-গেট-পূর্ব fallback-EN-লাউড
- P-H অপসারণে হঠাৎ-নির্ভরতা → zero-caller-প্রমাণ-পূর্ব (ERR-F02)

## Part 3 — Out of Scope

- LLM Gateway-অভ্যন্তর (Module 03 — শুধু P-C-সন্নিবেশ-বিন্দু); context-অঙ্গ-পূর্ণ-অডিট (Module 07)
- বাংলা-LoRA-প্রশিক্ষণ/GPU-প্রবাহ; TTS/OCR-অভ্যন্তর (বিদ্যমান টুল-নথি বহাল)
- তৃতীয়-ভাষা (es/zh) সম্প্রসারণ; RTL (বাংলা non-RTL); নতুন i18n-লাইব্রেরি
- telegram-অঙ্গ-পূর্ণ-অডিট (Module 18); নিরাপত্তা-অঙ্গ (Module 15)

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | এই নীলনকশার অবস্থান |
|---|---|
| Single-plan execution | প্রস্তাব-পাইপলাইন; একসময়ে একটিই active (P-D প্রথম) |
| Evidence-first | file:line + ACL/arXiv/unicode.org-তারিখ-চিহ্নিত |
| Extend-not-replace | নিজস্ব-স্ট্যাক বহাল; dual-read স্থানান্তর; ERR-F02 |
| Founder gates | L6-track সংগতি; CI-রিপোর্ট founder-gated |
| Zero-false-positive | ক্যাটালগ-চেকার warn-প্রথম |
| Branch discipline | docs-only; execution আলাদা ব্রাঞ্চ+PR |

## Part 5 — Verification & Rollback

- **Gate 4 (proof)**: P-D parity+NFC-সমতা+অক্ষর-সম্পূর্ণতা টেস্ট; P-A ক্যাটালগ-সম্পূর্ণতা; P-B মাউন্ট/স্থায়িত্ব টেস্ট; P-C প্রেফারেন্স→নির্দেশ টেস্ট; P-E এক-ম্যাপ-নির্ধারণতা টেস্ট; P-F PDF-বাংলা-স্ন্যাপশট টেস্ট
- **Gate 5 (measurement)**: বাংলা-বাজেট-ভুল-অনুপাত (→~০); cache/search-মিস-হার (NFC-পরে হ্রাস); ক্যাটালগ-কভারেজ %; BengaliNormalizer-রূপান্তর-গণনা (→০)
- **Gate 6 (rollback)**: প্রতিটি P এক-ফাইল/ডেটা-রোলব্যাক; P-D পুরনো-গণিত env-ফলব্যাক; P-F CDN-ফলব্যাক নোট

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| প্রস্তাব | Zero Cost | Lightweight | Fast Smooth | Zero Hardcode |
|---|---|---|---|---|
| P-D স্ক্রিপ্ট-ইউটিল | ✓ stdlib | ✓ এক-মডিউল | ✓ O(n) | ✓ env-রেশিও |
| P-A ক্যাটালগ | ✓ | ✓ json | ✓ | ✓✓ |
| P-B লুপ-মাউন্ট | ✓ | ✓ | ✓ | n/a |
| P-C প্রেফারেন্স-লুপ | ✓ | ✓ এক-ব্লক | ✓ | ✓ |
| P-E প্যারিটি-রেলস | ✓ | ✓ | ✓ | ✓✓ |
| P-F ফন্ট/PDF | ✓ OFL | ✓ ~২০০KB | ✓ cold-start-স্থিতি | n/a |
| P-G পরিমাপ-সত্য | ✓ | ✓ | ✓ | n/a |
| P-H ফাঁদ-নিয়তি | ✓ | ✓✓ কম-কোড | ✓ | n/a |
| i18n-লাইব্রেরি/MF2-runtime প্রত্যাখ্যান | ✓✓ | ✓✓ | ✓ | n/a |

**জন্মগত-সংগতি-ঘোষণা**: ভাষা-কর-হ্রাস নিজেই চার-স্তম্ভের সারসংক্ষেপ — খরচ কমে (সৎ-গণিত), বোঝা কমে (zero-dep), গতি সমান (O(n)), আর সব ডেটা-ফাইলে।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ২০-প্রার্থী**: notification/delivery-অঙ্গ (email_agent + core/messaging dispatcher + FastMCP-tower notify) — ৩য়-পক্ষ-প্রস্তুতি: outbox-প্যাটার্ন, SMTP-বনাম-ফ্রি-API-রেল, বার্তা-বাহক-অ্যাবস্ট্রাকশন
- **চক্র ২১-প্রার্থী**: simulated-class governance স্ক্রিপ্ট (মক-ক্লাস-পরিষ্কারক, zero-false-positive পূর্বশর্তে, Module-10/11-মতবাদ-সংগত)
- কিউ-পুনঃর‍্যাঙ্ক: Gate 5-পরিমাপে; প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল
