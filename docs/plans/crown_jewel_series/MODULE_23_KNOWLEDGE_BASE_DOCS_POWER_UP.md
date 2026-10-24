---
id: crown-jewel-module-23-knowledge-base-docs-power-up-2026-09-17
title: "Crown Jewel Module Series — Module 23: Knowledge-Base & Docs Organ Power-Up (জ্ঞানভাণ্ডার-অঙ্গ: শূন্য-তাক লাইব্রেরি — দুই পরিণত আমদানি-মেশিন অথচ একটিও বই আসেনি; পাঠকের দরজা প্রতি-কলে 500; ১২১ বাংলা-তথ্য তাক-বন্দি — retrieval-proof মতবাদে পূর্ণাঙ্গ নীলনকশা, বাংলা)"
status: proposed
document_role: architecture
owner_circle: Governance Circle (backend/core/knowledge_* + backend/api/routes/knowledge.py + backend/scripts/import_knowledge_base.py + backend/scripts/db/ingest_knowledge.py + knowledge/ data-কর্পাস — জ্ঞানভাণ্ডার-অঙ্গ)
target_scope: supremeai_internal
scope: "Crown Jewel Module Series-এর চক্র ২৩ — একটি মডিউল (knowledge-base/docs/importer-exporter), একটি সম্পূর্ণ power-up নীলনকশা। কী আছে → কী নেই → কী করতে হবে → কীভাবে করব → বেনিফিট → ক্ষতি/ঝুঁকি (Gate 1 six-field); Part 1 = গভীর ৩য়-পক্ষ বুদ্ধিমত্তা (RAG-ingest idempotency, চাংকিং-গবেষণা, RAGAS golden-set CI, freshness-governance, pgvector-মতবাদ, বাংলা retrieval); branch crown-jewel-v2 base 1b698ee6-এ spot-checkকৃত কোড-প্রমাণ + in-process runtime-repro"
depends_on:
  - "ভাঙা-দরজা (মূল-আবিষ্কার): services/knowledge_qa.py — `self.governance`-normalization ব্লক audit_logger-property-র return-এর পরে মৃত-কোড (L55–75 লক্ষ্য ছিল __init__ L43–53); ফলে L85 `self.governance[\"allowed_roles\"]` প্রতি-কলে AttributeError → **POST /api/knowledge/ask ও /ask-scribe প্রতিটি কলে 500** (in-process runtime-repro দ্বারা প্রমাণিত); routes লাইভ-মাউন্টেড (routers.py:254 is_critical) — অথচ test_knowledge_qa.py কেবল ধ্রুবক-assert করে (L63–65), ব্যবহারকারী-পথের সেই-মৃত্যু CI-অদৃশ্য"
  - "শূন্য-তাক: ৮টি সমান্তরাল knowledge-store (ChromaDB `supremeai_knowledge` chromadb_store.py:29 / Supabase pgvector knowledge_base supabase_client.py:515–521+RPC :525–552 / knowledge_chunks pgvector ingest L152–179 / Postgres long-term 19_harden_knowledge_base.sql:3–27 / memory_vault.json core/knowledge_base.py:7–13 (নাম-মিথ্যা — প্রম্পট-ক্যাশ) / Firestore ai_agent_knowledge_base agent_knowledge_store.py:15 / SQLite git_knowledge.db :27 / frontier/search_embeddings.json local_search_rag.py:52) — কিন্তু governed knowledge_base টেবিলে **শূন্য প্রোডাকশন-লেখক**; ৫-রেকর্ড manifest (data/supremeai_long_term_knowledge_v1.json) ছাড়া বই নেই"
  - "আমদানি-মেশিন-জীবন্ত-নয়: import_knowledge_base.py (৩০৬ লাইন — content_hash নির্ধারিত-অভিন্নতা L62–68, approved-সুরক্ষিত upsert :267, ১৮০-দিন review_after, snapshot-rollback :94–125+run_rollback :167–213, --validate-only) ও ingest_knowledge.py (৪৮৫ লাইন — pgvector DDL, HashEmbedder-সৎ-লেবেল :79–90, --dry-run/--approve/--deactivate-stale :311–320) — **দুটিই চমৎকার, দুটিই কখনো চলেনি** (শূন্য CI/cron কলার); এবং বাস্তব-ডেটা coldstart JSON-এর ফরম্যাট {meta,categories} — দুই importer-ই {records}/{batch,records} চায় → **অ্যাডাপ্টার ছাড়া বই ঢোকাই অসম্ভব**"
  - "জাল-সারফেস: /knowledge/seed গণনা-করে 'seeded: N success' ফেরত দেয় — **শূন্য persistence** (knowledge.py:98–117); /knowledge/search জ্ঞান-স্টোর নয় — **skill-manifests-এর ওপর substring** (knowledge.py:74–95); embedding-মাত্রা-মিথ্যা — skill চায় 1536 (core_knowledge_qa.py:35), embeddings.py:133–137 নীরবে 384 দেয়, RPC vector(1536) (supabase_client.py:516) → semantic search গণিতগতভাবে অসম্ভব, ilike-ফলব্যাক-নির্ভর; mission-control knowledge-graph.tsx:326 'Supabase/pgvector + Qdrant' দাবি — **Qdrant রেপোতে অস্তিত্বহীন**; :183–204 `memory_*` tower-tool-নাম বনাম mcp_server.py:509/514/562 unprefixed নিবন্ধন → প্যানেল চির-'empty'"
  - "বাংলা-সম্পদ-বন্দি: knowledge/coldstart_knowledge_seed_comprehensive.json — ১৩২ এন্ট্রি, **১২১-ই বাংলা** (U+0980–09FF), ঘোষিত-উদ্দেশ্য 'outage-কালীন cold-start resilience' — কিন্তু কোনো importer-ই এর ফরম্যাট পড়ে না; goldset.json — ৯১ retrieval-eval প্রশ্ন (৭৮ en/৫ bn/২ hi/২ es/২ ar/২ zh) expected_ids-সহ, অথচ tier*-corpus অনুপস্থিত → eval-harness-অ-চালু; sparse_bm25.py:24 একমাত্র বাংলা-সচেতন tokenizer ([^\\w\\s\\u0980–09FF]-preserve); ChromaDBStore _tokenize (chromadb_store.py:83–85) ASCII-নিম্নকরণ, NFC-শূন্য; apps/docs-এ bangla-guide.md + elai-code-extension-reference-bn.md — sidebars.ts কেবল intro দেখায় → **উভয় বাংলা-গাইড built-site-এ অদৃশ্য**"
  - "এক-জীবন্ত-লুপ: /deep_research লেখে ChromaDBStore-এ (deep_research.py:292–311,409) → /deep_research slash-command পড়ে (slash_commands.py:239–246) — অঙ্গের একমাত্র সম্পূর্ণ লেখা-পড়া-চক্র; তবে scraped-docs বিহীন tenant_id → cross-user-global (register §9-ঝুঁকি); chat.py:277–300 outage-ফলব্যাক ai_memory recall ব্যবহার করে — governed KB chat-পথে **অনুপস্থিত** (এবং 500-এও)"
  - "চাংকিং-অনুপস্থিতি: memory/rag_pipeline.py:15–26 chunk_text(500 words, overlap 100) whitespace-split — token-বাজেট/সেমান্টিক-সীমানা/config-চালিত-নীতি নেই; knowledge_base_indexer.py কোনো চাংকিংই করে না (পুরো মডিউল = এক doc, L58–70); Docusaurus CI-নির্মিত (maintenance.yml:348–356) কিন্তু root mkdocs.yml (৩৮২ md docs/) কোনো workflow-ই নির্মাণ করে না"
  - "টেস্ট-সত্য: ৯৫৩ লাইন/৭৬ টেস্ট/৮ ফাইল — learning-loop টেস্ট প্রকৃত e2e (TestClient→SQLite→stats), import-rollback টেস্ট প্রকৃত বিশুদ্ধ-লজিক (FakeCursor); কিন্তু test_knowledge_qa.py ও test_core_knowledge_qa.py mock-theater — **প্রতিনিধি retrieval-পথ পরীক্ষা শূন্য**; 500-বাগ সব-টেস্ট পাস করেই ঘুমাচ্ছে"
  - "৩য়-পক্ষ গবেষণা-ভিত্তি (2026-02-17 ওয়েব-প্রমাণ): idempotent content-hash ingestion শিল্প-মান (daily.dev 2026-08-23; firecrawl 2026-03-16); চাংকিং-গবেষণা — NVIDIA 2025-06-18 page-level-সর্বোচ্চ-কার্যকর, arXiv 2026-03-07 অবচাংকিং semantic-coherence নষ্ট করে, firecrawl 2026-02-24 Chroma-গবেষণা 400-token-এ 85–90% recall বনাম semantic 91–92% (২–৩% বাড়ির ব্যয়-বহুগুণ); freshness — atlan 2026-04-14 staleness+embedding-lag-ফেইলমোড, tianpan 2026-04-20 stale-retrieval-rate, kapa.ai 2026-07-02 sync-প্যাটার্ন, Databricks staleness-gap-মনিটরিং; golden-set CI — superlinked 2026-04-07, circleci 2025-10-06, qaskills 2026-07-01 CI-wiring; pgvector-মতবাদ — encore 2026-03-08 'documents+embeddings same DB', dev.to 2026-03-04 $0.33/GB, zenvanriel 2026-01-24 moderate-scale-সস্তা; docs-as-code — gitdoc 2026-06-09, oneuptime 2026-01-25, sourcegraph 2026-06-29, Fern 2026-01-17 link-lint; বাংলা-NLP — arXiv 2024-12-16 tokenization-মূল-চ্যালেঞ্জ, BanglaEmbed arXiv 2024-11-22, Vyakyarth 2025-02-27 Indic-মাল্টিলিঙ্গুয়াল"
