---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:orphan_components_wiring_master_plan
subject: 🔧 Crown Jewel Wiring Master Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🔧 Crown Jewel Wiring Master Plan
### সব "এতিম" (orphan) কম্পোনেন্ট একসাথে জোড়া লাগানোর সম্পূর্ণ রোডম্যাপ

কোডবেজ verify করে (২৮৮০ ফাইল স্ক্যান, cross-reference check) নিশ্চিত হয়েছি entry point গুলো ঠিক কোথায়:

- **Trio Pipeline** → `backend/core/orchestration/trio_pipeline.py` (Gemini→Kilo→Cline)
- **Self-Assemble** → `backend/api/routes/self_assemble.py` → `agents/meta_project_manager_agent.py`
  - ⚠️ **আবিষ্কার:** `DynamicAgentSpawner.execute_task()` বর্তমানে **`await asyncio.sleep(0.02)`** দিয়ে সিমুলেট করা — real Swarm/MCP Mesh call করে না। এটাই সবচেয়ে জরুরি ফিক্স।
- **Swarm Orchestrator** → `backend/core/orchestration/swarm_orchestrator.py` (real DAG engine, already has `execute_task()`)

নিচে প্রতিটি ধাপে **কোন ফাইলে, কোন লাইনের কাছে, কী কোড** যোগ হবে তা নির্দিষ্ট করা হলো — যাতে ধাপে ধাপে বাস্তবায়ন করা যায় (আপনার token-limit অনুযায়ী প্রতি সেশনে ২-৩টা করে করা যাবে)।

---

## 🗺️ Wiring Dependency Map (কোনটার আগে কোনটা করতে হবে)

```
PHASE 0 (Foundation — আগে করতেই হবে)
   └── Zero-Cost Gateway [J] ──► সব pipeline-এর সামনে বসবে

PHASE 1 (Core Engine Fix — সবচেয়ে বড় impact)
   ├── self_assemble → Swarm Orchestrator [C]  (fake sleep() রিপ্লেস)
   └── Swarm → MCP Mesh Engine (tool synthesis)

PHASE 2 (Trio Enhancement)
   ├── Trio → Adaptive Learning Loop [D]
   ├── Trio → Tree-of-Thought (pre-step for complex tasks) [L]
   ├── Trio → ToM/Intent LLM pivot
   └── Vision Pipelines (image/video/diagram) → Trio [H]

PHASE 3 (Distribution & Cost)
   ├── Parallel Cloud Router → P2P Broker [A]
   ├── Local Model Handler → BYOC nodes [K]
   └── BYOC Container Orchestrator → Credit System [B]

PHASE 4 (Economy & Evolution — দীর্ঘমেয়াদি)
   ├── Skill Marketplace → MCP Mesh output [G]
   ├── RLHF loop → Trio dual-draft UI [E]
   ├── Agent Evolution Engine → Self-Assemble runs [F]
   └── Decision Engine → auto-approve gate [M]
```

**যুক্তি:** Phase 0-1 আগে না করলে বাকি সব উপরে বসানো "সাজানো বাগান"-ই থেকে যাবে — কারণ core execution engine (self_assemble) এখনো fake sleep দিয়ে চলছে।

---

## 🥇 PHASE 0: Zero-Cost Gateway সামনে বসানো

**লক্ষ্য:** প্রতিটি রিকোয়েস্ট আগে ফ্রি রুট দিয়ে resolve করার চেষ্টা করবে, তারপর paid/BYOC-তে যাবে।

### ⚠️ CORRECTION (recheck-এ ধরা পড়েছে): Gateway নিজেই আংশিক fake!
কোড verify করে দেখা গেছে `ZeroCostGateway.generate_response()`-এর **Tier 1** (Free Quota Balancer) real provider call না পেলে এই fallback রিটার্ন করে:
```python
# বর্তমান কোড (core/llm/zero_cost_gateway.py, লাইন ~70):
if mock_provider_call:
    response_text = await mock_provider_call(selected_model, prompt)
else:
    response_text = f"Processed via {selected_model}: {prompt[:30]}..."  # ← FAKE placeholder!
```
মানে Tier 0 (cache) real, কিন্তু **Tier 1 এখনো কোনো আসল LLM API call করে না** — শুধু placeholder string। এটা আগে wire করতে হবে, নাহলে পুরো "minimal cost" claim ফাঁপা থেকে যাবে।

