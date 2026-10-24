from __future__ import annotations

try:
    from tools.knowledge.cards import ToolKnowledgeCard
except ImportError:
    from .cards import ToolKnowledgeCard


def build_knowledge_cards() -> list[ToolKnowledgeCard]:
    return [

        # ════════════════════════════════════════════════
        # JEWEL 1 — RADAR (Gap Detection & Diagnostics)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="radar.gap_finder",
            tool_name="Universal Gap Finder",
            category="RADAR",
            file_path="tools/gap_finder.py",
            intent_triggers=[
                "find gaps", "detect missing", "scan codebase", "audit code quality",
                "check test coverage", "find dead code", "unused imports", "bare except",
                "missing docstring", "hardcoded secret", "missing error handling"
            ],
            cognitive_intents=["AUDIT_RADAR"],
            description="Offline static analysis engine that scans the entire SupremeAI codebase for gaps, anti-patterns, security issues, missing tests, dead code, and quality regressions without network access or token cost.",
            when_to_use="Run before any major refactoring, after merging new code, on CI schedule, or when system health degrades.",
            when_not_to_use="Do not use for runtime dynamic errors or for finding solutions — use solution_synthesizer instead.",
            inputs=["project_root: str", "output_path: str (optional)", "severity_filter: str (optional)"],
            outputs=["gap-report.json with critical/high/medium/low findings", "categories: test_coverage, security, quality, dead_code"],
            chain_before=[],
            chain_after=["discovery_fabric.source_scout", "solution_synthesizer", "gap_miner.safe_autofix_plan"],
            cli_example="python tools/gap_finder.py . --output reports/gap-report.json",
            confidence_weight=0.97,
            cost_tokens="zero",
            requires_network=False,
            tags=["static-analysis", "offline", "zero-cost", "security", "quality"],
        ),

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.project_fingerprint",
            tool_name="Gap Miner — Project Fingerprint",
            category="RADAR",
            file_path="tools/gap_miner/tools/project_fingerprint.py",
            intent_triggers=[
                "project DNA", "codebase map", "ecosystem snapshot", "what stack do we use",
                "count files", "language breakdown", "dependency inventory"
            ],
            cognitive_intents=["AUDIT_RADAR", "FEATURE_SYNTHESIS"],
            description="Generates a complete DNA fingerprint of the SupremeAI project: language stats, file counts, service names, dependency graph, and technology ecosystem. Used as the first stage of the synthesis pipeline.",
            when_to_use="Always run as first stage of Feature Synthesis pipeline. Also useful before onboarding new tools to understand impact.",
            when_not_to_use="Not needed for runtime error repair.",
            inputs=["project_root: str"],
            outputs=["fingerprint.json: langs, services, file_count, dependencies, ecosystem"],
            chain_before=[],
            chain_after=["knowledge_squeezer.engine", "gap_miner.context_packager"],
            cli_example="python tools/gap_miner/project_fingerprint.py .",
            confidence_weight=0.99,
            cost_tokens="zero",
            requires_network=False,
            tags=["dna", "fingerprint", "offline", "zero-cost"],
        ),

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.incident_replay",
            tool_name="Gap Miner — Incident Replay",
            category="RADAR",
            file_path="tools/gap_miner/tools/incident_replay.py",
            intent_triggers=[
                "replay incident", "analyze error log", "debug crash", "parse traceback",
                "find root cause from log", "what caused the failure", "incident post-mortem"
            ],
            cognitive_intents=["REPAIR"],
            description="Parses error logs and tracebacks from CI/CD, Render, Sentry, or local runs to extract structured error fingerprints and root cause hypotheses. First step in the self-healing pipeline.",
            when_to_use="Immediately when a runtime error, CI failure, or Sentry alert arrives. Always the first step in REPAIR pipeline.",
            when_not_to_use="Not for proactive code quality audits — use gap_finder for that.",
            inputs=["log_path: str OR error_text: str"],
            outputs=["incident_fingerprint.json: error_type, traceback, affected_files, root_cause_hypothesis"],
            chain_before=[],
            chain_after=["discovery_fabric.source_scout", "knowledge_os.knowledge_quarantine", "solution_synthesizer"],
            cli_example="python tools/gap_miner/incident_replay.py --log logs/sentry_error.txt",
            confidence_weight=0.93,
            cost_tokens="zero",
            requires_network=False,
            tags=["incident", "repair", "debugging", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.drift_detector",
            tool_name="Gap Miner — Drift Detector",
            category="RADAR",
            file_path="tools/gap_miner/tools/drift_detector.py",
            intent_triggers=[
                "documentation drift", "api docs outdated", "README stale", "schema changed",
                "swagger mismatch", "docs not matching code"
            ],
            cognitive_intents=["AUDIT_RADAR"],
            description="Detects drift between actual codebase implementation and documentation/schemas. Finds stale READMEs, mismatched API specs, and outdated inline comments.",
            when_to_use="On weekly schedule or before public API releases.",
            when_not_to_use="Not for code quality issues — use gap_finder for that.",
            inputs=["project_root: str", "docs_path: str (optional)"],
            outputs=["drift_report.json: stale_files, mismatches, severity"],
            chain_before=["radar.gap_finder"],
            chain_after=["solution_synthesizer"],
            cli_example="python tools/gap_miner/drift_detector.py .",
            confidence_weight=0.89,
            cost_tokens="zero",
            requires_network=False,
            tags=["docs", "drift", "offline", "audit"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 2 — SHIELD (Security & Governance)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="shield.governance_policy",
            tool_name="Governance Policy — Allowlist-First Security Kernel",
            category="SHIELD",
            file_path="backend/core/security/governance_policy.py",
            intent_triggers=[
                "check if safe to modify", "can I change this file", "is this target allowed",
                "governance check", "allowlist validation", "block sensitive file"
            ],
            cognitive_intents=["REPAIR", "EVOLUTION", "FEATURE_SYNTHESIS"],
            description="Centralized allowlist-first governance kernel. Validates every proposed code change against explicit allowlist namespaces (skills/, adapters/, brain/) and immutable protected denylist (core/security/, billing/, api/dependencies.py). MUST be called before any automated code modification.",
            when_to_use="Always call BEFORE applying any automated patch, skill creation, or evolution proposal. It is the mandatory safety gate.",
            when_not_to_use="Never skip this check — there are no exceptions.",
            inputs=["target_path: str"],
            outputs=["(is_allowed: bool, reason: str)"],
            chain_before=["solution_synthesizer", "knowledge_squeezer"],
            chain_after=["evolution.canary_manager", "evolution.benchmark_runner"],
            cli_example="from core.security.governance_policy import get_governance_policy; get_governance_policy().validate_evolution_target('skills/my_tool.py')",
            confidence_weight=1.0,
            cost_tokens="zero",
            requires_network=False,
            tags=["security", "governance", "mandatory", "zero-cost", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="shield.artifact_integrity",
            tool_name="Artifact Integrity Gate — SHA-256 Verification",
            category="SHIELD",
            file_path="backend/evolution/artifact_integrity.py",
            intent_triggers=[
                "verify integrity", "sha256 check", "tamper detection", "pre-install check",
                "hash verification", "supply chain security"
            ],
            cognitive_intents=["EVOLUTION"],
            description="SHA-256 hash verification gate that prevents tampered or corrupted artifacts from being installed into the SupremeAI production environment. Runs as 4th defense-in-depth layer in the evolution pipeline.",
            when_to_use="Always before promoting any canary artifact to production.",
            when_not_to_use="Not for runtime error analysis.",
            inputs=["artifact_path: str", "expected_hash: str (optional)"],
            outputs=["ArtifactIntegrityResult: passed, hash, tampered"],
            chain_before=["evolution.benchmark_runner"],
            chain_after=["evolution.canary_manager promotion"],
            cli_example="from evolution.artifact_integrity import ArtifactIntegrityGate; ArtifactIntegrityGate().verify('artifacts/skill_v2.py')",
            confidence_weight=0.99,
            cost_tokens="zero",
            requires_network=False,
            tags=["security", "integrity", "sha256", "supply-chain"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 3 — ENGINE (Discovery, Synthesis, Repair)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="engine.discovery_fabric.source_scout",
            tool_name="Discovery Fabric — Source Scout",
            category="ENGINE",
            file_path="tools/discovery_fabric/supremeai_discovery/source_scout.py",
            intent_triggers=[
                "find open source solution", "search github", "find library", "discover package",
                "best python package for", "search npm", "huggingface model", "pypi search",
                "what tool exists for", "open source alternative"
            ],
            cognitive_intents=["REPAIR", "FEATURE_SYNTHESIS"],
            description="Searches GitHub, npm, PyPI, and HuggingFace for the best existing open-source solutions matching a query. Scores each candidate by trust (0.82 for GitHub), freshness, relevance, maturity, and license safety. Returns ranked candidates with MIT/Apache license filtering.",
            when_to_use="After gap_finder or incident_replay identifies a problem, use source_scout to find if an existing open-source solution already exists before building from scratch.",
            when_not_to_use="Do not use if ai_memory already contains a verified solution for this exact problem (query memory first).",
            inputs=["query: str", "limit_per_source: int (default 8)"],
            outputs=["candidates: list[Candidate] with trust, score, license, stars, freshness"],
            chain_before=["radar.gap_miner.incident_replay", "radar.gap_finder"],
            chain_after=["knowledge_os.knowledge_quarantine", "engine.knowledge_squeezer"],
            cli_example="python tools/discovery_fabric/supremeai_discovery/source_scout.py \"asyncio timeout retry python\" --limit 5",
            confidence_weight=0.88,
            cost_tokens="zero",
            requires_network=True,
            tags=["discovery", "open-source", "github", "pypi", "npm", "huggingface"],
        ),

        ToolKnowledgeCard(
            tool_id="engine.discovery_fabric.trust_engine",
            tool_name="Discovery Fabric — Trust Engine",
            category="ENGINE",
            file_path="tools/discovery_fabric/supremeai_discovery/trust_engine.py",
            intent_triggers=[
                "verify source trustworthiness", "score evidence quality", "how reliable is this",
                "authority score", "freshness check", "reproducibility", "conflict scoring"
            ],
            cognitive_intents=["REPAIR", "FEATURE_SYNTHESIS", "AUDIT_RADAR"],
            description="Scores discovered candidates on evidence quality, source authority, freshness, reproducibility, and conflict risk. Prevents low-quality or malicious sources from being adopted.",
            when_to_use="Always run after source_scout and before knowledge_quarantine.",
            when_not_to_use="Not a standalone tool — always part of the discovery pipeline.",
            inputs=["candidates: list[Candidate]", "prefer_open_source: bool"],
            outputs=["ranked candidates with composite trust scores"],
            chain_before=["engine.discovery_fabric.source_scout"],
            chain_after=["knowledge_os.knowledge_quarantine"],
            cli_example="from supremeai_discovery.trust_engine import TrustEngine; TrustEngine().score(candidates)",
            confidence_weight=0.91,
            cost_tokens="zero",
            requires_network=False,
            tags=["trust", "scoring", "security", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="engine.solution_synthesizer",
            tool_name="Solution Synthesizer — Autonomous Patch Engine",
            category="ENGINE",
            file_path="tools/solution_synthesizer/tools/solution_synthesizer.py",
            intent_triggers=[
                "apply fix", "generate patch", "synthesize solution", "repair code",
                "auto fix", "create patch file", "sandbox test fix", "apply diff"
            ],
            cognitive_intents=["REPAIR"],
            description="Takes a structured issue/gap report, gathers code context, requests a minimal structured patch from the AI solver endpoint (OpenAI-compatible), validates the patch in an isolated sandbox copy, runs tests, and only then optionally applies the verified patch with timestamped backup. Dry-run by default — requires --apply flag for real changes.",
            when_to_use="Final step in the REPAIR pipeline after discovery and governance validation. Only apply on allowlisted targets.",
            when_not_to_use="Never use on protected files (core/security/, billing/, api/dependencies.py).",
            inputs=["project_root: str", "issue: dict (gap-report entry or issue.json)", "--apply flag"],
            outputs=["solution_synthesizer.json report", "verified .patch file (optional)", ".supremeai_backups/ backup"],
            chain_before=["shield.governance_policy", "engine.discovery_fabric.source_scout", "knowledge_os.knowledge_quarantine"],
            chain_after=["evolution.canary_manager", "memory.ai_memory ingestion"],
            cli_example="python tools/solution_synthesizer/tools/solution_synthesizer.py . --issue reports/gap-report.json\npython tools/solution_synthesizer/tools/solution_synthesizer.py . --issue reports/gap-report.json --apply",
            confidence_weight=0.96,
            cost_tokens="low",
            requires_network=True,
            tags=["repair", "patch", "sandbox", "auto-fix", "safety"],
        ),

        ToolKnowledgeCard(
            tool_id="engine.knowledge_squeezer",
            tool_name="Knowledge Squeezer — Multi-Model Adversarial Distillation",
            category="ENGINE",
            file_path="tools/knowledge_squeezer/knowledge_squeezer/engine.py",
            intent_triggers=[
                "squeeze knowledge", "multi model debate", "adversarial audit", "socratic questioning",
                "best architecture for", "deep synthesis", "first principles", "distill knowledge",
                "what is the best way to", "expert consensus"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS"],
            description="7-stage multi-model knowledge distillation engine: (1) Independent generation, (2) Cross-model adversarial audit, (3) Socratic gap mining, (4) First-principles reconstruction, (5) Structured synthesis, (6) Confidence/scoring gate, (7) Optional promotion to ai_memory. Requires at least one of DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY.",
            when_to_use="For deep architectural decisions, complex problem solving, or when multiple AI models' perspectives are needed. Central engine of FEATURE_SYNTHESIS pipeline.",
            when_not_to_use="Do not call for simple bug fixes — use solution_synthesizer. Requires API keys and token budget.",
            inputs=["topic: str", "providers: list (deepseek/claude/gemini)"],
            outputs=["distilled_knowledge_artifact.json with principles, confidence, multi-model_consensus"],
            chain_before=["radar.gap_miner.project_fingerprint"],
            chain_after=["knowledge_os.truth_hierarchy", "intelligence_extensions.skill_distiller", "memory.ai_memory ingestion"],
            cli_example="python tools/knowledge_squeezer/scripts/knowledge_squeezer.py \"How to build a zero-cost distributed rate limiter?\"",
            confidence_weight=0.94,
            cost_tokens="medium",
            requires_network=True,
            tags=["knowledge", "multi-model", "adversarial", "synthesis", "distillation"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 4 — KNOWLEDGE OS (Trust, Safety & Memory)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="knowledge_os.knowledge_quarantine",
            tool_name="Knowledge OS — Quarantine Gate",
            category="MEMORY",
            file_path="tools/knowledge_os/supremeai_knowledge_os/knowledge_quarantine.py",  # NOTE: module not yet scaffolded — file will be created in Phase 3.2
            intent_triggers=[
                "quarantine knowledge", "isolate suspicious", "sandbox knowledge", "verify before admit",
                "trust check", "safety gate", "hold for review"
            ],
            cognitive_intents=["REPAIR", "FEATURE_SYNTHESIS"],
            description="Holds newly discovered knowledge in quarantine before admission to ai_memory. Applies trust scoring threshold checks, prevents unverified external knowledge from corrupting the memory store.",
            when_to_use="Always run after discovery_fabric and before truth_hierarchy. Required gatekeeper.",
            when_not_to_use="Not for runtime code analysis.",
            inputs=["knowledge_item: dict", "trust_threshold: float (default 0.70)"],
            outputs=["QuarantineResult: PASSED | HELD | REJECTED with reason"],
            chain_before=["engine.discovery_fabric.trust_engine"],
            chain_after=["knowledge_os.truth_hierarchy"],
            cli_example="from supremeai_knowledge_os.knowledge_quarantine import KnowledgeQuarantine; KnowledgeQuarantine().evaluate(item)",
            confidence_weight=0.95,
            cost_tokens="zero",
            requires_network=False,
            tags=["quarantine", "safety", "trust", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="knowledge_os.truth_hierarchy",
            tool_name="Knowledge OS — Truth Hierarchy",
            category="MEMORY",
            file_path="tools/knowledge_os/supremeai_knowledge_os/truth_hierarchy.py",
            intent_triggers=[
                "establish truth", "rank knowledge", "highest confidence", "verified fact",
                "conflicting information", "canonical answer", "authoritative source"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "AUDIT_RADAR"],
            description="Establishes a ranked truth hierarchy among multiple knowledge candidates. Resolves conflicts using authority, evidence quality, freshness, and reproducibility scoring to identify the single most reliable answer.",
            when_to_use="After quarantine passes, before admitting to permanent ai_memory.",
            when_not_to_use="Not for runtime code patching.",
            inputs=["candidates: list[dict]"],
            outputs=["TruthHierarchyResult: top_candidate, confidence, conflicts_resolved"],
            chain_before=["knowledge_os.knowledge_quarantine"],
            chain_after=["memory.ai_memory ingestion", "intelligence_extensions.skill_distiller"],
            cli_example="from supremeai_knowledge_os.truth_hierarchy import TruthHierarchy; TruthHierarchy().resolve(candidates)",
            confidence_weight=0.93,
            cost_tokens="zero",
            requires_network=False,
            tags=["truth", "conflict-resolution", "authority", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="knowledge_os.knowledge_firewall",
            tool_name="Knowledge OS — Knowledge Firewall",
            category="SHIELD",
            file_path="tools/knowledge_os/supremeai_knowledge_os/knowledge_firewall.py",
            intent_triggers=[
                "prevent memory poisoning", "block prompt injection", "knowledge security",
                "filter malicious knowledge", "memory integrity"
            ],
            cognitive_intents=["REPAIR", "FEATURE_SYNTHESIS", "AUDIT_RADAR"],
            description="Guards ai_memory from prompt injection attacks, memory poisoning, and adversarial knowledge insertion. Filters new knowledge before permanent storage.",
            when_to_use="Always active — integrated into memory ingestion pipeline.",
            when_not_to_use="Never bypass this in production.",
            inputs=["knowledge_item: dict"],
            outputs=["FirewallResult: CLEAR | BLOCKED with threat_type"],
            chain_before=["knowledge_os.truth_hierarchy"],
            chain_after=["memory.ai_memory ingestion"],
            cli_example="from supremeai_knowledge_os.knowledge_firewall import KnowledgeFirewall; KnowledgeFirewall().inspect(item)",
            confidence_weight=0.98,
            cost_tokens="zero",
            requires_network=False,
            tags=["security", "firewall", "anti-injection", "mandatory", "offline"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 5 — INTELLIGENCE EXTENSIONS
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="intelligence.skill_distiller",
            tool_name="Intelligence Extensions — Skill Distiller",
            category="ENGINE",
            file_path="tools/intelligence_extensions/supremeai_intelligence/skill_distiller.py",
            intent_triggers=[
                "create new skill", "distill workflow", "automate repeated task",
                "convert workflow to skill", "build reusable tool"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "EVOLUTION"],
            description="Converts repeated successful workflows into reusable, versioned skills with tests. When the same pattern of tool calls succeeds 3+ times, distiller extracts it into a permanent skill.",
            when_to_use="At the end of FEATURE_SYNTHESIS pipeline, after truth_hierarchy confirms the knowledge.",
            when_not_to_use="Not for one-off repairs.",
            inputs=["workflow_trace: list[dict]", "success_count: int"],
            outputs=["SkillDefinition: name, version, schema, test_cases"],
            chain_before=["knowledge_os.truth_hierarchy"],
            chain_after=["backend.core.evolution.auto_skill_creator", "memory.ai_memory ingestion"],
            cli_example="from supremeai_intelligence.skill_distiller import SkillDistiller; SkillDistiller().distill(workflow_trace)",
            confidence_weight=0.91,
            cost_tokens="zero",
            requires_network=False,
            tags=["skill", "automation", "distillation", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="intelligence.model_router_economist",
            tool_name="Intelligence Extensions — Model Router Economist",
            category="ENGINE",
            file_path="tools/intelligence_extensions/supremeai_intelligence/model_router_economist.py",
            intent_triggers=[
                "choose best model", "cost-aware routing", "which ai model", "budget routing",
                "model selection", "cheapest model for task", "zero cost ai"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "REPAIR"],
            description="Selects the optimal AI model for each subtask based on complexity, expected value, latency, historical accuracy per domain, and token budget. Prevents expensive models from being called for simple tasks.",
            when_to_use="Always before any LLM API call in the knowledge_squeezer or solution_synthesizer.",
            when_not_to_use="Not for offline/static analysis tasks.",
            inputs=["task: dict", "budget_tokens: int", "available_providers: list"],
            outputs=["ModelRoutingDecision: model, provider, estimated_cost, rationale"],
            chain_before=[],
            chain_after=["engine.knowledge_squeezer", "engine.solution_synthesizer"],
            cli_example="from supremeai_intelligence.model_router_economist import ModelRouterEconomist; ModelRouterEconomist().route(task)",
            confidence_weight=0.89,
            cost_tokens="zero",
            requires_network=False,
            tags=["routing", "budget", "optimization", "zero-cost-overhead"],
        ),

        ToolKnowledgeCard(
            tool_id="intelligence.failure_pattern_miner",
            tool_name="Intelligence Extensions — Failure Pattern Miner",
            category="RADAR",
            file_path="tools/intelligence_extensions/supremeai_intelligence/failure_pattern_miner.py",
            intent_triggers=[
                "learn from failure", "mine error patterns", "ci failure analysis",
                "what goes wrong repeatedly", "failure fingerprint", "recurring bug"
            ],
            cognitive_intents=["AUDIT_RADAR", "REPAIR"],
            description="Mines CI logs, rollback history, Sentry incidents, and rejected patches to build reusable failure fingerprints and prevention rules. Prevents the same failure from occurring twice.",
            when_to_use="After every failed CI run, rollback event, or rejected patch. Runs as background AUDIT task.",
            when_not_to_use="Not for real-time repair — use incident_replay for that.",
            inputs=["log_sources: list[str]", "window_days: int (default 30)"],
            outputs=["FailurePatternReport: patterns, fingerprints, prevention_rules"],
            chain_before=["radar.gap_miner.incident_replay"],
            chain_after=["memory.ai_memory ingestion"],
            cli_example="from supremeai_intelligence.failure_pattern_miner import FailurePatternMiner; FailurePatternMiner().mine(log_dir='logs/')",
            confidence_weight=0.92,
            cost_tokens="zero",
            requires_network=False,
            tags=["failure", "patterns", "learning", "offline"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 6 — MASTER ORCHESTRATOR (Control Plane)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="orchestrator.master_cognitive_orchestrator",
            tool_name="Master Cognitive Orchestrator — Central Control Plane",
            category="ORCHESTRATOR",
            file_path="backend/core/orchestration/master_cognitive_orchestrator.py",
            intent_triggers=[
                "orchestrate pipeline", "dispatch intent", "run full pipeline", "self heal",
                "deep synthesis", "run audit", "governed evolution", "autonomous repair"
            ],
            cognitive_intents=["REPAIR", "FEATURE_SYNTHESIS", "AUDIT_RADAR", "EVOLUTION"],
            description="The central metacognitive brain that routes to correct multi-tool pipeline chains based on CognitiveIntent. Dynamically merges tools: REPAIR=incident_replay+discovery+quarantine+synthesizer+governance, SYNTHESIS=dna+squeezer+truth+distiller+memory, AUDIT=gap_finder+drift+revaluation, EVOLUTION=proposal+governance+benchmark+canary.",
            when_to_use="This is the primary entry point for all autonomous cognitive tasks. Prefer this over calling individual tools directly.",
            when_not_to_use="For ultra-simple one-off CLI scripts that need no chaining.",
            inputs=["intent: CognitiveIntent", "payload: dict"],
            outputs=["PipelineExecutionResult: status, stages_completed, artifacts, confidence, evidence_ids"],
            chain_before=[],
            chain_after=[],
            cli_example="python tools/master_orchestrator.py --intent repair --error 'TimeoutError'\npython tools/master_orchestrator.py --intent synthesis --demand 'Build rate limiter'\npython tools/master_orchestrator.py --intent audit",
            confidence_weight=0.97,
            cost_tokens="varies",
            requires_network=True,
            tags=["orchestrator", "control-plane", "autonomous", "central"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 7 — AUTONOMY PACK
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="autonomy.self_heal_loop",
            tool_name="Autonomy Pack — Self-Heal Loop",
            category="ENGINE",
            file_path="tools/autonomy/tools/self_heal_loop.py",
            intent_triggers=[
                "continuous healing", "watch for errors", "daemon repair", "auto-monitor",
                "always-on healing", "background repair"
            ],
            cognitive_intents=["REPAIR"],
            description="Long-running background watchdog that monitors logs/health endpoints and triggers the self-healing pipeline whenever degradation is detected. Intended as a sidecar process.",
            when_to_use="Deploy as background daemon alongside the SupremeAI backend in production.",
            when_not_to_use="Not for one-shot repairs — use master_orchestrator --intent repair directly.",
            inputs=["watch_path: str", "poll_interval: int (seconds)"],
            outputs=["Continuous monitoring with triggered repair pipelines"],
            chain_before=[],
            chain_after=["orchestrator.master_cognitive_orchestrator"],
            cli_example="python tools/autonomy/self_heal_loop.py --watch logs/ --interval 60",
            confidence_weight=0.90,
            cost_tokens="zero",
            requires_network=False,
            tags=["autonomy", "daemon", "watchdog", "self-healing"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.deploy_guard",
            tool_name="Autonomy Pack — Deploy Guard",
            category="SHIELD",
            file_path="tools/autonomy/tools/deploy_guard.py",
            intent_triggers=[
                "pre-deploy check", "safe to deploy", "deployment gate", "CI gate",
                "validate before deploy", "deploy safety"
            ],
            cognitive_intents=["EVOLUTION"],
            description="Validates readiness before any production deployment: checks test coverage, security scans, environment variable completeness, and governance policy clearance.",
            when_to_use="Always as final gate in CI/CD before any git push to production or Render deploy.",
            when_not_to_use="Not a development-time tool.",
            inputs=["project_root: str", "env_vars: list[str]"],
            outputs=["DeployReadinessReport: gates_passed, gates_failed, blocking_issues"],
            chain_before=["shield.governance_policy", "shield.artifact_integrity"],
            chain_after=["deployment"],
            cli_example="python tools/autonomy/deploy_guard.py . --env-check",
            confidence_weight=0.95,
            cost_tokens="zero",
            requires_network=False,
            tags=["deployment", "safety", "ci-cd", "gate"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 8 — SCRIPT EXECUTION LIFECYCLE KNOWLEDGE
        # (কোন script কখন run করতে হবে — Complete Trigger Guide)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="lifecycle.script_execution_guide",
            tool_name="Script Execution Lifecycle Guide — When to Run Which Script",
            category="ORCHESTRATOR",
            file_path="tools/tool_knowledge_injector.py",
            intent_triggers=[
                "when to run script", "which script to run", "script execution order",
                "what runs first", "when to run gap finder", "when to run knowledge injector",
                "when to run solution synthesizer", "script trigger conditions",
                "development workflow order", "ci cd script order",
                "before deploy what to run", "after merge what to run",
                "kono script kokhon run korbo", "script gulo kokhon chalate hobe",
                "kono script age chalano dorkar", "script execution lifecycle"
            ],
            cognitive_intents=["AUDIT_RADAR", "EVOLUTION", "REPAIR", "FEATURE_SYNTHESIS"],
            description=(
                "Complete decision guide for WHEN to run each SupremeAI script across all phases.\n\n"
                "DEVELOPMENT PHASE (local coding):\n"
                "  gap_finder.py → Run BEFORE committing. Catches dead code, missing tests, secrets.\n"
                "  gap_miner/project_fingerprint.py → Run FIRST when starting a new feature synthesis.\n"
                "  tool_knowledge_injector.py (dry-run) → Run after adding new tools to preview cards.\n\n"
                "CI/CD PIPELINE (GitHub Actions):\n"
                "  gap_finder.py → Runs on every PR push. Blocks merge if CRITICAL findings exist.\n"
                "  autonomy/deploy_guard.py → Final CI gate before Render deploy. Mandatory.\n"
                "  gap_miner/drift_detector.py → Weekly cron. Detects stale docs/schema mismatches.\n"
                "  gap_miner/incident_replay.py → Runs immediately when CI fails.\n\n"
                "AFTER INCIDENT / RUNTIME ERROR (REPAIR pipeline order):\n"
                "  STEP 1: gap_miner/incident_replay.py → Parse error → get fingerprint.\n"
                "  STEP 2: discovery_fabric/source_scout.py → Find open-source solutions.\n"
                "  STEP 3: solution_synthesizer.py (dry-run) → Generate patch, no --apply yet.\n"
                "  STEP 4: governance_policy validation → Validate patch target is allowlisted.\n"
                "  STEP 5: solution_synthesizer.py --apply → Apply ONLY after all validation passes.\n\n"
                "KNOWLEDGE & MEMORY OPERATIONS:\n"
                "  tool_knowledge_injector.py --inject → When new Crown Jewel tools are added.\n"
                "  knowledge_squeezer engine → For deep architectural decisions ONLY (not bug fixes).\n"
                "  tool_knowledge_injector.py --verify → After injection to verify recall works.\n\n"
                "EVOLUTION / SELF-IMPROVEMENT CYCLE:\n"
                "  STEP 1: gap_finder.py → Baseline audit before evolution.\n"
                "  STEP 2: knowledge_squeezer → Deep synthesis of improvement ideas.\n"
                "  STEP 3: solution_synthesizer --apply → Apply approved changes.\n"
                "  STEP 4: autonomy/deploy_guard.py → Final gate before deploy.\n"
                "  STEP 5: tool_knowledge_injector.py --inject → Re-inject updated knowledge."
            ),
            when_to_use="Query this card whenever you need to decide WHICH script to run and IN WHAT ORDER for: development, CI failure, incident, or evolution cycle.",
            when_not_to_use="Do not use to get implementation details of each tool — query individual tool cards for that.",
            inputs=["situation: str (development | ci_failure | incident | evolution | knowledge_update)"],
            outputs=["Ordered script execution sequence with trigger conditions and safety gates"],
            chain_before=[],
            chain_after=["radar.gap_finder", "radar.gap_miner.incident_replay", "engine.solution_synthesizer"],
            cli_example=(
                "# DEVELOPMENT: Before committing\n"
                "python tools/gap_finder.py . --output reports/gap-report.json\n\n"
                "# CI FAILURE: Immediate incident analysis\n"
                "python tools/gap_miner/incident_replay.py --log logs/ci_error.txt\n\n"
                "# AFTER INCIDENT: Find open-source solution\n"
                "python tools/discovery_fabric/supremeai_discovery/source_scout.py \"asyncio timeout fix\"\n\n"
                "# KNOWLEDGE UPDATE: After adding new tools\n"
                "python tools/tool_knowledge_injector.py --inject --verify\n\n"
                "# PRE-DEPLOY GATE: Always last\n"
                "python tools/autonomy/deploy_guard.py . --env-check"
            ),
            confidence_weight=0.99,
            cost_tokens="zero",
            requires_network=False,
            tags=["lifecycle", "script-order", "when-to-run", "execution-guide", "workflow", "phase-trigger"],
        ),

        ToolKnowledgeCard(
            tool_id="lifecycle.pipeline_split_merge_strategy",
            tool_name="Pipeline Split & Merge Strategy — When to Split, When to Merge",
            category="ORCHESTRATOR",
            file_path="tools/pipeline_recipe_compiler.py",
            intent_triggers=[
                "when to split pipeline", "when to merge pipeline", "split merge strategy",
                "pipeline convergence", "parallel pipeline", "merge branches",
                "split pipeline stage", "pipeline fork join", "fan out fan in",
                "pipeline split condition", "when to converge", "pipeline topology",
                "kon porjone split korte hobe", "kon stage e merge korte hobe",
                "pipeline split merge", "kobe split kobe merge",
                "parallel execution when", "convergence point pipeline"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "REPAIR", "AUDIT_RADAR", "EVOLUTION"],
            description=(
                "Complete decision guide for WHEN to SPLIT and WHEN to MERGE pipeline stages.\n\n"
                "SPLIT (Fork / Parallel Execution) — কখন Split করবে:\n"
                "  1. INDEPENDENT PARALLEL DISCOVERY:\n"
                "     source_scout fans out to GitHub+PyPI+npm+HuggingFace simultaneously.\n"
                "     Split AFTER incident_replay outputs fingerprint → 4 parallel searches.\n"
                "  2. MULTI-MODEL ADVERSARIAL SYNTHESIS (knowledge_squeezer Stage 1):\n"
                "     DeepSeek + Claude + Gemini generate INDEPENDENTLY (no anchoring bias).\n"
                "     Split: Each model gets same topic → generates without seeing others.\n"
                "  3. MULTI-FILE INDEPENDENT PATCHES:\n"
                "     solution_synthesizer splits when ≥2 INDEPENDENT issues in gap-report.\n"
                "     Split condition: Issues affect different files with zero shared imports.\n"
                "  4. AUDIT PARALLELISM:\n"
                "     gap_finder splits into: test_coverage + security + quality + dead_code.\n"
                "     All 4 run in parallel threads → merged into unified gap-report.json.\n\n"
                "MERGE (Convergence / Reduce) — কখন Merge করবে:\n"
                "  1. TRUST SCORING REDUCES CANDIDATES:\n"
                "     After source_scout parallel branches → MERGE into trust_engine.\n"
                "     Condition: All parallel searches done AND ≥1 result returned.\n"
                "  2. ADVERSARIAL AUDIT CONVERGENCE (knowledge_squeezer Stage 2):\n"
                "     After Stage 1 independent generation → MERGE all model outputs.\n"
                "     Condition: All providers responded OR timed out with fallback.\n"
                "  3. QUARANTINE GATE:\n"
                "     After trust_engine → MERGE into quarantine (trust_score ≥ 0.70 required).\n"
                "  4. SOLUTION PATCH MERGE:\n"
                "     After split branches generate patches → MERGE into unified diff.\n"
                "     Condition: ALL patches pass sandbox + governance. If ANY fails → BLOCK all.\n"
                "  5. FINAL SYNTHESIS MERGE (knowledge_squeezer Stage 5):\n"
                "     After Stages 1-4 → MERGE into final synthesis.\n"
                "     Condition: ≥2 models agree on core principles (consensus ≥60%).\n"
                "     If consensus <60% → DO NOT MERGE → escalate to human review.\n\n"
                "TOPOLOGY BY PIPELINE TYPE:\n"
                "  REPAIR: incident_replay → [SPLIT×4 source_scout] → [MERGE: trust] → quarantine → synthesizer → governance → apply\n"
                "  SYNTHESIS: fingerprint → [SPLIT×N models] → [MERGE: adversarial] → [SPLIT: socratic] → [MERGE: reconstruct] → truth → distill → memory\n"
                "  AUDIT: [SPLIT×4 gap scanners] → [MERGE: gap-report.json] → drift_detector\n"
                "  EVOLUTION: proposal → governance → [SPLIT×3 benchmarks] → [MERGE: score] → canary → integrity → promote"
            ),
            when_to_use="Query when designing multi-stage pipelines to decide WHERE to insert parallel fan-out (SPLIT) and WHERE to insert convergence (MERGE) points.",
            when_not_to_use="Not for single-tool invocations or simple sequential pipelines with no parallelism.",
            inputs=["pipeline_type: str (repair | synthesis | audit | evolution)", "stage: str"],
            outputs=["Split/Merge topology map with trigger conditions and failure rollback rules"],
            chain_before=["orchestrator.master_cognitive_orchestrator"],
            chain_after=["engine.discovery_fabric.source_scout", "engine.knowledge_squeezer", "radar.gap_finder"],
            cli_example=(
                "# Full split/merge pipeline via master orchestrator:\n"
                "python tools/master_orchestrator.py --intent repair --error 'TimeoutError in ws_handler'\n"
                "python tools/master_orchestrator.py --intent synthesis --demand 'Build zero-cost rate limiter'\n"
                "python tools/master_orchestrator.py --intent audit"
            ),
            confidence_weight=0.97,
            cost_tokens="zero",
            requires_network=False,
            tags=["split", "merge", "pipeline", "parallel", "convergence", "fork-join", "topology", "fan-out", "fan-in"],
        ),

        ToolKnowledgeCard(
            tool_id="lifecycle.tool_knowledge_injector_self",
            tool_name="Tool Knowledge Injector — Self-Documentation & Re-Injection Policy",
            category="MEMORY",
            file_path="tools/tool_knowledge_injector.py",
            intent_triggers=[
                "when to re-inject knowledge", "update knowledge cards", "knowledge injector run",
                "inject new tool knowledge", "add tool to memory", "update ai memory tool registry",
                "knowledge card refresh", "tool registry update", "re-inject after adding tool",
                "knowledge injector schedule", "when to run injector", "tool card update policy"
            ],
            cognitive_intents=["EVOLUTION", "AUDIT_RADAR"],
            description=(
                "Re-injection policy for tool_knowledge_injector.py:\n\n"
                "DRY-RUN (no flags) — always safe:\n"
                "  When: Adding a new tool/module, previewing existing cards, verifying card content.\n"
                "  Command: python tools/tool_knowledge_injector.py\n\n"
                "LIVE INJECT (--inject):\n"
                "  When: New tool passes governance + tests + CI green.\n"
                "  When: Existing tool behavior significantly changed (new inputs/outputs/chain).\n"
                "  When: After Phase milestone completion (Phase 2→3, 3→4 etc.).\n"
                "  Command: python tools/tool_knowledge_injector.py --inject\n\n"
                "INJECT + VERIFY (--inject --verify):\n"
                "  When: First-time setup of ai_memory pgvector schema.\n"
                "  When: After Supabase migration or vector store reset.\n"
                "  When: Monthly scheduled re-injection to refresh embeddings.\n"
                "  Command: python tools/tool_knowledge_injector.py --inject --verify\n\n"
                "EXPORT (--export file.json):\n"
                "  When: Debugging card content without touching DB.\n"
                "  When: Pre-migration backup of knowledge registry.\n"
                "  Command: python tools/tool_knowledge_injector.py --export reports/knowledge_cards.json\n\n"
                "WARNING: Do NOT re-inject on every commit — duplicates create redundant pgvector rows.\n"
                "Only inject when tool registry actually changes."
            ),
            when_to_use="Run after adding/modifying Crown Jewel tools, after phase milestones, or monthly. Always dry-run first to preview.",
            when_not_to_use="Do not run if pgvector schema is not set up (Supabase ai_memory table must exist first).",
            inputs=["--inject (optional)", "--verify (optional)", "--export <path> (optional)", "--json (optional)"],
            outputs=["Injection summary: INJECTED/SKIPPED/FAILED counts", "Recall verification results (if --verify)"],
            chain_before=[],
            chain_after=["memory.ai_memory ingestion"],
            cli_example=(
                "python tools/tool_knowledge_injector.py                     # dry-run preview\n"
                "python tools/tool_knowledge_injector.py --inject             # live inject\n"
                "python tools/tool_knowledge_injector.py --inject --verify    # inject + verify recall\n"
                "python tools/tool_knowledge_injector.py --export reports/knowledge_cards_backup.json"
            ),
            confidence_weight=0.99,
            cost_tokens="zero",
            requires_network=False,
            tags=["knowledge-injector", "self-doc", "re-injection-policy", "memory-update", "tool-registry"],
        ),

        ToolKnowledgeCard(
            tool_id="lifecycle.gap_finder_schedule",
            tool_name="Gap Finder Execution Schedule — When & How Often to Run",
            category="RADAR",
            file_path="tools/gap_finder.py",
            intent_triggers=[
                "how often run gap finder", "gap finder schedule", "when gap finder",
                "gap finder ci schedule", "weekly gap scan", "pre-commit gap check",
                "gap finder trigger", "code audit schedule", "when to audit code",
                "automatic gap scan", "gap finder cron", "quality check schedule"
            ],
            cognitive_intents=["AUDIT_RADAR"],
            description=(
                "Gap Finder execution schedule and trigger conditions:\n\n"
                "MANDATORY TRIGGERS (never skip):\n"
                "  1. PRE-COMMIT (local): Before every git commit on feature branches.\n"
                "     CRITICAL findings → fix before commit. Do NOT bypass with --no-verify.\n"
                "  2. CI/CD PR CHECK: Runs on every pull_request GitHub Action automatically.\n"
                "     Blocks merge if CRITICAL findings exist. Reports uploaded as CI artifacts.\n"
                "  3. POST-MERGE (main branch): After every merge to main.\n"
                "     Catches regressions. Triggers incident_replay automatically via CI.\n\n"
                "SCHEDULED TRIGGERS:\n"
                "  4. WEEKLY FULL AUDIT (Sunday midnight UTC): Full codebase scan.\n"
                "     Output: reports/weekly-gap-{date}.json\n"
                "  5. PRE-DEPLOY: Must complete with zero CRITICAL before deploy_guard.py runs.\n"
                "     deploy_guard checks gap-report.json freshness (<24h).\n\n"
                "ON-DEMAND TRIGGERS:\n"
                "  6. AFTER MAJOR REFACTOR: Any time >50 files changed in one session.\n"
                "  7. AFTER DEPENDENCY UPGRADE: After pip/npm major version bumps.\n"
                "  8. BEFORE PHASE MILESTONE: Before closing any Phase (2→3, 3→4 etc.)\n\n"
                "SEVERITY GATES:\n"
                "  CRITICAL → Blocks CI merge. Fix immediately.\n"
                "  HIGH     → Blocks production deploy. Fix before next release.\n"
                "  MEDIUM   → Warning only. Fix within sprint.\n"
                "  LOW      → Informational. Add to backlog."
            ),
            when_to_use="Use to determine the correct gap_finder run frequency and trigger for any given situation.",
            when_not_to_use="Do not run inside hot path of user-facing API requests — offline/background tool only.",
            inputs=["project_root: str", "--output: str", "--severity: str (optional)"],
            outputs=["gap-report.json categorized by severity: critical/high/medium/low"],
            chain_before=[],
            chain_after=["radar.gap_miner.incident_replay", "engine.solution_synthesizer"],
            cli_example=(
                "# Pre-commit scan:\n"
                "python tools/gap_finder.py . --output reports/gap-report.json\n\n"
                "# Only CRITICAL and HIGH:\n"
                "python tools/gap_finder.py . --severity high --output reports/gap-high.json\n\n"
                "# Weekly audit with date:\n"
                "python tools/gap_finder.py . --output reports/weekly-gap-$(date +%Y%m%d).json"
            ),
            confidence_weight=0.98,
            cost_tokens="zero",
            requires_network=False,
            tags=["gap-finder", "schedule", "cron", "pre-commit", "ci", "audit-schedule"],
        ),

        ToolKnowledgeCard(
            tool_id="lifecycle.pipeline_recipe_compiler",
            tool_name="Pipeline Recipe Compiler — Dynamic Pipeline Assembly",
            category="ORCHESTRATOR",
            file_path="tools/pipeline_recipe_compiler.py",
            intent_triggers=[
                "compile pipeline", "build pipeline recipe", "pipeline assembly", "dynamic pipeline",
                "create pipeline from scratch", "pipeline template", "chain tools dynamically",
                "pipeline builder", "recipe compiler", "tool chain compiler",
                "assemble tool chain", "pipeline recipe", "dynamic tool chain"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "REPAIR", "AUDIT_RADAR", "EVOLUTION"],
            description=(
                "Pipeline Recipe Compiler — assembles multi-tool execution pipelines dynamically.\n\n"
                "WHEN TO USE:\n"
                "  - master_orchestrator cannot find a pre-built recipe for a novel task.\n"
                "  - Composing a CUSTOM pipeline from individual tool cards.\n"
                "  - Task requires a HYBRID pipeline (e.g., repair + synthesis combined).\n"
                "  - Testing a new pipeline topology before promoting to orchestrator.\n\n"
                "WHEN NOT TO USE:\n"
                "  - Standard REPAIR/SYNTHESIS/AUDIT intents → use master_orchestrator directly.\n"
                "  - Single-tool invocations → invoke the tool directly.\n\n"
                "COMPILATION PHASES:\n"
                "  1. Intent Classification → REPAIR | SYNTHESIS | AUDIT | EVOLUTION | HYBRID\n"
                "  2. Tool Card Query → Fetch relevant cards from ai_memory by intent\n"
                "  3. Dependency Graph Build → DAG from chain_before/chain_after metadata\n"
                "  4. Topology Optimization → Insert SPLIT points for parallel-capable stages\n"
                "  5. Safety Injection → Add governance_policy before any mutation step\n"
                "  6. Recipe Output → Ordered execution plan with fallback paths\n\n"
                "MERGE TRIGGERS IN COMPILED RECIPES:\n"
                "  - After ANY parallel fan-out group completes (all branches done or timeout)\n"
                "  - Before ANY mutation step (patch apply, memory write, skill creation)\n"
                "  - At confidence gates (trust_score ≥ threshold before proceeding)\n"
                "  - At phase boundaries (discovery → synthesis → validation → apply)"
            ),
            when_to_use="Use when you need a custom tool chain for a novel task not covered by standard orchestrator intents.",
            when_not_to_use="Do not use for standard intents — master_orchestrator handles those more efficiently.",
            inputs=["intent: str", "context: dict", "available_tools: list (auto-discovered from ai_memory)"],
            outputs=["ExecutionRecipe: ordered stages with split/merge topology, fallback paths, safety gates"],
            chain_before=["orchestrator.master_cognitive_orchestrator"],
            chain_after=["engine.discovery_fabric.source_scout", "engine.solution_synthesizer", "radar.gap_finder"],
            cli_example=(
                "# Compile custom hybrid pipeline:\n"
                "python tools/pipeline_recipe_compiler.py --intent hybrid --demand 'Fix AND improve rate limiter'\n\n"
                "# Preview compiled recipe (dry-run):\n"
                "python tools/pipeline_recipe_compiler.py --intent repair --context '{\"error\": \"TimeoutError\"}' --dry-run\n\n"
                "# Export recipe as JSON:\n"
                "python tools/pipeline_recipe_compiler.py --intent audit --export reports/audit_recipe.json"
            ),
            confidence_weight=0.93,
            cost_tokens="zero",
            requires_network=False,
            tags=["pipeline", "recipe", "compiler", "dynamic", "assembly", "dag", "topology"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 9 — EVOLUTION ENGINE (Self-Evolution Core)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="evolution.agent_breeder",
            tool_name="Evolution Engine — Agent Breeder (Genetic Algorithm)",
            category="EVOLUTION",
            file_path="backend/core/evolution/agent_breeder.py",
            intent_triggers=[
                "breed agents", "genetic algorithm", "evolve agent", "crossover agents",
                "produce better agent", "agent mutation", "roulette selection",
                "spawn superior offspring", "agent genetics", "llm crossover"
            ],
            cognitive_intents=["EVOLUTION"],
            description=(
                "Performs genetic breeding of two parent agents to produce a superior offspring. "
                "4-step process: (1) Selection via roulette-wheel or tournament from breeding pool, "
                "(2) Crossover of JSONB chromosomes (uniform or single-point), "
                "(3) Mutation via Gaussian perturbation + LLM-guided trait refinement, "
                "(4) Evaluation via fitness scoring through shadow deployment. "
                "Uses genetic algorithms to evolve agents beyond human-designed configurations."
            ),
            when_to_use="Run during EVOLUTION cycle when FitnessEngine reports 2+ agents with complementary strengths. Breeds a new candidate agent.",
            when_not_to_use="Do not run during active production traffic. Always test offspring in shadow deployment first.",
            inputs=["parent_a: AgentConfig", "parent_b: AgentConfig", "breeding_strategy: str (roulette|tournament)"],
            outputs=["offspring_config: AgentConfig with bred traits", "mutation_log", "fitness_estimate"],
            chain_before=["evolution.fitness_engine", "evolution.performance_oracle"],
            chain_after=["evolution.fitness_engine", "evolution.self_evolution_agent"],
            cli_example="from core.evolution.agent_breeder import AgentBreeder; AgentBreeder().breed(parent_a, parent_b)",
            confidence_weight=0.88,
            cost_tokens="low",
            requires_network=False,
            tags=["evolution", "genetic-algorithm", "breeding", "crossover", "mutation", "self-evolution"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.auto_skill_creator",
            tool_name="Evolution Engine — Auto Skill Creator (Zero-Gap Pipeline)",
            category="EVOLUTION",
            file_path="backend/core/evolution/auto_skill_creator.py",
            intent_triggers=[
                "auto create skill", "generate new skill autonomously", "skill generation",
                "create capability automatically", "autonomous skill synthesis",
                "validate generated code", "ast security scan new skill",
                "ci dry run new skill", "atomic skill registration"
            ],
            cognitive_intents=["EVOLUTION", "FEATURE_SYNTHESIS"],
            description=(
                "Core of the SupremeAI self-evolution engine. Autonomously generates, validates, and "
                "registers new skills. Pipeline: generate skill code via LLM -> AST security scan "
                "-> CI/CD dry run -> atomic database transaction for registration. "
                "Implements Zero-Gap pipeline to ensure only safe, validated code enters production. "
                "Triggered when SelfEvolutionAgent identifies a missing capability."
            ),
            when_to_use="After SelfEvolutionAgent identifies a missing skill or after repeated task failures expose a capability gap.",
            when_not_to_use="Never call directly without governance_policy clearance. Always requires AST scan before any file write.",
            inputs=["skill_spec: dict (name, description, expected_inputs, expected_outputs)", "context: str"],
            outputs=["SkillDefinition: file_path, version, test_cases, security_scan_result"],
            chain_before=["shield.governance_policy", "evolution.self_evolution_agent"],
            chain_after=["evolution.fitness_engine", "intelligence.skill_distiller", "memory.ai_memory ingestion"],
            cli_example="from core.evolution.auto_skill_creator import AutoSkillCreator; AutoSkillCreator().create(skill_spec)",
            confidence_weight=0.91,
            cost_tokens="low",
            requires_network=True,
            tags=["evolution", "skill-creation", "autonomous", "ast-scan", "zero-gap", "self-evolution"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.daily_learner",
            tool_name="Evolution Engine — Daily Learner (Self-Directed Learning Cycle)",
            category="EVOLUTION",
            file_path="backend/core/evolution/daily_learner.py",
            intent_triggers=[
                "daily learning", "scan arxiv", "auto learn new techniques",
                "self directed learning", "goal decomposition", "impact to effort",
                "learn from github", "integrate new discoveries", "daily improvement",
                "autonomous research", "knowledge refresh daily"
            ],
            cognitive_intents=["EVOLUTION", "FEATURE_SYNTHESIS"],
            description=(
                "Fully autonomous learning agent that runs daily: "
                "(1) Auto-decomposes goals into executable sub-tasks, "
                "(2) Scans ArXiv, GitHub, and internal knowledge base for new techniques, "
                "(3) Self-prioritizes learning based on impact-to-effort ratio, "
                "(4) Integrates discoveries into EvolutionEngine, "
                "(5) Generates self-validation test suites for learned capabilities. "
                "Zero-cost: uses heuristic scoring + free-tier LLM routing + cached results."
            ),
            when_to_use="Run daily (scheduled cron, midnight UTC). Also run after any Phase milestone to discover next-phase techniques.",
            when_not_to_use="Do not run more than once per day — results are cached. Not for immediate incident response.",
            inputs=["goals: list[str]", "knowledge_sources: list (arxiv|github|internal)"],
            outputs=["LearningPlan: prioritized sub-tasks, discovered techniques, test suites"],
            chain_before=[],
            chain_after=["evolution.evolution_engine", "memory.ai_memory ingestion"],
            cli_example="from core.evolution.daily_learner import DailyLearner; await DailyLearner().run_daily_cycle(goals=['improve rate limiting'])",
            confidence_weight=0.87,
            cost_tokens="zero",
            requires_network=True,
            tags=["learning", "daily", "arxiv", "github", "self-directed", "goal-decomposition", "cron"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.evolution_engine",
            tool_name="Evolution Engine — Core (Failure Pattern Detector & Improvement Hub)",
            category="EVOLUTION",
            file_path="backend/core/evolution/evolution_engine.py",
            intent_triggers=[
                "record task outcome", "detect failure pattern", "propose skill improvement",
                "optimize prompt", "evolution engine core", "task failure tracking",
                "llm improvement proposal", "supabase sqlite evolution",
                "user feedback evolution", "adapt system"
            ],
            cognitive_intents=["EVOLUTION", "REPAIR"],
            description=(
                "Core evolutionary learning engine. Records task outcomes, detects repeated failure "
                "patterns (underperforming prompts, repeated failures), and proposes improvements "
                "via LLM interaction. Manages user feedback loop. "
                "Dual storage: Supabase (production) + local SQLite (offline fallback). "
                "The central hub that all other evolution modules report to and pull from."
            ),
            when_to_use="Invoked after every task completion to record outcome. Also query for failure patterns before proposing skill improvements.",
            when_not_to_use="Not for real-time request processing — background async only.",
            inputs=["task_id: str", "outcome: dict (success/failure, latency, quality_score)", "user_feedback: str (optional)"],
            outputs=["EvolutionRecord stored in DB", "ImprovementProposal (if pattern detected)", "updated skill scores"],
            chain_before=[],
            chain_after=["evolution.auto_skill_creator", "evolution.agent_breeder", "memory.ai_memory ingestion"],
            cli_example="from core.evolution.evolution_engine import EvolutionEngine; await EvolutionEngine().record_outcome(task_id, outcome)",
            confidence_weight=0.93,
            cost_tokens="zero",
            requires_network=False,
            tags=["evolution", "pattern-detection", "feedback-loop", "sqlite", "supabase", "core"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.fitness_engine",
            tool_name="Evolution Engine — Fitness Engine (Skill Lifecycle Manager)",
            category="EVOLUTION",
            file_path="backend/core/evolution/fitness_engine.py",
            intent_triggers=[
                "fitness score", "skill performance", "deprecate skill", "prune skill",
                "skill lifecycle", "underperforming skill", "skill quality control",
                "soft prune", "skill registry fitness", "automated fitness"
            ],
            cognitive_intents=["EVOLUTION", "AUDIT_RADAR"],
            description=(
                "Manages fitness evaluation and lifecycle of dynamic AI skills. "
                "Tracks skill execution metrics, calculates composite performance scores, "
                "and automatically deprecates or soft-prunes underperforming skills. "
                "Phase 3: AutomatedFitnessEngine with precision scoring and zero fake fallbacks. "
                "Integrates with skill registries, databases, and filesystem."
            ),
            when_to_use="Run continuously as background process after every skill execution. Run before breeding and before evolution proposals to get current fitness scores.",
            when_not_to_use="Not a real-time tool — scores accumulate over many executions before pruning decisions.",
            inputs=["skill_id: str", "execution_metrics: dict (latency, success_rate, quality)"],
            outputs=["FitnessScore: composite score", "LifecycleDecision: KEEP|IMPROVE|DEPRECATE|PRUNE"],
            chain_before=["evolution.evolution_engine"],
            chain_after=["evolution.agent_breeder", "evolution.self_evolution_agent"],
            cli_example="from core.evolution.fitness_engine import FitnessEngine; FitnessEngine().score_skill(skill_id, metrics)",
            confidence_weight=0.92,
            cost_tokens="zero",
            requires_network=False,
            tags=["fitness", "skill-lifecycle", "deprecation", "pruning", "quality-control", "evolution"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.performance_oracle",
            tool_name="Evolution Engine — Performance Oracle (Agent Weakness Identifier)",
            category="EVOLUTION",
            file_path="backend/core/evolution/performance_oracle.py",
            intent_triggers=[
                "track agent performance", "weakest link agent", "retrain agent",
                "replace agent", "deprecate agent", "composite agent score",
                "response time tracking", "accuracy tracking", "cost tracking",
                "performance oracle", "agent weakness identification"
            ],
            cognitive_intents=["EVOLUTION", "AUDIT_RADAR"],
            description=(
                "Tracks agent performance (response time, accuracy, cost), identifies weakest links, "
                "and suggests: Retrain / Replace / Deprecate / Optimize / Breed new agent. "
                "Uses configurable weights for composite scoring — all thresholds from settings, not hardcoded. "
                "Feeds recommendations to AgentBreeder and SelfEvolutionAgent."
            ),
            when_to_use="Run on scheduled interval (every 6h) to score all active agents. Run before any breeding or replacement decision.",
            when_not_to_use="Not for real-time per-request decisions — use model_router_economist for that.",
            inputs=["agent_id: str", "metrics_window: int (hours, default 24)"],
            outputs=["PerformanceReport: scores per agent, weakest_links, recommended_actions"],
            chain_before=[],
            chain_after=["evolution.agent_breeder", "evolution.self_evolution_agent"],
            cli_example="from core.evolution.performance_oracle import PerformanceOracle; PerformanceOracle().identify_weakest_links(window_hours=24)",
            confidence_weight=0.90,
            cost_tokens="zero",
            requires_network=False,
            tags=["performance", "oracle", "weakness-detection", "retrain", "replace", "evolution"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.self_evolution_agent",
            tool_name="Evolution Engine — Self Evolution Agent (Autonomous Improvement Daemon)",
            category="EVOLUTION",
            file_path="backend/core/evolution/self_evolution_agent.py",
            intent_triggers=[
                "self evolution", "continuous evolution loop", "monitor skill fitness",
                "trigger skill refactor", "generate new capabilities",
                "zero gap pipeline", "ast security scan evolution",
                "autonomous self improve", "evolution loop daemon"
            ],
            cognitive_intents=["EVOLUTION"],
            description=(
                "Autonomous continuous loop that monitors skill fitness and drives self-improvement. "
                "Evaluates all skill fitness scores -> identifies below-threshold skills "
                "-> initiates refactoring OR generates new skills to fill gaps. "
                "Zero-Gap pipeline ensures safe integration: AST scan -> CI/CD dry run -> atomic DB transaction. "
                "Runs as a background daemon in FastAPI lifespan."
            ),
            when_to_use="Deploy as background daemon alongside the backend. Also call directly to trigger an immediate evolution cycle.",
            when_not_to_use="Do not call in a request-response context. Background-only.",
            inputs=["fitness_threshold: float (default 0.7)", "cycle_interval: int (seconds)"],
            outputs=["EvolutionCycleReport: skills_improved, skills_created, skills_deprecated"],
            chain_before=["evolution.fitness_engine", "evolution.performance_oracle"],
            chain_after=["evolution.auto_skill_creator", "evolution.agent_breeder"],
            cli_example="from core.evolution.self_evolution_agent import SelfEvolutionAgent; await SelfEvolutionAgent().run_evolution_cycle()",
            confidence_weight=0.91,
            cost_tokens="low",
            requires_network=True,
            tags=["self-evolution", "continuous", "daemon", "zero-gap", "ast-scan", "autonomous"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.self_updater",
            tool_name="Evolution Engine — Self Updater (Runtime Multi-File Patch Engine)",
            category="EVOLUTION",
            file_path="backend/core/evolution/self_updater.py",
            intent_triggers=[
                "apply runtime patch", "self update code", "multi file patch",
                "self healing rollback", "code update runtime", "apply diff runtime",
                "automated code patch", "rollback patch"
            ],
            cognitive_intents=["EVOLUTION", "REPAIR"],
            description=(
                "Secure mechanism for applying runtime code updates and multi-file patches. "
                "All write operations restricted to ALLOWED_BASE_DIR (cannot escape repo root). "
                "Supports atomic multi-file patch application with automatic rollback on failure. "
                "Self-healing: if a patch causes failures, auto-reverts to previous state."
            ),
            when_to_use="Final step of EVOLUTION pipeline after governance_policy, artifact_integrity, and canary all pass. Applies the verified patch to production code.",
            when_not_to_use="NEVER call without prior governance_policy clearance and artifact_integrity verification.",
            inputs=["patch: dict (file_path, content, backup_path)", "authorized: bool (must be True)"],
            outputs=["PatchResult: applied_files, backup_paths, rollback_available"],
            chain_before=["shield.governance_policy", "shield.artifact_integrity"],
            chain_after=["evolution.fitness_engine"],
            cli_example="from core.evolution.self_updater import SelfUpdater; SelfUpdater(authorized=True).apply_patch(patch)",
            confidence_weight=0.95,
            cost_tokens="zero",
            requires_network=False,
            tags=["self-updater", "patch", "runtime", "rollback", "atomic", "evolution"],
        ),

        ToolKnowledgeCard(
            tool_id="evolution.skill_graph",
            tool_name="Evolution Engine — Skill Graph (Semantic Skill DAG Router)",
            category="EVOLUTION",
            file_path="backend/core/evolution/skill_graph.py",
            intent_triggers=[
                "skill graph", "skill dependencies", "semantic skill map",
                "skill routing", "fallback skill routing", "skill compatibility",
                "dynamic skill weights", "skill dag", "input output type matching"
            ],
            cognitive_intents=["EVOLUTION", "FEATURE_SYNTHESIS"],
            description=(
                "Dynamic directed graph (DAG) representation of all skills using networkx. "
                "Features: input-output type compatibility verification, dynamic weights, "
                "and fallback routing when primary skill is unavailable. "
                "Enables finding alternative skill paths when one skill fails. "
                "Used by master_orchestrator and skill_manager for routing decisions."
            ),
            when_to_use="Query before any skill invocation to verify compatibility and find fallback paths. Updated automatically when skills are added/deprecated.",
            when_not_to_use="Not a standalone CLI tool — library module used by orchestrators.",
            inputs=["skill_id: str", "input_types: list", "output_types: list"],
            outputs=["CompatiblePath: list of skills", "FallbackRoute: alternative path if primary unavailable"],
            chain_before=[],
            chain_after=["orchestrator.master_cognitive_orchestrator", "evolution.fitness_engine"],
            cli_example="from core.evolution.skill_graph import EvolutionSkillGraph; path = EvolutionSkillGraph().find_path(from_skill, to_skill)",
            confidence_weight=0.89,
            cost_tokens="zero",
            requires_network=False,
            tags=["skill-graph", "dag", "routing", "fallback", "networkx", "compatibility"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 10 — ORCHESTRATION LAYER
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="orchestration.agent_orchestrator",
            tool_name="Orchestration — Agent Orchestrator (FastAPI Periodic Task Scheduler)",
            category="ORCHESTRATOR",
            file_path="backend/core/orchestration/agent_orchestrator.py",
            intent_triggers=[
                "schedule periodic task", "fitness scoring schedule", "health status endpoint",
                "fastapi lifespan tasks", "periodic background task", "orchestrator startup",
                "task scheduler backend", "background job orchestrator"
            ],
            cognitive_intents=["EVOLUTION", "AUDIT_RADAR"],
            description=(
                "FastAPI-integrated orchestrator that schedules periodic background tasks. "
                "Key responsibilities: fitness scoring on schedule, health/status endpoint, "
                "integrated with FastAPI lifespan (startup/shutdown hooks). "
                "Coordinates all background maintenance loops."
            ),
            when_to_use="Always active — runs via FastAPI lifespan. Automatically starts fitness scoring, health checks on server startup.",
            when_not_to_use="Not called manually — lifecycle-managed by FastAPI.",
            inputs=["periodic_tasks: list[Callable]", "intervals: dict"],
            outputs=["Background task execution", "health endpoint at /orchestrator/health"],
            chain_before=[],
            chain_after=["evolution.fitness_engine", "autonomy.self_heal_loop"],
            cli_example="# Auto-started via FastAPI lifespan\n# GET /orchestrator/health",
            confidence_weight=0.93,
            cost_tokens="zero",
            requires_network=False,
            tags=["orchestrator", "fastapi", "lifespan", "scheduler", "background", "periodic"],
        ),

        ToolKnowledgeCard(
            tool_id="orchestration.swarm_orchestrator",
            tool_name="Orchestration — Swarm Orchestrator (Parallel Multi-Agent Swarm)",
            category="ORCHESTRATOR",
            file_path="backend/core/orchestration/swarm_orchestrator.py",
            intent_triggers=[
                "swarm agents", "parallel agents", "fan out tasks",
                "multi agent parallel execution", "swarm intelligence",
                "distributed task agents", "agent swarm consensus"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "REPAIR"],
            description=(
                "Manages parallel execution of multiple AI agents as a swarm. "
                "Distributes subtasks across multiple agent instances simultaneously (fan-out), "
                "collects results (fan-in), resolves conflicts via voting or trust scores, "
                "and merges into unified output. "
                "Optimized for zero-cost parallel execution via free-tier provider routing."
            ),
            when_to_use="Use when a task can be parallelized across multiple independent agents: multi-source research, parallel code generation, consensus voting.",
            when_not_to_use="Not for sequential dependent tasks. Not for tasks requiring shared mutable state.",
            inputs=["task: dict", "agent_count: int", "merge_strategy: str (vote|trust|first)"],
            outputs=["SwarmResult: merged_output, agent_responses, consensus_score"],
            chain_before=["orchestrator.master_cognitive_orchestrator"],
            chain_after=["knowledge_os.truth_hierarchy"],
            cli_example="from core.orchestration.swarm_orchestrator import SwarmOrchestrator; await SwarmOrchestrator().execute(task, agents=5)",
            confidence_weight=0.88,
            cost_tokens="low",
            requires_network=True,
            tags=["swarm", "parallel", "fan-out", "fan-in", "multi-agent", "consensus"],
        ),

        ToolKnowledgeCard(
            tool_id="orchestration.crew_departments",
            tool_name="Orchestration — Crew Departments (Domain-Specialized Agent Teams)",
            category="ORCHESTRATOR",
            file_path="backend/core/orchestration/crew_departments.py",
            intent_triggers=[
                "crew ai departments", "specialized agent teams", "domain routing agents",
                "dev team agent", "business team agent", "ux team agent",
                "route to department", "domain-specific agent"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "REPAIR", "EVOLUTION"],
            description=(
                "CrewAI-style department routing with specialized agent teams. "
                "Departments: DEV (code generation, debugging), BUSINESS (strategy, analysis), "
                "UX (design, accessibility), OPS (deployment, monitoring). "
                "Routes incoming tasks to the most appropriate department based on task type. "
                "Each department has specialized prompts, tools, and model preferences."
            ),
            when_to_use="Use when a task has a clear domain (dev/business/ux/ops). Better than generic orchestrator for domain-specific tasks.",
            when_not_to_use="Not for cross-domain tasks — use master_cognitive_orchestrator for those.",
            inputs=["task: dict", "domain: str (dev|business|ux|ops|auto-detect)"],
            outputs=["DepartmentResult: output, department_used, confidence"],
            chain_before=["orchestrator.master_cognitive_orchestrator"],
            chain_after=["evolution.evolution_engine"],
            cli_example="from core.orchestration.crew_departments import CrewDepartments; await CrewDepartments().route(task)",
            confidence_weight=0.87,
            cost_tokens="low",
            requires_network=True,
            tags=["crew", "departments", "specialized", "routing", "domain", "teams"],
        ),

        ToolKnowledgeCard(
            tool_id="orchestration.cloud_sandbox",
            tool_name="Orchestration — Cloud Sandbox Orchestrator (Safe Code Execution)",
            category="ORCHESTRATOR",
            file_path="backend/core/orchestration/cloud_sandbox_orchestrator.py",
            intent_triggers=[
                "cloud sandbox execution", "safe code execution", "isolated execution environment",
                "sandbox orchestrator", "run untrusted code safely",
                "sandboxed agent execution", "validate patch in sandbox"
            ],
            cognitive_intents=["EVOLUTION", "REPAIR"],
            description=(
                "Orchestrates code execution in isolated cloud sandbox environments. "
                "Prevents untrusted or AI-generated code from affecting production systems. "
                "Used for: testing evolution candidates, running user-submitted code, "
                "validating patches before application. Integrates with microvm_sandbox for isolation."
            ),
            when_to_use="Always use before applying any AI-generated code patch to production. Use for running user-submitted scripts safely.",
            when_not_to_use="Not for production trusted code — overhead too high for normal execution.",
            inputs=["code: str", "language: str", "timeout: int (seconds)", "env_vars: dict"],
            outputs=["SandboxResult: stdout, stderr, exit_code, security_violations"],
            chain_before=["shield.governance_policy"],
            chain_after=["shield.artifact_integrity", "evolution.self_updater"],
            cli_example="from core.orchestration.cloud_sandbox_orchestrator import CloudSandboxOrchestrator; await CloudSandboxOrchestrator().run(code, language='python')",
            confidence_weight=0.94,
            cost_tokens="zero",
            requires_network=False,
            tags=["sandbox", "cloud", "isolation", "safe-execution", "microvm", "security"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 11 — AUTONOMY SUB-TOOLS
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="autonomy.agent_change_budget",
            tool_name="Autonomy — Agent Change Budget (Risk Level Classifier)",
            category="ENGINE",
            file_path="tools/autonomy/tools/agent_change_budget.py",
            intent_triggers=[
                "change budget", "risk classify change", "how risky is this change",
                "change impact assessment", "low medium high critical change",
                "safe to automate change", "change risk level"
            ],
            cognitive_intents=["EVOLUTION", "REPAIR"],
            description=(
                "Risk classifier for proposed code changes. Scores changes as LOW/MEDIUM/HIGH/CRITICAL "
                "based on: number of files changed, external dependencies, data migration, "
                "auth/security changes, production scope. "
                "Prevents agents from making overly risky changes autonomously."
            ),
            when_to_use="Always run BEFORE any automated code change. If CRITICAL -> require human approval before proceeding.",
            when_not_to_use="Not for runtime request handling.",
            inputs=["--files list", "--external (flag)", "--data-migration (flag)", "--auth (flag)", "--production (flag)"],
            outputs=["change_budget.json: {score, level: LOW|MEDIUM|HIGH|CRITICAL}"],
            chain_before=[],
            chain_after=["shield.governance_policy", "engine.solution_synthesizer"],
            cli_example="python tools/autonomy/tools/agent_change_budget.py --files a.py b.py --production --output reports/change_budget.json",
            confidence_weight=0.95,
            cost_tokens="zero",
            requires_network=False,
            tags=["change-budget", "risk", "classifier", "safety", "autonomous", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.autonomy_cycle",
            tool_name="Autonomy — Autonomy Cycle (Observe-Diagnose-Plan-Verify Loop)",
            category="ENGINE",
            file_path="tools/autonomy/tools/autonomy_cycle.py",
            intent_triggers=[
                "autonomy cycle", "observe diagnose plan verify", "full autonomy loop",
                "run all autonomy tools", "autonomous improvement cycle",
                "complete local self-improvement"
            ],
            cognitive_intents=["EVOLUTION", "AUDIT_RADAR"],
            description=(
                "Orchestrates the full autonomy cycle: Observe -> Diagnose -> Plan -> Verify. "
                "Runs in sequence: maintenance_watchdog -> deploy_guard -> capability_builder. "
                "Single command to run the complete local autonomy loop "
                "without touching the production backend."
            ),
            when_to_use="Run weekly or after major feature additions as a local autonomy health check. Best entry point for the full offline autonomy pipeline.",
            when_not_to_use="Not for production — local offline tool only.",
            inputs=["project: str (project root path)", "--output: str"],
            outputs=["autonomy_cycle.json: combined results from all 3 steps"],
            chain_before=[],
            chain_after=["autonomy.maintenance_watchdog", "autonomy.deploy_guard", "autonomy.capability_builder"],
            cli_example="python tools/autonomy/tools/autonomy_cycle.py . --output reports/autonomy_cycle.json",
            confidence_weight=0.90,
            cost_tokens="zero",
            requires_network=False,
            tags=["autonomy", "cycle", "observe", "diagnose", "plan", "verify", "loop", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.capability_builder",
            tool_name="Autonomy — Capability Builder (Project Capability Gap Mapper)",
            category="ENGINE",
            file_path="tools/autonomy/tools/capability_builder.py",
            intent_triggers=[
                "map project capabilities", "what can this project do",
                "capability gap analysis", "missing capability", "project domain analysis",
                "what needs to be built", "existing vs needed capability"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "AUDIT_RADAR"],
            description=(
                "Analyzes a project codebase to map existing capabilities and identify gaps "
                "relative to a stated goal. Domains: web_app, api, data, ai, devops, automation. "
                "Keyword matching against file names classifies current capabilities. "
                "Outputs a capability plan showing what exists and what is missing for the goal."
            ),
            when_to_use="Run when starting a new feature to understand what already exists and what needs building. Part of the autonomy_cycle.",
            when_not_to_use="Not for runtime decisions.",
            inputs=["project: str (project root)", "--goal: str (what you want to build)"],
            outputs=["capability_plan.json: {existing_capabilities, missing_for_goal, recommendations}"],
            chain_before=["autonomy.autonomy_cycle"],
            chain_after=["engine.solution_synthesizer"],
            cli_example="python tools/autonomy/tools/capability_builder.py . --goal 'build real-time rate limiter' --output reports/capability_plan.json",
            confidence_weight=0.85,
            cost_tokens="zero",
            requires_network=False,
            tags=["capability", "mapping", "gap-analysis", "domain", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.knowledge_ingestor",
            tool_name="Autonomy — Knowledge Ingestor (External Knowledge Intake with Provenance)",
            category="MEMORY",
            file_path="tools/autonomy/tools/knowledge_ingestor.py",
            intent_triggers=[
                "ingest external knowledge", "add knowledge from file",
                "knowledge intake", "record new knowledge", "knowledge provenance",
                "authority score knowledge", "sha256 knowledge record"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS"],
            description=(
                "Ingests external knowledge from a file into a structured knowledge record. "
                "Computes SHA-256 content hash for deduplication and integrity. "
                "Records authority score, provenance, and ingestion timestamp. "
                "Output is a knowledge_record.json ready for quarantine -> truth_hierarchy -> ai_memory pipeline."
            ),
            when_to_use="When adding external knowledge (documentation, research papers, design docs) into the ai_memory pipeline. Always pair with knowledge_quarantine afterwards.",
            when_not_to_use="Not for ingesting code — use source_scout + trust_engine for code.",
            inputs=["--source: str (file path)", "--title: str", "--authority: float (0-1, default 0.8)"],
            outputs=["knowledge_record.json: {id, title, authority, content_sha256, claims, provenance}"],
            chain_before=[],
            chain_after=["knowledge_os.knowledge_quarantine", "knowledge_os.truth_hierarchy"],
            cli_example="python tools/autonomy/tools/knowledge_ingestor.py --source docs/architecture.md --title 'Architecture Overview' --authority 0.9",
            confidence_weight=0.87,
            cost_tokens="zero",
            requires_network=False,
            tags=["knowledge", "ingestor", "external", "provenance", "sha256", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.maintenance_watchdog",
            tool_name="Autonomy — Maintenance Watchdog (Tech Debt & Large File Scanner)",
            category="RADAR",
            file_path="tools/autonomy/tools/maintenance_watchdog.py",
            intent_triggers=[
                "maintenance watchdog", "find tech debt", "large files scan", "todo fixme finder",
                "find debt markers", "codebase maintenance health", "technical debt report",
                "find hacky code", "code smell finder"
            ],
            cognitive_intents=["AUDIT_RADAR"],
            description=(
                "Scans codebase for maintenance red flags: "
                "(1) Large files (>300KB) that need splitting, "
                "(2) Technical debt markers: TODO, FIXME, XXX, HACK across all code files. "
                "Outputs prioritized list of large files and debt markers with line numbers. "
                "Recommendations: split large files, convert TODOs to tracked GitHub issues."
            ),
            when_to_use="Run weekly or as part of autonomy_cycle. Run before sprint planning to prioritize tech debt.",
            when_not_to_use="Not for security scanning — use security_config_miner or gap_finder for that.",
            inputs=["project: str (project root)", "--output: str"],
            outputs=["maintenance.json: {large_files, debt_markers, recommendations}"],
            chain_before=[],
            chain_after=["engine.solution_synthesizer"],
            cli_example="python tools/autonomy/tools/maintenance_watchdog.py . --output reports/maintenance.json",
            confidence_weight=0.88,
            cost_tokens="zero",
            requires_network=False,
            tags=["maintenance", "tech-debt", "todo", "large-files", "watchdog", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.source_trust_engine",
            tool_name="Autonomy — Source Trust Engine (Offline Evidence Quality Scorer)",
            category="ENGINE",
            file_path="tools/autonomy/tools/source_trust_engine.py",
            intent_triggers=[
                "score knowledge sources", "source trust score", "evidence quality ranking",
                "accept reject source", "authority freshness provenance scoring",
                "offline source reliability check"
            ],
            cognitive_intents=["REPAIR", "FEATURE_SYNTHESIS"],
            description=(
                "Scores a list of knowledge sources on 5 dimensions: "
                "authority (35%), freshness (20%), provenance (20%), corroboration (15%), conflicts (-25%). "
                "Decision gate: trust_score >= 75 AND conflicts < 0.2 -> ACCEPT; >= 50 -> REVIEW; else REJECT. "
                "Offline CLI version (different from discovery_fabric trust_engine)."
            ),
            when_to_use="Run after collecting raw sources before quarantine. Scores and ranks sources for ai_memory admission.",
            when_not_to_use="Not for real-time request handling — batch offline tool.",
            inputs=["--input: str (JSON file with sources list)"],
            outputs=["source_trust.json: {sources with trust_score and decision: accept|review|reject}"],
            chain_before=["autonomy.knowledge_ingestor"],
            chain_after=["knowledge_os.knowledge_quarantine"],
            cli_example="python tools/autonomy/tools/source_trust_engine.py --input reports/sources.json --output reports/source_trust.json",
            confidence_weight=0.91,
            cost_tokens="zero",
            requires_network=False,
            tags=["trust", "scoring", "evidence", "offline", "source-quality"],
        ),

        ToolKnowledgeCard(
            tool_id="autonomy.test_synthesizer",
            tool_name="Autonomy — Test Synthesizer (Failure-Driven Test Case Generator)",
            category="ENGINE",
            file_path="tools/autonomy/tools/test_synthesizer.py",
            intent_triggers=[
                "generate tests from failure log", "auto test generation",
                "synthesize test cases from ci", "regression test from error",
                "test from failure log", "auto create regression tests"
            ],
            cognitive_intents=["REPAIR", "EVOLUTION"],
            description=(
                "Generates test case suggestions from CI/error logs. "
                "Parses logs for: AssertionError, Traceback, FAILED, HTTP status, timeout patterns. "
                "For each clue, generates appropriate test template: "
                "API regression test, timeout regression test, assertion test. "
                "Does NOT write tests automatically — outputs suggestions for human review."
            ),
            when_to_use="Run after any CI failure or incident to generate test suggestions that would catch the same failure next time.",
            when_not_to_use="Not for writing production test code directly — review suggestions first.",
            inputs=["--log: str (path to CI/error log file)"],
            outputs=["test_suggestions.json: {test_cases with kind, body, rationale}"],
            chain_before=["radar.gap_miner.incident_replay"],
            chain_after=["evolution.auto_skill_creator"],
            cli_example="python tools/autonomy/tools/test_synthesizer.py --log logs/ci_failure.txt --output reports/test_suggestions.json",
            confidence_weight=0.83,
            cost_tokens="zero",
            requires_network=False,
            tags=["test-synthesis", "auto-test", "regression", "ci-failure", "offline"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 12 — INTELLIGENCE EXTENSIONS (Full Registry)
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="intelligence.autonomous_red_team",
            tool_name="Intelligence — Autonomous Red Team (AI Vulnerability Simulator)",
            category="SHIELD",
            file_path="tools/intelligence_extensions/supremeai_intelligence/autonomous_red_team.py",
            intent_triggers=[
                "red team ai", "adversarial attack simulation", "security test ai system",
                "prompt injection test", "jailbreak test", "autonomous red team",
                "ai vulnerability scan", "memory poisoning test"
            ],
            cognitive_intents=["AUDIT_RADAR", "EVOLUTION"],
            description=(
                "Runs autonomous adversarial attacks against SupremeAI to find vulnerabilities. "
                "Tests: prompt injection, jailbreak attempts, memory poisoning, governance bypass. "
                "Generates attack vectors, executes in sandbox, records successes/failures. "
                "Results feed back into governance_policy and knowledge_firewall improvements."
            ),
            when_to_use="Run monthly or before any major release as a security health check. Also run after adding new tools that handle external input.",
            when_not_to_use="Never run against production without isolated sandbox. Use cloud_sandbox_orchestrator only.",
            inputs=["target_surface: str (memory|governance|api|llm)", "attack_budget: int"],
            outputs=["RedTeamReport: vulnerabilities_found, severity, recommended_fixes"],
            chain_before=["orchestration.cloud_sandbox"],
            chain_after=["shield.governance_policy", "knowledge_os.knowledge_firewall"],
            cli_example="from supremeai_intelligence.autonomous_red_team import AutonomousRedTeam; AutonomousRedTeam().attack(target='memory', budget=50)",
            confidence_weight=0.89,
            cost_tokens="low",
            requires_network=False,
            tags=["red-team", "adversarial", "security", "attack-simulation", "vulnerability"],
        ),

        ToolKnowledgeCard(
            tool_id="intelligence.contradiction_hunter",
            tool_name="Intelligence — Contradiction Hunter (Knowledge Conflict Detector)",
            category="ENGINE",
            file_path="tools/intelligence_extensions/supremeai_intelligence/contradiction_hunter.py",
            intent_triggers=[
                "find contradictions in knowledge", "knowledge conflicts", "conflicting information",
                "inconsistent facts", "contradiction detection", "conflicting claims"
            ],
            cognitive_intents=["AUDIT_RADAR", "FEATURE_SYNTHESIS"],
            description=(
                "Finds contradictions and conflicts within the knowledge base. "
                "Compares knowledge items for logical inconsistencies, conflicting facts, "
                "or mutually exclusive claims. "
                "Used in knowledge_squeezer Stage 2 (adversarial audit) to surface conflicts "
                "between AI models outputs before synthesis."
            ),
            when_to_use="Run during knowledge_squeezer Stage 2 to identify model disagreements. Also run before injecting new knowledge that might contradict existing memory.",
            when_not_to_use="Not for code analysis — for knowledge/text content only.",
            inputs=["knowledge_items: list[dict]"],
            outputs=["ConflictReport: {contradictions, severity, recommended_resolution}"],
            chain_before=["engine.knowledge_squeezer"],
            chain_after=["knowledge_os.truth_hierarchy"],
            cli_example="from supremeai_intelligence.contradiction_hunter import ContradictionHunter; ContradictionHunter().find(knowledge_items)",
            confidence_weight=0.87,
            cost_tokens="zero",
            requires_network=False,
            tags=["contradiction", "conflict", "knowledge-quality", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="intelligence.memory_curator",
            tool_name="Intelligence — Memory Curator (Vector Store Health Manager)",
            category="MEMORY",
            file_path="tools/intelligence_extensions/supremeai_intelligence/memory_curator.py",
            intent_triggers=[
                "curate ai memory", "prune vector store", "clean ai memory",
                "remove stale knowledge", "memory organization", "memory health check",
                "deduplicate vector store", "memory pruning monthly"
            ],
            cognitive_intents=["EVOLUTION", "AUDIT_RADAR"],
            description=(
                "Curates and prunes the ai_memory vector store to maintain quality. "
                "Operations: remove stale/expired knowledge, deduplicate semantically similar entries, "
                "re-rank by recency and usage, archive low-confidence items. "
                "Prevents memory bloat and recall quality degradation over time."
            ),
            when_to_use="Run monthly or when ai_memory query quality degrades. Run after bulk knowledge injection to clean up duplicates.",
            when_not_to_use="Do not run during active AI request processing — read-write conflicts.",
            inputs=["staleness_days: int (default 90)", "similarity_threshold: float (default 0.95)"],
            outputs=["CurationReport: {pruned_count, deduplicated_count, archived_count}"],
            chain_before=[],
            chain_after=["memory.ai_memory ingestion"],
            cli_example="from supremeai_intelligence.memory_curator import MemoryCurator; MemoryCurator().curate(staleness_days=90)",
            confidence_weight=0.88,
            cost_tokens="zero",
            requires_network=False,
            tags=["memory", "curator", "prune", "deduplicate", "stale", "health", "monthly"],
        ),

        ToolKnowledgeCard(
            tool_id="intelligence.knowledge_graph_builder",
            tool_name="Intelligence — Knowledge Graph Builder (Fact Relationship Network)",
            category="ENGINE",
            file_path="tools/intelligence_extensions/supremeai_intelligence/knowledge_graph_builder.py",
            intent_triggers=[
                "build knowledge graph", "semantic graph facts", "fact relationships",
                "entity relationships knowledge", "knowledge map", "connect facts",
                "knowledge network", "graph enhanced retrieval"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "AUDIT_RADAR"],
            description=(
                "Builds a semantic graph connecting knowledge items by relationships. "
                "Nodes: knowledge items (facts, tools, skills). "
                "Edges: relationships (supports, contradicts, extends, requires). "
                "Enables graph traversal queries: 'What does X depend on?' / 'What contradicts Y?' "
                "Enhances retrieval accuracy beyond pure vector similarity."
            ),
            when_to_use="Build/update graph after every knowledge injection batch. Query for enhanced retrieval during synthesis tasks.",
            when_not_to_use="Not for real-time per-request lookups — precomputed graph only.",
            inputs=["knowledge_items: list[dict]"],
            outputs=["KnowledgeGraph: nodes, edges, adjacency_map"],
            chain_before=["knowledge_os.truth_hierarchy"],
            chain_after=["memory.ai_memory ingestion"],
            cli_example="from supremeai_intelligence.knowledge_graph_builder import KnowledgeGraphBuilder; KnowledgeGraphBuilder().build(knowledge_items)",
            confidence_weight=0.85,
            cost_tokens="zero",
            requires_network=False,
            tags=["knowledge-graph", "semantic", "relationships", "graph", "retrieval"],
        ),

        # ════════════════════════════════════════════════
        # JEWEL 13 — GAP MINER SUB-TOOLS
        # ════════════════════════════════════════════════

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.safe_autofix_plan",
            tool_name="Gap Miner — Safe Autofix Plan (Ranked Remediation Planner)",
            category="RADAR",
            file_path="tools/gap_miner/tools/safe_autofix_plan.py",
            intent_triggers=[
                "safe autofix plan", "remediation plan ranked", "autofix prioritized",
                "patch execution plan", "fix order priority", "what to fix first",
                "remediation priority table"
            ],
            cognitive_intents=["REPAIR"],
            description=(
                "Generates a ranked, patch-ready remediation plan from gap-report.json. "
                "Sorts findings by severity (CRITICAL > HIGH > MEDIUM > LOW > INFO). "
                "Outputs Markdown table with: Priority, Severity, Path, Finding, Suggested Change. "
                "Includes autonomous execution policy: "
                "SAFE TO AUTOMATE: formatting, report generation, adding missing tests. "
                "HUMAN APPROVAL REQUIRED: auth, secrets, DB migrations, deployments. "
                "NEVER edits source code directly — planning tool only."
            ),
            when_to_use="Run immediately after gap_finder.py to convert the raw report into an ordered action plan. ALWAYS use before solution_synthesizer.",
            when_not_to_use="Not a code-editing tool — planning only.",
            inputs=["report: str (path to gap-report.json)", "--out: str (default reports/autofix-plan.md)"],
            outputs=["autofix-plan.md: prioritized remediation table + automation policy"],
            chain_before=["radar.gap_finder"],
            chain_after=["engine.solution_synthesizer"],
            cli_example="python tools/gap_miner/tools/safe_autofix_plan.py reports/gap-report.json --out reports/autofix-plan.md",
            confidence_weight=0.96,
            cost_tokens="zero",
            requires_network=False,
            tags=["autofix", "plan", "remediation", "priority", "offline", "safe"],
        ),

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.security_config_miner",
            tool_name="Gap Miner — Security Config Miner (Hardcoded Secret & Gitignore Scanner)",
            category="SHIELD",
            file_path="tools/gap_miner/tools/security_config_miner.py",
            intent_triggers=[
                "scan hardcoded secrets", "security config miner", "gitignore missing rules",
                "credential detection scan", "sensitive filename check",
                "api key hardcoded check", "security hygiene scan"
            ],
            cognitive_intents=["AUDIT_RADAR"],
            description=(
                "Read-only security and config hygiene scanner. Never prints secret values. "
                "Detects: (1) sensitive filenames (.env, id_rsa, credentials.json), "
                "(2) possible hardcoded credentials (credential-like assignments >=16 chars), "
                "(3) missing .gitignore rules (.env, *.pem, *.key). "
                "Lightweight alternative to full gap_finder for security-only scans."
            ),
            when_to_use="Run before every commit and on every new repository setup. Faster than full gap_finder for security-only checks.",
            when_not_to_use="Not a replacement for full gap_finder — only catches credential/config issues.",
            inputs=["root: str (project root, default '.')", "--out: str"],
            outputs=["security_config.json: {issues: [{severity, type, path}], count}"],
            chain_before=[],
            chain_after=["engine.solution_synthesizer"],
            cli_example="python tools/gap_miner/tools/security_config_miner.py . --out reports/security_config.json",
            confidence_weight=0.94,
            cost_tokens="zero",
            requires_network=False,
            tags=["security", "secrets", "gitignore", "credentials", "offline", "scan"],
        ),

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.context_packager",
            tool_name="Gap Miner — Context Packager (Ranked AI Context Navigator)",
            category="RADAR",
            file_path="tools/gap_miner/tools/context_packager.py",
            intent_triggers=[
                "pack context for ai", "context navigator", "project summary for llm",
                "relevant files context", "context packager", "ai navigation summary",
                "project tree for llm synthesis"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS", "REPAIR"],
            description=(
                "Packages a navigation-oriented context summary of the project for LLM consumption. "
                "Selects most relevant files based on importance scoring "
                "(file name importance + keyword relevance + file size). "
                "Output is structured Markdown with project tree and selected file summaries. "
                "Gives the AI a high-quality codebase snapshot before synthesis tasks."
            ),
            when_to_use="Run as first step of FEATURE_SYNTHESIS to give the LLM accurate project context. Also run before solution_synthesizer for better patch quality.",
            when_not_to_use="Not a source-of-truth replacement — navigation aid only.",
            inputs=["project_root: str", "--max-files: int (default 50)"],
            outputs=["context_pack.md: project tree + top N most relevant files"],
            chain_before=["radar.gap_miner.project_fingerprint"],
            chain_after=["engine.solution_synthesizer", "engine.knowledge_squeezer"],
            cli_example="python tools/gap_miner/tools/context_packager.py . --max-files 50 --out reports/context_pack.md",
            confidence_weight=0.88,
            cost_tokens="zero",
            requires_network=False,
            tags=["context", "packager", "llm", "navigation", "offline"],
        ),

        ToolKnowledgeCard(
            tool_id="radar.gap_miner.prompt_distiller",
            tool_name="Gap Miner — Prompt Distiller (Prompt Deduplication Compressor)",
            category="ENGINE",
            file_path="tools/gap_miner/tools/prompt_distiller.py",
            intent_triggers=[
                "distill prompts", "compress prompt file", "deduplicate prompt blocks",
                "remove duplicate prompt boilerplate", "prompt optimization",
                "prompt compression token reduction"
            ],
            cognitive_intents=["FEATURE_SYNTHESIS"],
            description=(
                "Compresses repetitive AI prompt/template files while preserving explicit constraints. "
                "Identifies duplicate prompt blocks via normalized SHA-1 signature matching. "
                "Safety: NEVER collapses blocks containing: must, never, always, required, security, constraint, format. "
                "Reduces prompt token usage without losing critical instructions."
            ),
            when_to_use="Run on prompt template files that have grown large with repeated boilerplate. Reduces token costs for system prompts.",
            when_not_to_use="Do not run on prompts with unique context or dynamic content.",
            inputs=["input: str (path to prompt file)", "--out: str (default reports/prompt-distilled.txt)"],
            outputs=["prompt-distilled.txt: deduplicated prompt; reports blocks removed count"],
            chain_before=[],
            chain_after=["engine.knowledge_squeezer"],
            cli_example="python tools/gap_miner/tools/prompt_distiller.py prompts/system_prompt.txt --out reports/prompt-distilled.txt",
            confidence_weight=0.85,
            cost_tokens="zero",
            requires_network=False,
            tags=["prompt", "distiller", "compression", "deduplication", "token-optimization", "offline"],
        ),
    ]