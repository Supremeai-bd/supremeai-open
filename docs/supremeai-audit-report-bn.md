# SupremeAI — সম্পূর্ণ কোডবেস ও সার্ভিস নিরাপত্তা অডিট রিপোর্ট

**তারিখ:** ২০২৬-১০-২৩ (UTC ২০২৬-১০-২২ ১৮:১৭ – ১৮:৩০ উইন্ডো)
**পরিধি:** `supremeai-mcp-tower.onrender.com/mcp` (MCP Control Tower), ৭টি Render সার্ভিস, ৭টি GitHub রিপো, Supabase / Upstash Redis (৫-অ্যাকাউন্ট চেইন) / Cloudflare (৫-অ্যাকাউন্ট) / Infisical / Qdrant / Vercel / Firecrawl / Kaggle / Stripe / Telegram
**পদ্ধতি:** সম্পূর্ণ **read-only** — শুধু ডায়াগনস্টিক/পড়ার টুল ব্যবহৃত হয়েছে। কোনো deploy, restart, cache flush, token rotate, tenant/client পরিবর্তন, DB রাইট বা বাইরের সার্ভারে কোনো সংবেদনশীল ডেটা পাঠানো হয়নি। সব সিক্রেট/কী রিপোর্টে **মাস্কড** বা কেবল নাম হিসেবে উল্লেখ করা হয়েছে।

---

## ০. এক নজরে (Executive Summary)

| গুরুত্ব | সংখ্যা | মূল বিষয় |
|---|---|---|
| 🔴 সংকটপূর্ণ | ৮ | হার্ডকোডেড signing secret, স্পুফেবল auth bypass, খোলা URL-proxy, খোলা Gemini-রিলে, অথ-হীন গেস্টে প্রাইভেট রিপো/ইনফ্রা মেটাডেটা রিড |
| 🟠 উচ্চ | ৭ | admin fail-open, CORS `*`+credentials, vault key লিক, autoDeploy × `0.0.0.0/0` × লাল secret-scan, ভাঙা memory sidecar (২৪ টুল অকেজো) |
| 🟡 মধ্যম | ৮ | কী-এ মেয়াদোত্তীর্ণতা নেই, ৪৮-বিট HMAC truncation, অসামঞ্জস্য হেলথ-রিপোর্ট, ভাঙা MCP resources, CI ছাড়া রিপো |
| 🟢 নিম্ন | ৬ | প্রম্পট লগিং, ত্রুটিতে `err.message` ফাঁস, ৪-ডিজিট kill-switch PIN, লাইসেন্স অনুপস্থিতি |

**এখনই যা করা উচিত (শীর্ষ ৩):**
1. `service/keygen.py`-এর `DEFAULT_SIGNING_SECRET` সরিয়ে fail-closed করা ও সব জারিকৃত API key রোটেট করা (env না থাকলে রিপোর সিক্রেট দিয়েই key forge করা যায়)।
2. `service/app.py`-র হেডার/Origin-ভিত্তিক auth bypass (`X-Guest-Mode`, `vercel.app` Referer, `"guest"/"demo"` টোকেন) ও fail-open বন্ধ করা; পাশাপাশি `cloudflare-worker`-এর খোলা URL-proxy-তে auth+allowlist দেওয়া।
3. MCP টাওয়ারের **গেস্ট টুল-সারফেস সংকুচিত করা** (বর্তমানে অথ-হীন ক্লায়েন্ট প্রাইভেট রিপো পড়তে, রেন্ডার লগ/env-key তালিকা ও ইনফ্রা মেটাডেটা দেখতে পারছে)।

---

## ১. সিস্টেম ম্যাপ

### ১.১ সার্ভিস (৭টি Render + সহায়ক)

| সার্ভিস | রিপো (autoDeploy, main) | প্ল্যান/অবস্থা | উল্লেখযোগ্য |
|---|---|---|---|
| `supremeai-primary-node` (core-api) | supremeai-core | free, ১ ইনস্ট্যান্স, সিঙ্গাপুর | health `/health/live`, allowlist `0.0.0.0/0` |
| `supremeai-worker-node` (async) | supremeai-core | free | health `/health` |
| `supremeai-scraper-node` | supremeai-browser | free | Playwright স্ক্র্যাপার |
| `supremeai-mcp-tower` (Control Tower) | supremeai-open | free | এই অডিটের প্রধান অবজেক্ট |
| `supremeai-api` (Gateway Shield) | supremeai-api | free | **healthCheckPath সেট নেই** |
| `ecosystem-full`, `ecosystem-test-core-v2` | `paykaribazaronline/supremeai-testing` | free, ওরেগন | সেপ্টেম্বর থেকে আপডেট নেই — স্টেল |