**Fix-0a (আগে করতে হবে):** `mock_provider_call`-এর জায়গায় existing `GeminiWriter`/`LLMRouter`-এর real call pass করা:
```python
# core/llm/zero_cost_gateway.py ব্যবহারের সময়:
from agents.ide.trio_adapters import GeminiWriter
writer = GeminiWriter()

async def real_provider_call(model_name: str, prompt: str) -> str:
    return await writer.generate(prompt, model_override=model_name)

zc_result = await zero_cost_gateway.generate_response(
    prompt, context_hash=hash_val, mock_provider_call=real_provider_call
)
```

**Fix-0b — Gateway wire করা Trio-তে:**
**ফাইল:** `backend/core/llm/zero_cost_gateway.py` (Tier 0 real) →
wire করতে হবে `backend/core/orchestration/trio_pipeline.py`-এর `_pre_cognitive_cache_lookup()`-এর ঠিক আগে (`execute()` মেথডে, লাইন ~187)।

```python
# trio_pipeline.py — TrioPipeline.__init__() এর ভেতরে
from core.llm.zero_cost_gateway import ZeroCostGateway
self.zero_cost_gateway = ZeroCostGateway()

# execute() মেথডের একদম শুরুতে, _pre_cognitive_cache_lookup এর আগে:
zc_result = await self.zero_cost_gateway.generate_response(
    prompt, context_hash=context_hash, mock_provider_call=real_provider_call
)
if zc_result.get("cache_hit") or zc_result.get("tier") == "Tier_1_Free_Quota_Balancer":
    return zc_result  # cache-hit বা free-tier resolve, $0 বা near-$0 খরচ
# Tier_2_Graceful_Fallback হলে normal Trio flow-তে যাবে (নিচে চলবে)
```
⚠️ নোট: Gateway `resolved` নামে কোনো key রিটার্ন করে না — actual keys হলো `tier`, `cache_hit`, `text`, `provider`। উপরের চেক এই actual schema অনুযায়ী ঠিক করা হয়েছে।

**কষ্ট:** ⭐⭐ Low-Medium (আগে ⭐ ধরা হয়েছিল, কিন্তু Fix-0a-সহ এটা Low-Medium) | **ইমপ্যাক্ট:** 🔥🔥🔥 — এটাই "minimal maintenance cost" লক্ষ্যের ভিত্তি।

---

## 🥇 PHASE 1: Self-Assemble-এর Fake Simulation রিপ্লেস করা

এটা **সবচেয়ে জরুরি** কারণ এই মুহূর্তে `self_assemble` API আসলে কিছুই "করছে না" — শুধু `sleep(0.02)` দিয়ে fake artifact রিটার্ন করছে।

**ফাইল:** `backend/agents/meta_project_manager_agent.py`, লাইন ~172 (`DynamicAgentSpawner.execute_task`)

**বর্তমান (fake):**
```python
await asyncio.sleep(0.02)
artifacts = {"architecture_spec": {...hardcoded...}}
```

**নতুন (real):**
```python
from core.orchestration.swarm_orchestrator import SwarmOrchestrator
from tools.mcp.mcp_mesh_engine import DynamicMCPRegistry

class DynamicAgentSpawner:
    _swarm = SwarmOrchestrator()
    _mesh = DynamicMCPRegistry()

    @classmethod
    async def execute_task(cls, task: ProjectTask, context: dict) -> dict:
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # প্রয়োজনে নতুন tool synthesize করো (MCP Mesh)
        if task.required_skills:
            for skill in task.required_skills:
                if not cls._mesh.has_tool(skill):
                    await cls._mesh.synthesize_tool(skill, context)

        # Real DAG-based parallel execution (Swarm)
        result = await cls._swarm.execute_task(
            prompt=task.description,
            user_id=context.get("user_id", "system"),
        )
        task.output_log.append(f"[{task.agent_type}] Swarm executed via DAG.")
        return {"artifacts": result.artifacts, "status": result.status}
```