implements:
  - "retrieval-proof মতবাদ (অস্বাভাবিক-চিন্তার কেন্দ্র): **'যা উদ্ধার করা যায় না, তা জানা নেই'** — জ্ঞানভাণ্ডারের মূল্য তার ক্যাটালগ-মেশিনারির পরিশীলনে নয়; মাপকাঠি একটাই — কোনো প্রশ্ন কি প্রমাণিতভাবে (eval-সহ) fresh বই উদ্ধার করতে পারে? মেশিনারি অক্ষত থেকে শূন্য-তাক লাইব্রেরি সমাজ-দৃষ্টিতে 'জ্ঞান-সক্ষম' দাবি করতে পারে — এটাই এই অঙ্গের ERR-F02-স্বাক্ষর; প্রতিটি P-move তাই retrieval-proof-এ বন্ধ (goldset recall@k gate)"
  - "বই-আগে-মেশিন-পরে (P-C অগ্রাধিকার): দুই পরিণত আমদানি-মেশিন অচল কারণ কার্গো-ফরম্যাট-অমিল — ছোট adapter (coldstart {meta,categories}→importer-ফরম্যাট) = মেশিন-প্রতিস্থাপন নয়, মালপত্র-সংযোগ; প্রথম বই-কনভয়ই অঙ্গকে জীবন্ত করে"
  - "এক-দরজা-আট-তাক (P-B, ERR-F02-খেলা): KnowledgeFacade-ই একমাত্র পাঠ-দরজা; ৮-store-এর ১ canonical ঘোষণা (Postgres long-term + knowledge_chunks একীকরণ-সিদ্ধান্ত founder-gated); বাকি তাক freeze/shim/delete-candidate — Module 01/09 playbook-এর গ্রাহক"
  - "সততা-সারফেস (P-E/P-H): seed persist-or-501; search বাস্তব-স্টোর+tenant-filter (register §9/§10 মতবাদ); Qdrant-দাবি-অপসারণ (infra-দাবি-বিহীন-infra = জাল-সারফেস-শ্রেণি); প্রতিটি endpoint হয় বাস্তব-স্টোরে ছোঁয়, নয় সৎ 501/empty"
  - "বাংলা-প্রথম-রিট্রিভাল (P-G, Module 19-সম্প্রসারণ): ১২১ বাংলা-এন্ট্রি ingest; NFC+দাঁড়ি-সচেতন normalize; goldset-৫-bn-প্রশ্ন CI-gate; বাংলা-গাইড sidebar-নিবন্ধন — ভাষা-কর-মতবাদের retrieval-সমতুল্য"
  - "rails-as-data + zero-cost-বাঁধা: চাংক-নীতি/freshness-সীমা/role-permission manifest-ডেটা-ফাইলে (কোনো ইন-কোড hardcode নয়); RAGAS/semantic-chunking/নতুন vector-DB/model-swap সুস্পষ্ট প্রত্যাখ্যান-নথিভুক্ত"