সহায়ক: Supabase (Postgres+Auth), Upstash Redis ৫-অ্যাকাউন্ট রোটেশন চেইন, Cloudflare Edge ৫-অ্যাকাউন্ট, Infisical (সিক্রেট), Qdrant, Vercel, Firecrawl (৪ পুল), Kaggle (৬ কী), Stripe, Telegram অ্যালার্ট-বট।

### ১.২ কোডবেস (৭ রিপো)
- **supremeai-open** — MCP Control Tower (TypeScript): টুল রেজিস্ট্রি, RBAC/policy ইঞ্জিন, HITL, tenant/client, memory-sidecar প্রক্সি, bridge workflow
- **supremeai-core** — Python: Agent FSM, DAG planner (Kahn), Decision engine, Context synthesizer, `adaptive_engine/*`, stdio MCP client
- **supremeai-api** — দুটি প্যারালেল গেটওয়ে (`gateway/main.py`, `service/app.py`), `service/keygen.py`, `mcp/` (TS), command/agents/skills
- **supremeai-browser** — `ghost_tower/*` (Gemini-web রিলে), স্ক্র্যাপার, `cloudflare-worker/`
- **supremeai-studio** — ফ্রন্টএন্ড (auth store, RoleGuard, tokenStorage)
- **supremeai-vscode** — VS Code এক্সটেনশন + Tauri desktop
- **Supremeai-bd/supremeai** — monorepo (browser/ghost_tower ইত্যাদি) — উপরের কয়েকটি কোড এখানেও আছে (কোড-ডুপ্লিকেশন/সিঙ্ক ঝুঁকি)

---

## ২. MCP Control Tower অডিট (প্রধান ফোকাস)

**সার্ভার:** `supremeai-control-tower` v1.0.0, Streamable HTTP — **১১৪টি টুল**, ১২ resources, ২ prompts।

### ২.১ টুল-সারফেস নকশা
একই এন্ডপয়েন্টে মিশ্রিত: ডায়াগনস্টিক রিড (২০+), ধ্বংসমূলক অপস (`action_redis_flush`, `action_cloudflare_purge`, `action_render_deploy`), অ্যাডমিন (`tenant_*`, `client_*_token`, `policy_approve`), অটোনমি (`autonomy_kill_switch/enable`), লেখার সুবিধা (`supabase_insert/update`, `qdrant_upsert`, `memory_delete_*`) ও বাইরের কল (`remote_call`, `firecrawl_scrape`)।
**ফাইন্ডিং M-1 (মধ্যম):** রিড-অনলি ক্লায়েন্টের জন্য আলাদা strict subset ডিফল্ট নয় — নিরাপত্তা নির্ভর করছে প্রতিটি টুলের ভেতরের authz চেকের উপর (defense-in-depth দুর্বল)। `client_set_profile`-এ `readonly` প্রোফাইল আছে, কিন্তু গেস্ট অটো-রেজিস্ট্রেশনে তা প্রয়োগ হচ্ছে কি না প্রমাণ নেই।

### ২.২ অথ/অথরাইজেশন — যা ভালো, যা নয়
✅ **ভালো:** `tenant_list` → "Forbidden: only the global SupremeAI admin"; `client_list` → tenant admin token দাবি করে; RBAC-এ missing request-context fail-closed (admin নয়, viewer); stdio transport-এ admin context স্পষ্ট opt-in; `webhook_signature.ts` fail-closed + timing-safe; HITL অ্যাপ্রুভাল-লিংকে স্থায়ী admin key নয়, মেয়াদোত্তীর্ণ HMAC সিগনেচার (এটি সুন্দর একটি সিকিউরিটি ফিক্স)।