**কষ্ট:** ⭐⭐ Low-Medium (main risk: `ProjectTask`/`ExecutionResult`-এর schema mismatch হ্যান্ডেল করা লাগবে — টেস্ট দরকার)
**ইমপ্যাক্ট:** 🔥🔥🔥🔥 সর্বোচ্চ — পুরো "self-assemble" ফিচার প্রথমবারের মতো real হবে।

---

## 🥈 PHASE 2: Trio Pipeline Enhancement

### 2.1 — Adaptive Learning Loop hook [D]
**ফাইল:** `trio_pipeline.py` → pipeline সম্পূর্ণ হওয়ার পরে (return-এর ঠিক আগে)
```python
from adaptive_engine.learning_loop import learning_loop
await learning_loop.ingest(experience={
    "prompt": prompt, "result": final_result,
    "iterations": iteration_count, "success": final_result["status"] == "green",
})
```
⭐ Very Low কষ্ট — একলাইনের hook।

### 2.2 — Tree-of-Thought pre-step [L]
জটিল টাস্কের জন্য (length বা complexity heuristic দিয়ে detect করে) Writer কল করার আগে:
```python
if is_complex_task(prompt):  # e.g. token count > threshold, বা multi-file
    from engine.tree_of_thought import TreeOfThoughtReasoner
    tot = TreeOfThoughtReasoner()
    reasoning = await tot.reason(prompt)
    prompt = f"{prompt}\n\n[Reasoning guide]: {reasoning['best_path']}"
```

### 2.3 — ToM Intent Pivot (nn.Linear → LLM prompt swap)
**ফাইল:** `evolution/theory_of_mind/tom_system.py` — `infer_mental_state()` রিপ্লেস করে LLM-কল দিয়ে:
```python
async def infer_mental_state(self, user_input: str) -> dict:
    prompt = f"User said: '{user_input}'. তার আসল উদ্দেশ্য/সমস্যা কী তা এক লাইনে লিখুন।"
    resp = await self.llm_gateway.acompletion(prompt=prompt)
    return {"intent": resp}
```
Trio-তে Writer কলের আগে এই intent যোগ করে দিলে output-এর প্রাসঙ্গিকতা বাড়বে।

### 2.4 — Vision Pipelines → Trio [H]
**ফাইল:** `services/video_to_code_pipeline.py`, `tools/code/image_to_code.py`, `tools/code/diagram_to_architecture.py`
তিনটার output-এর শেষে:
```python
from core.orchestration.trio_pipeline import TrioPipeline
verified = await TrioPipeline().execute(prompt=generated_code, mode="verify_only")
return verified
```

**কষ্ট (সবগুলো একসাথে):** ⭐⭐ Low-Medium | **ইমপ্যাক্ট:** 🔥🔥🔥 output quality + trust বাড়বে

---

## 🥉 PHASE 3: Distribution & Cost Optimization

### 3.1 — Parallel Cloud Router → P2P Broker [A]
**ফাইল:** P2P broker module-এ (`backend/p2p/`) node registry-তে static cloud entry যোগ করা:
```python
from brain.parallel_cloud_router import ParallelCloudRouter
p2p_broker.register_remote_pool([
    {"name": "gcp_cloud_run", "weight": 0.40, "handler": ParallelCloudRouter.gcp_call},
    {"name": "railway", "weight": 0.35, "handler": ParallelCloudRouter.railway_call},
    {"name": "render", "weight": 0.25, "handler": ParallelCloudRouter.render_call},
])
```

### 3.2 — Local Model Handler → BYOC edge inference [K]
BYOC node registration flow-তে (`byoc/container_orchestrator.py`) চেক যোগ করা:
```python
from models.local_model_handler import LocalModelHandler
local = LocalModelHandler(ollama_base_url=node.endpoint)
if await local.health_check():
    node.capabilities.append("free_edge_inference")  # cloud API cost এড়ানো যাবে
```

