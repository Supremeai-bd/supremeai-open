---
id: vision-strategic-positioning
subject: "SupremeAI — The One-Man-Army Master Plan"
document_role: roadmap
planning_authority: Planning Circle
canonical: candidate
status: active
evidence_state: partial
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
target_scope: supremeai_internal
---

# SupremeAI — The One-Man-Army Master Plan

**From current stage to production. How a single builder's system beats top AI models in their own strongest fields.**

> স্বপ্নটা ছোট নয়: নিজের হাতে বানানো একটা AI system, যে বড় ল্যাবগুলোর মডেলরা যেখানে সবচেয়ে শক্তিশালী — ঠিক সেই মাঠেই তাদের হারাবে।
> এই ডকুমেন্ট সেই পুরো পরিকল্পনা — আজকের codebase থেকে production পর্যন্ত, ধাপে ধাপে, খরচের হিসাবসহ।
>
> এই পরিকল্পনা পুরোপুরি আমাদের **Constitution** (README "SupremeAI Constitution") মেনে লেখা। প্রতিটি ধাপে কোন নীতি কাজ করছে সেটা চিহ্নিত করা আছে — কারণ নীতি ভাঙা শর্টকাট এই প্ল্যানে নেই।

---

## 0. The Dream, Translated Into Engineering

First, honesty. A one-person project will **never** out-pretrain OpenAI, Anthropic, DeepSeek or Google. That battlefield costs billions. Any plan that starts with "train a 70B frontier model" is fantasy, not strategy — and our Constitution already tells us why we should not want that fight:

- **Eternal Brain (Constitution #1):** SupremeAI's identity is its memory, experience and capability graph — *not* any vendor's weights. Frontier models are replaceable processing engines we rent at zero cost.
- **Sustainable Cost (#14):** minimum sustainable infrastructure. Our budget is pocket change; theirs is power plants. We only fight on fields where this asymmetry does not matter.

So the dream must be re-stated as an engineering claim:

> **A frontier model, shipped as a bare API, loses to a governed system on any field where the SYSTEM is the product: verified reliability, task completion, memory that compounds, cost per solved problem, and language/regional depth. SupremeAI will beat the best models-as-deployed on those fields — and will own small models of its own where they matter most.**

This is not a consolation prize. It is where every serious benchmark trend is heading: GAIA proved agents beat raw models on real tasks; SWE-bench's hard tasks are system problems; cost-per-task leaderboards decide real adoption. The moat is not the model. The moat is the machinery around it — exactly the machinery we are already building.

---

## 1. The Battlefields We Choose (and the ones we refuse)

| # | Battlefield | Who we must beat | Why we can win | Constitution |
|---|---|---|---|---|
| B1 | **Verified reliability (pass^k)** | Frontier APIs are tuned for impressive pass@1 demos; they are *inconsistent* — ask the same hard question 3 times, get 3 answers | Governed verify-loop + `pass^k` gate (shipped this sprint in `core/self_benchmark.py`) measures and enforces consistency. We can honestly report pass^3 while they cannot | Verification Before Trust (#5), No Silent Failure (#13) |
| B2 | **Agentic task completion** | o3/GPT-4-class *as deployed* (raw chat APIs with no memory, no capability discovery, no repair loop) | Capability-Composition Model + governed execution + retry/failover. GAIA-style: the system that composes tools beats the model that guesses | Reuse Before Creation (#3), One System Many Surfaces (#10) |
| B3 | **Cost frontier** | Every commercial API | Zero-cost provider chain, Tier0 fast path, semantic cache, TokenJuice compression, scout's zero-token summarizer. We publish **cost per verified task** — the metric nobody else wants printed | Sustainable Cost (#14) |
| B4 | **Memory that compounds** | Every API call starts from zero | hierarchical memory tree + Auto-RAG + learning loop + experience DB. Task #50 is cheaper, faster, more reliable than task #5. Theirs never learns | Memory Must Compound (#11), Eternal Brain (#1) |
| B5 | **Bengali + regional depth** | Top models are weakest in low-resource languages; none build for Bangladesh | We already normalize Bengali (`BengaliNormalizer`), write our own docs in Bangla, and will train a dedicated Bengali adapter (Phase 3). This is the one field where we are *native* and they are *tourists* | Provider Agnostic, User Loyal (#9) |
| B6 | **Integration surface (MCP federation)** | Single-vendor tool ecosystems | Governed MCP federation gateway (shipped), one-URL connect, capability registry. Any model can sit behind our fabric; no single lab can match the fabric's reach | Capability Sovereignty (#2), Dynamic Discovery (#4) |

**Fields we refuse to fight:** raw parameter count, frontier reasoning benchmarks, multimodal scale, model pretraining size records. Fighting there burns the one resource we have — time — against opponents with a thousand times more of it.

**The honest scoreboard we will publish:** for each battlefield B1–B6, a measurable number (see §5 gates). We win when the number says we win — not when the marketing says so. That is *Deliver honestly*.

---

## 2. Where We Stand Today (audit of this working tree, `main @ dac1b37`)

Strengths already in place (verified by this session's deep audit):

- **4 live services** on Render (core, worker, scraper, MCP tower) + Cloudflare edge failover circuit breaker — *Graceful Degradation working today*.
- **Zero-cost LLM chain** (Gemini/Groq/OpenRouter/Ollama) with multi-key support and 18 quality patches from the senior-review sprint already merged upstream.
- **Governance spine**: HITL engine + append-only audit ledger, RLS tenant isolation, policy-governed MCP federation, constitution-governance CI.
- **Memory**: pgvector RPC recall path, Auto-RAG injection in the chat/SSE pipelines, hierarchical memory tree.
- **Governed scout crawler** — hardened *this sprint*: per-domain rate pacing, robots.txt compliance, per-hop redirect re-validation, full event coverage, fail-closed policy.
- **Reliability gate** — added *this sprint*: unbiased `pass^k` estimator (`C(s,k)/C(n,k)`) in `core/self_benchmark.py`.
- **Learning loop** (`core/learning/`) shipping events from the LLM gateway with privacy scrubbing; proposals never auto-applied.

Known gaps this plan must close (each traced to a plan/doc that promised it):

| Gap | Source plan | Phase |
|---|---|---|
| Broken UI wires: reasoning-chain SSE channel dead; BranchPoint frontend missing | ROADMAP_BANGLA Sprint 2 | 0–1 |
| Scout crawler not yet wired into research pipelines (still dead code from the API's view) | specs/002 | 1 |
| Two parallel connection registries not fully unified; execution-mode UI absent | UNIVERSAL_ZERO_COMPLEXITY plan | 1 |
| `ConfigValidationReport`, CORS unification, contract tests | specs/001 | 1 |
| `behavioral_intelligence` package is dead code; RLHF eval dimensions missing | HUMAN_BEHAVIOR_ALIGNMENT doc | 3 |
| 125 test skips; dual migration systems; coverage gates at 30/16 | PRODUCTION_ROADMAP / COVERAGE_90_PLAN | 2 |
| No mission-level E2E benchmark suite | README "The most valuable future tests" | 2 |
| No own-model adapter trained yet | this plan (§5 Phase 3) | 3 |

---

## 3. Strategy: The System Beats the Model, Then the System Trains Its Own

The plan in one paragraph:

1. **Finish the machine** — every promised-but-unwired capability gets closed, so the capability graph is honest and complete (Reuse Before Creation applied to our own backlog).
2. **Make reliability measurable** — pass^k and mission tests become CI gates; then every change is justified by the scoreboard, not by vibes.
3. **Feed the flywheel** — every solved task produces governed training data (scout corpus + learning events + verification outcomes + feedback).
4. **Train small, train narrow** — own adapters (Bengali, behavioral alignment, router/verifier) trained on the flywheel via the existing pipelines, promoted behind canary + pass^k gates. Eternal Brain: our weights, our registry, swappable.
5. **Attack chosen benchmarks publicly** — beat top *deployments* on B1/B2/B3/B5 and publish the evidence.

Each step uses machinery that already exists in this repo. That is not an accident — it is the Constitution's *Reuse Before Creation* applied to strategy itself.

---

## 4. The Ladder: Phase 0 → Phase 6 (current stage → production)

### Phase 0 — Stop the Bleed (Weeks 1–2) ✅ *this sprint's patch*

**Goal:** every shipped feature must actually work; every number must be honest.

- Close broken wires: connections camelCase contract (UI was reading `undefined`), duplicate `detect_protocol` removed, dead `ready_states` purged, `user_execution_mode` migration created, `CapabilityUnavailableExplainer` finally rendered, workspace shows real connections from the Zero-Friction registry. *(shipped in this patch)*
- Kill governance violations: RLHF no longer fabricates records or fake "simulation success"; training refuses empty data honestly. *(shipped in this patch)*
- Scout hardened: rate pacing, robots.txt, redirect re-validation, full events, fail-closed. *(shipped in this patch)*
- Housekeeping queue: Supabase `ai_memory` Phase C table, STATUS.md duplicate block, `docs/SKIPPED_TESTS.md` recreation, delete stray `.ini` log file + rotate that Render key.

**Gate (Constitution #13):** zero features that look alive but are dead inside. Every status page tells the truth.

### Phase 1 — Capability Completion (Weeks 3–8) 🚧 *this patch ships the core wires*

**Goal:** the capability graph matches the promises in our planning corpus.

- **Scout goes live** (specs/002 close-out) ✅ *(shipped in this patch)*: `deep_research._web_search` is now scout-first — tenant's active `CrawlPolicy` drives a governed crawl (robots.txt, rate pacing, SSRF gate, dedup) with the browser agent as fallback; durable persistence (`scout/persistence.py` + Alembic `2026_09_13_090000` for `crawl_policies`/`crawl_history`/`crawl_events`); full admin CRUD (`PATCH /policies/{id}`, `enable`/`disable`, `DELETE`) and real `GET /events` telemetry on `crawler_admin.py`; governed `research` capability registered in the conversation orchestrator.
- **One connection registry** (Zero-Complexity close-out) ✅ *(shipped)*: `/connections/register` writes through `ConnectionRegistry` (durable `supremeai_connections` table) and returns the real record id; capability promotion path and execution-mode UI remain open items.
- **Reasoning stream** ✅ *(shipped)*: `core/observability/reasoning_stream.py` emits steps on the session SSE `reasoning` channel (SSE-only fanout via `LogBatcherService.publish` — no DB poisoning); `sessionCockpitStore` appends to `reasoningChain`; `ReasoningLog.tsx` finally shows the thought process — visible intelligence is perceived intelligence.
- **Config hardening** (specs/001 close-out) ✅ *(shipped)*: `ConfigValidationReport` + `build_config_validation_report()`; `server.py` origins built through `middleware/cors_policy` resolvers (wildcard-proof); `GET /config/validation-report`; `tests/api/routes/test_config_contract.py`.
- **Admin surface** ✅ *(shipped)*: real `/api/v1/admin/stats|users|audit-logs` (were 404) in `admin_v1.py`.
- **Mission suite kickoff** ✅ *(shipped, Phase 2 bridge)*: first 5 missions / 12 tests in `tests/missions/`; `scripts/ci/mission_passk.py` prints pass^3 in CI (`reports/mission_passk.json`); `docs/SKIPPED_TESTS.md` recreated with the 125-marker baseline.
- **Still open in this phase:** capability health-probe promotion out of `IDEA` lifecycle; execution-mode UI in Settings; frontend `SCRAPER_BACKEND_URL` resolver.

**Gate (Constitution #3):** no new subsystems this phase — only finishing what was promised. Coverage of "near-ready" capabilities → "available".

### Phase 2 — The Reliability Moat (Weeks 9–16)

**Goal:** make *measured reliability* the product's core metric. This is battlefield B1.

- **Mission tests** (README's own definition): 20 realistic end-to-end user missions — research, file work, repo repair, scheduling — scored automatically. `pass^3 ≥ 0.8` on the mission suite is the promotion bar for every future change.
- **Risk-Tiered Safety Pipeline** (`docs/architecture/RISK_TIERED_AUTONOMOUS_SAFETY_PIPELINE.md`): operationalize "Simple by default, deep by risk" — L1 deterministic rule gate, L2 parallel GitHub matrix, L3 independent adversarial reviewer ("assume it's wrong"), browser staging simulator, and automatic runtime rollback.
- **Governed Multi-Agent Decision Framework** (`docs/architecture/GOVERNED_MULTI_AGENT_DECISION_ARCHITECTURE.md`): operationalize Cost-Minimized Execution ($0 capability ladder, duplicate reasoning reuse) + Continuous Project-Scoped Security + Cross-Agent Challenge Matrix (Security vs Cost vs Safety).
- **CI gates rise**: pass^k harness runs nightly against the live zero-cost chain; coverage gate climbs 30→50 backend / 16→30 frontend; skip count 125→<30 with `docs/SKIPPED_TESTS.md` tracking every waiver.
- **Performance**: kill remaining sync-in-async stalls (the services-review list), PgBouncer tuning, Tier0 hit-rate ≥ 40% on repeat traffic.
- **Migration unification**: Alembic declared canonical, `database/migrations/legacy/` archived.

**Gate (Constitution #5):** nothing promotes — model, adapter, provider, or code — without a pass^k number attached.

### Phase 3 — Own Model v1: Small, Narrow, Ours (Months 4–6)

**Goal:** the "own build AI model" dream begins — not a frontier clone, but adapters where small models beat big ones *because* the task is narrow and the data is ours. This is the Eternal Brain made real.

- **Data flywheel (Memory Must Compound → training data):**
  - scout corpora: governed crawls + zero-token extractive summaries (zero cost, per-tenant scoped);
  - learning events: privacy-scrubbed `learning_events` from the gateway;
  - verification outcomes: every verify-before-trust result labels its own trace;
  - explicit feedback: `/feedback` → `RLHFPipeline` with provenance (dataset_version, source — shipped this sprint).
- **Three adapters, three battlefields:**
  1. **Bengali conversation adapter** (B5): base = an open 2–7B instruct model; fine-tune via LoRA/DPO on flywheel Bangla pairs + scout-Bangla corpus. Target: beat Gemini/GPT-class *on Bangla conversational quality and idiom* at 1/50 the cost — the field where "their own strong field" logic flips, because ours is native.
  2. **Behavioral alignment adapter** (B1 support): activate the dead `behavioral_intelligence` package (finish the 4 missing modules: `intent_signals`, `preference_store`, `evaluator`, `metrics`); train on interaction signals so responses match user rhythm (concise vs. step-by-step vs. code-first).
  3. **Router/verifier micro-model** (B3 support): a 0.5–1B classifier that routes requests and judges outputs inside the verify loop — replaces thousands of paid verification calls with a free local decision, raising pass^k *and* lowering cost.
- **Training infrastructure already in the repo:** `pipelines/synthetic_data_pipeline.py` → `tools/learning/rlhf_pipeline.py` (now honest) → `tools/learning/model_trainer.py` (RunPod/Modal LoRA) → `core/kaggle_orchestrator.py` (free Kaggle GPU, ~30h/week) → promotion via `evolution/canary_manager.py` behind the pass^k gate.
- **Serving:** adapters registered in the provider-agnostic gateway as just another provider entry — `Graceful Degradation` means if the adapter is cold, the chain falls back to Groq/Gemini transparently. User experience never depends on our model being warm.

**Gate (Constitution #7, Reversible Evolution):** an adapter reaches production only if it beats its base model by ≥10% on its own eval set AND pass^3 does not regress. Rollback path always warm.

### Phase 4 — Public Benchmark Attacks (Months 7–9)

**Goal:** publish evidence on the chosen fields. Public numbers are the one-man army's marketing department.

- **B1 — Reliability:** publish pass^k curves for SupremeAI vs. raw frontier APIs on the mission suite. Expectation: frontier APIs score high on pass@1, degrade on pass^3/pass^5; our verify-loop keeps pass^k high. This chart *is* the pitch.
- **B2 — Task completion:** GAIA-text subset + a SWE-bench-lite-style repo-repair harness using our own governed executor; compare against the same underlying model *without* our machinery — isolating "the system is the moat".
- **B3 — Cost:** publish cost-per-verified-task. The zero-cost chain + Tier0 + cache + scout summarizer makes this number embarrassing for paid stacks on comparable quality tiers.
- **B5 — Bengali:** a public Bangla eval set (conversation, summarization, code-switching) built from governed sources; our adapter vs. the giants. Native wins.

**Gate (Constitution #5, #13):** every published number reproduces from a committed script. No benchmark theater.

### Phase 5 — Production Hardening & Launch (Months 10–12)

**Goal:** from "works for me" to "works for users I don't know".

- SLA enforcement wired to the metrics we already export (P95 < 2s chat first-token, error < 1%); load tests at 10× current traffic; OpenTelemetry traces end-to-end.
- Security re-audit (the 30-category matrix) + pen-test pass; secrets rotation automation; TOTP for all admin paths.
- Thin-client launch (VS Code extension + desktop): 100% thin, zero user keys, local Ollama as the only offline fallback — the CHECKPOINT.md architecture reminder, kept.
- Onboarding funnel: one-URL connect → first verified task in < 5 minutes.
- **The Founder's Demo:** a public page showing live system truth — uptime, pass^3, tasks solved, cost per task, adapter evals. Radical transparency as brand.

**Gate:** 99.5% monthly uptime for the quarter, P95 inside target, zero P0 security findings open.

### Phase 6 — Compounding (Year 2)

**Goal:** the capability graph grows faster than one person could build features.

- Self-evolution flywheel at full speed: agent-breeder proposals (with the GA fix) → sandbox eval → pass^k gate → canary promotion → capability registry. The system proposes its own capabilities; I approve them.
- MCP marketplace economy: tenants publish governed capabilities; the registry compounds from everyone's contributions.
- The one-man army becomes a one-person *orchestra* — SupremeAI runs SupremeAI's ops, tests, repairs and roadmap drafts; I audit, decide, and steer.

---

## 5. The Data Flywheel — Why Every Phase Gets Cheaper

```
User task ──► governed execution ──► verified result
                        │                     │
            scout corpus (zero-token)    verification label
                        │                     │
                        ▼                     ▼
                learning_events (privacy-scrubbed) + feedback
                                     │
                                     ▼
                        synthetic_data_pipeline
                                     │
                                     ▼
                     LoRA/DPO adapter (narrow field)
                                     │
                          pass^k gate + canary
                                     │
                                     ▼
                gateway serves adapter ──► next task cheaper, faster,
                                           more reliable than the last
```

The flywheel is the Constitution's *Memory Must Compound* upgraded from "recall" to "weights". Every real task either (a) is solved by existing capability — cheap now — or (b) leaves behind data that makes the *next* task of its kind cheap forever. Top labs cannot copy this: their flywheel needs scale; ours needs *the system we already run*.

---

## 6. The One-Man-Army Operating System

Time is the scarcest resource; this is how the plan survives contact with reality.

- **50% product / 30% moat / 20% ops.** Product = user-visible capability. Moat = reliability, data, adapters. Ops = the machine that watches itself.
- **Dogfood without mercy:** every patch (including this sprint's) is developed under the same governed pipeline SupremeAI offers users — plan → execute → verify → audit. When the pipeline hurts me, that is the bug list. SupremeAI files its own GitHub issues; AutoHealer watches the monitors; the learning loop drafts roadmap items (I approve). *One System, Many Execution Surfaces* includes the founder as just another tenant.
- **Budget math (Sustainable Cost):**
  - Render free/low tiers (core, worker, scraper, MCP) + Supabase free (pgvector) + Upstash free (Redis) + Cloudflare free (edge) — effectively ~$0–25/mo;
  - LLM: zero-cost chain (Groq/Gemini/OpenRouter free tiers + Ollama local) — ~$0 baseline;
  - Training: Kaggle free GPU (~30h/wk) for LoRA/DPO runs; RunPod burst ~$20–50/mo only when a promotion gate justifies it;
  - **Total: under ~$75/month** while attacking four battlefields. The asymmetry is the strategy.
- **Decision rule for every new idea:** *Reuse → Compose → Adapt → Extend → Create.* If an idea cannot state which existing capability it extends, it waits. The backlog is long; the moat compounds only if I finish things.
- **Kill criteria (honesty about risk):** if by end of Phase 2 the mission-suite pass^3 cannot reach 0.7, the verify-loop design is wrong — redesign before Phase 3. If by end of Phase 3 the Bengali adapter cannot beat the zero-cost chain on its own eval, park own-models and double B1/B2/B3. If infra friction exceeds 20% of time for two consecutive months, consolidate services. This plan is a commitment, not a religion.

---

## 7. Scoreboard (the numbers that decide "did we beat them?")

| Field | Metric | Today | Phase 2 gate | Phase 4 target |
|---|---|---|---|---|
| B1 Reliability | pass^3 on mission suite | unmeasured | ≥ 0.8 internal | ≥ 0.8 published, vs raw-API pass^3 baseline |
| B2 Tasks | GAIA-text-style mission success | unmeasured | 20-mission suite green | ≥ frontier-API-as-deployed baseline +10pts |
| B3 Cost | $ per verified task | unmeasured | instrumented | published; ≤ 1/10 of paid-stack baseline |
| B4 Memory | repeat-task cost delta | unmeasured | measured via learning events | repeat task ≥ 30% cheaper than first run |
| B5 Bengali | Bangla eval win-rate vs zero-cost chain | unmeasured | eval set v1 | adapter wins head-to-head |
| B6 Surface | one-URL connect → first verified task | minutes | < 5 min | < 3 min, marketplace live |

Every cell gets a committed script. The scoreboard is a CI artifact, not a slide.

---

## 8. The Next 14 Days (concrete, from this patch's momentum)

1. ✅ Ship this sprint's patch (connections contract fix, scout hardening, RLHF governance, pass^k).
2. ✅ Recreate `docs/SKIPPED_TESTS.md` from the 125-skip audit (Phase 1 patch).
3. Run Supabase `ai_memory` Phase C SQL (Phase 0 close-out).
4. ✅ Wire scout into `deep_research._web_search` behind the admin crawler policy (Phase 1 — done).
5. ✅ Emit reasoning steps on the session SSE channel; light up `ReasoningLog.tsx` (Phase 1 — done).
6. ✅ Add the first 5 mission tests; get pass^3 printed in CI for the first time (Phase 1 patch — `scripts/ci/mission_passk.py`).
7. Turn on the remaining Phase 1 open items: health-probe promotion out of `IDEA`, execution-mode UI, `SCRAPER_BACKEND_URL` resolver.
8. Nightly pass^k on the live zero-cost chain; publish the first scoreboard artifact.

The scoreboard starts measuring the moment we do. তারপর প্রতিটি সপ্তাহে একটা করে সংখ্যা সোজা হবে — এবং সংখ্যাগুলোই আমাদের স্বপ্নের সাক্ষী দেবে।