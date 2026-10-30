# Scout Finding — OpenRouter `:free` ক্যাটালগ delta: ১টি মৃত configured মডেল + ১১টি অব্যবহৃত zero-cost মডেল

**Task ID:** bridge-20261030-gateway-free-catalog-delta-glm16 · **Agent:** GLM Agent 16 (Job ID: 486792)
**Role:** ecosystem-scout (single-runner lock, continuous loop dispatch) · **Class:** report-only scout receipt — কোড এডিট নয় (ম্যান্ডেট)
**Probe window:** 2026-10-30T13:4x–13:5xZ · **শূন্য-ক্রেডেনশিয়াল** (কোনো key/secret ব্যবহৃত হয়নি)

## বাংলা সারসংক্ষেপ

দুটি লাইভ-প্রমাণিত ফাইন্ডিং, দুটোই zero-credential প্রোব থেকে: (১) gateway-র openrouter free-list-এ configured **`meta-llama/llama-3.3-70b-instruct:free` লাইভ ক্যাটালগ থেকে অবসর নিয়েছে** — পরিবার এখনো জীবিত (৮টি meta-llama মডেল, paid `llama-3.3-70b-instruct`-ও আছে), শুধু `:free` SKU-ই নেই; এই member-এ পৌঁছানো প্রতিটি cascade traversal একটি নিষ্ফল hop। (২) লাইভ ক্যাটালগে **১৬টি `:free` মডেল (সবগুলোর prompt pricing $0)**, gateway configured ৬টির মধ্যে মাত্র ৫টি জীবিত — অর্থাৎ **১১টি zero-cost মডেল অব্যবহৃত**, যার মধ্যে `nvidia/nemotron-3-ultra-550b-a55b:free` (ctx 1,000,000), `thinkingmachines/inkling:free` (ctx 1,048,576), `google/gemma-4-31b-it:free` (ctx 262,144)। Zero-cost cascade-এর capability ceiling উল্লেখযোগ্যভাবে ওঠার সুযোগ — বিশেষত sentry-সিরিজে বারবার নথিভুক্ত degraded-provider জানালার সময়।

## পদ্ধতি (পুনরুৎপাদনযোগ্য)

```bash
curl -s https://openrouter.ai/api/v1/models   # 200, ~91ms, auth-হীন, 456 মডেল
# :free-প্রত্যয়িত আইডি ফিল্টার → ১৬টি; সবগুলোর pricing.prompt == "0"
```

দুইবার প্রোব (session-শুরু ও রিপোর্ট-পূর্ব) — উভয়বার অভিন্ন ১৬-id সেট: ক্যাটালগ-স্থিরতা নমুনা-স্তরে যাচাইকৃত। প্রোব আর্কাইভ: `/tmp/scout_openrouter_free.json` (agent-side; full 16-id list + timestamps)।

## ফাইন্ডিং ১ — মৃত configured মডেল (রিলায়েবিলিটি খরচ)

- **Configured:** `gateway/service/providers/adapters.py` → `"openrouter": [...]` তালিকায় `meta-llama/llama-3.3-70b-instruct:free` (৬ এন্ট্রির একটি)।
- **লাইভ:** ক্যাটালগে `:free` ভ্যারিয়েন্ট অনুপস্থিত; `meta-llama/llama-3.3-70b-instruct` (paid) ও পরিবারের অন্য ৭টি উপস্থিত → **SKU-অবসর নিশ্চিত, auth-gating নয়**।
- **প্রভাব:** ওই member-কে ট্রাই করা প্রতিটি cascade step ব্যর্থ hop (404/no-route শেপ) — dynamic_llm_router-এর fallback সময় বাড়ে; `gateway/tests/test_model_cascades.py`-র প্রত্যাশাও মৃত SKU-র উপর দাঁড়িয়ে থাকতে পারে।

## ফাইন্ডিং ২ — অব্যবহৃত zero-cost ক্যাপাসিটি (সুযোগ)

লাইভ কিন্তু unconfigured ১১টি `:free` মডেল:

```
google/gemma-4-26b-a4b-it:free          google/gemma-4-31b-it:free
nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
nvidia/nemotron-3-ultra-550b-a55b:free  nvidia/nemotron-3.5-content-safety:free
nvidia/nemotron-3.5-super-vl:free       poolside/laguna-xs-2.1:free
recursive/flint-v1.0:free               thinkingmachines/inkling-small:free
thinkingmachines/inkling:free           xingchen-agi/xing4.0-29b-a4b:free
```

হেডলাইন স্পেক (লাইভ রেসপন্স থেকে): `nemotron-3-ultra-550b-a55b:free` — ctx 1,000,000, prompt $0; `inkling:free` — ctx 1,048,576, $0; `gemma-4-31b-it:free` — ctx 262,144, $0।

## বাস্তবায়ন পথ (gateway স্যাটেলাইট বাউন্ডারির ভিতরে — প্রস্তাব মাত্র)

1. `gateway/service/providers/adapters.py`: মৃত `meta-llama/llama-3.3-70b-instruct:free` সরিয়ে জীবিত `:free` দিয়ে প্রতিস্থাপন (শীর্ষ প্রার্থী: `nvidia/nemotron-3-ultra-550b-a55b:free`, `google/gemma-4-31b-it:free`)।
2. `gateway/routing_policy.json` + `gateway/dynamic_llm_router.py` (`default_model`): একই নাম-সেট সিঙ্ক (দুটি সাইটই আজ `nemotron-3.5-lightning:free`-এ দাঁড়িয়ে)।
3. `gateway/tests/test_model_cascades.py`: মৃত-SKU pin সরিয়ে নতুন member-এর প্রত্যাশা।
4. ক্রম: প্রথমে keyed যাচাই (নিচের সীমাবদ্ধতা), তারপর PR — single-producer SSOT প্যাটার্নে (R66 শিক্ষা) free-তালিকা এক জায়গায় ডেরাইভ করা হলে ভবিষ্যৎ অবসর-ক্লাস কাঠামোগতভাবে ধরা পড়বে।

## সীমাবদ্ধতা (সৎ সীমা — অনুমান নয়)

- ক্যাটালগ-সদস্যতা **প্রয়োজনীয় শর্ত, পর্যাপ্ত নয়**: তালিকাভুক্ত মডেলও 429/503 দিতে পারে; free-tier rate-limit (keyed কল ছাড়া অযাচাইকৃত) আলাদা সীমা। সুতরাং অপসারণ/সংযোজনের আগে একটি keyed স্মোক কল বাধ্যতামূলক — এটি gateway-owner-দের লেন।
- `$0` pricing শুধু prompt-ঘরে যাচাইকৃত; completion/অন্যান্য ঘরের মান রিপোর্টে দাবি করা হয়নি।
- এই রিসিট report-only: বাস্তবায়ন সিদ্ধান্ত verdict plane / gateway মালিকানার — কোনো auto-close দাবি নেই (keep-open কনভেনশন)।

## রেফারেন্স

- লাইভ এন্ডপয়েন্ট: `https://openrouter.ai/api/v1/models` (200/91ms, zero-credential, 456 মডেল)
- Configured সাইট: `gateway/service/providers/adapters.py` (openrouter free list), `gateway/routing_policy.json`, `gateway/dynamic_llm_router.py`
- সম্পর্কিত সিরিজ: sentry পাস #3355 (degraded-provider জানালা), #2516 (dispatch-census), R74 census (controller-side adoption lane)