### 3.3 — BYOC Orchestrator → Credit System [B]
নতুন node deploy সফল হলে:
```python
credit_system.award(user_id=node.owner_id, amount=DEPLOY_CREDIT, reason="byoc_node_online")
```

**কষ্ট:** ⭐⭐ Low-Medium | **ইমপ্যাক্ট:** 🔥🔥🔥 — এটাই আসল "market disruption" অংশ, কারণ cost user-দের নিজেদের hardware-এ শিফট হচ্ছে।

---

## 🏅 PHASE 4: Economy & Long-term Evolution

| Task | ফাইল | সংক্ষেপে |
|---|---|---|
| Skill Marketplace publish hook [G] | `core/tier8/skill_marketplace_curator.py` | MCP Mesh-এর `synthesize_tool()` সফল হলে → `curator.submit_draft(tool)` |
| RLHF dual-draft UI [E] | `tools/learning/rlhf_pipeline.py` + frontend | `MultiModelWriter`-এর ২টা draft ফ্রন্টএন্ডে পাঠানো, user pick → `record_preference()` |
| Agent Evolution Engine [F] | `core/tier8/agent_evolution_engine.py` | প্রতিটা successful self_assemble run শেষে → `genome.fitness += 1`, প্রতি ১০০ রানে `mutate()` চেষ্টা |
| Decision Engine gate [M] | `core/decision_engine.py` | Swarm/self_assemble-এর high-risk task-এ execute হওয়ার আগে `decision_engine.approve(task)` চেক |
| Digital Twin pre-deploy test | `evolution/digital_twin/simulator.py` | BYOC deploy করার আগে `simulator.simulate_service_failure(new_config)` |
| Temporal pattern → Context Graph [prev #4] | `evolution/temporal_abstraction/temporal_system.py` | Context Graph event stream-এ subscribe করানো |
| Federated Learning pivot | `evolution/federated_learning/fed_learning.py` | Image tensor input → embedding vector-এ swap, BYOC node experience share |

**কষ্ট:** ⭐⭐⭐ Medium (প্রতিটা), তবে দীর্ঘমেয়াদে এগুলোই "self-improving, self-funding" সিস্টেম তৈরি করবে।

---

## ✅ Execution Checklist (session-by-session, token-বাঁচিয়ে)

আপনার preference অনুযায়ী প্রতি সেশনে অল্প কিছু ফিক্স করে continue করব। প্রস্তাবিত ক্রম:

- [ ] **Session 1:** Phase 0 (Zero-Cost Gateway wire) + Phase 1 (self_assemble → Swarm real fix) — এই দুইটাই সবচেয়ে বেশি impact
- [ ] **Session 2:** Phase 2.1 + 2.2 (Learning Loop + ToT hook) + টেস্ট
- [ ] **Session 3:** Phase 2.3 + 2.4 (ToM pivot + Vision→Trio)
- [ ] **Session 4:** Phase 3.1 + 3.2 (Cloud Router + Local Model → BYOC)
- [ ] **Session 5:** Phase 3.3 + Decision Engine gate
- [ ] **Session 6+:** Phase 4 (Marketplace, RLHF UI, Agent Evolution) — একটা একটা করে

প্রতিটা ধাপ শেষে relevant test ফাইল রান করে দেখব ভাঙেনি তো, তারপর নির্দিষ্ট repo-তে push করার আগে আপনাকে জানাব কোন repo (admin backend/production backend) কোন কোড যাচ্ছে — যেহেতু দুইটা আলাদা Render account-এ প্রভাব ফেলবে।

---

## ⚠️ Push করার আগে একটা কথা

আপনি দুটো আলাদা GitHub repo আলাদা Render backend-এ পুশ করার কথা বলেছেন (admin ও production)। আমি ভুল repo-তে ভুল কোড পুশ হওয়া এড়াতে **প্রতিটা push-এর ঠিক আগে কোন ফাইল কোন repo-তে যাচ্ছে তা এক লাইনে জানিয়ে** তারপর push করব — যাতে production backend-এ ভুলে admin-only কোড না চলে যায়।

শুরু করব Session 1 (Zero-Cost Gateway + self_assemble real fix) দিয়ে?