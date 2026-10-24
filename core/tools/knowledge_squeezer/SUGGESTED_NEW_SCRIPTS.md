# Scripts that would make SupremeAI materially stronger

## Tier 1 — Highest ROI

### 1. `evidence_verifier.py`
Turns each important claim into verifiable subclaims and asks independent tools/sources
to confirm or reject them. Store evidence and timestamps with the artifact.

### 2. `contradiction_hunter.py`
Searches existing `ai_memory` before promotion and detects:
- direct contradictions
- incompatible assumptions
- obsolete versions
- duplicate knowledge with weaker/stronger confidence

### 3. `knowledge_revalidator.py`
Re-checks old artifacts on a schedule. High-volatility knowledge gets short TTLs;
stable engineering principles get long TTLs.

### 4. `execution_verifier.py`
For code/architecture claims, generates tests, benchmarks, static-analysis checks,
and sandbox experiments before an artifact can become `verified`.

### 5. `memory_curator.py`
Promotes, merges, demotes, archives, and deletes knowledge instead of treating every
vector as equally trustworthy.

## Tier 2 — Major capability upgrades

### 6. `model_router_economist.py`
Chooses models based on task difficulty, expected value, latency, historical accuracy,
and budget. Do not call every model for every prompt.

### 7. `failure_pattern_miner.py`
Mining failures, incidents, CI logs, rollbacks, and rejected patches into reusable
failure fingerprints and prevention rules.

### 8. `decision_trace.py`
Stores not private chain-of-thought, but an auditable decision record:
inputs, evidence, tools, constraints, outputs, verification, and final action.

### 9. `knowledge_graph_builder.py`
Builds entity/concept/causal links around artifacts so retrieval can follow relationships,
not only nearest-vector similarity.

### 10. `skill_distiller.py`
Converts repeated successful workflows into reusable tools/skills with tests and versioning.

## Tier 3 — Advanced

### 11. `digital_twin_executor.py`
Runs proposed changes in a simulated or isolated environment before production.

### 12. `autonomous_red_team.py`
Continuously attacks APIs, agents, tool permissions, prompts, memory boundaries, and
workflow assumptions.

### 13. `regression_knowledge_suite.py`
Every verified artifact can emit regression tests. Future code changes are checked
against accumulated knowledge.

### 14. `knowledge_decay_manager.py`
Detects facts whose freshness window has elapsed and prevents stale knowledge from
being ranked as current.

### 15. `consensus_calibrator.py`
Learns which models/roles are actually reliable for which domains rather than assuming
equal model quality.

## Recommended order

Knowledge Squeezer
→ Evidence Verifier
→ Contradiction Hunter
→ Execution Verifier
→ Memory Curator
→ Revalidator
→ Economic Model Router
→ Knowledge Graph
→ Skill Distiller
→ Autonomous Red Team