supersedes: []
superseded_by: []
source_of_truth: false  # proposed বিশ্লেষণ-নীলনকশা; সম্পাদন শুধুই ফাউন্ডার অনুমোদনের পরে (Gate 2); প্রতিটি Phase আলাদা ছোট execution প্ল্যান
last_verified: "2026-09-17 (branch crown-jewel-v2 base 1b698ee6: knowledge_qa.py পূর্ণপাঠ+runtime-repro (AttributeError repro), knowledge.py/import_knowledge_base.py/ingest_knowledge.py/sync_knowledge.py পূর্ণপাঠ, ৮-store grep-গণনা, coldstart/goldset JSON পার্স (132/91), embeddings.py-মাত্রা-পাঠ, frontend KnowledgePage/knowledge-graph/apps-docs চুক্তি, plans-overlap grep; ৩য়-পক্ষ দাবি 2026-02-17 ওয়েব-সার্চে তারিখ-চিহ্নিত)"
code_evidence:
  - "শূন্য-তাক-লাইব্রেরি — গ্রন্থাগারিক (facade), ক্যাটালগ-প্রেস (importer×২), রোলব্যাক-রেজিস্টার (snapshot) সব আছে; তাকে বই পৌঁছায়নি (শূন্য প্রোডাকশন-লেখক, ফরম্যাট-অমিল), আর পাঠকের দরজা তালাবদ্ধ নয় — ভাঙা (প্রতি-কলে 500)"
  - "নাম-বনাম-আচরণ — core/knowledge_base.py নামে জ্ঞানভাণ্ডার, বাস্তবে memory_vault প্রম্পট-ক্যাশ (L7–13); knowledge-graph.tsx 'Qdrant' দাবি, বাস্তবে অস্তিত্বহীন — দুই-শ্রেণির V6-স্বাক্ষর (মিথ্যা-নাম + মিথ্যা-infra-দাবি)"
  - "মৃত-কোড-স্থানান্তর-ব্যাগ — knowledge_qa.py-র governance-ব্লক সম্ভবত এক __init__-রিফ্যাক্টরে return-এর পরে পড়ে গেছে; এক-টেস্টও ধরতে পারেনি কারণ টেস্ট কেবল ধ্রুবক-assert — টেস্ট-থিয়েটারের ব্যয় এখানেই দৃশ্যমান"
  - "বাংলা-কর্পাস-সমৃদ্ধি-বনাম-রিট্রিভাল-দারিদ্র্য — ১২১/১৩২ বাংলা-এন্ট্রি বিশ্বের-সেরা coldstart-সম্পদ, অথচ একটি importer-ও ফরম্যাট পড়ে না; goldset-বাংলা-প্রশ্ন হার্নেস-বিহীন — সম্পদ-বনাম-সক্ষমতা-ব্যবধান এই-অঙ্গের মূল-লাভ-ক্ষেত্র"
  - "মাত্রা-মিথ্যার গাণিতিক-অনিবার্যতা — 384-ভেক্টর → vector(1536) RPC: নীরব-ডাউনগ্রেড (embeddings.py:133–137) পুরো semantic-স্তরকে গণিতগতভাবে অচল করে; ilike-ফলব্যাক-নির্ভরতা = 'semantic search' দাবির জাল-সত্য"
test_evidence: "বিদ্যমান: ৯৫৩ লাইন/৭৬ টেস্ট — learning-loop e2e (TestClient→store→stats) ও import-rollback (FakeCursor) প্রকৃত; knowledge_qa/core_knowledge_qa mock-theater (কেবল ধ্রুবক/MagicMock); প্রস্তাব-টেস্ট: answer()-e2e (FakeChroma, tenant-scoped) — 500-বাগ-রোধ-রেগ্রেশন, seed-persist-or-501, search-বাস্তব-স্টোর+tenant-filter, adapter ফরম্যাট-রাউন্ডট্রিপ (coldstart→importer→N-rows), NFC/danda-normalize, goldset recall@k gate (5 bn সহ), facade-এক-দরজা-assert, মাত্রা-সামঞ্জস্য (384↔vector স্তম্ভ-মিল)"
acceptance_criteria:
  - "প্রতিটি প্রস্তাব চার-স্তম্ভ-দর্শন-সংগত (Part 5.5); কোনো নতুন নির্ভরতা/ভেন্ডর/DB নয় (RAGAS/Qdrant/semantic-chunking/model-swap প্রত্যাখ্যান-নথিভুক্ত)"
  - "/api/knowledge/ask ও /ask-scribe প্রতি-কলে-500 অবসান — answer() e2e-টেস্ট-প্রমাণিত; জাল-'seeded' ও ভুল-কর্পাস-সার্চ অবশিষ্ট শূন্য"
  - "প্রথম বই-কনভয়: coldstart-১৩২-এন্ট্রি importer-ফরম্যাটে adapter-মাধ্যমে validate-only-প্রমাণিত; goldset recall@k CI-gate (বাংলা-৫-প্রশ্নসহ) সবুজ"
  - "সব নীতি (চাংক-আকার/freshness-দিন/role-permission) ডেটা-ফাইল+env; জাল-infra-দাবি (Qdrant) ও অদৃশ্য-বাংলা-গাইড অবশিষ্ট শূন্য; লিন্ট 0 error / 0 warning (সিরিজ)"
---

# Module 23 — Knowledge-Base & Docs Organ Power-Up (জ্ঞানভাণ্ডার-অঙ্গ)

## বাংলা সারসংক্ষেপ

জ্ঞানভাণ্ডার-অঙ্গ সিরিজের সবচেয়ে বেদনাদায়ক আয়না: **"শূন্য-তাক লাইব্রেরি"** — গ্রন্থাগারিক (KnowledgeFacade), দুই পরিণত আমদানি-মেশিন (import_knowledge_base.py: rollback+validate-only সহ; ingest_knowledge.py: dry-run+HITL-approve+stale-archive সহ), রোলব্যাক-রেজিস্টার — সব আছে; কিন্তু **তাকে কোনো বই পৌঁছায়নি** (governed টেবিলে শূন্য প্রোডাকশন-লেখক; বাস্তব-কর্পাসের ফরম্যাট কোনো মেশিনই পড়ে না), আর **পাঠকের দরজা ভাঙা** — `POST /api/knowledge/ask` ও `/ask-scribe` প্রতিটি কলে 500 (মৃত-কোড governance-ব্লক, runtime-repro-প্রমাণিত)। সাথে জাল-সারফেস-স্যুইট: 'seeded: N' বিনা-persistence-এ, skill-manifest-সার্চকে জ্ঞান-সার্চ বলে, 1536-vs-384 মাত্রা-মিথ্যা semantic-স্তরকে গণিতগতভাবে অচল করে, 'Qdrant' নামে অস্তিত্বহীন infra-দাবি। সবচেয়ে মূল্যবান সম্পদ — **১২১/১৩২ বাংলা coldstart-এন্ট্রি ও ৫ বাংলা eval-প্রশ্ন — সম্পূর্ণ বন্দি**। মতবাদ: **retrieval-proof — 'যা উদ্ধার করা যায় না, তা জানা নেই'**; প্রতিটি সংশোধন একটি eval-প্রমাণিত বই-কনভয়ে বন্ধ, শূন্য নতুন অবকাঠামো।

## Part 1 — Third-Party & Competitor Intelligence (৩য়-পক্ষ বুদ্ধিমত্তা, তারিখ-চিহ্নিত ওয়েব-প্রমাণ)