🔴 **ফাইন্ডিং M-2 (সংকটপূর্ণ) — অথ-হীন "guest" ক্লায়েন্টের বড় রিড-সারফেস:** নতুন যেকোনো ক্লায়েন্ট কোনো টোকেন ছাড়াই `tenant_default`-এ অটো-রেজিস্টার্ড হয়ে এবং সরাসরি পেয়ে যায়:
- প্রাইভেট রিপোর ফাইল পড়া (`github_read_file`, `github_repo_tree`, `github_code_search`) — supremeai-core-এর README/সোর্স পড়া সফল হয়েছে;
- Render সার্ভিস মেটাডেটা: সার্ভিস ID, dashboard URL, **SSH address**, ownerId, টিম ID (`render_list_services`);
- **env-ভেরিয়েবল KEY-নামের পূর্ণ তালিকা** (`render_get_env_var_keys`) — যেমন `MCP_SUPER_ADMIN_KEY`, `GITHUB_PAT_SUPREMEAIBD`, `CLOUDFLARE_*_GLOBAL_API_KEY`, `UPSTASH_*_TOKEN`, `INFISICAL_CLIENT_SECRET` (মান নয়, নাম — তবে আক্রমণকারীর জন্য পূর্ণ নকশা);
- অ্যাপ/বিল্ড লগ (`render_get_logs`), Stripe অ্যাকাউন্ট ID (`acct_****`), এজেন্ট-স্লট/ক্লায়েন্ট রেজিস্ট্রি।
পাশাপাশি ক্লায়েন্ট-আইডিতে কলারের **IP অংশ লেখা হচ্ছে** (`guest_generic_8_219_189_25`) — লগে IP প্রকাশ, GDPR-সদৃশ ঝুঁকি।

🟡 **ফাইন্ডিং M-3:** `policy_preview` — যা "execute করার আগে ঝুঁকি প্রিভিউ" নামে পরিচিত — আসলে `[Simulated Execution] An approval request (REQ-…) has been created and sent` বলে একটি অনুরোধ তৈরি করার দাবি করে; কিন্তু `policy_list_pending` খালি দেখায়। অর্থাৎ অথবা (ক) "read-only preview"-তে রাইট-সাইড-ইফেক্ট আছে, অথবা (খ) গভর্নেন্স অডিট-ট্রেইল অসঙ্গতিপূর্ণ — দুটোই সংশোধনযোগ্য ত্রুটি। (নোট: পরীক্ষায় pending-তালিকা খালি ছিল, তাই কোনো অনুমোদন-অনুরোধ সক্রিয় রয়ে যায়নি।)

🟡 **ফাইন্ডিং M-4 (কার্যকরী বাগ):** memory sidecar স্টার্ট হচ্ছে না — `memory_status`: `ready: false`, ৬বার চেষ্টা, কারণ `/backend/memory/mcp_server.py` নেই ও `SUPREMEAI_BACKEND_DIR` unset। ফলে **২৪টি `memory_*` টুল প্রকাশিত হয়েও অকেজো** (গ্রেসফুল ডিগ্রেডেশন ঠিক আছে, তবে টুল-সারফেসে মিথ্যা দাবি)। লগে এই ত্রুটি প্রতি ~৮ সেকেন্ডে পুনরাবৃত্ত হচ্ছে (লগ-স্প্যাম)।

🟡 **ফাইন্ডিং M-5 (MCP কন্ট্রাক্ট ভাঙা):** `resources/list`-এ `uri` ফিল্ডে বৈধ URI নেই (`server-manifest`, `docs-supabase`); `resources/read` এই `uri` দিয়ে গেলে `Invalid URL`, আর `name`-এর URI দিলে `not found` — অর্থাৎ **সব resources অপঠনযোগ্য**। এছাড়া `github_repo_tree.maxFiles` স্কিমায় সীমা নেই, রানটাইমে `≤50` চায়; `memory_*` টুলগুলোর inputSchema সম্পূর্ণ খালি (প্যারাম প্রয়োজন হওয়া সত্ত্বেও) — স্কিমা/রানটাইম অমিল।

🟢 **ফাইন্ডিং M-6 (নিম্ন):** MCP সেশন খুব দ্রুত মেয়াদোত্তীর্ণ হয় (~২ মিনিটের মধ্যে `session_not_found`); তবে এররটি তথ্যবহুল ও recoverable (`action: send-initialize`) — ক্লায়েন্ট অটো-রিকভারি সম্ভব।

