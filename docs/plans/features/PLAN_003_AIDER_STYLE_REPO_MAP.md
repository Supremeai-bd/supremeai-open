---
id: head-of-planning-aider-repo-map-v1-2026-09-17
title: "Head of Planning — Plan #003: Aider-Style Repo Map (stdlib-ast, শূন্য নতুন Dependency) — DynamicPlanningEngine-এর Epistemic Probe-কে সত্যিকারের কোডবেস-দৃষ্টি দেওয়া"
status: complete
document_role: implementation
owner_circle: C5 (Execution — LLM Gateway) + Task Circle (backend/services/dynamic_planner.py মালিকানা)
scope: "ONE complete plan, fully grounded in actual repo code (2026-09-17 fresh main 5155c27), following the corrected planning discipline AND the strengthened PLAN_LIFECYCLE_POLICY (2026-09-17): single-plan execution, Gate 0–6, quantitative-claim labeling, explicit out-of-scope"
depends_on:
  - backend/core/markdown_indexer.py (existing singleton-indexer pattern — এই প্ল্যান একই প্যাটার্ন অনুসরণ করে)
  - backend/core/embeddings.py (existing local-first EmbeddingEngine — all-MiniLM-L6-v2 + hash_vectorize zero-cost fallback)
  - backend/services/dynamic_planner.py L117–124 (existing Epistemic State Probe node — capability="probe_system_state")
  - backend/core/llm/advanced_model_router.py L137–162 (existing DomainExpertAnalyzer.classify_domain → ExpertType.CODER)
  - backend/services/intent_deciphering.py L87–101 (existing domain wiring into IntentAnalysis)
  - Python stdlib ast/pathlib/re/math (বিদ্যমান runtime — কোনো নতুন package নয়)
  - README.md Constitution #3 (Reuse Before Creation), #4 (Dynamic Discovery), #5 (Verify Before Trust), #14 (Sustainable Cost)
  - AGENTS.md Mandatory Rule #9 (Enterprise-Grade Completeness & Safety by Design)