### ১.১ গ্রহণযোগ্য প্যাটার্ন (গ্রহণ — প্যাটার্ন হিসেবে, নির্ভরতা নয়)

| উৎস (তারিখ) | ধারণা | আমাদের অঙ্গে প্রয়োগ | চার-স্তম্ভ-বিচার |
|---|---|---|---|
| **idempotent content-hash ingestion** (daily.dev 2026-08-23; firecrawl 2026-03-16) | duplicate-upload/versioning/idempotency/content-hash-skip = প্রোডাকশন-ingest-মান | আমাদের import_knowledge_base.py ইতোমধ্যে এই-মানে (content_hash :62–68, approved-সুরক্ষা :267) — শিল্প-সংগতি নিশ্চিত; adapter-পরে সেই-রেলেই বই-কনভয় | নতুন-কিছু-নয় ✓ |
| **চাংকিং-গবেষণা** (NVIDIA 2025-06-18 page-level-সর্বোচ্চ; arXiv 2026-03-07; firecrawl 2026-02-24 Chroma 400-token 85–90%) | সরল-নীতিমালা-চালিত চাংকিংই বাস্তবে পর্যাপ্ত; token-বাজেট-সচেতনতা জরুরি | P-C-সহায়ক: rag_pipeline.py-র whitespace-500-কে config-চালিত token-বাজেটে (rails-as-data); semantic-chunking প্রত্যাখ্যান (১.২) | stdlib/config ✓ |
| **freshness-governance** (atlan 2026-04-14 staleness+embedding-lag; tianpan 2026-04-20 stale-retrieval-rate; kapa.ai 2026-07-02; Databricks) | staleness পরিমাপযোগ্য ফেইলমোড; sync-প্যাটার্ন শিল্প-প্রতিষ্ঠিত | P-D: review_after (import-এ ইতোমধ্যে-স্ট্যাম্পড) sweeper-রিপোর্ট + stale-rate-মেট্রিক — নতুন টেবিল নয়, বিদ্যমান কলামের পাঠক | শূন্য-নতুন-স্টোর ✓ |
| **golden-set CI-eval** (superlinked 2026-04-07; circleci 2025-10-06; qaskills 2026-07-01) | retrieval-পাইপলাইন golden-dataset ছাড়া অদৃশ্যভাবে ক্ষয়ে যায়; CI-তে wire করা মান | P-G: নিজস্ব goldset.json (৯১ প্রশ্ন) + validate_retrieval.py (১৯৭ লাইন, বিদ্যমান!) — RAGAS-লাইব্রেরি ছাড়াই recall@k gate | নির্ভরতা-প্রত্যাখ্যান ✓ |
| **pgvector-এক-DB-মতবাদ** (encore 2026-03-08 'docs+embeddings same DB'; dev.to 2026-03-04 $0.33/GB; zenvanriel 2026-01-24) | moderate-scale-এ বিদ্যমান-Postgres-ই সস্তা-সরল | P-B-ভিত্তি: canonical store = বিদ্যমান Postgres (long-term+chunks একীকরণ-প্রস্তাব); Qdrant/Pinecone স্থায়ী-প্রত্যাখ্যান; knowledge-graph-এর জাল-Qdrant-দাবি অপসারণীয় | zero-cost ✓ |
| **docs-as-code** (gitdoc 2026-06-09; oneuptime 2026-01-25; sourcegraph 2026-06-29; Fern 2026-01-17 link-lint) | ডকস রেপোতে+একই CI; ভাঙা-লিংক lint | P-F: knowledge→markdown exporter (codebase_exporter-প্যাটার্ন-পুনঃব্যবহার) → Docusaurus; sidebar-বাংলা-গাইড-নিবন্ধন | বিদ্যমান-টুলচেইন ✓ |
| **বাংলা-NLP-সত্য** (arXiv 2024-12-16 tokenization-চ্যালেঞ্জ; BanglaEmbed 2024-11-22; Vyakyarth 2025-02-27) | বাংলা tokenizer/normalization মূল-গুণতা-লিভার; বিশেষায়িত embedding-মডেল বিদ্যমান | P-G: NFC+দাঁড়ি-সচেতন normalize (BM25-এর Bengali-ব্লক-রেজেক্স :24 ইতোমধ্যে-সঠিক — ChromaDBStore-tokenizerে সম্প্রসারণ); model-swap প্রত্যাখ্যান (১.২) | stdlib-unicodedata ✓ |

### ১.২ প্রত্যাখৃত বিকল্প (কারণ-সহ)

| বিকল্প | কেন আকর্ষণীয় | কেন প্রত্যাখ্যান (চার-স্তম্ভ) |
|---|---|---|
| **semantic chunking** (Pinecone 2025-06-28; agenta 2025-08-15) | 91–92% vs 85–90% recall (Chroma-গবেষণা) | ২–৩% লাভের বিনিময়ে embedding-ব্যয়-বহুগুণ + জটিলতা; NVIDIA page-level-প্রমাণ সরল-নীতিকেই সমর্থন; lightweight-লঙ্ঘন |
| **RAGAS ফ্রেমওয়ার্ক** (docs.ragas.io; circleci 2025-10-06) | শিল্প-মান RAG-মেট্রিক | LLM-judge-ব্যয় + নতুন নির্ভরতা; আমাদের goldset+validate_retrieval.py-ই deterministic recall@k দেয় — নিজস্ব-হার্নেস-মতবাদ (truth-mirror-সংগত) |
| **BanglaEmbed/Vyakyarth model-swap** (arXiv 2024-11-22; 2025-02-27) | বাংলা-বিশেষায়িত গুণতা | মডেল-হোস্টিং-ব্যয় + 132-এন্ট্রি-স্কেলে অ-প্রয়োজনীয়; প্রথমে lexical-preserving+normalize-ই ফ্রি-লাভ; ভবিষ্যৎ-পুনর্বিবেচনা-নোট |
| **Qdrant/Pinecone** (firecrawl 2026-08-03-তুলনা) | managed vector-DB | নতুন অবকাঠামো+ব্যয়; pgvector-ই যথেষ্ট (encore/dev.to-গবেষণা); **বর্তমানে রেপোতে 'Qdrant' দাবিই জাল** — প্রথমে সত্য-অপসারণ |
| **ingestion-ভেন্ডর** (unstructured.io 2026-02-26; Firecrawl-pipeline) | পরিণত পাইপলাইন | বিদ্যমান importer-দ্বয় ইতোমধ্যে শিল্প-প্যাটার্ন-সম্পূর্ণ; ভেন্ডর-যোগ = নিজস্ব-রেল-অবহেলা; zero-cost-লঙ্ঘন |
| **auto-curation cron** (design/knowledge_acquisition_plan.md — Firestore + gap-analysis-cron) | 'recursive acquisition' দৃষ্টিসম্পন্ন | ৯ম সমান্তরাল-স্টোর সৃষ্টি (Firestore); অ-সংযুক্ত প্রতিশ্রুতি; store-first+HITL-approve মতবাদের বিপরীত — reconcile-প্রস্তাব P-B-তে |