### ২.৩ টাওয়ারের ভেতরের কোড (supremeai-open) — মিশ্র চিত্র
✅ সুন্দর দিক: `policy/masking.ts` — key-নাম নয়, **মানের আকৃতি** দেখে সিক্রেট মাস্ক (JWT, bcrypt/argon2, `redis://user:pass@`, উচ্চ-এন্ট্রপি টোকেন); `rate_limit.ts` — per-IP + per-(identity,tool) sliding window + payload validation + output truncation; `policy/approvals/signing.ts` — পুরনো `?token=<MCP_ADMIN_KEY>` লিংক সরিয়ে মেয়াদোত্তীর্ণ, সিঙ্গেল-পারপাস HMAC লিংক (দিকনির্দেশনা: ভালো অনুশীলন); `render.yaml`-এ issue-tracked ইনফ্রা ফিক্স (#506/#507/#707/#1441) ও pinned `uv` (supply-chain সচেতনতা)।
⚠️ দুর্বলতা: গেস্ট অটো-রেজিস্ট্রেশন + বড় ডিফল্ট রিড-সারফেস (M-2), এবং বহু-টেন্যান্ট "control tower" একক free-plan ইনস্ট্যান্সে (single point of failure)।

---

## ৩. ইনফ্রা / অপস অডিট

🔴 **ফাইন্ডিং I-1:** Telegram অ্যালার্ট-বট **অচল** (`system_health`: unreachable; `notify_telegram`: `fetch failed`) → সব ইনসিডেন্ট/পলিসি-অ্যালার্ট চ্যানেল বন্ধ; HITL অনুমোদন-লিংকও Telegram-এই যায় → গভর্নেন্স ফ্লো আংশিক ভাঙা।

🟠 **ফাইন্ডিং I-2 (ডিপ্লয় পস্টার):** সব সার্ভিসে `autoDeploy = commit to main` (PR-গেট ছাড়া), IP allowlist `0.0.0.0/0` ("everywhere"), free plan + একক ইনস্ট্যান্স (HA নেই), এবং supremeai-api-তে healthCheckPath ফাঁকা। অর্থাৎ main-এ যেকোনো পুশ সরাসরি প্রোডাকশনে, ব্যর্থ হলে স্বয়ংক্রিয় রোলব্যাক সিগন্যালও নেই।

🟡 **ফাইন্ডিং I-3 (অসামঞ্জস্য স্বাস্থ্য-রিপোর্ট):** `system_summary` "17/17 services available" দেখায়, কিন্তু `system_health` একই মুহূর্তে "16 healthy · 1 unreachable" (telegram) — ড্যাশবোর্ড ইচ্ছাকৃতভাবে সবুজ দেখালে অপারেটর বিভ্রান্ত হবেন।

🟡 **ফাইন্ডিং I-4 (Redis রোটেশন অবস্থা):** `redis_stats` বলছে active primary = `primary`, কিন্তু কয়েক সেকেন্ড পর `redis_ping` বলছে `primary` cooldown-এ (২০২৬-১১-০১ পর্যন্ত) ও active = `secondary` — রোটেশন-স্টেট রিপোর্টিং অস্থির/অসঙ্গতিপূর্ণ। ৫টি Upstash অ্যাকাউন্ট × ৫০০k কমান্ড কোটা (বর্তমান ব্যবহার প্রায় শূন্য)।

🟢 **স্বাভাবিক:** বাকি ১৬টি সার্ভিস সুস্থ (Render ৫, GitHub ৬, Supabase, Redis, Cloudflare worker, Infisical/Kaggle/Firecrawl/Vercel/Stripe/Qdrant চেক সবুজ)। `health_full_sweep`-এ ০টি ইনসিডেন্ট, কোনো পেন্ডিং পলিসি-অনুমোদন নেই।

---

## ৪. কোডবেস অডিট — মূল ফাইন্ডিংস

### ৪.১ supremeai-api + supremeai-browser (বিস্তারিত সাব-রিপোর্ট: `.openclaw/tmp/audit/api-browser.md`)

🔴 **C-1 হার্ডকোডেড signing secret → সম্পূর্ণ auth bypass** — `service/keygen.py:19`-এ `DEFAULT_SIGNING_SECRET = "supremeai_master_****_2026"` (মাস্কড) এবং `:22-27`-এ env-ফলব্যাক শেষে এই পাবলিক কনস্ট্যান্টে নেমে আসে। env না থাকলে রিপোতে থাকা সিক্রেট দিয়েই যে কেউ বৈধ `sk-supreme-…` key বানাতে পারে (`service/app.py:94-97` তা গ্রহণ করে)।

🔴 **C-2 খোলা URL-fetch প্রক্সি (SSRF/রিলে)** — `cloudflare-worker/src/index.js:15,33`: অথ-ছাড়া `?url=` দিলেই puppeteer সেটা লোড করে কন্টেন্ট ফেরত দেয়; কোনো allowlist/private-IP ব্লক নেই (Python পাথের SSRF গেট এখানে নেই)।

🔴 **C-3 স্পুফেবল হেডার-ভিত্তিক auth bypass** — `service/app.py:74-85`: `X-Guest-Mode: true`, Origin/Referer-এ `vercel.app`/`supremeai-studio`, বা টোকেন `guest/demo/public-guest` হলেই প্রমাণীকরণ পাস; `:86-91,112-113` env-এ কী না থাকলে fail-open। উপরে `:47-53` CORS `*` + `allow_credentials=True`।

🔴 **C-4 খোলা Gemini-web রিলে** — `ghost_bridge_server.py:78,95-96,365`: `/api/chat`, `/v1/chat/completions`, `/v1/generate`-এ কোনো auth নেই, `0.0.0.0` বাইন্ড + Render `0.0.0.0/0` → ইন্টারনেট-মুখী অথেন্টিকেশনবিহীন LLM-রিলে (abuse/খরচ/ToS ঝুঁকি)।

🟠 **উচ্চ:** `service/app.py:329-366` admin এন্ডপয়েন্ট fail-open (`if SUPERADMIN_KEY and …`); CORS wildcard দুই জায়গায়; `credential_vault.py:36-45` master key ciphertext-এর পাশে ফাইলে + তৈরির সময় stdout-এ প্রিন্ট; `autoDeploy × 0.0.0.0/0 × লাল secret-scan` সংমিশ্রণ।

🟡 **মধ্যম:** `service/keygen.py:40-42,68-70` HMAC সিগনেচার ১২ হেক্স (**৪৮-বিট**) truncation, কোনো expiry/revocation নেই (একবার জারি = চিরকাল বৈধ); `gateway/main.py:76-85` key ছাড়াই guest `chat` scope (ইচ্ছাকৃত ডিজাইন হলেও এক্সপোজার); SSRF-তে residual TOCTOU (IP pinning নেই, `security.py:14-20`-এ নথিভুক্ত); `sync_cookies_to_infisical.py` — ২৩৭+ ডিক্রিপ্টেড সেশন-কুকি (Gemini/ChatGPT/Grok/Perplexity) ক্লাউড ভল্টে, যেকোনো মাইক্রোসার্ভিস কুকি ছাড়াই লগইন রিস্টোর করতে পারে → **blast radius বড়** (Infisical client secret ফাঁস হলে সমস্ত AI-অ্যাকাউন্ট ফ্লিট হাতে)। আর `auto_login.py` স্বয়ংক্রিয় Google sign-in + TOTP — ToS/অ্যাকাউন্ট-নিষেধাজ্ঞা ঝুঁকি।

🟢 **নিম্ন:** `ghost_bridge_server.py:90` প্রম্পটের প্রথম ৮০ অক্ষর লগ (PII); `cf_worker.js:48-53` `err.message` রেসপন্সে; supremeai-api-তে লাইসেন্স নেই; Windows-স্টাইল পাথ (`credential_vault.py:25`)।

✅ **যা সত্যিই ভালো:** `security.py`-র দুই-স্তরের SSRF গেট + প্রতিটি redirect hop-এ পুনরায় যাচাই (`web_scraper.py:65-77`); `mcp/src/lib/webhook_signature.ts` fail-closed timing-safe HMAC; `mcp/src/lib/env.ts` strict env parsing (#2720 ফিক্স); `gateway/main.py` explicit CORS allowlist + key-redaction + offline pytest-বন্ধানী।

### ৪.২ supremeai-core + supremeai-open
- **core:** `AgentStateMachine` (অপরিবর্তনীয় transition audit trail), `DAGPlanner` (Kahn দিয়ে acyclicity যাচাই), `DecisionEngine` (role + scope/risk governance), `ContextSynthesizer` (৩-স্তরের token budget চুক্তি) — নকশা পরিষ্কার ও সুনির্দিষ্ট। `core_mcp_client` সাবপ্রসেস চালায় (`subprocess.Popen`, লিস্ট-কমান্ড, `shell=True` নেই) — কমান্ড কনফিগ-নির্ভর বলে ইনজেকশন ঝুঁকি কম।
- **open:** উপরে §২.৩ দেখুন।
- ⚠️ **কোড-ডুপ্লিকেশন:** `browser/ghost_tower/*` ও কিছু কনফিগ monorepo `Supremeai-bd/supremeai`-তেও আছে — একই কোড দুই জায়গায় হলে সিকিউরিটি ফিক্স এক জায়গায় হয়ে অন্যটায় থেকে যায়।

### ৪.৩ supremeai-studio + supremeai-vscode
- ✅ `src/services/tokenStorage.ts` — নিরাপত্তা অডিট FE-04 অনুযায়ী টোকেন এখন `sessionStorage` + মেমোরিতে, পুরনো `localStorage` টোকেন অটো-মাইগ্রেশন; ফাইলেই residual XSS ঝুঁকি স্বীকার করা আছে — সৎ ও ভালো অনুশীলন।
- 🟡 `src/auth/identity.ts:28` — এখনও `sessionStorage || localStorage` ফলব্যাক (ফিক্স অসম্পূর্ণ)।
- ✅ `RoleGuard.tsx` — স্পষ্ট লেখা আছে frontend guard শুধু UX, ব্যাকএন্ড RBAC-ই কর্তৃত্বপূর্ণ (সঠিক মানসিকতা)।
- 🟢 `chat_view.ts:175` `innerHTML` কেবল খালি করার জন্য (ব্যবহারকারীর কন্টেন্ট ইনজেক্ট হয় না — XSS প্রমাণ পাওয়া যায়নি); তবে ডিফল্ট গেটওয়ে URL `http://127.0.0.1:8080` (প্লেইন HTTP) — রিমোট URL সেট করলে টোকেন অপ্রমাণিত চ্যানেলে যেতে পারে।
- 🟡 VS Code এক্সটেনশন: emergency kill-switch-এ **৪-অঙ্কের PIN** যথেষ্ট ধরা হয় (`extension.ts:51-55`) — ফেডারেশন-ব্যাপী বন্ধ করার জন্য দুর্বল গোপনীয়তা; তবে modal confirm আছে, আর PIN `password: true` ইনপুটে (লগ হয় না)। মডাল/থ্রেট-মডেল ঠিক আছে।

---

## ৫. CI/CD সমীক্ষা

| রিপো | মোট রান | সাম্প্রতিক অবস্থা | মূল্যায়ন |
|---|---|---|---|
| supremeai-open | ৩৫৯৫ | CI সবুজ; `Landing — Auto-Merge & Bridge Dispatch` অটো-মার্জ সক্রিয় | সবচেয়ে সক্রিয়; অটো-মার্জ ঝুঁকিপূর্ণ (required checks কড়া কি না যাচাই করুন) |
| supremeai-api | ৪৮ | `secret-scan` **টানা ৪ রান ব্যর্থ** (১০-২২); শেষ সবুজ ১০-১৯ | 🔴 সিক্রেট-স্ক্যান লাল = অ্যালার্ট উপেক্ষা; **টেস্ট CI নেই** |
| supremeai-studio | ৬৫ | `ci` #40 **ব্যর্থ** (firebase অপসারণ কমিট); আগের ৩টি সবুজ | লিন্ট/টেস্ট CI আছে — ভালো |
| supremeai-vscode | ৭ | `Release Client Hub` ৩/৪ ব্যর্থ, `Build & Release` ব্যর্থ | রিলিজ পাইপলাইন ভাঙা |
| supremeai-core | **০** | কোনো workflow নেই | 🔴 কোর ইঞ্জিনে কোনো টেস্ট/লিন্ট গেট নেই |
| supremeai-browser | **০** | কোনো workflow নেই | 🔴 সরাসরি main→deploy |

⚠️ **টুল-সীমা:** `github_get_failed_logs` শুধু trailing লগ ফেরত দেয় — প্রকৃত ব্যর্থতার কারণ দেখা যায়নি (যেমন secret-scan কী পেয়েছিল, তা নিশ্চিত করা যায়নি)। CI-তে গিয়ে প্রতিটি লাল রানের কারণ আলাদা করে দেখে নেওয়া উচিত।

---

## ৬. সংকটপূর্ণ ফাইন্ডিংস — একীভূত তালিকা

| ID | ফাইন্ডিং | অবস্থান | প্রভাব |
|---|---|---|---|
| C-1 | হার্ডকোডেড fallback signing secret | `service/keygen.py:19,22-27` | সমস্ত API key forge-যোগ্য |
| C-2 | অথ-ছাড়া খোলা URL-fetch প্রক্সি | `cloudflare-worker/src/index.js:15,33` | SSRF / অ্যাননিমাস স্ক্র্যাপিং-রিলে |
| C-3 | স্পুফেবল হেডার auth bypass + fail-open | `service/app.py:74-91,112-113` | যে কেউ অথ ছাড়াই API ব্যবহার করতে পারে |
| C-4 | অথ-ছাড়া Gemini-web রিলে, `0.0.0.0` | `ghost_bridge_server.py:78,95-96,365` | খোলা LLM-রিলে, অ্যাকাউন্ট/ToS ঝুঁকি |
| C-5 | গেস্ট (অটো-রেজিস্টার্ড, অথ-হীন) ক্লায়েন্টে প্রাইভেট রিপো রিড | MCP: `github_read_file` ইত্যাদি | সোর্স-কোড/IP ফাঁস |
| C-6 | গেস্টে env-key তালিকা + SSH address + লগ | MCP: `render_get_env_var_keys`, `render_get_logs`, `render_list_services` | রিকনে/নিম্ন পরিশ্রমে বড় আক্রমণ-পৃষ্ঠা |
| C-7 | admin এন্ডপয়েন্ট fail-open | `service/app.py:329-366` | state-changing এন্ডপয়েন্ট খোলা |
| C-8 | সিক্রেট-স্ক্যান CI টানা লাল + autoDeploy + `0.0.0.0/0` | supremeai-api / Render | দূষিত কমিট সরাসরি প্রোডাকশনে |

---

## ৭. সুপারিশ (অগ্রাধিকার)

### P0 — আজ/আগামীকাল
1. `DEFAULT_SIGNING_SECRET` সরাও; env না থাকলে **fail-closed crash**; সব জারিকৃত `sk-supreme-…` key বাতিল করে রোটেট; key-তে expiry + revocation list যোগ করো।
2. `service/app.py`: `X-Guest-Mode`/Origin-ভিত্তিক bypass ও `"guest"/"demo"` টোকেন বাদ; fail-open বাদ; `/admin/*`-এ শর্তহীন key যাচাই; CORS wildcard বাদ করে `gateway/main.py`-র allowlist মডেল একীভূত করো।
3. `cloudflare-worker/src/index.js`: shared-token auth + URL allowlist + private/metadata IP ব্লক; `ghost_bridge_server.py`: `/api/chat`,`/v1/*`-এ auth+rate limit, না হলে `0.0.0.0` বাইন্ড/পাবলিক রুট বন্ধ।
4. MCP টাওয়ার: গেস্ট প্রোফাইল থেকে `github_read_file/repo_tree/code_search`, `render_get_logs/env_var_keys/list_services` সরাও (অন্তত প্রাইভেট রিপো/লগ/env-key); প্রয়োজনে allowlist-ড রিড-অনলি প্রোফাইল; IP-সহ ক্লায়েন্ট আইডি বন্ধ।

### P1 — এই সপ্তাহে
5. Telegram অ্যালার্ট-বট ঠিক করো (টোকেন/নেটওয়ার্ক যাচাই) — ছাড়া ইনসিডেন্ট-অ্যালার্ট ও HITL লিংক অচল; বিকল্প চ্যানেল (email/webhook) রাখো।
6. secret-scan সবুজ করো + branch protection: checks green না হলে deploy ব্লক (Render autoDeploy বাদ দিয়ে manual/PR-gated deploy); Render-এ `healthCheckPath` সেট করো, allowlist সংকুচিত করো।
7. supremeai-core ও supremeai-browser-এ ন্যূনতম lint+test+secret-scan CI; supremeai-api-এ pytest CI-তে যোগ; vscode-এর রিলিজ পাইপলাইন সংশোধন।
8. `policy_preview`-এর পার্শ্বপ্রভাব/বার্তা সংশোধন (সত্যিই নিরীহ প্রিভিউ হোক, অথবা pending-তালিকায় দৃশ্যমান হোক); memory sidecar পাথ (`SUPREMEAI_BACKEND_DIR`) ঠিক করো বা ২৪টি টুল লুকাও।
9. `credential_vault.py`: master key vault-ডিরেক্টরির বাইরে (env/KMS), প্রিন্ট বাদ, `0600`; কুকি-সিঙ্কের blast radius কমাতে টেন্যান্ট/সার্ভিসভিত্তিক সংকীর্ণ scope।

### P2 — পরবর্তী স্প্রিন্ট
10. দুই গেটওয়ে ইমপ্লিমেন্টেশন একীভূত/অবসরপ্রাপ্ত; `archive/legacy_gateway/` ও monorepo-র ডুপ্লিকেট কোড পরিষ্কার; ৪৮-বিট HMAC truncation → পূর্ণ দৈর্ঘ্য; kill-switch PIN → শক্তিশালী গোপনীয়তা; MCP resources `uri` কন্ট্রাক্ট ও টুল-স্কিমা ঠিক করো; Redis রোটেশন-স্টেট সুসংগত করো; `system_summary`-এ সত্য স্বাস্থ্য দেখাও।
11. আইনি পর্যালোচনা: gemini.google.com স্ক্র্যাপিং/স্বয়ংক্রিয় লগইন Google ToS-এর সাথে সাংঘর্ষিক হতে পারে; supremeai-api-তে লাইসেন্স যোগ করো।
12. মাল্টি-টেন্যান্ট "control tower"-এর single free-plan ইনস্ট্যান্স ঝুঁকি: ব্যাকআপ/রিড-রেপ্লিকা/মনিটরিং পরিকল্পনা।

---

## ৮. যা ভালো করা হয়েছে (উল্লেখ করা উচিত)
- মান-আকৃতিভিত্তিক সিক্রেট মাস্কিং, per-tool rate limiting, output truncation (MCP টাওয়ার)
- HITL লিংকে স্থায়ী admin key সরিয়ে মেয়াদোত্তীর্ণ HMAC সিগনেচার — নিজেদের অডিট-ফিক্স হিসেবে নথিভুক্ত
- দুই-স্তরের SSRF গেট + প্রতিটি redirect hop-এ পুনরায় যাচাই (browser স্ক্র্যাপার)
- RBAC fail-closed (missing context = viewer), frontend guard-এর সীমা স্বীকার করা
- FE-04 অনুযায়ী টোকেন স্টোরেজ মাইগ্রেশন, `timingSafeEqual`/`compare_digest` ব্যবহার
- issue-numbered ইনফ্রা ফিক্স ও pinned dependency (supply-chain সচেতনতা)

---

## ৯. পদ্ধতি, প্রমাণ ও সীমাবদ্ধতা
- **প্রমাণ-সংগ্রহ:** MCP JSON-RPC (initialize → tools/list → read-only tools/call), ৬০+ কল; সংগৃহীত কাঁচা ডেটা `.openclaw/tmp/mcp*/out_*.json`, সাব-রিপোর্ট `.openclaw/tmp/audit/api-browser.md`।
- **সীমাবদ্ধতা:** (১) GitHub search API rate limit-এ কিছু কোড-সার্চ ব্যাহত; (২) CI ব্যর্থতার প্রকৃত কারণ trailing-log সীমায় যাচাই করা যায়নি; (৩) কোড পর্যালোচনা নমুনা-ভিত্তিক (৬০+ ফাইল), প্রতিটি লাইন নয়; (৪) ডেটাবেস সারণি/Redis কী-মান/কোনো সিক্রেট মান ইচ্ছাকৃতভাবে পড়া হয়নি (PII/সিক্রেট সুরক্ষা); (৫) কোনো আক্রমণাত্মক পরীক্ষা (স্ক্যান, ব্রুটফোর্স, এক্সপ্লয়েট) করা হয়নি — শুধু সরবরাহকৃত রিড-অনলি টুলের স্বাভাবিক ব্যবহার।
- **গোপনীয়তা:** এই রিপোর্টে কোনো API key/token/password-এর মান নেই; শুধু ফাইল+লাইন রেফারেন্স ও মাস্কড উল্লেখ।

*রিপোর্ট তৈরি: read-only অডিট; কোনো পরিবর্তনমূলক কাজ করা হয়নি।*