implements:
  - Dev/coding টাস্কের agent-কে টোকেন-বাজেটের মধ্যে পুরো কোডবেসের সিম্বল-লেভেল ম্যাপ দেওয়া (Constitution #4 Dynamic Discovery)
  - implementation_plan.md §1-এর discovery-first প্রতিশ্রুতির বাস্তব ভিত্তি (Constitution #3 Reuse Before Creation)
  - Epistemic State Probe-কে ঘোষণা থেকে বাস্তব ক্ষমতায় রূপান্তর (Constitution #5 Verify Before Trust)
  - নতুন subsystem নয় — বিদ্যমান indexer/embedding/planner প্যাটার্নের সংযোজন (Constitution #3)
supersedes: []
superseded_by: []
source_of_truth: false
implementation_evidence: "IMPLEMENTED 2026-09-17 on main — core/code_indexer.py (new, stdlib-only): CodeIndexer singleton (markdown_indexer pattern), bounded walk (_MAX_FILES=2000, _MAX_FILE_BYTES=100KB, _MAX_TOTAL_BYTES=64MB, _MAX_SYMBOLS=200k — the 512MB cap-guard; files_skipped_cap honest stat), top-level ast symbol extraction (Cls:/Def:), intra-package edge resolution (absolute dotted module → file-or-__init__ exists-check + relative-import sibling fallback — covers flat and nested packages, beyond plan sketch), pure-Python PageRank (20 iters, damp 0.85, dangling-mass-kept), render_repo_map budget-bounded with cosine goal-boost via existing core/embeddings (batch encode, boost capped ×1.5, graceful pure-rank fallback); services/dynamic_planner.py: CODER-domain Epistemic Probe input_params now carries repo_map (guard-protected try/except; non-CODER byte-identical; ExpertType+Path imports added); tests/core/test_code_indexer.py 9/9 (symbols, edges, PageRank ordering, budget, parse_failures, honest empty map, cap-guard, goal-boost no-crash, singleton); tests/services/test_dynamic_planner.py zero regression (6/6); live smoke Gate-5: backend self-index 1836 files, 0 parse_failures, 8953 symbols, 3213 edges, 12.7MB source, build 2.47s (<5s threshold), render 0.29s, map 3979/4000 chars, hub files present; CODER probe end-to-end repo_map injected / general probe unchanged (asserted)"
last_verified: "2026-09-17 (fresh main 5155c27 code-read: markdown_indexer.py L18–29, embeddings.py L18–66, dynamic_planner.py L108–124, advanced_model_router.py L137–162, intent_deciphering.py L87–101; backend py-file count = 1819; grep-verified no existing CodeIndexer; tree_sitter imported in style_learner.py L56 but NOT declared in pyproject.toml); re-verified 2026-09-17 on main b37f3f10 — embeddings.py drifted via eb589909 (hash_vectorize → process-stable blake2b _stable_hash — evidence STRENGTHENED: fallback embedding now deterministic across workers/restarts), new lines: _LOCAL_MODEL_NAME L19, get_local_encoder L36, _stable_hash L50, hash_vectorize L62–81; markdown_indexer.py / dynamic_planner.py / advanced_model_router.py / intent_deciphering.py / style_learner.py all 0-diff and line-confirmed; backend py-file count now 1827; grep re-confirmed no CodeIndexer exists); re-verified 2026-09-17 on main 83084ee8 — all evidence files 0-diff since b37f3f10 (c606e028..83084ee8), all cited lines hold; target_scope: supremeai_internal recorded per founder 3-tier taxonomy (ab0f7d51)"
code_evidence:
  - backend/core/markdown_indexer.py L18–29 — MarkdownIndexer singleton + get_instance + EmbeddingEngine.get_instance pattern (এই প্ল্যানের CodeIndexer হুবহু এই প্যাটার্ন মেনে চলবে)
  - backend/core/embeddings.py L19–81 — _LOCAL_MODEL_NAME "all-MiniLM-L6-v2" (384-dim), get_local_encoder, hash_vectorize pure-Python zero-cost fallback (L62–81; since eb589909 uses process-stable blake2b _stable_hash at L50 — deterministic vectors, Plan #003-এর map ranking-এর জন্য আরও ভালো)
  - backend/services/dynamic_planner.py L117–124 — Epistemic State Probe TaskNode, capability="probe_system_state", input_params এখন শুধু {"goal", "domain"} — কোনো কোডবেস-দৃষ্টি নেই; probe_system_state নামক কোনো executor backend-এ grep-অনুযায়ী অন্যত্র নেই
  - backend/core/llm/advanced_model_router.py L137–162 — classify_domain → ExpertType.CODER (zero-cost keyword matching; Bengali script check সহ)
  - backend/tools/learning/style_learner.py L56–62 — tree_sitter try/except graceful import (dependency ঘোষিত নয় — প্রি-এক্সিস্টিং hygiene নোট, এই প্ল্যানের scope নয়)
  - implementation_plan.md §1 — "discover_reusable_implementation is logically available for every dev task" — backend-এ এই নামে কোনো Python symbol নেই (grep-verified 2026-09-17) — aspiration, implemented capability নয় (policy reconciliation rule 7 অনুযায়ী চিহ্নিত)
test_evidence: none yet — implementation PR must deliver backend/tests/core/test_code_indexer.py (acceptance_criteria নিচে; mocked টেস্ট contract behavior প্রমাণ করে, real-workload প্রমাণ নয় — Gate 4)
acceptance_criteria:
  - pytest backend/tests/core/test_code_indexer.py → all PASS: (ক) সিম্বল এক্সট্র্যাকশন (class/function), (খ) intra-package import edge resolution, (গ) PageRank hub-file ranking, (ঘ) budget respected, (ঙ) malformed file → parse_failures গণনা, (চ) empty dir → honest empty map
  - dynamic_planner-এর বিদ্যমান টেস্ট (backend/tests/services/test_dynamic_planner.py) → zero regression
  - live smoke: backend নিজের উপর render_repo_map() → 1819-file রিপোর জন্য map তৈরি, স্ট্যাটস honest (files_indexed>1000, parse_failures<50 — threshold নিচে)
  - non-CODER domain intent-এ planner আউটপুট অপরিবর্তিত (repo_map ইনজেকশন হয় না)
  - pyproject.toml diff = শূন্য (কোনো নতুন dependency নেই)
test_evidence_note: Gate 4 অনুযায়ী টেস্ট contract প্রমাণ করে; Gate 5 অনুযায়ী live backend-ওয়াইড index লেটেন্সি/সাইজ মাপা বাধ্যতামূলক
risk_and_rollback: wiring একটি guard-যুক্ত try/except ব্লকে — CodeIndexer ব্যর্থ হলে probe node আজকের মতোই চলে (no fake repo_map); rollback = একক revert; কোনো DB/config/ডেটা পরিবর্তন নেই; indexer শুধু-পঠন (read-only) — কোনো mutation নেই
baseline: "(hypothesis — execution PR-এ মাপা হবে) আজ: dev-task probe-এর কাছে কোনো কোডবেস সিম্বল-কনটেক্সট নেই; agent ফাইল-পাথ অনুমান করে বা বারবার read করে"
measurement_method: (a) render_repo_map() সময় (time.perf_counter, backend নিজের উপর), (b) map আউটপুট সাইজ vs budget, (c) নমুনা dev-intent-এ map-এ প্রাসঙ্গিক ফাইল থাকল কি না (manual grade, 10-sample), (d) PageRank top-20-তে পরিচিত hub ফাইল (orchestrator.py, gateway.py জাতীয়) থাকল কি না
success_threshold: backend-ওয়াইড index তৈরি ≤5s (acceptance threshold, Render 512MB container-সামঞ্জস্য) এবং 10-sample dev-intent গ্রেডে ≥7 স্যাম্পলে প্রাসঙ্গিক ফাইল map-এ উপস্থিত — উভয়ই hypothesis, Gate 5-এ measured result হবে
plan_lifecycle: living — implemented 2026-09-17 on main (see implementation_evidence); single-plan discipline honored
target_scope: supremeai_internal
---

# Head of Planning — Plan #003: Aider-Style Repo Map

> **বাংলা সারসংক্ষেপ:** এই প্ল্যান ওপেন-সোর্স জগতের সবচেয়ে প্রশংসিত AI pair-programmer **Aider**-এর সবচেয়ে শক্তিশালী আবিষ্কার — **Repository Map** — থেকে অনুপ্রাণিত। Aider tree-sitter দিয়ে প্রতিটি ফাইলের সিম্বল (class/function) বের করে, ফাইলগুলোর মধ্যে import-সম্পর্কের একটা গ্রাফ বানায়, সেই গ্রাফে **গ্রাফ-র‍্যাংকিং (PageRank-জাতীয়)** চালিয়ে বোঝে কোন ফাইল রিপোর "কেন্দ্র" — তারপর টোকেন-বাজেটের মধ্যে সেরা অংশের একটা সংক্ষিপ্ত ম্যাপ LLM-কে দেয়। ফলে Aider **পুরো রিপো দেখে** কাজ করে, অথচ কনটেক্সট খুব ছোট থাকে। Cursor ও Claude Code-ও একই জাতীয় codebase-indexing ক্ষমতা তাদের প্রোডাক্টের মেরুদণ্ড করেছে (vendor-documented)। SupremeAI-তে আমাদের `DynamicPlanningEngine` প্রতিটি টাস্কের শুরুতে একটা "Epistemic State Probe" নোড বানায় যার কথিত কাজ "Inspect system state, **relevant files**, and contracts" — কিন্তু বাস্তবে সেই প্রোবের হাতে **কোনো কোডবেস-দৃষ্টি নেই** (input_params-এ শুধু goal/domain স্ট্রিং)। এই প্ল্যান Python **stdlib `ast`** দিয়ে (tree-sitter-এর মতো ভারী কিছু ছাড়াই, **শূন্য নতুন dependency**) একই ধারণা বাস্তবায়ন করে সেই প্রোবে সত্যিকারের চোখ জুড়ে দেবে। **১টি নতুন ফাইল (বিদ্যমান ডিরেক্টরিতে, বিদ্যমান প্যাটার্নে) + ১ ফাইলে ~১০ লাইনের guard-যুক্ত wiring + ১টি টেস্ট ফাইল; ০ নতুন dependency; ০ নতুন infra; ০ LLM কল।**

---

## Part 0 — Competitor & Open-Source Intelligence (কেন এই প্ল্যান)

সব বাহ্যিক দাবি web-verified, তারিখসহ (Gate: external evidence policy)।

### ০.১ Aider Repository Map (ওপেন-সোর্স, সবচেয়ে সরাসরি সোর্স)

- **Sorce (vendor-documented):** aider.chat/docs/repomap.html এবং aider.chat blog "Building a better repository map with tree sitter" (2023-10-22; 2026-09-16 অনুসন্ধানে পুনঃযাচাইকৃত)।
- **কীভাবে কাজ করে (vendor-published):** tree-sitter দিয়ে সিম্বল এক্সট্র্যাকশন → ফাইল-টু-ফাইল সিম্বল-রেফারেন্স গ্রাফ → **graph ranking algorithm** (PageRank-জাতীয়) → টোকেন বাজেটে র‍্যাংক-ক্রমে সংক্ষিপ্ত আউটলাইন রেন্ডার।
- **মূল শিক্ষা:** "পুরো কোডবেস পড়া" আর "পুরো কোডবেস কনটেক্সটে পাঠানো" এক নয় — র‍্যাংকিং করা সংক্ষিপ্ত ম্যাপ ছোট বাজেটে whole-repo awareness দেয়।

### ০.২ Cursor / Claude Code (প্রতিযোগী, vendor-documented capability)

- Cursor-এর codebase indexing ও Claude Code-এর codebase exploration (Grep/Glob/structure awareness) — উভয়েরই মূল বিক্রয়-বিন্দু: agent **কোডবেস-জুড়ে চোখ** রাখে, শুধু ওপেন ফাইলে সীমাবদ্ধ নয় (vendor ডকুমেন্টেড capability; 2026-09-16 অনুসন্ধান)।
- **মূল শিক্ষা:** প্রতিযোগীদের জন্য codebase-awareness এখন table-stakes — SupremeAI "governed task-execution platform" হিসেবে নিজের dev-domain টাস্কে এটার ভিত্তি না থাকলাে discovery-first দাবি দুর্বল থাকে।

### ০.৩ SupremeAI-বনাম-প্রতিযোগী গ্যাপ টেবিল

| ক্ষমতা | Aider | Cursor | Claude Code | SupremeAI আজ (code-verified 5155c27) |
|---|---|---|---|---|
| সিম্বল-লেভেল কোডবেস ম্যাপ | ✅ | ✅ (indexing) | ✅ (exploration) | ❌ নেই — `probe_system_state`-এর input-এ শুধু স্ট্রিং |
| গ্রাফ-র‍্যাংকিং (গুরুত্বপূর্ণ ফাইল আগে) | ✅ | (proprietary) | (proprietary) | ❌ |
| টোকেন-বাজেটে ম্যাপ রেন্ডার | ✅ | — | — | ❌ |
| নতুন infra লাগে? | না | — | — | **আমাদের প্ল্যানেও না** (stdlib ast + বিদ্যমান local embeddings) |

---

## Part 0.5 — Gate 0 Reconciliation (strengthened PLAN_LIFECYCLE_POLICY)

1. **বিদ্যমান সমতুল্য প্ল্যান/কোড আছে কি?** না — `docs/plans/` জুড়ে repo-map/code-indexing বিষয়ে কোনো proposed/active প্ল্যান নেই (index-verified 2026-09-17); backend-এ `CodeIndexer` নামে কোনো module নেই (grep-verified)। `markdown_indexer.py` শুধু markdown কর্পাস ইনডেক্স করে — কোড নয়; তাই সমতুল্য নয়, প্যাটার্ন-সোর্স।
2. **implementation_plan.md-র সাথে:** এই প্ল্যান §1 (Bootstrap Brain: "discover_reusable_implementation for every dev task" — বর্তমানে aspiration, code-evidence উপরে), §7 (External Implementation Discovery-র অভ্যন্তরীণ বিকল্প), §10 P1 (Brain decision loop) সরাসরি সমর্থন করে। §13 Reconciliation Register-এ নিবন্ধিত হচ্ছে (এই PR-এ)।
3. **PLAN_001/PLAN_002-এর সাথে:** ইচ্ছাকৃতভাবে সম্পূরক — PLAN_001 = কস্ট (cache), PLAN_002 = সেশন-স্মৃতি (compaction), PLAN_003 = কোডবেস-দৃষ্টি (repo map)। একে অপরকে বাতিল বা দ্বন্দ্ব করে না; তিনটি ভিন্ন সমস্যা-স্পেস।
4. **HEAD_OF_PLANNING_STRATEGIC_LEVERAGE-এর সাথে:** Lever L2 (Orphan Spine — ঘোষিত কিন্তু অসম্পূর্ণ ক্ষমতা) ও L4 (Memory Flywheel-এর discovery ভিত্তি) সমর্থন করে।
5. **প্রি-এক্সিস্টিং hygiene নোট (scope-বহি):** `backend/tools/learning/style_learner.py` L56-এ `tree_sitter` import করে কিন্তু `pyproject.toml`-এ ঘোষিত নয় (graceful try/except)। এই প্ল্যান সেটি স্পর্শ করে না; ভবিষ্যতের এক-লাইনের hygiene PR-এর প্রার্থী (reconciliation rule 6 অনুযায়ী code-evidence সহ নোটকৃত)।

---

## Part 1 — Complete Plan (Six-Field)

Plan identifier: `PLAN-003-AIDER-STYLE-REPO-MAP`
Constitution anchor: #3 Reuse Before Creation (primary), #4 Dynamic Discovery (primary), #5 Verify Before Trust, #14 Sustainable Cost

**Out of scope (সুস্পষ্ট সীমা — Gate 1):** tree-sitter/নতুন parser dependency যোগ; non-Python ভাষার সিম্বল-এক্সট্র্যাকশন (v1-এ ফাইল-লেভেল presence only); MCP tool হিসেবে এক্সপোজ (ভবিষ্যৎ প্রার্থী); ফ্রন্টএন্ড UI; markdown_indexer-এর স্পর্শ; style_learner-এর tree_sitter hygiene ফিক্স; persistent index cache/DB; planner-এর অন্য কোনো নোড পরিবর্তন। এগুলোর কোনোটি ইঞ্জিনিয়ারিং PR-এ নীরবে ঢুকবে না (Gate 3)।

### ১.১ কি আছে (What we have — code-verified on 5155c27)

1. **Indexer-প্যাটার্ন প্রতিষ্ঠিত** — `backend/core/markdown_indexer.py` L18–29: singleton `get_instance(root_dir)`, incremental chunks, `EmbeddingEngine.get_instance()` ব্যবহার। নতুন `CodeIndexer` হুবহু এই গৃহীত প্যাটার্নে হবে।
2. **Local-first embeddings বিদ্যমান** — `backend/core/embeddings.py`: `all-MiniLM-L6-v2` (SentenceTransformer, lazy), ব্যর্থ হলে `hash_vectorize` pure-Python fallback (শূন্য-খরচ, 384-dim)। ফাইল-সিগনেচার embedding + goal-এর সাথে cosine-বুস্ট এই ইঞ্জিনেই হবে — কোনো নতুন ML stack নয়।
3. **Probe নোড বিদ্যমান কিন্তু অন্ধ** — `backend/services/dynamic_planner.py` L117–124: `TaskNode(name="Epistemic State Probe", capability="probe_system_state", input_params={"goal", "domain"})` — কোডবেস-দৃষ্টি শূন্য; `probe_system_state`-এর কোনো স্বতন্ত্র executor backend-এ নেই (grep-verified)। অর্থাৎ ক্ষমতাটি ঘোষিত, বাস্তবায়ন অনুপস্থিত।
4. **ডোমেইন-গেট বিদ্যমান** — `advanced_model_router.py` L137–162: `classify_domain` → `ExpertType.CODER` (zero-cost keyword); `intent_deciphering.py` L87–89 এই value `IntentAnalysis.domain`-এ বসায়। তাই "dev-টাস্কেই শুধু repo map" শর্ত নতুন কিছু তৈরি না করেই সম্ভব।
5. **স্কেল জানা** — backend-এ 1819টি .py ফাইল (2026-09-17 count)। stdlib `ast` পার্স ≈ প্রতি ফাইলে মিলিসেকেন্ড-স্কেল (estimate) — 2000-ফাইল ক্যাপে বাউন্ডেড।
6. **টেস্ট ট্রি বিদ্যমান** — `backend/tests/core/` সক্রিয় (automation, contracts, health, intelligence সাব-ট্রি সহ); `backend/tests/services/test_dynamic_planner.py` রিগ্রেশন-গার্ড।

### ১.২ কি নাই (What we don't have)

1. **কোনো কোড সিম্বল-ইনডেক্স নেই** — backend/ জুড়ে `CodeIndexer`/repo-map শ্রেণির কিছু নেই (grep-verified 2026-09-17)।
2. **Probe-এর কোনো কোডবেস-ইনপুট নেই** — `input_params`-এ শুধু goal/domain স্ট্রিং; নিচের executor-দের কাছে কোনো ফাইল-গ্রাফ যায় না।
3. **`discover_reusable_implementation` বাস্তবে নেই** — implementation_plan.md §1 এটি "logically available" বলে, কিন্তু এই নামে backend-এ কোনো Python symbol নেই (grep-verified) — policy rule 7 অনুযায়ী এটি aspiration; এই প্ল্যান তার প্রথম বাস্তব ভিত্তি দেয় (পুরো প্রতিশ্রুতি নয় — শুধু ম্যাপ-স্তর)।
4. **গ্রাফ-র‍্যাংকিং কিছু নেই** — networkx-ও ঘোষিত নয় (pyproject grep-verified), pure-Python PageRank লাগবে (~৩০ লাইন)।
5. **কোনো টেস্ট নেই** এই স্তরের কোনো আচরণের।

### ১.৩ কি করতে হবে (What to do)

CODER-domain টাস্কের Epistemic Probe-এ টোকেন-বাজেটের র‍্যাংক-করা রিপো-ম্যাপ যোগ — **১টি নতুন ফাইল (বিদ্যমান ডিরেক্টরি, বিদ্যমান প্যাটার্ন) + ১টি ফাইলে ছোট wiring + ১টি টেস্ট ফাইল।**

### ১.৪ কিভাবে করব (How to do it — file-by-file)

**Change 1 — নতুন ফাইল `backend/core/code_indexer.py` (~150 lines, stdlib-only):**

`MarkdownIndexer`-এর সাথে সামঞ্জস্যপূর্ণ প্যাটার্ন (imports, logging, singleton):

```python
# backend/core/code_indexer.py
"""Aider-inspired Repository Map (stdlib-ast, zero-dependency).
Mirrors core/markdown_indexer.py singleton pattern. Read-only, bounded, honest stats."""
from __future__ import annotations

import ast, math, re, time
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.logging_config import logger

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", "dist", "build"}
_MAX_FILES, _MAX_FILE_BYTES, _PR_ITERS, _PR_DAMP = 2000, 100_000, 20, 0.85


class CodeIndexer:
    """Read-only symbol graph over a Python workspace root (bounded walk)."""

    _instance: "CodeIndexer | None" = None

    @classmethod
    def get_instance(cls, root_dir: str | Path = ".") -> "CodeIndexer":
        if cls._instance is None:
            cls._instance = cls(root_dir)
        return cls._instance

    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root = Path(root_dir)
        self._stats: dict[str, Any] = {}
        self._symbols: dict[str, list[str]] = {}     # rel_path -> ["Cls:Foo", "Def:bar", ...]
        self._edges: dict[str, set[str]] = defaultdict(set)  # rel_path -> {rel_path, ...}

    # -- bounded walk + ast extraction (read-only) --
    def _walk_py_files(self) -> list[Path]:
        files = [p for p in self.root.rglob("*.py")
                 if not (set(p.parts) & _SKIP_DIRS) and p.stat().st_size <= _MAX_FILE_BYTES]
        files.sort(key=lambda p: p.stat().st_size)[:_MAX_FILES]  # ছোট ফাইল আগে — বাউন্ডেড
        return files

    def build(self) -> dict[str, Any]:
        t0 = time.perf_counter()
        files = self._walk_py_files()
        path_index: dict[str, Path] = {}
        parse_failures = 0
        for p in files:
            rel = str(p.relative_to(self.root))
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                parse_failures += 1
                continue
            syms: list[str] = []
            for node in tree.body:  # শুধু top-level — সস্ত ও যথেষ্ট
                if isinstance(node, ast.ClassDef):
                    syms.append(f"Cls:{node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    syms.append(f"Def:{node.name}")
                elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("core."):
                    target = node.module.replace(".", "/") + ".py"  # intra-package edge
                    path_index[target] = self.root / target
                    if (self.root / target).exists():
                        self._edges[rel].add(target)
            self._symbols[rel] = syms
        self._stats = {"files_indexed": len(self._symbols), "parse_failures": parse_failures,
                       "elapsed_s": round(time.perf_counter() - t0, 3)}
        logger.info(f"[CodeIndexer] {self._stats}")  # সৎ স্ট্যাটস — No Silent Failure
        return dict(self._stats)

    # -- pure-Python PageRank (networkx-মুক্ত) --
    def _pagerank(self) -> dict[str, float]:
        nodes = list(self._symbols)
        if not nodes:
            return {}
        rank = {n: 1.0 / len(nodes) for n in nodes}
        for _ in range(_PR_ITERS):
            new = {n: (1 - _PR_DAMP) / len(nodes) for n in nodes}
            for src in nodes:
                out = self._edges.get(src)
                if out:
                    share = _PR_DAMP * rank[src] / len(out)
                    for dst in out:
                        if dst in new:
                            new[dst] += share
                else:
                    new[src] += _PR_DAMP * rank[src]
            rank = new
        return rank

    # -- aider-style budgeted render, optional goal-boost via বিদ্যমান local embeddings --
    def render_repo_map(self, budget_chars: int = 4000, goal: str | None = None) -> str:
        if not self._symbols and not self._stats:
            self.build()
        rank = self._pagerank()
        lines: list[tuple[float, str]] = []
        for rel, syms in self._symbols.items():
            r = rank.get(rel, 0.0)
            head = ", ".join(syms[:8]) + (" …" if len(syms) > 8 else "")
            lines.append((r, f"{rel} — {head}" if head else rel))
        if goal:
            try:
                from core.embeddings import local_embed, hash_vectorize
                g = local_embed(goal) or hash_vectorize(goal)
                def boost(item):
                    _, line = item
                    rel = line.split(" — ")[0]
                    f = local_embed(rel) or hash_vectorize(rel)
                    dot = sum(a * b for a, b in zip(g, f))
                    n = math.sqrt(sum(a * a for a in g)) * math.sqrt(sum(b * b for b in f)) or 1.0
                    return item[0] * (1.0 + max(0.0, dot / n))
                lines.sort(key=boost, reverse=True)
            except Exception as exc:  # graceful: বুস্ট ছাড়া rank-ক্রমই যথেষ্ট
                logger.warning(f"[CodeIndexer] goal-boost skipped ({exc})")
                lines.sort(key=lambda x: x[0], reverse=True)
        else:
            lines.sort(key=lambda x: x[0], reverse=True)
        out, used = [], 0
        for _, line in lines:
            if used + len(line) + 1 > budget_chars:
                break
            out.append(line)
            used += len(line) + 1
        header = f"[REPO MAP] root={self.root.name} files={self._stats.get('files_indexed')} budget={budget_chars}c"
        return "\n".join([header, *out])
```

**Change 2 — `backend/services/dynamic_planner.py` (~12 lines, probe node-এ guard-যুক্ত wiring):**

```python
# plan_task()-এ probe_node তৈরির আগে (L117-এর ব্লকে):
repo_map_text: str | None = None
if intent.domain == ExpertType.CODER.value:   # বিদ্যমান classify_domain প্লাম্বিং পুনঃব্যবহার
    try:
        from core.code_indexer import CodeIndexer
        repo_map_text = CodeIndexer.get_instance(
            root_dir=str(Path(__file__).resolve().parents[2])
        ).render_repo_map(budget_chars=4000, goal=intent.ultimate_goal)
    except Exception as exc:
        logger.warning(f"[DynamicPlanner] repo map unavailable ({exc}); probe continues without it — honest degradation")

probe_node = TaskNode(
    ...,
    input_params={
        "goal": intent.ultimate_goal, "domain": intent.domain,
        **({"repo_map": repo_map_text} if repo_map_text else {}),   # অনুপস্থিত = নিঃশব্দ ভাব নয়, স্পষ্ট অনুপস্থিতি
    },
)
```
(ExpertType/Path import ফাইলে ইতিমধ্যে আছে কি না PR-এ যাচাই হবে; না থাকলে stdlib/expert import যোগ — নতুন dependency নয়, বিদ্যমান module।)

**Change 3 — নতুন টেস্ট `backend/tests/core/test_code_indexer.py` (~90 lines):** `tmp_path`-এ ছোট synthetic রিপো (৩ ফাইল: a.py imports b, b.py imports c, c.py একক) দিয়ে: সিম্বল এক্সট্র্যাকশন, edge resolution, PageRank-এ b অধিক র‍্যাংক, budget সম্মান, SyntaxError ফাইল → parse_failures=1, খালি ডিরেক্টরি → honest empty map। Mocked টেস্ট = contract প্রমাণ (Gate 4); live threshold মাপা হবে Gate 5-এ।

**পরিবর্তনের মোট পরিসর:** ১ নতুন module (বিদ্যমান ডিরেক্টরি `backend/core/`, বিদ্যমান প্যাটার্ন) + ১ ফাইলে ~১২ লাইন wiring + ১ টেস্ট ফাইল; **০ নতুন dependency (stdlib ast/pathlib/re/math/collections); ০ নতুন infra; ০ LLM কল; ০ frontend পরিবর্তন; read-only (কোনো mutation নেই)।**

### ১.৫ বেনিফিট (Benefit — estimates labeled)

1. **Dev-agent পুরো রিপো "দেখবে" (hypothesis):** probe-এ টোকেন-বাজেটে (≤4000 chars ≈ 1000 tokens, estimate) র‍্যাংক-করা সিম্বল ম্যাপ — এজেন্ট ফাইল-পাথ অনুমান না করে বাস্তব টার্গেট ধরবে।
2. **implementation_plan.md §1-এর প্রতিশ্রুতির প্রথম বাস্তব ভিত্তি:** "discovery-first dev task" আজ কাগজে; এই প্ল্যানের পর probe-এর হাতে ন্যূনতম discovery-উপাত্ত থাকবে (Constitution #3, #4)।
3. **Zero marginal cost (estimate):** কোনো LLM/embedding API কল নেই — index + PageRank + hash/embedding বুস্ট সব local CPU; প্রথম index ≤5s threshold (hypothesis), singleton-cached পরে প্রায়-শূন্য (estimate)।
4. **প্রতিযোগী parity ভিত্তি:** Aider/Cursor/Claude Code-এর table-stakes codebase-awareness-এর স্বনির্ভর, zero-cost সংস্করণ — নিজের স্ট্যাকে (vendor-documented pattern, নিজের বাস্তবায়ন)।
5. **Reusability:** `CodeIndexer` probe ছাড়াও ভবিষ্যতে MCP tool / PR Guardian context / self-benchmark-এ পুনঃব্যবহারযোগ্য — কিন্তু সেসব এই প্ল্যানের বাইরে।

### ১.৬ ক্ষতি/রিস্ক (Harm/Risk — honest)

| রিস্ক | মাত্রা | মাইটিগেশন |
|---|---|---|
| 1819-ফাইল প্রথম index-এ CPU spike (Render 512MB) | মাঝারি | হার্ড ক্যাপ (2000 ফাইল / 100KB-প্রতি-ফাইল), ছোট-ফাইল-আগে walk, singleton cache; success_threshold ≤5s পূরণ না হলে plan **blocked** (Gate 5) |
| Import-edge রেজলিউশন হিউরিস্টিক (শুধু `core.*` package-path) | কম | v1-এ সচেতন সীমা — আউটপুটে স্ট্যাটস সৎ; relative-import/alias edge বাদ (out-of-scope ঘোষিত) |
| খারাপ goal-boost → অপ্রাসঙ্গিক ফাইল উপরে | কম | boost ব্যর্থ → pure PageRank fallback; boost max ×1.5-সীমিত না হলেও multiplicative-শুধু; টেস্টে ranking assertion |
| Planner-এ নতুন import/latency | নিম্ন | guard-যুক্ত try/except; indexer ব্যর্থ → probe অপরিবর্তিত (কোনো fake map নয় — Guardian Rule 3) |
| ast শুধু Python — non-.py ফাইল অদৃশ্য | নিম্ন | v1-এ স্বীকৃত সীমা (out-of-scope ঘোষিত); ফাইল-পাথ স্টিল docstring/header-এ উপস্থিত থাকতে পারে (ভবিষ্যৎ scope) |
| Map দেখে agent ভুল ফাইল স্পর্শ | নিম্ন | map শুধু **তথ্য** — কোনো অনুমতি পরিবর্তন নয়; বিদ্যমান task_policy/action_policy আগের মতোই প্রযোজ্য (Constitution #12 অক্ষত) |

---

## Part 2 — 9-Rule Discipline + Policy Gates Compliance

| নিয়ম/গেট | সম্মতি | প্রমাণ |
|---|---|---|
| 1. One plan at a time | ✅ | এই মেমোতে একটাই প্ল্যান; execution-discipline: অনুমোদনের পর এটিই একমাত্র active |
| 2. Small change to existing code | ✅ | নতুন ফাইল বিদ্যমান ডিরেক্টরি+প্যাটার্নে (markdown_indexer mirror); wiring ১ ফাইলে ~১২ লাইন |
| 3. No new infrastructure | ✅ | নতুন server/account/tier নেই |
| 4. No CI cost amplification | ✅ | টেস্ট বিদ্যমান pytest রানে; LLM/নেটওয়ার্ক কল CI-তে নেই |
| 5. No credit-burn risk | ✅ | কোনো external API কল নেই — সম্পূর্ণ local |
| 6. No academic leaderboard chasing | ✅ | সরাসরি dev-টাস্ক প্রোডাক্ট ক্ষমতা |
| 7. Realistic resource budget | ✅ | হার্ড ক্যাপ + 512MB-safe; threshold ≤5s |
| 8. Complete six-field format | ✅ | §১.১–১.৬ |
| 9. Reality check before drafting | ✅ | 2026-09-17 fresh main 5155c27-এ সব উদ্ধৃত ফাইল সরাসরি পঠিত, line numbers সহ |
| Policy Gate 0 | ✅ | Part 0.5 reconciliation + grep-verified absence claims |
| Policy Gate 1 | ✅ | six-field + Out-of-Scope + acceptance criteria + rollback |
| Policy Gate 2 | ✅ | status: proposed — founder approval ছাড়া অ-নিষ্পাদনযোগ্য |
| Policy Gate 4/5 | ✅ | test_evidence + measurement_method + success_threshold সংজ্ঞায়িত; hypothesis-labeling সর্বত্র |

## Part 3 — Constitution Compliance Matrix

| ধারা | প্রভাব | কিভাবে |
|---|---|---|
| #3 Reuse Before Creation | ✅ | বিদ্যমান indexer-প্যাটার্ন + embeddings + planner-নোডের উপর বিল্ড; নতুন subsystem নয় |
| #4 Dynamic Discovery | ✅ মূল লক্ষ্য | হার্ডকোডেড ইনভেন্টরির বদলে রানটাইম রিপো-inspection |
| #5 Verify Before Trust | ✅ | টেস্ট + live threshold; map-এ সৎ parse_failures গণনা |
| #8 Graceful Degradation | ✅ | indexer ব্যর্থ → probe অপরিবর্তিত |
| #12 Least Privilege | ✅ | read-only index; ক্ষমতা ≠ অনুমতি |
| #13 No Silent Failure | ✅ | স্ট্যাটস লগড; map-অনুপস্থিতি স্পষ্ট |
| #14 Sustainable Cost | ✅ | ০ external কল; local CPU, বাউন্ডেড |

## Part 4 — Verification & Acceptance (Gates 4–5)

1. `pytest backend/tests/core/test_code_indexer.py -v` → all PASS (≥9 assertions)।
2. `pytest backend/tests/services/test_dynamic_planner.py` → zero regression (before/after)।
3. Live smoke (Gate 5): backend নিজের উপর `render_repo_map(goal="add caching to llm gateway")` → map-এ `core/llm/llm_gateway/gateway.py` জাতীয় hub ফাইল উপস্থিত কি না manual-grade; elapsed_s ও স্ট্যাটস লগ সংরক্ষণ PR-এ।
4. **Rollback:** wiring try/except-বেষ্টিত ও single-commit — revert এ probe সম্পূর্ণ পূর্বাবস্থা; CodeIndexer module orphan হলেও read-only, কোনো স্টেট দূষণ নেই।

## Part 5 — পরবর্তী প্রার্থীর বীজ (শুধু scouting-স্টেটাস; এই মেমোর স্কোপ নয়)

- **#004 (candidate):** PLAN_002-র compacted summary → Memory Circle-এর সেশন-জুড়ে promotion (ChatGPT/Claude memory প্যাটার্ন)।
- **#005 (candidate):** ইউজার-নিয়ন্ত্রিত `/compact` + `/map` ট্রিগার (Claude Code প্যাটার্ন) — PLAN_002/003-এর উপর দাঁড়াবে।

> **প্রকাশনা শৃঙ্খলা:** ফাউন্ডারের নির্দেশনায় প্ল্যানিং ডিপার্টমেন্ট GitHub API মাধ্যমে ধারাবাহিক প্ল্যান প্রকাশ করছে; প্রতিটি `status: proposed` — অনুমোদন-পূর্বে অ-নিষ্পাদনযোগ্য (Gate 2)। ইস্যুর পর ইন-প্লেস সম্পাদনা নয়; সংশোধন v2 sibling (AGENTS.md Mandatory Rule #6)।