### ১.৩ প্রতিযোগী-তুলনার অন্তর্দৃষ্টি (ভিন্নভাবে ভাবা)

শিল্প RAG-টিউটোরিয়াল মেশিনারি দিয়ে শুরু করে ডেটা দিয়ে শেষ করে; আমাদের অবস্থা বিপরীত — **মেশিনারি পরিণত (rollback, HITL-approve, stale-archive পর্যন্ত), ডেটা-পথ অজাত**। তাই এখানে 'RAG-নির্মাণ' নয়, **'কার্গো-সংযোগ + দরজা-মেরামত'** — এবং প্রতিটি দাবির পেছনে একটি eval। মূল-অন্তর্দৃষ্টি: একটি জ্ঞানভাণ্ডারের সৎ-অবস্থা তিনটি প্রশ্নে মাপা যায় — (১) দরজা খোলা কি? (answer() প্রতি-কলে-সফল), (২) তাকে বই আছে কি? (প্রোডাকশন-লেখক+import-প্রমাণ), (৩) প্রশ্ন কি বই পায়? (goldset recall@k)। এই-ত্রয়ীই retrieval-proof মতবাদের অপারেশনাল-রূপ — এবং আজ তিনটিরই উত্তর 'না'।

## Part 1.5 — Gate 0 Reconciliation

