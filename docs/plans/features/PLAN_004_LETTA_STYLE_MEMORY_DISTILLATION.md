---
id: head-of-planning-letta-style-memory-distillation-v1-2026-09-17
title: "Head of Planning — Plan #004: Letta/ChatGPT-Style Write-Time Memory Distillation (বিদ্যমান Eternal Brain ফ্যাসাডে, শূন্য নতুন Dependency, শূন্য নতুন Infra)"
status: complete
document_role: implementation
owner_circle: Memory Circle (backend/core/circles/centers/memory_center.py) + C5 (Execution — LLM Gateway)
scope: "ONE complete plan, fully grounded in actual repo code (2026-09-17 fresh main, commit 37b05f4b), following the strengthened PLAN_LIFECYCLE_POLICY.md (2026-09-17) — all required metadata, Gates 0–6, labeled quantitative claims, explicit out-of-scope"
depends_on:
  - backend/core/unified_memory.py (existing UnifiedMemoryInterface — Eternal Brain write/query facade, L27–121)
  - backend/services/memory_service.py (existing CascadeMemoryService — store_memory L298, query_context L496, _embed L218)
  - backend/core/llm/llm_gateway (existing singleton `llm_gateway` — acompletion, zero-cost provider chain)
  - backend/core/embeddings.py (existing local-first embedding: SentenceTransformer → hash_vectorize fallback, 384-dim)
  - backend/agents/syncguard/syncguard_agent.py (existing async production memory-writer, run_full_audit L35, store call L83)
  - backend/api/routes/unified_memory_api.py (existing async HTTP memory endpoint, L21–41)
  - backend/tests/memory/ (existing test tree — test_memory_service.py patterns)
  - README.md Constitution #11 (Memory Must Compound), #1 (Eternal Brain), #13 (No Silent Failure), #8 (Graceful Degradation), #3 (Reuse Before Creation)
  - PLAN_LIFECYCLE_POLICY.md (2026-09-17) Gates 0–6
