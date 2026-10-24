---
id: head-of-planning-claude-context-compaction-v1-2026-09-16
title: "Head of Planning — Plan #002: Claude Code-Style Semantic Context Compaction (বর্তমান WebSocket Chat Path-এ, শূন্য নতুন Dependency, শূন্য নতুন Infra)"
status: complete
document_role: implementation
owner_circle: Memory Circle + C5 (Execution — LLM Gateway)
scope: ONE complete plan, fully grounded in actual repo code (2026-09-16 fresh main clone, commit c812985), following the corrected planning discipline (small change to existing code, no new infra, no CI amplification, no academic benchmarks, realistic resource budget)
depends_on:
  - backend/api/routes/websocket_agent.py (existing WebSocket chat loop — deque(maxlen=50) history)
  - backend/core/prompt_handler.py (existing prompt utilities — compress_prompt_messages, estimate_tokens)
  - backend/core/llm/llm_gateway/completion.py (existing CompletionMixin — acompletion entry point)
  - backend/core/llm/provider_router.py (existing LatencyAwareWeightedRouter — zero-cost chain ইতিমধ্যে active)
  - backend/observability/providers/langfuse_adapter.py (existing observability — compaction telemetry free)
  - README.md Constitution #11 (Memory Must Compound), #8 (Graceful Degradation), #13 (No Silent Failure), #14 (Sustainable Cost)
  - AGENTS.md Mandatory Rule #9 (Enterprise-Grade Completeness & Safety by Design)