| পূর্ববর্তী নথি | সম্পর্ক | সিদ্ধান্ত |
|---|---|---|
| `docs/audits/SUPREMEAI_CANONICAL_DEFECT_AND_FAILURE_REGISTER.md` — ERR-F02 (L824), ERR-H05 (§4.5 — FIXED PR #397), §7 RAG indirect prompt-injection (L78–81), §9 cross-tenant leakage (L88–91), §10 retrieval-auth bypass (L93–96), L765 ask-scribe-সন্দেহ-তালিকা | এই-অঙ্গ F02-এর নিজস্ব-প্রজন্ম + §7/§9/§10-এর প্রয়োগ-ক্ষেত্র | P-E tenant+namespace-filter বাধ্যতামূলক; P-A answer()-e2e রেজিস্টার-আপডেট-প্রস্তাব |
| `docs/plans/M3_MEMORY_STORE_CONSOLIDATION_DECISION_TABLE.md:35,47` — chromadb_store 'knowledge/episodic vector side' **KEEP** | chromadb-র ভূমিকা Module 01-সিদ্ধান্তে সংরক্ষিত | P-B ChromaDB-কে freeze (অপসারণ নয়) — M3-সিদ্ধান্ত-সম্মান; canonical-প্রশ্নে founder-gated একীকরণ-সিদ্ধান্ত-প্রস্তাব |
| `docs/plans/design/knowledge_acquisition_plan.md` (৪৮ লাইন — Firestore+auto-cron) | ওভারল্যাপিং-প্রতিশ্রুতি, ৯ম-স্টোর | ১.২-প্রত্যাখ্যান; reconcile-নোট P-B-তে (status আপডেট-প্রস্তাব founder-গেটে) |
| `docs/plans/phases/implementation_and_milestone_trackers.md:53` — sync_knowledge/pdf_to_sdk broken-import তালিকা | আংশিক-পুরাতন | sync_knowledge এখন import-পরিষ্কার (পাথ-ড্রিফটে নীরব-no-op :21–24); P-E-তে সৎ-বাস্তবায়ন-বা-অপসারণ-প্রস্তাব |
| MODULES_LIST.md:44–45,125–130 (tools/knowledge 🟢; git_knowledge_extractor/agent_knowledge_store dormant) | অবস্থা-রেজিস্টার | dormant-দ্বয়ের deletion-candidate অবস্থা Module 09-মতোই founder-gated বহাল |
| সিরিজ-ম্যাপ (README কিউ ১–২২) | এই-অঙ্গে কোনো পূর্ববর্তী মডিউল নেই | চক্র ২৩ = MODULE_23-স্লট খোলা — এক-মডিউল-এক-ডকুমেন্ট শৃঙ্খলা বহাল |

## Part 2 — Six-Field Analysis

### ২.১ কী আছে

- **কাঠামো (৪,৫৫১ প্রোডাকশন-লাইন / ৯৫৩ টেস্ট-লাইন)**: core-ফ্যামিলি (knowledge_facade 41L + knowledge_contract 38L + embeddings 215L + rag/hybrid_retriever 85L + sparse_bm25 115L + factual_verifier 289L); services/knowledge_qa.py 195L (tenant-scoped QA-র পূর্ণ-নকশা); routes 303L (knowledge 250L লাইভ-মাউন্টেড routers.py:254 is_critical + hybrid_search 53L :369); tools 1,487L; scripts 1,211L; skills/core_knowledge_qa.py 190L+manifest।
- **দুই পরিণত আমদানি-মেশিন**: import_knowledge_base.py — ১১-ফিল্ড-ভ্যালিডেশন, secret-scan, content_hash-নির্ধারিত-অভিন্নতা, approved-সুরক্ষিত upsert, ১৮০-দিন review_after, snapshot-rollback+run_rollback, --validate-only, exit-code-২; ingest_knowledge.py — pgvector DDL (ivfflat+GIN), ৬-ভাষা সমর্থন-কলাম, সৎ HashEmbedder-লেবেল, retry/backoff OpenAICompatibleEmbedder, --dry-run/--approve(HITL)/--deactivate-stale।
- **এক জীবন্ত লুপ**: /deep_research→ChromaDBStore→slash-command-পাঠ — অঙ্গের একমাত্র সম্পূর্ণ চক্র (তবে tenant-বিহীন)।
- **বাংলা-সম্পদ**: coldstart-১৩২-এন্ট্রি (১২১ বাংলা), goldset-৯১-প্রশ্ন (৫ বাংলা), sparse_bm25-এর বাংলা-সচেতন regex, ২টি বাংলা ডক-গাইড (sidebar-অদৃশ্য)।
- **সৎ-প্যাটার্ন-নমুনা**: skill-এর unconfigured→empty-not-fake (:56–61), QA-র 'no grounded context'-সৎ-উত্তর (:143–149), prompt-injection-গার্ড (:132–135), HashEmbedder-সৎ-স্ব-লেবেল — এই-চারটি প্যাটার্ন সংরক্ষণীয়।

### ২.২ কী নেই

- **দরজা**: knowledge_qa.py-র governance-ব্লক মৃত-স্থানে (property-return-পরবর্তী) → উভয় governed QA-route প্রতি-কলে 500 (repro-প্রমাণিত); রেগুলেশন-টেস্টও নেই যা ধরে।
- **বই**: governed knowledge_base-এ শূন্য প্রোডাকশন-লেখক; দুই importer-এর কোনো CI/cron-চালন নেই; বাস্তব-কর্পাস-ফরম্যাট-অমিল (adapter-বিহীন) → 'লাইব্রেরি খোলা কিন্তু জিরো বই'।
- **সততা**: /knowledge/seed জাল-success (শূন্য persistence); /knowledge/search ভুল-কর্পাস (skill-manifests); 1536-vs-384 নীরব-মাত্রা-মিথ্যা → semantic-স্তর গাণিতিকভাবে অসম্ভব; 'Qdrant' জাল-infra-দাবি; sync_knowledge পাথ-ড্রিফট-নীরব-no-op।
- **সংযোগ**: KnowledgePage.tsx অনাথ — GET-vs-POST (405 অবধারিত) + response-shape-অমিল + seed-জাল-endpoint-কল; mission-control tower-নাম-অমিল (`memory_*` বনাম unprefixed) → চির-empty প্যানেল; governed KB chat-পথে অনুপস্থিত (outage-ফলব্যাক ai_memory-নির্ভর)।
- **নবায়নযোগ্যতা**: review_after-স্ট্যাম্প আছে, **পাঠক নেই** (কোনো sweeper নেই); --deactivate-stale মেশিন আছে, চালক নেই; stale-rate-মেট্রিক নেই।
- **বাংলা-সক্ষমতা**: NFC-normalization শূন্য (Module 19-প্রমাণের retrieval-সমতুল্য); ChromaDBStore-tokenizer বাংলা-অ-সচেতন; goldset-বাংলা-হার্নেস-অ-চালু; বাংলা-গাইড built-site-এ অদৃশ্য।
- **রপ্তানি/ডকস**: knowledge→markdown exporter নেই; mkdocs.yml-এর কোনো CI-নির্মাণ নেই; Docusaurus sidebar 4/5 md লুকায়।
- **নীতি**: চাংক-আকার/freshness-সীমা/role-permission manifest-এর বাইরে hardcode (skill :113–117 manifest-সাবসেট — Admin-এর hr_policies হারায়); token-বাজেট-চাংকিং নেই; e2e retrieval-টেস্ট নেই।

### ২.৩ কী করতে হবে

আটটি P-move — প্রতিটি retrieval-proof-এ বন্ধ, শূন্য নতুন অবকাঠামো:

| কোড | প্রস্তাব | retrieval-proof |
|---|---|---|
| **P-A** | চুক্তি-সত্য: governance-ব্লক `__init__`-এ পুনরুত্থান (৩-লাইন); role_permissions manifest-as-source (skill-হার্ডকোড-অবসান); FakeChroma-সহ answer()-e2e-টেস্ট | /ask প্রতি-কলে-সফল-অথবা-সৎ-খালি; 500-রেগ্রেশন-টেস্ট সবুজ |
| **P-B** | এক-দরজা-আট-তাক: KnowledgeFacade একমাত্র পাঠ-দরজা; canonical-স্টোর-ঘোষণা (Postgres long-term+chunks একীকরণ-প্রস্তাব, founder-gated); ChromaDB-freeze-shim; agent_knowledge_store/git_knowledge_extractor deletion-candidate (Module 09-ধারাবাহিকতা) | facade-assert-টেস্ট; প্রতিটি অবশিষ্ট পাঠ-পথ facade-গ্রাহক |
| **P-C** | বই-কনভয়: coldstart→importer-ফরম্যাট adapter (ছোট স্ক্রিপ্ট); এক CI-job — `import --validate-only` + `ingest --dry-run` artifact; প্রথম ১৩২-এন্ট্রি validate-প্রমাণিত; --approve HITL ম্যানুয়াল-বহাল | validate-report-artifact সবুজ; N-rows round-trip-টেস্ট |
| **P-D** | নবায়নযোগ্যতা: review_after-sweeper-রিপোর্ট (endpoint/CI সাপ্তাহিক) + stale-rate-মেট্রিক; --deactivate-stale-পুনঃব্যবহার; নতুন টেবিল নয় | stale-count-রিপোর্ট লাইভ; মেট্রিক baseline-N-নথিভুক্ত |
| **P-E** | সততা-সার্চ: /knowledge/search → বাস্তব-স্টোর (tenant+namespace-filter বাধ্যতামূলক — register §9/§10); /knowledge/seed → persist-অথবা-501; sync_knowledge-সৎ-বাস্তবায়ন-অথবা-অপসারণ-প্রস্তাব | seed-এর ফেরত N = বাস্তব-সারি-গণনা; search-ফল বাস্তব-তাক-থেকে |
| **P-F** | রপ্তানি+ডকস: knowledge→markdown exporter (codebase_exporter-প্যাটার্ন); Docusaurus sidebar-সংশোধন (৪/৫ md প্রকাশ, বাংলা-গাইড-দ্বয়সহ); mkdocs বিষয়ে সিদ্ধান্ত-নোট (নির্মাণ-অথবা-অপসারণ-প্রস্তাব) | built-site-এ বাংলা-গাইড দৃশ্যমান; exporter-স্ন্যাপশট-টেস্ট |
| **P-G** | বাংলা-প্রথম-রিট্রিভাল: P-C-adapter-ই ১২১-বাংলা-এন্ট্রি ingest করে; NFC+দাঁড়ি-সচেতন normalize (unicodedata, stdlib) ChromaDBStore-tokenizerে; goldset-৫-bn-প্রশ্ন CI-gate (validate_retrieval.py); BM25-বাংলা-regex বহাল | recall@k gate সবুজ (en+bn); normalize-রাউন্ডট্রিপ-টেস্ট |
| **P-H** | সারফেস-সত্য: tower-নাম-সংশোধন (`read_graph`/`search_nodes`/`search_semantic`); 'Qdrant'-দাবি-অপসারণ (সৎ-ক্যাপশন); KnowledgePage mount-অথবা-delete + GET→POST + shape-মিল; প্রতিটি জীবন্ত-সারফেসে ১টি Playwright-CT | প্যানেল প্রকৃত-গ্রাফ দেখায় অথবা সৎ-খালি; CT-টেস্ট সবুজ |
| **P-I** | জিরো-বাইপাস এমবেডিং ও নলেজ আরএজি গেটওয়ে ইন্টিগ্রেশন: কোনো এমবেডার বা আরএজি কুয়েরি সরাসরি বাহ্যিক এপিআইতে বাইপাস করবে না; সেন্ট্রাল Gateway-র মাধ্যমে `InferenceContext(task_type='knowledge_embedding')` সহকারে রুট হবে এবং ভেক্টর অনুসন্ধানে কঠোর টেন্যান্ট আইসোলেশন প্রযোজ্য হবে | গেটওয়ে অডিট লগে এমবেডিং টোকেন ট্র্যাকিং দৃশ্যমান; ক্রস-টেন্যান্ট লিক শূন্য |

### ২.৪ কীভাবে করব

ক্রম-শৃঙ্খলা (নির্ভরতা-ভিত্তিক, প্রতিটি ছোট founder-reviewable execution-প্ল্যানে): **P-A → P-C → P-G → P-E → P-D → P-B → P-F → P-H → P-I**। P-A প্রথম (৩-লাইন + টেস্ট — দরজা খোলে); P-C adapter লেখে (বই-পথ খোলে; NVIDIA/arXiv-চাংকিং-গবেষণা অনুসারে config-চালিত token-বাজেট-নীতি rag_pipeline-এ, ডিফল্ট অপরিবর্তিত-আচরণ); P-G normalization+eval-gate (বাংলা-প্রমাণ); P-E/P-D সততা+নবায়নযোগ্যতা (register-মতবাদ-প্রয়োগ); P-B কনসলিডেশন (founder-gated সিদ্ধান্ত-পয়েন্টসহ); P-F/P-H সারফেস; P-I গেটওয়ে বাইন্ডিং ও টেন্যান্ট আইসোলেশন। সব নীতি ডেটা-ফাইলে (knowledge_policy.json প্রস্তাব — চাংক/ফ্রেশনেস/role এক ফাইলে, Module 15 P-B-প্রেসিডেন্ট); কোনো নতুন নির্ভরতা/ভেন্ডর/DB নয়; সব টেস্ট নিজস্ব-harness (RAGAS-প্রত্যাখ্যান)।

### ২.৫ বেনিফিট

- **প্রতিশ্রুতি-বাস্তবায়ন**: 'knowledge base' ব্র্যান্ড-দাবি প্রথমবার retrieval-proof হয় — দরজা+বই+eval ত্রয়ী সবুজ; আউটেজ-কালীন coldstart-রেজিলিয়েন্স (নিজ-ঘোষিত উদ্দেশ্য) প্রকৃত-কার্যকর।
- **জিরো-বাইপাস এমবেডিং ও টেন্যান্ট নিরাপত্তা**: নলেজ বেসের প্রতিটি ভেক্টর রূপান্তর সেন্ট্রাল গেটওয়ে অডিটের অন্তর্ভুক্ত এবং কঠোর মাল্টি-টেন্যান্ট সুরক্ষিত।
- **বাংলা-প্রথম**: ১২১ বাংলা-এন্ট্রি প্রথমবার উদ্ধারযোগ্য; ৫-বাংলা-প্রশ্নের স্থায়ী CI-গ্যারান্টি — ভাষা-কর-মতবাদের (Module 19) retrieval-সমতুল্য প্রথম-প্রমাণ।
- **জাল-সারফেস-শূন্য**: seed/search/metrics/Qdrant চতুর্পাশ্বিক সততা-সংশোধন — V6-doctrine-এর এই-অঙ্গ-ক্লিন-আপ।
- **সংখ্যা-সংগত**: শূন্য নতুন স্টোর/নির্ভরতা/ব্যয়; ৪,৫৫১-লাইনের বিদ্যমান সম্পদ প্রথমবার সম্পূর্ণ-কার্যকর (estimate: অঙ্গের কার্যকারিতা শূন্য-থেকে-পূর্ণ, কোড-বৃদ্ধি মাত্র adapter+normalize+exporter ≈ ৩০০–৪০০ লাইন)।
- **পরিমাপযোগ্য**: goldset recall@k + stale-rate = চক্র ২৪-এর Gate 5-পুনঃর‍্যাঙ্কের প্রথম retrieval-মেট্রিক-ইনপুট।

### ২.৬ ক্ষতি/ঝুঁকি

- **P-A-রিগ্রেশন**: governance-স্থানান্তর ভুল-সেমান্টিকস (manifest-missing ক্ষেত্রে) — প্রশমন: টেস্ট-প্রথম (500-রেগ্রেশন + খালি-manifest-পথ); rollback = এক-ফাইল git-revert।
- **P-B-কনসলিডেশন-ঝুঁকি**: canonical-ঘোষণা ভুল-হলে পাঠ-পথ-বিভ্রান্তি — প্রশমন: founder-gated সিদ্ধান্ত-টেবিল; freeze-shim-এ পুরাতন-পথ অ-ভাঙা; ChromaDB-র M3-KEEP-অবস্থা অ-লঙ্ঘিত।
- **P-C-ডেটা-ঝুঁকি**: ভুল ingest হলে তাক দূষিত — প্রশমন: প্রথম চালন সর্বদা --validate-only/--dry-run; approved-সুরক্ষা+snapshot-rollback importer-নিজস্ব; কোনো অটো-approve নয়।
- **P-G-ইউনিকোড-ঝুঁকি**: NFC-পুনর্গঠন বিদ্যমান-নথি-হ্যাশ-অমিল করতে পারে (content_hash-অসংগতি) — প্রশমন: normalize কেবল retrieval-পথে, ingest-হ্যাশে নয় (পুনঃingest-অনিবার্যতা-এড়াতে); রাউন্ডট্রিপ-টেস্ট।
- **P-E/P-H-সংযোগ-ঝুঁকি**: KnowledgePage-mount নতুন-বাগ-সারফেস খুলতে পারে — প্রশমন: shape-মিল-টেস্ট + সৎ-খালি-অবস্থা; delete-বিকল্প founder-গেটে।
- **CI-ব্যয়**: validate-only/dry-run নিঃশব্দ-সস্তা, কিন্তু ভবিষ্যৎ-বাস্তব-embed-run ব্যয়ী — প্রশমন: HITL-approve ম্যানুয়াল-বহাল; ব্যয়-নীতি knowledge_policy.json-এ লেবেলযুক্ত।
- **টেস্ট-ঋণ**: ৭৬-টেস্টের mock-theater-অংশ সংশোধন-পরে অপ্রচলিত হবে — প্রশমন: সংশোধন-প্রতি-টেস্ট-আপগ্রেড execution-প্ল্যানে বাধ্যতামূলক।

## Part 3 — Out of Scope

- Memory-অঙ্গ (Module 01) ও M3-consolidation-সিদ্ধান্ত-পুনর্লিখন — কেবল সংযোগ-সম্মান (chromadb-KEEP)।
- Context Engine (Module 07) token-বাজেট-মেশিনারি — কেবল নীতি-সংযোগ, বাস্তবায়ন নয়।
- Scout/knowledge_extractor (Module 08) ও factual_verifier-অভ্যন্তর — সীমানা-অ-অতিক্রম।
- mission-control tower-অভ্যন্তর (নাম-সংশোধন ছাড়া), mcp-control-plane TS-টুল-নিবন্ধন-অভ্যন্তর।
- RAGAS/নতুন embedding-মডেল/নতুন vector-DB/ingestion-ভেন্ডর — সবই ১.২-প্রত্যাখ্যান-নথিভুক্ত।
- real-time doc-sync-crawler (kapa.ai-প্যাটার্ন) — বর্তমান-স্কেলে অ-প্রয়োজনীয়; ভবিষ্যৎ-পুনর্বিবেচনা-নোট।
- tools/knowledge_squeezer (root tools/ কপি, dormant) — Module 09-ডিসপোজিশন-অপেক্ষমাণ।

## Part 4 — ৯-নিয়ম ও Constitution-সংগতি

| নিয়ম | প্রয়োগ |
|---|---|
| প্রমাণ-শৃঙ্খলা | প্রতিটি দাবি backtick-path+লাইন-রেফ; runtime-repro স্পষ্ট-লেবেল; ৩য়-পক্ষ দাবি তারিখ-চিহ্নিত |
| এক-মডিউল-এক-ডক | এই ডক কেবল knowledge-base/docs-অঙ্গ |
| extend-not-replace | importer/facade/goldset/validate_retrieval — সবই বিদ্যমান-সম্পদ-গ্রাহক |
| zero-cost | কোনো নতুন নির্ভরতা/ভেন্ডর/DB/মডেল নয়; CI = validate-only/dry-run |
| zero-hardcode | সব নীতি knowledge_policy.json+manifest; in-code সীমা অবশিষ্ট শূন্য (লক্ষ্য) |
| সততা-সারফেস | seed persist-or-501; জাল-Qdrant-অপসারণ; প্রতিটি সংখ্যা বাস্তব-গণনা |
| founder-gated ধ্বংসাত্মক কাজ | canonical-ঘোষণা, dormant-deletion, KnowledgePage-delete, mkdocs-সিদ্ধান্ত — সবই Gate 2-পরবর্তী |
| HITL-সংরক্ষণ | --approve ম্যানুয়াল-বহাল; কোনো অটো-ingest নয় |
| পরিমাপ-প্রথম | goldset recall@k + stale-rate baseline; Gate 5-চক্রে পুনঃপরিমাপ |

Constitution-টেবিল: §7 prompt-injection (QA-গার্ড বহাল+tenant-filter বাড়তি), §9/§10 (P-E প্রয়োগ), zero-fabrication (P-E/P-H), tenant-isolation (P-E/P-G বাধ্যতামূলক-ফিল্টার), Bengali-first (P-G) — সংঘাত-শূন্য।

## Part 5 — Verification & Rollback

- **Gate 4 (প্রস্তাব-সম্পূর্ণতা)**: উপরের টেস্ট-তালিকা প্রতিটি P-move-এর জন্য নাম-উল্লেখসহ; acceptance_criteria-চারটি পরিমাপযোগ্য।
- **Gate 5 (execution-পরে)**: 500-রেগ্রেশন-টেস্ট সবুজ; validate-report-artifact সবুজ; goldset recall@k (en+bn) বেসলাইন-রেকর্ডড; stale-report চালু; প্রতিটি জাল-সারফেস-পতাকা নেমেছে (grep-প্রমাণ)।
- **Gate 6 (regression-শৃঙ্খলা)**: বিদ্যমান ৭৬-টেস্ট পাস (mock-theater-আপগ্রেডসহ); learning-loop/import-rollback টেস্ট অ-ভাঙা; lint 0/0।
- **Rollback**: P-A/P-E/P-H = এক-ফাইল git-revert; P-C = importer-নিজস্ব snapshot-rollback (rollback_id) + --validate-only-পুনঃচালন; P-G = normalize-পতাকা-বিপরীত; P-B = freeze-shim-অপসারণ-বিপরীত (কোনো ডেটা-মাইগ্রেশন-ধ্বংস নেই)।
- **Baseline (measured, 2026-09-17)**: governed-QA সফল-কল-হার 0% (500); বই-সংখ্যা (governed) ৫; goldset-harness অ-চালু; বাংলা-দৃশ্যমান-গাইড ০/২ — সবই এই-ডকের পরিমাপ-ভিত্তি।

## Part 5.5 — দর্শন-সংগতি পাস (Philosophy Alignment Audit)

| স্তম্ভ | বিচার | সিদ্ধান্ত |
|---|---|---|
| zero cost | RAGAS/Qdrant/model-swap/ভেন্ডর প্রত্যাখৃত; validate-only/dry-run CI; stdlib unicodedata; নিজস্ব-harness | সংগত ✓ |
| lightweight | adapter ≈১৫০ লাইন; normalize কেবল retrieval-পথে; কোনো নতুন প্রসেস/লুপ নয় (sweeper = CI/ম্যানুয়াল, resident-লুপ নয়) | সংগত ✓ |
| fast-smooth | P-A-পরে /ask hot-path বাস্তব-কিন্তু-ছোট-কর্পাস; চাংক-নীতি config-ডিফল্ট-অপরিবর্তিত-আচরণ; কোনো বুট-লেটেন্সি-যোগ নয় | সংগত ✓ |
| zero-hardcode | role/চাংক/freshness সব ডেটা-ফাইল+env; skill-হার্ডকোড-সাবসেট-অবসান (P-A) | সংগত ✓ |
| সততা | seed-501, জাল-Qdrant-অপসারণ, সৎ-খালি-অবস্থা, সংখ্যা-বাস্তব-গণনা | সংগত ✓ |

অস্বাভাবিক-চিন্তা-নোট: শিল্প 'আরও ভালো RAG' বিক্রি করে; আমাদের লাভ-রেখা 'প্রথম সৎ RAG' — ভাঙা দরজা ঠিক করা ও প্রথম বই-কনভয় নামানো, মেশিনারি-উন্নতি নয়। ব্যয়-সর্বনিম্ন, প্রমাণ-সর্বোচ্চ।

## Part 6 — পরবর্তী মডিউল লাইনেজ

- **চক্র ২৪-প্রস্তাব (সিরিজ-ঘোষিত)**: Gate 5-পরিমাপ-ভিত্তিক কিউ-পুনঃর‍্যাঙ্ক + **প্রথম execution-চক্রের প্রস্তাব** — ফাউন্ডার-অনুমোদিত P-গুলোর মধ্যে সর্বোচ্চ-লাভ/সর্বনিম্ন-ঝুঁকি নির্বাচন (বিশ্লেষণ→সম্পাদন রূপান্তর-প্রস্তুতি); এই-অঙ্গের P-A (৩-লাইন+টেস্ট) ও P-C-adapter প্রার্থী-তালিকায় প্রবেশ করবে।
- প্রতিটি চক্র ৩য়-পক্ষ-গবেষণা-চুক্তি বহাল; এক-মডিউল-এক-ডকুমেন্ট শৃঙ্খলা অব্যাহত।