implements:
  - Write-time memory distillation on the existing Eternal Brain facade (Constitution #11 Memory Must Compound, #1 Eternal Brain)
  - Honest, logged fallback to legacy truncation on any distiller failure (Constitution #13, #8)
  - No new subsystem, no new dependency, no new infra, no schema change (Constitution #3)
supersedes: []
superseded_by: []
source_of_truth: false
implementation_evidence: "IMPLEMENTED 2026-09-17 on main — core/unified_memory.py: MEMORY_DISTILL_ENV kill-switch read at CALL time via _memory_distill_enabled(), MEMORY_DISTILL_MIN_CONTENT_CHARS=400 cost gate, MEMORY_DISTILL_SYSTEM_PROMPT, pure _extract_json_object() (no exception escapes), async distill_content() (locked non-stream acompletion contract: {'success','text',...} — plan sketch's 'content' key corrected to 'text' during implementation), _store_long_term_with_summary() private override helper (public store_long_term_memory signature unchanged — 3 existing callers intact), store_long_term_memory_distilled() with metadata['distilled']=True + metadata['memory_structure'] provenance; agents/syncguard/syncguard_agent.py store call switched to distilled variant (async context); api/routes/unified_memory_api.py optional distill=false query flag (default legacy path); tests/memory/test_memory_distillation.py 13/13 (valid-JSON extract, no-JSON, non-dict, malformed; gateway success, gateway exception; distilled write w/ provenance, fallback-to-legacy-truncation w/ success=True, malformed-JSON summary-only, short-content skips distiller, SUPREMEAI_MEMORY_DISTILL=false kill-switch, honest False on backend failure); tests/memory/ tree 171/171; tests/security/test_cross_tenant_isolation.py 33/33"
last_verified: "2026-09-17 (code-read on fresh main 37b05f4b, re-verified on main 1f570558 — `git diff 37b05f4b..1f570558 -- backend/ frontend/ apps/ packages/` is empty, code identical; unified_memory.py L27–121, memory_service.py L218/L298–348/L496–530, syncguard_agent.py L35–95, unified_memory_api.py L21–41, embeddings.py L1–66; web citations dated below); re-verified 2026-09-17 on main b37f3f10 — memory_service.py drifted via eb589909 (local hash_vectorize copy now delegates to canonical core.embeddings blake2b implementation; net −10 lines → symbol lines shifted), updated lines: _embed L208, store_memory L288, `embedding = self._embed(summary)` L306, pg INSERT INTO ai_memory L312–321, query_context L486; unified_memory.py L57–58 placeholder, syncguard_agent.py L83–90 store call, unified_memory_api.py L21–41 endpoint — সব sed-confirmed অপরিবর্তিত); re-verified 2026-09-17 on main 83084ee8 — all evidence files 0-diff since b37f3f10 (c606e028..83084ee8), unified_memory.py L57–58 placeholder sed-confirmed; Gate 0 adjacency note: founder pinned M3 memory-consolidation blueprint (ERR-F02, defect register 2026-09-17) — canonical store হবে Supabase `ai_memory` (vector 384), যেখানে এই প্ল্যানের distilled summary লেখা হয় — সম্পূরক (complementary), কোনো conflict নেই; target_scope: supremeai_internal recorded per founder 3-tier taxonomy (ab0f7d51)"
code_evidence:
  - "backend/core/unified_memory.py L57–58: summary = content[:200]  # Placeholder ; structure = \"{}\"  # Placeholder (literal placeholder comments in the Eternal Brain write path)"
  - "backend/services/memory_service.py L306: embedding = self._embed(summary) — retrieval embedding is computed from the summary only; pg INSERT INTO ai_memory (L312–321) persists summary+embedding+metadata but NOT content or structure (lines updated for eb589909 drift on b37f3f10; was L316/L323–333 on 37b05f4b)"
  - "backend/agents/syncguard/syncguard_agent.py L83–90: production async writer sends full JSON audit report as content → truncated to 200 chars by L57"
  - "backend/core/unified_memory.py L95–110: store_short_term_memory has zero non-test production callers (grep-verified 2026-09-17)"
  - "backend/api/routes/websocket_agent.py L9: 'from core.llm.llm_gateway import llm_gateway' — established singleton import pattern"
test_evidence:
  - "PLANNED (not yet run — Gate 4/5): backend/tests/memory/test_memory_distillation.py — stubbed-gateway unit tests proving distilled write, fallback-on-failure write, malformed-JSON degradation; offline retrieval eval script (on-demand, not CI) for Gate 5 outcome measurement"
acceptance_criteria:
  - "All existing backend/tests/memory/ suites pass unchanged (zero regression)"
  - "New distillation tests pass: distilled summary written when gateway succeeds; legacy truncation written (success=True) when gateway fails — no exception escapes, no fabricated memory"
  - "Offline retrieval eval (Gate 5): distilled entries outperform legacy-truncation entries on seed top-3 hit-rate by the acceptance threshold below"
risk_and_rollback:
  - "Single-commit, additive change: legacy sync path untouched; distilled path is opt-in per call site (syncguard + endpoint flag)"
  - "Rollback = git revert of the single implementation commit; no DB migration, no config migration, no data migration — pre-existing memories remain valid"
  - "Runtime kill-switch: env flag SUPREMEAI_MEMORY_DISTILL=false forces the distilled variant to delegate straight to legacy truncation (checked at call time)"
baseline:
  - "Code-verified (2026-09-17): Eternal Brain summary = first 200 chars of content (unified_memory.py L57); structure = literal '{}' (L58); retrieval embedding derived from that summary (memory_service.py L306)"
measurement_method:
  - "Offline, on-demand (never per-CI): seed ≥20 representative memory entries (syncguard-style JSON reports, browser-session payloads, API-endpoint-style notes); write each twice — legacy truncation vs distilled — into the degraded-mode SQLite path; run CascadeMemoryService.query_context with ≥10 natural-language seed queries; compare top-3 hit-rate between the two corpora; record per-query results in the plan's outcome evidence block"
success_threshold:
  - "Acceptance threshold (hypothesis until measured): distilled top-3 hit-rate ≥ legacy top-3 hit-rate + 15 percentage points on the seed set; failure of this threshold ⇒ plan marked failed/blocked per Gate 6, no silent success"
plan_lifecycle: "living — single complete plan #004; implemented 2026-09-17 on main (see last_verified); Gate-5 offline retrieval eval remains the recorded pending outcome measurement"
target_scope: supremeai_internal
---

# Head of Planning — Plan #004: Letta/ChatGPT-Style Write-Time Memory Distillation

> **বাংলা সারসংক্ষেপ:** বিশ্বের সেরা AI প্রোডাক্টগুলো ২০২৫–২৬ সালে যে ফিচার নিয়ে সবচেয়ে বেশি আলোচিত হয়েছে তার একটি হলো **স্থায়ী মেমোরি** — ChatGPT-এর "saved memory", Claude-এর chat-memory, আর ওপেন-সোর্স জগতে Letta (সাবেক MemGPT)-এর self-editing memory blocks। এদের সবার মূল রহস্য একটাই: **লেখার সময়েই (write-time) কথোপকথন থেকে ঘন, স্ট্রাকচার্ড, অনুসন্ধানযোগ্য সারসংক্ষেপ তৈরি হয়** — raw dump নয়। আমাদের SupremeAI-র কাগজে-কলমে একটি পূর্ণাঙ্গ "Eternal Brain" স্থাপত্য আছে (Constitution #1, #11 — UnifiedMemoryInterface ফ্যাসাড: long-term + short-term + checkpoint) — কিন্তু কোড পরীক্ষা করে দেখা গেছে, সেই ফ্যাসাডের লেখার পথে সারসংক্ষেপ হিসেবে কাজ করছে মাত্র **প্রথম ২০০ অক্ষরের কাঁচা কাট-পেস্ট** (কোডে নিজেই লেখা আছে `# Placeholder`), আর সেই কাটা অংশ দিয়েই embedding তৈরি হয়ে ভেক্টর-অনুসন্ধান চলে। অর্থাৎ মেমোরি হাজারটা লেখা হচ্ছে, কিন্তু তা **কম্পাউন্ড করছে না** — ৫০ নম্বর কাজ ৫ নম্বর কাজের অভিজ্ঞতা থেকে শিখতে পারছে না, ঠিক যেটা Constitution #11 নিষেধ করেছে। এই প্ল্যান বিদ্যমান LLM Gateway-এর zero-cost chain দিয়ে **write-time distillation** যোগ করে: ঘন সারসংক্ষেপ + স্ট্রাকচার্ড facts যাবে বিদ্যমান metadata কলামে। ব্যর্থ হলে আজকের আচরণই (সৎ fallback)। **৩টি ফাইলে ছোট পরিবর্তন + ১টি টেস্ট ফাইল, ০ নতুন dependency, ০ নতুন infra, ০ schema change।**

---

## Part 1 — Competitor Intelligence (dated external evidence, verified 2026-09-17)

### ১.১ Letta (f.k.a. MemGPT) — OSS মেমোরি স্থাপত্য

- **Sorce:** github.com/letta-ai/letta — "Build stateful agents with memory that can learn and improve over time"; letta.com blog (2025-07-07) — recall memory saves automatically; archival memory দীর্ঘমেয়াদি স্তর; vectorize.io (2026-03-14) — "Agent self-edits its own memory blocks; memory tiers".
- **মূল শিক্ষা:** মেমোরি কাঁচা ট্রান্সক্রিপ্ট নয় — **স্তরে সাজানো, সংশোধনযোগ্য, অনুসন্ধানযোগ্য ব্লক**। লেখার সময়েই distill হয়, তাই পরে পড়া সস্তা ও নির্ভুল।

### ১.২ ChatGPT Memory (OpenAI)

- **Sorce:** help.openai.com Memory FAQ — "The memory summary is automatically updated with new context as you chat"; openai.com (2024-02-13) — saved memories, ইউজার নিয়ন্ত্রণ।
- **মূল শিক্ষা:** distillation হয় **অটোমেটিক**, ইউজার চাইলে দেখতে/মুছতে পারে। আমাদের এই প্ল্যানে UI নেই (out-of-scope), কিন্তু metadata-তে স্ট্রাকচার্ড facts রাখায় ভবিষ্যতে সেই দরজা খোলা থাকে।

### ১.৩ Claude Memory + Claude Code MEMORY.md (Anthropic)

- **Sorce:** support.claude.com — "Claude can generate memory based on your chats… transforms from a stateless chat interface into a knowledgeable collaborator" (siliconangle.com, 2025-09-11: memory became automatic); code.claude.com — "Claude keeps MEMORY.md **concise** by moving detailed notes into separate topic files… measures the file against the [budget]".
- **মূল শিক্ষা:** সংক্ষিপ্ততা **বাজেট-নিয়ন্ত্রিত** — অসীম সারসংক্ষেপ নয়। আমাদের ডিস্টিলারেও ≤১৮০-টোকেন summary বাজেট থাকবে।

### ১.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল

| ক্ষমতা | Letta | ChatGPT | Claude | SupremeAI আজ (code-verified 37b05f4b) |
|---|---|---|---|---|
| লেখার সময়ে ঘন সারসংক্ষেপ | ✅ | ✅ | ✅ | ❌ `content[:200]` কাঁচা কাট (L57 `# Placeholder`) |
| স্ট্রাকচার্ড facts (entity/preference) | ✅ blocks | ✅ saved memory | ✅ topic files | ❌ `structure = "{}"` (L58 literal) |
| সারসংক্ষেপ-ভিত্তিক ভেক্টর অনুসন্ধান | ✅ | ✅ | ✅ | ⚠️ আছে, কিন্তু খারাপ summary-র উপর (memory_service.py L306) |
| ব্যর্থতায় সৎ fallback | ✅ | — | — | এই প্ল্যান যোগ করছে (#13) |

---

## Part 1.5 — Gate 0: Discovery & Reconciliation (fresh main 37b05f4b, 2026-09-17)

1. **Existing-equivalent search:** `docs/plans/`-এ distillation/promotion-ঘেঁষা ডক: HEAD_OF_PLANNING_STRATEGIC_LEVERAGE (L4 lever — কৌশলগত দিক, implementation plan নয়), PLAN_002 (in-session chat compaction — স্থায়ী মেমোরি নয়), PLAN_003 (repo map — ভিন্ন সমস্যা)। **কোনো বাস্তবায়ন-স্তরের memory-distillation plan নেই।**
2. **Complement declarations (policy rule 3):** PLAN_001 = provider-side caching; PLAN_002 = সেশনের ভিতরের অস্থায়ী কনটেক্সট; PLAN_003 = CODER-domain workspace context; **PLAN_004 = সেশন-পার হয়ে যাওয়া স্থায়ী মেমোরির গুণমান**। চারটি ভিন্ন স্তর — ইচ্ছাকৃতভাবে complementary, কোনোটিই অন্যটির canonical replacement নয়।
3. **implementation_plan.md reconciliation:** এই PR §13 রেজিস্টারে PLAN_004-এর সারি যোগ করবে (§13 main-এ 2026-09-17 থেকে বিদ্যমান, L439)।
4. **Code reality (Rule 9/Gate 0):** নিচের সব দাবির সঠিক ফাইল+লাইন রেফারেন্স `code_evidence` ফিল্ডে দেওয়া আছে — fresh main থেকে সরাসরি পঠিত।
5. **Duplicate-within-repo check:** `store_long_term_memory`-এর ৩টি প্রোডাকশন কলার আছে (syncguard, browser_routes, unified_memory_api) — অর্থাৎ লেখার পথ **অনাথ নয়**; শুধু তার সারসংক্ষেপ-বুদ্ধিমত্তাই নেই। নতুন কোনো store/ফ্যাসাড বানানো হবে না (Reuse Before Creation)।

---

## Part 2 — Plan #004: Six-Field Complete Plan

Plan identifier: `PLAN-004-LETTA-STYLE-MEMORY-DISTILLATION`
Owner Circle: Memory Circle + C5 (LLM Gateway) · Constitution anchor: #11 (primary), #1, #13, #8, #3

### ২.১ কি আছে (code-verified, fresh main 37b05f4b)

1. **পূর্ণাঙ্গ মেমোরি ফ্যাসাড** — `UnifiedMemoryInterface` (backend/core/unified_memory.py L27–121): long-term store/query, short-term store/recall, task checkpoint — কাগজে সম্পূর্ণ Eternal Brain।
2. **ব্যাকিং সার্ভিস** — `CascadeMemoryService` (backend/services/memory_service.py): `store_memory` L288 (pg `ai_memory` INSERT: user_id, session_id, agent_type, task_type, summary, embedding, metadata), `query_context` L486 (pgvector RPC ranking + in-Python cosine fallback + row cap), `_embed` L208 → `embed_for_pgvector` (local-first, 384-dim, hash fallback — backend/core/embeddings.py; eb589909-এর পর থেকে hash fallback deterministic)।
3. **LLM Gateway singleton** — `from core.llm.llm_gateway import llm_gateway` (websocket_agent.py L9-এ প্রতিষ্ঠিত ইমপোর্ট প্যাটার্ন); `acompletion(prompt=..., task_type=...)` জেনেরিক; zero-cost provider chain (router + local Ollama fallback) সক্রিয়।
4. **বাস্তব প্রোডাকশন লেখক** — `syncguard_agent.py` `run_full_audit()` (async, L35) L83-90: পূর্ণ JSON অডিট রিপোর্ট মেমোরিতে লেখে; `unified_memory_api.py` L21–41: HTTP এন্ডপয়েন্ট (async); `browser_routes.py` L652: ব্রাউজ-সেশন লেখে (content = শুধু URL)।
5. **টেস্ট ট্রি** — `backend/tests/memory/` বিদ্যমান (test_memory_service.py, test_sliding_window_memory.py ইত্যাদি) — প্রতিষ্ঠিত pytest প্যাটার্ন।
6. **metadata JSON কলাম বিদ্যমান** — pg INSERT-এ metadata পার্সিস্ট হয় (memory_service.py L312–321) — স্ট্রাকচার্ড facts নতুন কলাম ছাড়াই এখানে ভ্রমণ করতে পারে (**শূন্য schema change**)।

### ২.২ কি নাই

1. **কোনো LLM-ভিত্তিক write-time distillation নেই** — summary = `content[:200]` (L57, কোডেই `# Placeholder` লেখা), structure = `"{}"` (L58)।
2. **retrieval embedding খারাপ summary থেকে হয়** — memory_service.py L316: `embedding = self._embed(summary)`; কাঁচা কাটা ২০০ অক্ষরে ভেক্টর-অনুসন্ধানের মান সীমিত (মানটি পরিমাপই হয়নি — তাই baseline+measurement নিচে বাধ্যতামূলক)।
3. **syncguard-এর ঘন JSON রিপোর্ট কাটা পড়ে** — L83 content-এ পূর্ণ রিপোর্ট যায়, লেখা থাকে প্রথম ২০০ অক্ষর।
4. **কোনো distillation টেস্ট/metric নেই** — backend/tests/memory/-তে distillation assertion শূন্য।

### ২.৩ কি করতে হবে

বিদ্যমান Eternal Brain লেখার পথে **opt-in write-time distillation** যোগ — বিদ্যমান sync/legacy পথ অক্ষুণ্ণ রেখে (non-regression):

1. `unified_memory.py`-এ **নতুন async মেথড** `store_long_term_memory_distilled()` + distillation prompt বিল্ডার (pure helper)।
2. `syncguard_agent.py`-এর এক লাইনের কল সুইচ (async context-এ আছে বলে নিরাপদ) — প্ল্যানটি day-one থেকেই বাস্তব প্রোডাকশনে চলবে।
3. `unified_memory_api.py` এন্ডপয়েন্টে ঐচ্ছিক `"distill": true` ফ্ল্যাগ — ডিফল্ট আচরণ অপরিবর্তিত।
4. নতুন টেস্ট ফাইল `backend/tests/memory/test_memory_distillation.py`।

### ২.৪ কিভাবে করব (file-by-file)

**Change 1 — `backend/core/unified_memory.py` (+~70 lines):**

```python
MEMORY_DISTILL_ENABLED = os.getenv("SUPREMEAI_MEMORY_DISTILL", "true").lower() != "false"

MEMORY_DISTILL_SYSTEM_PROMPT = (
    "You are SupremeAI's memory distiller (Letta/MemGPT-style write-time block builder). "
    "From the raw content, produce: (1) a dense summary <=180 tokens preserving durable "
    "facts, decisions, preferences, entity names, paths/commands, unresolved issues; "
    "(2) a JSON object {\"facts\": [...], \"preferences\": [...], \"entities\": [...], "
    "\"open_items\": [...]} (empty arrays allowed; NO prose outside JSON)."
)

def _extract_json_object(text: str) -> dict[str, Any] | None:
    """টলারেন্ট JSON এক্সট্র্যাক্টর — প্রথম {...} ব্লক; ব্যর্থ হলে None (কোনো exception ছড়ায় না)।"""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

async def distill_content(content: str) -> tuple[str, dict[str, Any] | None]:
    """(summary, structure) রিটার্ন করে; যেকোনো ব্যর্থতায় (None, None) — কলার legacy পথে নামবে।"""
    from core.llm.llm_gateway import llm_gateway  # প্রতিষ্ঠিত singleton প্যাটার্ন
    result = await llm_gateway.acompletion(
        prompt=[
            {"role": "system", "content": MEMORY_DISTILL_SYSTEM_PROMPT},
            {"role": "user", "content": content[:8000]},
        ],
        task_type="summarization",
    )
    text = result.get("content") if isinstance(result, dict) else str(result)
    if not text or not text.strip():
        return "", None
    return " ".join(text.split())[:1200], _extract_json_object(text)
```

```python
# UnifiedMemoryInterface-এর নতুন মেথড:
async def store_long_term_memory_distilled(self, *, session_id, agent_type, task_type,
                                           content, metadata=None, user_id=None) -> bool:
    """Letta-স্টাইল write-time distillation। ব্যর্থ হলে হৃদয়ংকুপিত fallback:
    ঠিক আজকের মতো legacy truncation লেখা হয় — memory কখনো হারায় না, শুধু ঘনত্ব কমে।"""
    summary, structure = None, None
    if MEMORY_DISTILL_ENABLED and content and len(content) > 400:
        try:
            summary, structure = await distill_content(content)
        except Exception as exc:  # #8 Graceful Degradation, #13 সৎ লগ
            logger.warning(f"memory distillation failed ({exc}); using legacy truncation fallback")
    if summary:
        enriched = dict(metadata or {})
        if structure:
            enriched["memory_structure"] = structure  # বিদ্যমান metadata JSON কলামে — শূন্য schema change
        enriched["distilled"] = True
        return self.store_long_term_memory(
            session_id=session_id, agent_type=agent_type, task_type=task_type,
            content=content, metadata=enriched, user_id=user_id) if self._store_with_override(
            session_id, agent_type, task_type, content, summary, enriched, user_id) else False
    # legacy path (আজকের আচরণ — অপরিবর্তিত)
    return self.store_long_term_memory(
        session_id=session_id, agent_type=agent_type, task_type=task_type,
        content=content, metadata=metadata, user_id=user_id)
```

> **বাস্তবায়ন নোট (honest):** উপরের স্কেচে summary-override সহজ করতে ইমপ্লিমেন্টেশন PR-এ `store_long_term_memory`-এ ছোট private helper (`_store_with_override`) বা সমতুল্য প্যারামিটার-থ্রেডিং হবে; `store_long_term_memory`-এর পাবলিক সিগনেচার অপরিবর্তিত থাকবে (৩টি বিদ্যমান কলার ভাঙবে না)। `acompletion` non-stream return-এর সঠিক শেপ PR-এ পুনঃপাঠ করে লক করা হবে (PLAN_002-তেও একই যাচাই-নোট আছে)।

**Change 2 — `backend/agents/syncguard/syncguard_agent.py` (১ লাইন):**

```python
# L83: sync call → distilled async call (run_full_audit ইতিমধ্যে async — নিরাপদ)
success = await unified_memory.store_long_term_memory_distilled(
    session_id=f"syncguard_audit_{audit_report['timestamp']}",
    agent_type="SyncGuard", task_type="System_Audit",
    content=json.dumps(audit_report, indent=2),
    metadata={"status": audit_report["status"]},
)
```

**Change 3 — `backend/api/routes/unified_memory_api.py` (+~8 lines):** request body-তে ঐচ্ছিক `distill: bool = False`; true হলে distilled ভ্যারিয়েন্ট, অন্যথায় বিদ্যমান পথ — ব্যাকওয়ার্ড-কম্প্যাটিবল।

**Change 4 — নতুন টেস্ট `backend/tests/memory/test_memory_distillation.py` (~90 lines):** stubbed gateway (টেস্ট টুলিং stub — প্রোডাক্টে নয়): (ক) distill সফল → distilled summary + `metadata["memory_structure"]` লেখা হয়; (খ) gateway exception → legacy truncation, রিটার্ন True, কোনো exception বের হয় না; (গ) malformed JSON → summary-only, structure স্কিপ; (ঘ) `len(content) <= 400` → distiller আহ্বানই হয় না (খরচ সাশ্রয়); (ঙ) SUPREMEAI_MEMORY_DISTILL=false → straight legacy।

**পরিসর:** ২টি বিদ্যমান ফাইলে ছোট এডিট + ১টি এন্ডপয়েন্টে ~৮ লাইন + ১টি নতুন টেস্ট ফাইল (বিদ্যমান `backend/tests/memory/` ট্রি) · **০ নতুন dependency · ০ নতুন infra · ০ schema migration · ০ frontend পরিবর্তন · ০ CI ব্যয়বৃদ্ধি (টেস্টে LLM কল নেই — stub)**।

### ২.৫ বেনিফিট

1. **Memory Flywheel প্রথমবারের মতো সত্যিকারে ঘোরবে (#11):** ঘন, facts-সমৃদ্ধ summary থেকে embedding → `query_context`-এর র‍্যাংকিং মান বাড়বে; task #50 task #5-এর অভিজ্ঞতা থেকে শিখতে পারবে।
2. **Competitor parity:** Letta/ChatGPT/Claude-র মূল মেমোরি-বুদ্ধিমত্তার সঙ্গে কার্যকর parity — স্থাপত্য আমাদেরই আছে, শুধু বুদ্ধিটা ছিল placeholder।
3. **syncguard মেমোরি অবমূল্যায়ন বন্ধ:** পূর্ণ JSON রিপোর্ট → ঘন সারসংক্ষেপ + স্ট্রাকচার্ড facts (metadata-তে)।
4. **খরচ সসীম ও ~$0 (estimate):** distillation শুধু >400-অক্ষরের লেখায়, বিদ্যমান zero-cost chain-এ; syncguard অডিট হার অনুযায়ী কল-সংখ্যা নগণ্য; ≤180-টোকেন আউটপুট বাজেট।
5. **ভবিষ্যৎ প্রস্তুতি:** `metadata["memory_structure"]` দিয়ে পরে ChatGPT-স্টাইল user-visible memory UI বা L4-লেভারের flywheel consolidation — উভয়ের দরজা খোলা।

### ২.৬ ক্ষতি/রিস্ক (honest)

| রিস্ক | মাত্রা | মাইটিগেশন |
|---|---|---|
| ডিস্টিলার ব্যর্থতা/সার্ভিস ডাউন | কম | হৃদয়ংকুপিত fallback: ঠিক আজকের legacy পথ; warning লগ; memory হারায় না |
| খারাপ/ভুল distillation → মেমোরি দূষণ | মাঝারি | ≤180-টোকেন বাজেট; JSON টলারেন্স; `metadata["distilled"]=true` প্রোভেন্যান্স ফ্ল্যাগ — পরে অডিট/মুছতে পারা যায় |
| syncguard কল-পথে নতুন await | নিম্ন | run_full_audit ইতিমধ্যে async; try/except ভেতরে সম্পূর্ণ কনটেইনড |
| Non-stream `acompletion` রিটার্ন শেপ অনিশ্চিত | কম | ইমপ্লিমেন্টেশন PR-এ শেপ পুনঃপাঠ বাধ্যতামূলক; টেস্টে সেই শেপ stub |
| Latency: syncguard অডিটে ১–৩s অতিরিক্ত (প্রতি অডিটে একবার) | নিম্ন | অডিট লুপ infrequent (background audit); ব্যবহারকারী-মুখী latency নয় |
| ভেক্টর মান উন্নতি "আশা"-ই থাকতে পারে | মাঝারি | Gate 5: offline eval বাধ্যতামূলক; threshold মিস হলে plan failed/blocked ঘোষণা — কোনো নীরব সাফল্য-দাবি নয় |

---

## Part 3 — Explicit Out-of-Scope (সুস্পষ্ট ঘোষণা)

1. **মেমোরি-স্টোর টপোলজি কনসোলিডেশন নয়** — HEAD_OF_PLANNING L4 লেভারের "15+ competing stores" M3 decision table আলাদা কাজ; এই প্ল্যান শুধু বিদ্যমান একক ফ্যাসাডের (UnifiedMemoryInterface) লেখার গুণমান বাড়ায়।
2. **schema/pgvector পরিবর্তন নয়** — structure বিদ্যমান metadata JSON-এ ভ্রমণ করে।
3. **ব্রাউজ/এন্ডপয়েন্ট কলারের বাধ্যতামূলক মাইগ্রেশন নয়** — browser_routes আজকের মতোই; ভবিষ্যৎ প্ল্যানে opt-in।
4. **মেমোরি ম্যানেজমেন্ট UI নয়** — ফ্রন্টএন্ডে শূন্য পরিবর্তন।
5. **agent-task-completion hook নয়** — সব এজেন্ট কলারে auto-distill পরে (single-plan discipline: প্রথমে এটা সম্পূর্ণ ও পরিমাপিত হোক)।
6. **tree_sitter dependency ঘোষণা (PLAN_003 hygiene note)-ও এখানে নয়।**

---

## Part 4 — 9-Rule Discipline + Constitution Compliance

| Rule (PLAN_001 সংশোধিত শৃঙ্খলা) | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | একটাই প্ল্যান; বাকি আইডিয়া reference-এ |
| 2. Small change to existing code | ✅ | বিদ্যমান ফ্যাসাড+gateway+syncguard-এ ছোট এডিট; নতুন ফাইল শুধু বিদ্যমান tests/memory ট্রিতে |
| 3. No new infrastructure | ✅ | Render/Supabase/GH Actions — কিছুই নতুন নয় |
| 4. No CI cost amplification | ✅ | টেস্টে LLM stub; eval অন-ডিমান্ড, per-CI নয় |
| 5. No credit-burn risk | ✅ | zero-cost chain; >400-অক্ষর গেট; env kill-switch |
| 6. No academic leaderboard | ✅ | সরাসরি প্রোডাক্ট ক্ষমতা |
| 7. Realistic resource budget | ✅ | 512MB-safe; ≤180-টোকেন আউটপুট; কল-হার নগণ্য |
| 8. Complete six-field format | ✅ | §২.১–২.৬ |
| 9. Reality check before drafting | ✅ | fresh main 37b05f4b code-read; `code_evidence` ফিল্ডে line refs |

| Constitution ধারা | প্রভাব |
|---|---|
| #1 Eternal Brain | ✅ মূল লক্ষ্য — মেমোরি এখন সত্যিকার অর্থে "জ্ঞানে" পরিণত হয় |
| #3 Reuse Before Creation | ✅ নতুন subsystem/store/dep শূন্য |
| #5 Verify Before Trust | ✅ Gate 4 টেস্ট + Gate 5 offline eval বাধ্যতামূলক |
| #8 Graceful Degradation | ✅ fallback আজকের আচরণ |
| #11 Memory Must Compound | ✅ প্রাথমিক অ্যাংকর |
| #13 No Silent Failure | ✅ ব্যর্থতা warning-লগড, প্রোভেন্যান্স ফ্ল্যাগড |
| #14 Sustainable Cost | ✅ বিদ্যমান ফ্রি-কোটার মধ্যে সসীম; পরিমাপযোগ্য |

---

## Part 5 — Verification & Acceptance (Gates 4–6)

1. **Gate 4 (verification):** `pytest backend/tests/memory/ -v` → সব বিদ্যমান + নতুন distillation টেস্ট PASS; প্রভাবিত পথে রিগ্রেশন শূন্য; `SUPREMEAI_MEMORY_DISTILL=false`-তে বিহেভিয়ার byte-সমতুল্য legacy।
2. **Gate 5 (outcome evidence):** offline retrieval eval (measurement_method অনুযায়ী ≥20 entries, ≥10 queries) — per-query ফলাফল এই প্ল্যানের আউটকাম-ব্লকে রেকর্দ; **threshold মিস → Gate 6 অনুযায়ী failed/blocked ঘোষণা**।
3. **Deployment evidence (যখন প্রযোজ্য):** deployed ≠ successful — Langfuse/observability-তে distillation call-হার ও fallback-হার পর্যবেক্ষণ; fallback-হার অস্বাভাবিক হলে পজিশনিং।
4. **Gate 6 (unlock):** সম্পূর্ণ প্রমাণ-রেকর্ড ছাড়া `complete` ট্যাগ নয়; পরবর্তী execution plan কেবল তখনই স্কাউট-টু-প্রোপোজড।

**Rollback:** একক ইমপ্লিমেন্টেশন কমিট revert; runtime kill-switch (env); কোনো data/config migration নেই — পুরনো মেমোরি বৈধ থাকে।

---

## Part 6 — পরবর্তী ক্যান্ডিডেট লাইনেজ (শুধু reference; rule 10 — candidate list ≠ execution queue)

- **#005 (candidate):** ChatGPT-স্টাইল user-visible memory controls (view/edit/delete) — এই প্ল্যানের `metadata["memory_structure"]` উপরে দাঁড়াবে।
- **#006 (candidate):** agent-task-completion auto-distill hook (সব এজেন্ট কলার opt-in)।
- **#007 (candidate):** user-controlled `/compact` + `/map` triggers (Claude Code প্যাটার্ন) — PLAN_002/003-এর উপরে।

> **প্রকাশনা শৃঙ্খলা:** ফাউন্ডারের নির্দেশনায় planning department GitHub API দিয়ে `docs/plans/`-এ ধারাবাহিক ক্যান্ডিডেট প্রকাশ করছে। সব ক্যান্ডিডেট `status: proposed` — Gate 2 অনুমোদন ছাড়া কোনোটিই executable নয়; একবারে কেবল একটি plan active হতে পারে। এই ডকুমেন্ট ইস্যুর পর ইন-প্লেস সম্পাদিত হয় না; সংশোধন v2 sibling।