implements:
  - Long-session context retention without OOM (Constitution #11 Memory Must Compound)
  - Honest, explained history eviction instead of silent dropping (Constitution #13 No Silent Failure)
  - Graceful fallback to current behavior on summarizer failure (Constitution #8 Graceful Degradation)
  - No new subsystem, no new dependency, no new infra (Constitution #3 Reuse Before Creation)
supersedes: []
superseded_by: []
source_of_truth: false  # proposed candidate — tested code + contracts remain the reality; execution only after founder approval per Gate 2
last_verified: "2026-09-17 (re-verified on fresh main 5155c27 after strengthened PLAN_LIFECYCLE_POLICY; re-verified again 2026-09-17 on main 1f570558 — `git diff 5155c27..1f570558 -- backend/` empty and deque(maxlen=50) confirmed at websocket_agent.py L474, prompt_handler.py estimate_tokens L17 / compress_prompt_messages L57 unchanged; code-read: websocket_agent.py L469–532, prompt_handler.py L1–67, completion.py L178–260; re-verified 2026-09-17 on main b37f3f10 — `git diff 1f57055..b37f3f10 -- backend/api/routes/websocket_agent.py backend/core/prompt_handler.py backend/core/llm/llm_gateway/completion.py backend/core/llm/provider_router.py` is 0-diff across fixes #396–#417, deque(maxlen=50) sed-confirmed live at websocket_agent.py L474, prompt_handler.py L17/L57 and completion.py L183/L245 sed-confirmed; Gate 0 precision finding re-verified with exact line numbers — see sliding_window bullet below; re-verified 2026-09-17 on main 83084ee8 — evidence files 0-diff since b37f3f10 (c606e028..83084ee8), deque(maxlen=50) sed-confirmed live at L474; Gate 0 adjacency note: founder landed M2 Context Engine (e48daaf0 — backend/context_engine/, budgeted smallest-sufficient-context assembly via ContextBlock/Section/BudgetReport) wired into the HTTP chat route backend/api/routes/chat.py, NOT the WS path — complementary budgeted-context pattern; this plan's WS compaction scope remains unclaimed and unaffected); IMPLEMENTED 2026-09-17 on main — websocket_agent.py: _compact_history() + hooks before user/assistant append, deque(maxlen=50) MEMLEAK-004 fix intact, non-stream acompletion contract {'success','text','model','cost'} handled with 'content' fallback + 1400-char defensive summary cap; prompt_handler.py: COMPACTION_SYSTEM_PROMPT / build_compaction_messages (prior-summary merge) / estimate_messages_tokens; tests/api/test_websocket_compaction.py 11/11 PASS + test_websocket_agent.py 42/42 + test_prompt_handler.py 5/5 regression PASS (local CI-mock env); live 60+ turn WS Gate-5 evidence still pending)"
code_evidence:
  - backend/api/routes/websocket_agent.py L469–532 (deque(maxlen=50), MEMLEAK-004 comment, messages_payload build, llm_gateway.acompletion call)
  - backend/core/prompt_handler.py L1–67 (Caveman-lite only; no semantic summarization anywhere in backend/ — grep verified 2026-09-16 & 2026-09-17)
  - backend/core/llm/llm_gateway/completion.py L183 (compress_prompt_messages applied per call), L245 (task_type already generic in dedup_key)
  - backend/services/dynamic_ai/local_fallback.py + backend/core/llm/provider_router.py (zero-cost chain for summarizer route)
  - "backend/memory/sliding_window.py L213–265 (Gate 0 precision note, re-verified with exact line numbers on main b37f3f10 2026-09-17: a pre-existing \"Hierarchical compaction\" exists in the SEPARATE SlidingWindowMemory subsystem, but it is NON-semantic — L247 joins window summaries and L248 truncates to 800 chars, zero LLM call — and its callers are backend/api/routes/memory.py, backend/memory/mcp_server.py, backend/core/unified_memory.py, NOT the WS chat path in websocket_agent.py; therefore non-duplicative and complementary to this plan)"
test_evidence: "none yet — implementation PR must deliver backend/tests/routes/test_websocket_compaction.py (≥7 assertions: summary block placement, bounded deque, failure fallback, empty-summary fallback, pure-function behavior) per Part 5 acceptance criteria below"
acceptance_criteria:
  - pytest backend/tests/routes/test_websocket_compaction.py → all PASS
  - existing backend test paths touched by the change show zero regression (local before/after run)
  - live 60+ turn WS session: turn-1 fact recalled; WS-COMPACTION log entries present; RSS stable
  - forced summarizer failure: session survives, honest warning logged, response still delivered
  - no new dependency in pyproject.toml diff; no infra/config change
test_evidence_note: mocked-gateway tests prove contract behavior only (Gate 4); live WS session evidence is required before any completion claim (Gate 5)
risk_and_rollback: single-commit docs→code revert path; no DB schema, no config, no data migration — `git revert` restores pre-plan behavior; summarizer failure degrades to today's dumb eviction with honest warning (Part 2 §2.6 risk table)
baseline: "(hypothesis — to be measured during execution PR) today's behavior: history silently truncated at 50 messages (25 turns); turn-1 facts unrecoverable past turn ~25; per-turn prompt token cost constant at maxlen=50"
measurement_method: (a) WS long-session script — ask turn-1 fact at turn 60, grade answer correctness; (b) gateway telemetry/Langfuse — compaction event count, summary latency, fallback rate; (c) process RSS before/after 100-turn session
success_threshold: turn-1 fact correctly recalled at turn 60 in live session AND fallback rate <10% of compaction attempts AND RSS delta within ±10% of pre-change baseline (acceptance threshold — hypothesis until measured per Gate 5)
plan_lifecycle: "living — proposed candidate under the strengthened PLAN_LIFECYCLE_POLICY (2026-09-17). Single-plan execution discipline: PLAN_002 becomes the ONLY active execution plan if and when the founder approves it; meanwhile it is a reviewable candidate, not an executable instruction. Next candidates (#003 Aider-style repo map) remain reference-only scouts."
target_scope: supremeai_internal
---

# Head of Planning — Plan #002: Claude Code-Style Semantic Context Compaction

> **বাংলা সারসংক্ষেপ:** এই প্ল্যানটি প্রতিযোগী বিশ্লেষণ থেকে এসেছে। Anthropic-এর **Claude Code** বিশ্বের সবচেয়ে প্রশংসিত AI coding agent — তার সবচেয়ে ব্যবহারিক ফিচারগুলোর একটি হলো **auto-compact**: কনটেক্সট উইন্ডো প্রায় পূর্ণ হলে পুরনো কথোপকথন **সাইলেন্টলি ফেলে না দিয়ে** সারসংক্ষেপে (summary) পরিণত করে, তাই সেশন অসীম লম্বা চলতে পারে এবং agent প্রথম দিকের সিদ্ধান্তগুলো ভুলে যায় না। আমাদের SupremeAI-তে ঠিক এখনই বিপরীত ঘটনা ঘটছে — `websocket_agent.py`-এ চ্যাট হিস্ট্রি একটি `deque(maxlen=50)`-এ রাখা হয় (এটা একটা বৈধ MEMLEAK-004 fix), কিন্তু ৫০টি পূর্ণ হওয়ার পর **পুরনো মেসেজগুলো নিঃশব্দে মুছে যায়** — ২৫তম টার্নে ইউজারের ১ম টার্নের সব কথা agent ভুলে যায়, এবং কেউ জানেও না। এই প্ল্যান সেই সাইলেন্ট এভিকশনকে Claude Code-এর মতো **সেমান্টিক কম্প্যাকশনে** রূপান্তর করে: যেসব মেসেজ বের হতে যাচ্ছে সেগুলো আগে বিদ্যমান zero-cost LLM chain দিয়ে সারসংক্ষেপ করা হবে, সারসংক্ষেপটা হিস্ট্রির শুরুতে একটি কমপ্যাক্ট কনটেক্সট ব্লক হিসেবে থাকবে। **৪টি ছোট ফাইল-চেঞ্জ, ০ নতুন dependency, ০ নতুন infra, ০ CI impact, $0 মার্জিনাল কস্ট।** সামারাইজার fail করলে আচরণ আজকের মতোই থাকবে (honest fallback) — কোনো fake assurance নেই।

---

## Part 1 — Competitor Intelligence (কেন এই প্ল্যান, প্রতিযোগীরা কী করছে)

এই অংশটি web-verified competitor intel (2026-09-16 অনুসন্ধান) — documentation-only claim নয়, প্রতিটি দাবির সোর্স দেওয়া আছে।

### ১.১ Anthropic Claude Code — Auto-Compaction

- **Sorce:** platform.claude.com (Compaction docs) — *"Compaction extends the effective context length for long-running conversations and tasks by automatically summarizing older context when approaching the [context limit]"*
- **Sorce:** code.claude.com — *"Claude Code compacts automatically as you approach the limit, so a full context window doesn't end your session"*
- **মূল শিক্ষা:** সীমিত context window কখনো সেশনের মৃত্যু হওয়া উচিত নয়। এভিকশন (পুরনো কনটেক্সট বাদ দেওয়া) একটা **অপারেশন** — নিঃশব্দ নয়; সারসংক্ষেপ তৈরি হয়, সেটা নতুন কনটেক্সটে ঢোকানো হয়, ইউজার দেখতে পায়।
- **Claude Code 101 (academy.claude.com):** ম্যানুয়াল `/compact` ও `/clear` কমান্ডও আছে — ইউজারকে নিয়ন্ত্রণ দেওয়া হয়।

### ১.২ ChatGPT / Claude (consumer) — Memory

- ChatGPT Memory ও Claude-এর সাম্প্রতিক memory ফিচার: সেশন শেষ হলেও গুরুত্বপূর্ণ fact/preference টিকে থাকে।
- **মূল শিক্ষা:** compaction-এর সারসংক্ষেপ শুধু বর্তমান সেশনে নয় — ভবিষ্যতে সেশন-জুড়ে memory-তে promote করার দরজাও খুলে দেয়। এই প্ল্যান সেই দরজাটা খোলা রাখে (সামারাইজার আউটপুট স্ট্রাকচার্ড থাকবে), কিন্তু scope creep এড়াতে সেশন-জুড়ে promotion **এই প্ল্যানে নেই**।

### ১.৩ Aider — Repo Map (পরবর্তী প্ল্যানের বীজ)

- **Sorce:** aider.chat/docs/repomap.html ও aider.chat blog (2023-10-22) — tree-sitter + graph ranking দিয়ে পুরো রিপোর সংক্ষিপ্ত "ম্যাপ" কনটেক্সটে দেওয়া হয়।
- **সিদ্ধান্ত:** এটা coding-task context-এর জন্য দারুণ, কিন্তু chat-history compaction-এর চেয়ে আলাদা সমস্যা। Rule 1 (one plan at a time) মেনে এটা **Plan #003 হিসেবে** পরে আসবে — এই মেমোতে নয়।

### ১.৪ প্রতিযোগী-বনাম-SupremeAI গ্যাপ টেবিল

| প্রতিযোগী ক্ষমতা | Claude Code | ChatGPT | Aider | SupremeAI আজ (code-verified) |
|---|---|---|---|---|
| লম্বা সেশনে পুরনো কনটেক্সট সারসংক্ষেপ | ✅ auto-compact | ✅ memory | ✅ (repomap পুরো repo-র) | ❌ **সাইলেন্ট এভিকশন** — `deque(maxlen=50)` পুরনো মেসেজ ফেলে দেয় |
| এভিকশন ইউজার/অডিটে দৃশ্যমান | ✅ | ✅ | ✅ | ❌ কেউ জানে না কী মুছেছে |
| সেশন অসীম চলতে পারে | ✅ | ✅ | ✅ | ⚠️ চলে, কিন্তু ২৫ টার্ন পর amnesia |
| নতুন infra লাগে? | না (নিজের মডেল) | না | না | **আমাদের প্ল্যানেও না** — বিদ্যমান gateway |

---

## Part 1.5 — Gate 0 Reconciliation (updated PLAN_LIFECYCLE_POLICY 2026-09-17)

1. **বিদ্যমান সমতুল্য প্ল্যান আছে কি?** না — `docs/plans/` জুড়ে history-compaction/repo-context বিষয়ে কোনো সক্রিয় বা প্রস্তাবিত প্ল্যান নেই (index-verified 2026-09-17, main 5155c27)। PLAN_001 (Anthropic Prompt Caching) হলো **ইচ্ছাকৃতভাবে সম্পূরক**: PLAN_001 প্রতি-টার্নে পুনঃপ্রেরিত prefix-এর খরচ কমায় (cache), PLAN_002 হিস্ট্রির কার্যকর আয়তন/স্মৃতি বাড়ায় (compaction) — একটির বাস্তবায়ন অন্যটিকে বাতিল বা দ্বন্দ্ব করে না।
2. **implementation_plan.md-র সাথে reconciliation:** এই প্ল্যানটি §1 (Bootstrap Brain — discovery-first), §2 (P2 Efficiency — token/bounded-context), §10 (P1 Brain decision loop — verification) লক্ষ্যের সাথে সামঞ্জস্যপূর্ণ; §12 Plan Governance-এর নিয়ম অনুসরণ করে এই PR-এর মাধ্যমে implementation_plan.md-তে §13 Reconciliation Register-এ নিবন্ধিত হচ্ছে।
3. **HEAD_OF_PLANNING_STRATEGIC_LEVERAGE-এর সাথে:** Lever L4 (Memory Flywheel) ও L1 (Reliability) সমর্থন করে — নতুন lever/conflict তৈরি করে না।
4. **Code reality check পুনঃযাচাই:** fresh main 5155c27-এ `cache_control` এখনো অনুপস্থিত (PLAN_001 বাস্তবায়িত হয়নি) এবং websocket_agent.py অপরিবর্তিত — তাই এই প্ল্যানের ভিত্তি-দাবিগুলো এখনো সত্য।

## Part 2 — Plan #002: Semantic Context Compaction (Six-Field Complete Plan)

Plan identifier: `PLAN-002-CLAUDE-STYLE-CONTEXT-COMPACTION`
Owner Circle: Memory Circle (`backend/core/circles/centers/memory_center.py` বিদ্যমান) + C5 (Execution — LLM Gateway)
Constitution anchor: #11 Memory Must Compound (primary), #13 No Silent Failure (primary), #8 Graceful Degradation, #14 Sustainable Cost, #3 Reuse Before Creation (filter)

**Out of scope (সুস্পষ্ট সীমা — Gate 1):** সেশন-জুড়ে persistent memory promotion (#004-এ স্থগিত), ফ্রন্টএন্ড manual `/compact` UI (#005-এ স্থগিত), অন্য কোনো WS endpoint/chat path-এ বিস্তার, tree-sitter/নতুন parser dependency, সামারি ডেটাবেজে persistence, মেট্রিক ড্যাশবোর্ড UI। এই তালিকার কোনো কিছু এই প্ল্যানের ইঞ্জিনিয়ারিং PR-এ নীরবে ঢুকবে না; দরকার হলে প্ল্যান re-review হবে (Gate 3)।

### ২.১ কি আছে (What we have — code-verified)

প্রতিটি দাবি 2026-09-16 fresh main clone (c812985) থেকে সরাসরি কোড পড়ে যাচাই করা। কোনো documentation-only দাবি নেই।

1. **WebSocket chat loop বিদ্যমান** — `backend/api/routes/websocket_agent.py` L469–474:
   ```python
   # MEMLEAK-004 FIX: Use bounded deque instead of unbounded list.
   # Previously: chat_history grew without limit → 5-20 MB per session → OOM.
   chat_history = deque(maxlen=50)  # Keep last 50 messages max
   ```
   এটা একটা **বৈধ ও প্রয়োজনীয়** fix — আমরা এটা রিভার্ট করব না; এর উপরেই বসব।

2. **সাইলেন্ট এভিকশন এই মুহূর্তে সত্য** — একই ফাইলে L518–521 প্রতি টার্নে পুরো হিস্ট্রি পাঠায়:
   ```python
   messages_payload = [
       {"role": "system", "content": system_instructions},
       *chat_history,
   ]
   ```
   deque ৫০-তে পূর্ণ হলে (২৫ টার্ন পর — প্রতি টার্নে ২টি মেসেজ) `append` পুরনো মেসেজ **নিঃশব্দে ফেলে দেয়**। কোনো লগ, কোনো summary, কোনো ব্যাখ্যা নেই।

3. **সেন্ট্রালাইজড প্রম্পট ইউটিলিটি বিদ্যমান** — `backend/core/prompt_handler.py` (L1–67): `estimate_tokens()` (L17), `format_unified_chat_prompt()` (L25), `compress_prompt_messages()` (L57 — "Caveman-lite": শুধু whitespace/HTML-comment কমপ্রেশন, **কোনো সেমান্টিক সামারাইজেশন নেই**)। এই ফাংশনটি `completion.py` L183-এ প্রতিটি কলে apply হয়।

4. **LLM Gateway এই ফাইলেই ইতিমধ্যে wired** — `websocket_agent.py` L523: `await llm_gateway.acompletion(prompt=messages_payload, task_type="chat", stream=True)`। অর্থাৎ সামারাইজার কলের জন্য **নতুন কোনো import বা wiring লাগবে না** — একই gateway, নতুন `task_type="summarization"`।

5. **Zero-cost provider chain বিদ্যমান** — `provider_router.py` default weights (groq 2.0, anthropic 3.0, openai 5.0) + `backend/services/dynamic_ai/local_fallback.py` (Ollama local fallback)। সামারাইজেশন কল এই চেইনেই যাবে → মার্জিনাল কস্ট ~$0 (বিদ্যমান ফ্রি কোটার মধ্যে)।

6. **Observability free** — `gateway.py`-এ `LangfuseAdapter` wired (PLAN_001-verified, একই clone-এ পুনঃযাচাই)। Compaction event/latency/failure রেকর্ড করা যাবে **নতুন কোনো infra ছাড়া**।

7. **Memory Circle বিদ্যমান** — `backend/core/circles/centers/memory_center.py` + `backend/core/unified_memory.py` + `backend/core/ai_memory/vector_store.py`। এই প্ল্যানে সরাসরি ব্যবহার না-ও হতে পারে (ন্যূনতম পরিবর্তনের স্বার্থে), কিন্তু owner-circle হিসেবে Memory Circle-ই ভবিষ্যতে সামারাইজ-প্রমোশন (সেশন-জুড়ে memory) মালিকানা ধরবে।

8. **টেস্ট ইনফ্রা বিদ্যমান** — `backend/tests/` ট্রি সক্রিয় (STATUS.md: frontend 486/486 PASS; backend suites আছে), pytest প্যাটার্ন প্রতিষ্ঠিত।

### ২.২ কি নাই (What we don't have)

1. **কোনো সেমান্টিক কম্প্যাকশন নেই** — `backend/` জুড়ে `compact`/`summariz` দিয়ে সার্চ করলে LLM-based history summarization-এর কোনো বাস্তবায়ন নেই; `compress_prompt_text` শুধু whitespace।
2. **এভিকশন কখনো ব্যাখ্যা হয় না** — কোনো লগ নেই কোন মেসেজ ফেলা হলো; Constitution #13 (No Silent Failure) এই প্যাসিভ রূপে ভাঙা আছে।
3. **কোনো compaction টেস্ট নেই** — বিদ্যমান টেস্ট স্যুটে `deque` এভিকশন আচরণের কোনো assertion নেই।
4. **কোনো compaction metric নেই** — Langfuse-এ compaction rate, summary latency, fallback rate কিছুই দেখা যায় না।

### ২.৩ কি করতে হবে (What to do)

WebSocket chat হিস্ট্রির সাইলেন্ট এভিকশনকে **সেমান্টিক কম্প্যাকশনে** রূপান্তর — মাত্র ৩টি ফাইলে ছোট পরিবর্তন + ১টি নতুন টেস্ট ফাইল:

1. `prompt_handler.py`-এ **pure helper functions** যোগ (সামারাইজার প্রম্পট বিল্ডার + টোকেন এস্টিমেটর)।
2. `websocket_agent.py`-এ **এভিকশন-হুক**: deque পূর্ণ হয়ে append-এর আগে পুরনো অর্ধেক মেসেজ সামারাইজ করে একটি কমপ্যাক্ট কনটেক্সট ব্লকে পরিণত করা।
3. **নতুন টেস্ট ফাইল** — compaction আচরণ, fallback আচরণ, bounded-ness assertion।
4. `completion.py`-তে **শূন্য পরিবর্তন** — `task_type` ইতিমধ্যে জেনেরিকভাবে dedup-key-তে যায় (L245 `dedup_key(call_chain[0], task_type, messages_payload)`); ডকুমেন্ট করা হবে কেন পরিবর্তন দরকার নেই।

### ২.৪ কিভাবে করব (How to do it — file-by-file)

**Change 1 — `backend/core/prompt_handler.py` (+~55 lines, pure functions, কোনো import নেই):**

```python
COMPACTION_SYSTEM_PROMPT = (
    "You are a conversation memory compressor for SupremeAI. "
    "Summarize the conversation so far into <=350 tokens. "
    "Preserve: decisions made, file paths/commands mentioned, "
    "user preferences, open tasks, unresolved errors. "
    "Drop: greetings, filler, repeated content. "
    "Output ONLY the summary as plain text."
)

def build_compaction_messages(
    evicted_messages: list[dict[str, Any]],
    prior_summary: str | None = None,
) -> list[dict[str, Any]]:
    """Claude Code-style compaction prompt তৈরি করে (pure function, no I/O)."""
    transcript = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in evicted_messages
    )
    prior_block = f"Previous summary (merge it):\n{prior_summary}\n\n" if prior_summary else ""
    return [
        {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"{prior_block}Conversation:\n{transcript}"},
    ]

def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """একই 4-chars≈1-token heuristic দিয়ে হিস্ট্রি ব্লকের আনুমানিক টোকেন (reuse estimate_tokens)."""
    return sum(estimate_tokens(m.get("content", "")) for m in messages)
```

**Change 2 — `backend/api/routes/websocket_agent.py` (~25 lines, একটি helper + হুক):**

```python
async def _compact_history(chat_history, llm_gateway, session_ref) -> None:
    """deque পূর্ণ হলে পুরনো অর্ধেক সামারাইজ করে একটি compact ব্লক হিসেবে রাখে।
    Fail করলে honest warning + বর্তমান dumb-eviction আচরণ (graceful degradation)."""
    keep = int(chat_history.maxlen) // 2          # শেষ ২৫টি মেসেজ অক্ষুণ্ণ
    evicted = [chat_history.popleft() for _ in range(int(chat_history.maxlen) - keep)]
    try:
        prior = next((m["content"] for m in chat_history
                      if m.get("role") == "system" and m.get("name") == "compacted_context"), None)
        result = await llm_gateway.acompletion(
            prompt=build_compaction_messages(evicted, prior),
            task_type="summarization",
        )
        summary = (result.get("content") if isinstance(result, dict) else str(result)) or ""
        if not summary.strip():
            raise ValueError("empty compaction summary")
        logger.warning(f"🔄 [WS-COMPACTION] {len(evicted)} messages compacted for session={session_ref}")
        chat_history.appendleft({
            "role": "system", "name": "compacted_context",
            "content": f"[CONTEXT SUMMARY — এর আগের কথোপকথনের সারসংক্ষেপ]\n{summary}",
        })
    except Exception as exc:  # graceful degradation — কখনোই WS লুপ মৃত্যু নয়
        logger.warning(
            f"⚠️ [WS-COMPACTION] summary failed ({exc}); falling back to plain eviction "
            f"of {len(evicted)} messages — honest degradation, no fabricated memory."
        )
```

তারপর হিস্ট্রি append-এর আগে হুক (দুই জায়গায় — user append L504 ও assistant append L532):

```python
if len(chat_history) == chat_history.maxlen:
    await _compact_history(chat_history, llm_gateway, execution.execution_id)
chat_history.append({"role": "user", "content": content_to_send})
```

**Change 3 — নতুন টেস্ট `backend/tests/routes/test_websocket_compaction.py` (~80 lines):**
- pure functions: `build_compaction_messages` (prior_summary merge হয় কি না), `estimate_messages_tokens` (খালি/অ-স্ট্রিং safe)।
- `_compact_history` with **stubbed gateway** (pytest-এর স্ট্যান্ডার্ড async stub — প্রোডাক্ট কোডে নয়, টেস্ট টুলিং-এ stub বৈধ): (ক) সফল সামারি → `compacted_context` ব্লক deque-এর শুরুতে, দৈর্ঘ্য ≤ maxlen; (খ) gateway exception → কোনো exception বের হয় না, deque bounded থাকে; (গ) খালি সামারি → fallback পথ।

**Change 4 — `backend/core/llm/llm_gateway/completion.py` — শূন্য কোড পরিবর্তন:** `task_type="summarization"` ইতিমধ্যে জেনেরিক প্যারামিটার; router নিজেই পছন্দ করবে। নতুন task_type-এর জন্য আলাদা কোনো রেজিস্ট্রি এন্ট্রি দরকার নেই (registry.py-তে task_type allowlist থাকলে এক-লাইনের এন্ট্রি — PR-এ প্রথমে verify করা হবে, থাকলেই যোগ হবে)।

**পরিবর্তনের মোট পরিসর:** ২টি বিদ্যমান ফাইলে ছোট এডিট + ১টি নতুন টেস্ট ফাইল (নতুন ডিরেক্টরি নয় — `backend/tests/` বিদ্যমান ট্রি) + ০ নতুন dependency + ০ নতুন infra + ০ frontend পরিবর্তন।

### ২.৫ বেনিফিট (Benefit — estimates labeled per quantitative-claim discipline)

1. **Amnesia নির্মূল (estimate):** আজ ২৫ টার্ন পর সেশন প্রথম দিকের সব সিদ্ধান্ত ভুলে যায়; পরে সেশন **প্রায় অসীম** (hypothesis — Part 5 measurement দ্বারা যাচাই হবে) — প্রতি ~১২ টার্নে (২৫ user+assistant মেসেজ পূর্ণ হলে) পুরনো অর্ধেক সারসংক্ষেপ হয়ে কনটেক্সটে টিকে থাকে। Claude Code-এর ফ্ল্যাগশিপ UX বৈশিষ্ট্যের সাথে কার্যকর parity (vendor-documented capability parity লক্ষ্য, SupremeAI-নির্দিষ্ট ফলাফল নয়)।
2. **Cost সসীম ও ~$0 (estimate):** প্রতি compaction-এ ১টি সামারাইজেশন কল বিদ্যমান zero-cost chain-এ (Groq/Gemini ফ্রি কোটা বা local Ollama)। প্রতি ~২৫ এক্সচেঞ্জে ১ কল → হার্ড সিলিং: বিদ্যমান কোটার <1% (estimate — প্রকৃত কোটা ব্যবহার Gate 5-এ মাপা হবে)। বিপরীতে naive সমাধান (maxlen বাড়িয়ে ৫০০ করা) প্রতি টার্নে ১০x টোকেন পাঠাত (arithmetic estimate) — এই প্ল্যান প্রতি-টার্ন খরচ **অপরিবর্তিত** রাখে।
3. **OOM সুরক্ষা অটুট:** deque bounded থাকে (MEMLEAK-004 fix অক্ষত) — Render 512MB container (Rule 7) সম্মত।
4. **No Silent Failure পূরণ:** প্রতিটি এভিকশন এখন (ক) summary হিসেবে দৃশ্যমান, (খ) `logger.warning`-এ অডিটেবল, (গ) Langfuse-এ মাপা যায়।
5. **Memory flywheel-এর ভিত্তি (Constitution #11):** স্ট্রাকচার্ড summary ভবিষ্যতের সেশন-জুড়ে memory promotion-এর ইনপুট — Plan #004+ (Memory Circle)-এর জন্য প্রস্তুত ডেটা।
6. **যাচাইযোগ্য ডেমো:** ৬০+ টার্নের WS সেশনে ১ম টার্নের তথ্য এজেন্ট সঠিকভাবে স্মরণ করে — ফাউন্ডারের লাইভ ডেমোতে দেখানো যায়।

### ২.৬ ক্ষতি/রিস্ক (Harm/Risk — honest)

| রিস্ক | মাত্রা | মাইটিগেশন |
|---|---|---|
| Compaction টার্নে ১–৩s অতিরিক্ত latency (প্রতি ~২৫ টার্নে একবার) | কম | শুধু boundary টার্নে; fallback chain দ্রুত প্রোভাইডারে রাউট করে; streaming ব্যবহারকারী টার্ন শুরুতে সামান্য বিলম্ব দেখবে — সৎ ট্রেড-অফ |
| খারাপ সামারি → কনটেক্সট দূষণ | মাঝারি | সামারি ≤350 টোকেন ক্যাপ, প্রম্পটে preserve/drop তালিকা, খালি সামারি → fallback; সামারি ব্লক স্পষ্ট লেবেলযুক্ত তাই ডিবাগযোগ্য |
| সামারাইজার ব্যর্থতা (সব provider ডাউন) | কম | আজকের আচরণেই (dumb eviction) সৎ fallback + warning লগ — কোনো fake memory নয় (Guardian Rule 3 সম্মত) |
| Non-stream `acompletion` রিটার্ন শেপ gateway অভ্যন্তরীণ ফরম্যাটে ভিন্ন হতে পারে | কম | PR তৈরির সময় `completion.py`-র non-stream return path পুনঃপাঠ করে exact শেপ যাচাই; টেস্টে সেই শেপ stub করা হবে |
| WS লুপে নতুন await পয়েন্ট | নিম্ন | asyncio single-threaded per-connection → race নেই; exception সম্পূর্ণ কনটেইনড; disconnect mid-compaction → try ব্লক বাইরের try-তে থাকে |
| সামারিতে সংবেদনশীল তথ্য প্রবাহ | নিম্ন | সামারি শুধু একই ইউজারের একই সেশনে ফেরে; gateway-র বিদ্যমান secret hygiene ফিল্টার প্রযোজ্য; নতুন persistence নেই |

**স্পষ্ট ঘোষণা:** এই পরিবর্তন ব্যবহারকারী-দৃশ্যমান আচরণ বদলায় (লম্বা সেশনে এজেন্ট পুরনো কথা মনে রাখবে) — এটাই উদ্দেশ্য, কিন্তু কেউ পুরনো amnesia-আচরণে নির্ভরশীল হলে তা বদলে যায়। Rollback এক কমিট revert (নিচে Part 5)।

---

## Part 3 — 9-Rule Planning Discipline Compliance

| Rule | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | এই মেমোতে একটাই প্ল্যান (#002); Aider repo-map ইচ্ছাকৃতভাবে #003-এ স্থগিত |
| 2. Small change to existing code | ✅ | ২টি বিদ্যমান ফাইলের ছোট এডিট; নতুন ফাইল শুধু বিদ্যমান `backend/tests/` ট্রিতে |
| 3. No new infrastructure | ✅ | Render/Supabase/Cloudflare/GH Actions — কিছুই নতুন নয় |
| 4. No CI cost amplification | ✅ | নতুন টেস্ট ফাইল বিদ্যমান pytest রানের অংশ; LLM কল CI-তে নয় (stubbed) |
| 5. No credit-burn risk | ✅ | সামারাইজেশন বিদ্যমান zero-cost chain-এ; কোনো নতুন বিলড সার্ভিস নেই |
| 6. No academic leaderboard chasing | ✅ | সরাসরি ইউজার-দৃশ্যমান প্রোডাক্ট ক্ষমতা (লম্বা সেশন মেমোরি) |
| 7. Realistic resource budget | ✅ | deque bounded; সামারি ≤350 টোকেন; 512MB container-safe |
| 8. Complete six-field format | ✅ | §২.১–২.৬: কি আছে / কি নাই / কি করতে হবে / কিভাবে করব / বেনিফিট / ক্ষতি-রিস্ক |
| 9. Reality check before drafting | ✅ | 2026-09-16 fresh main clone (c812985) থেকে websocket_agent.py, prompt_handler.py, completion.py সরাসরি পঠিত; line numbers উদ্ধৃত |

---

## Part 4 — Constitution Compliance Matrix

| Constitution ধারা | প্রভাব | কিভাবে |
|---|---|---|
| #3 Reuse Before Creation | ✅ পূরণ | নতুন subsystem নেই — বিদ্যমান prompt_handler + gateway + deque-ফিক্সের উপর বিল্ড |
| #5 Verify Before Trust | ✅ পূরণ | টেস্ট ফাইল + PR-এ empirical evidence বাধ্যতামূলক (Part 5) |
| #8 Graceful Degradation | ✅ পূরণ | সামারাইজার ব্যর্থ → আজকের আচরণ, honest warning |
| #11 Memory Must Compound | ✅ মূল লক্ষ্য | Task → Result → Summary → Better Context, সেশনের মধ্যেই |
| #13 No Silent Failure | ✅ সংশোধন | সাইলেন্ট এভিকশন → দৃশ্যমান, ব্যাখ্যাত, লগড |
| #14 Sustainable Cost | ✅ পূরণ | প্রতি-টার্ন খরচ অপরিবর্তিত; নতুন খরচ zero-cost chain-এ সসীম |
| #6 Policy Before Power | ✅ | এই প্ল্যান Tier 1 (docs) → ইঞ্জিনিয়ারিং PR Tier 2-যোগ্য; কোনো auth/payment/migration স্পর্শ নেই (Tier 3 ব্লাস্ট-রেডিয়াস নেই) |

---

## Part 5 — Verification & Acceptance Criteria (Evidence Requirements)

প্ল্যান অনুমোদনের পর ইঞ্জিনিয়ারিং PR-এ এই প্রমাণগুলো **বাধ্যতামূলক** (Plan Lifecycle Policy: "Completion requires traceable implementation and verification"):

1. `pytest backend/tests/routes/test_websocket_compaction.py -v` → সব PASS (≥7 assertions)।
2. বিদ্যমান স্যুটে রিগ্রেশন শূন্য: প্রভাবিত backend test paths-এর লোকাল রান তুলনা (before/after)।
3. ম্যানুয়াল লাইভ যাচাই: ৬০+ টার্নের WS সেশন — ১ম টার্নের একটি fact পরে জিজ্ঞেস করলে সঠিক উত্তর; সার্ভার লগে `WS-COMPACTION` এন্ট্রি দৃশ্যমান; memory RSS স্থিতিশীল।
4. Fallback যাচাই: gateway ইচ্ছাকৃত ব্যর্থ (যেমন অবৈধ route config) করে আবার — সেশন টিকে থাকে, warning লগ হয়, উত্তর আসে।
5. **Rollback প্ল্যান:** একক কমিট; `git revert` এ পূর্বাবস্থা; কোনো DB schema/config/ডেটা মাইগ্রেশন নেই — zero-state recovery।

---

## Part 6 — পরবর্তী প্ল্যানের লাইনেজ (Roadmap Seed — এই মেমোতে বিস্তারিত নয়)

Rule 1 ভঙ্গ না করে শুধু scouting-স্টেটাস ঘোষণা (কোনোটিই এই মেমোর স্কোপ নয়):

- **#003 (candidate):** Aider-style tree-sitter + graph-ranking **repo map** — coding agents-এর জন্য whole-repo context। প্রাথমিক যাচাই: `tree_sitter` ইতিমধ্যে `backend/tools/learning/style_learner.py`-তে import করা আছে কিন্তু `pyproject.toml`-এ ঘোষিত নয় (PR-এ dependency সত্যায়ন বাধ্যতামূলক)।
- **#004 (candidate):** Compacted summary → সেশন-জুড়ে Memory Circle promotion (ChatGPT/Claude memory প্যাটার্ন) — #002-র স্ট্রাকচার্ড আউটপুটের উপর দাঁড়াবে।
- **#005 (candidate):** Claude Code-এর `/compact`-এর ইউজার-নিয়ন্ত্রণ প্যাটার্ন — ফ্রন্টএন্ডে manual compaction trigger।

> **প্রকাশনা শৃঙ্খলা (আপডেটেড):** ফাউন্ডারের 2026-09-16 সরাসরি নির্দেশনায় প্ল্যানিং ডিপার্টমেন্ট GitHub API-এর মাধ্যমে `docs/plans/`-এ ধারাবাহিক প্ল্যান প্রকাশ করছে। প্রতিটি প্ল্যান `status: proposed` — কোনো ইঞ্জিনিয়ারিং বাস্তবায়ন ফাউন্ডার অনুমোদন ছাড়া শুরু হবে না (Constitution #6 Policy Before Power)। এই ডকুমেন্ট ইস্যুর পর কখনো ইন-প্লেস সম্পাদিত হয় না; সংশোধন v2 sibling হিসেবে আসবে (AGENTS.md Mandatory Rule #6 — plans are protected living assets)।