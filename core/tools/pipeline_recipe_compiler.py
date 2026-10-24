#!/usr/bin/env python3
"""
SupremeAI Pipeline Recipe Compiler
=====================================
Defines, compiles, and stores proven multi-tool pipeline recipes in ai_memory
so the Master Cognitive Orchestrator can instantly retrieve the optimal chain
for any given intent/problem pattern without recalculating from scratch.

A Recipe = {
    trigger_patterns,  # What conditions invoke this recipe
    pipeline_chain,    # Ordered list of tools to execute
    merge_strategy,    # How to combine outputs
    success_metrics,   # What "success" looks like
}

Usage:
    python tools/pipeline_recipe_compiler.py               # preview all recipes
    python tools/pipeline_recipe_compiler.py --inject      # store to ai_memory
    python tools/pipeline_recipe_compiler.py --export recipes.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Windows UTF-8 safety
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        print('Silenced error in except block')

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, BACKEND_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineStep:
    tool_id: str
    purpose: str
    inputs_from_prev: list[str]   # fields consumed from previous step output
    outputs_key: str              # key this step writes to shared context
    can_skip_if: str | None = None   # condition expression to skip
    timeout_seconds: int = 60


@dataclass
class PipelineRecipe:
    recipe_id: str
    recipe_name: str
    intent: str                   # REPAIR | SYNTHESIS | AUDIT | EVOLUTION
    trigger_patterns: list[str]   # Semantic keywords that match this recipe
    problem_description: str
    pipeline_chain: list[PipelineStep]
    merge_strategy: str           # sequential | parallel_merge | conditional_branch
    success_criteria: list[str]
    failure_fallback: str | None   # recipe_id to fallback to on failure
    avg_confidence: float
    avg_duration_seconds: int
    token_budget: str             # zero | low | medium | high
    requires_network: bool
    tags: list[str] = field(default_factory=list)

    def to_memory_content(self) -> str:
        steps_text = "\n".join(
            f"  {i+1}. [{s.tool_id}] — {s.purpose}"
            for i, s in enumerate(self.pipeline_chain)
        )
        return f"""
PIPELINE RECIPE: {self.recipe_name}
RECIPE ID: {self.recipe_id}
INTENT: {self.intent}

PROBLEM: {self.problem_description}

TRIGGER PATTERNS: {', '.join(self.trigger_patterns)}

PIPELINE CHAIN:
{steps_text}

MERGE STRATEGY: {self.merge_strategy}
SUCCESS CRITERIA: {'; '.join(self.success_criteria)}
FALLBACK RECIPE: {self.failure_fallback or 'none'}
AVERAGE CONFIDENCE: {self.avg_confidence}
AVERAGE DURATION: {self.avg_duration_seconds}s
TOKEN BUDGET: {self.token_budget}
NETWORK REQUIRED: {self.requires_network}
TAGS: {', '.join(self.tags)}
""".strip()

    def to_summary(self) -> str:
        chain_ids = " -> ".join(s.tool_id.split(".")[-1] for s in self.pipeline_chain)
        return f"[{self.intent}] {self.recipe_name}: {chain_ids}"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE RECIPE REGISTRY — PROVEN EXECUTION PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

def build_recipes() -> list[PipelineRecipe]:
    return [

        # ══════════════════════════════════════════════════
        # REPAIR RECIPES
        # ══════════════════════════════════════════════════

        PipelineRecipe(
            recipe_id="repair.async_timeout",
            recipe_name="Self-Heal: Asyncio Timeout / Execution Timeout",
            intent="REPAIR",
            trigger_patterns=[
                "asyncio.TimeoutError", "execution timeout", "task timeout exceeded",
                "TimeoutError", "deadline exceeded", "step timed out"
            ],
            problem_description="A runtime asyncio or execution timeout error has occurred. The tool chain identifies root cause, discovers an open-source resilience pattern, validates it in sandbox, and applies a governance-approved patch.",
            pipeline_chain=[
                PipelineStep("radar.gap_miner.incident_replay", "Parse error log to extract timeout root cause", [], "incident_fingerprint"),
                PipelineStep("engine.discovery_fabric.source_scout", "Find open-source async retry/timeout patterns", ["incident_fingerprint.affected_component"], "candidates"),
                PipelineStep("engine.discovery_fabric.trust_engine", "Score and rank candidates by trust/license", ["candidates"], "ranked_candidates"),
                PipelineStep("knowledge_os.knowledge_quarantine", "Quarantine and verify top candidate", ["ranked_candidates[0]"], "quarantine_result"),
                PipelineStep("shield.governance_policy", "Validate target file is allowlisted for modification", ["incident_fingerprint.target_file"], "governance_result", can_skip_if="quarantine_result.status != PASSED"),
                PipelineStep("engine.solution_synthesizer", "Synthesize minimal patch and test in sandbox", ["incident_fingerprint", "quarantine_result", "governance_result"], "patch_result"),
            ],
            merge_strategy="sequential",
            success_criteria=["patch_result.verified_in_sandbox == True", "governance_result.is_allowed == True", "quarantine_result.status == PASSED"],
            failure_fallback="repair.generic_static_fix",
            avg_confidence=0.96,
            avg_duration_seconds=45,
            token_budget="low",
            requires_network=True,
            tags=["repair", "async", "timeout", "self-healing"],
        ),

        PipelineRecipe(
            recipe_id="repair.security_vulnerability",
            recipe_name="Self-Heal: Security Vulnerability / CVE / Hardcoded Secret",
            intent="REPAIR",
            trigger_patterns=[
                "hardcoded secret", "plaintext password", "CVE", "security vulnerability",
                "sql injection", "SSRF", "exposed API key", "bare except security"
            ],
            problem_description="A security gap (hardcoded credential, injection vulnerability, or exposed secret) has been detected. The pipeline identifies the exact location, applies a secure pattern, and verifies via governance shield.",
            pipeline_chain=[
                PipelineStep("radar.gap_finder", "Scan for security gaps with critical/high severity filter", [], "gap_report", can_skip_if="pre_existing_gap_report"),
                PipelineStep("engine.discovery_fabric.source_scout", "Find OWASP/security best practices for this type of vulnerability", ["gap_report.category"], "candidates"),
                PipelineStep("knowledge_os.knowledge_quarantine", "Quarantine security fix candidate", ["candidates[0]"], "quarantine_result"),
                PipelineStep("shield.governance_policy", "Double-check: security fixes NEVER touch core/security/ itself", ["gap_report.target_file"], "governance_result"),
                PipelineStep("engine.solution_synthesizer", "Generate minimal security patch with dry-run first", ["gap_report", "quarantine_result", "governance_result"], "patch_result"),
                PipelineStep("shield.artifact_integrity", "SHA-256 verify patch integrity before apply", ["patch_result.patch_file"], "integrity_result"),
            ],
            merge_strategy="sequential",
            success_criteria=["integrity_result.passed == True", "patch_result.verified_in_sandbox == True"],
            failure_fallback=None,
            avg_confidence=0.98,
            avg_duration_seconds=60,
            token_budget="low",
            requires_network=True,
            tags=["security", "repair", "cve", "owasp"],
        ),

        PipelineRecipe(
            recipe_id="repair.generic_static_fix",
            recipe_name="Self-Heal: Generic Static Code Fix (Test Failure / Lint Error)",
            intent="REPAIR",
            trigger_patterns=[
                "test failed", "pytest failure", "lint error", "import error",
                "ModuleNotFoundError", "AttributeError", "syntax error",
                "AssertionError in test", "CI failed"
            ],
            problem_description="A general code error (test failure, import error, syntax error, or lint issue) detected in CI or locally. Minimal fix without discovery fabric needed.",
            pipeline_chain=[
                PipelineStep("radar.gap_miner.incident_replay", "Parse CI log to identify failing test/file", [], "incident_fingerprint"),
                PipelineStep("shield.governance_policy", "Verify target file is safe to modify", ["incident_fingerprint.target_file"], "governance_result"),
                PipelineStep("engine.solution_synthesizer", "Generate minimal targeted patch", ["incident_fingerprint", "governance_result"], "patch_result"),
            ],
            merge_strategy="sequential",
            success_criteria=["patch_result.verified_in_sandbox == True", "governance_result.is_allowed == True"],
            failure_fallback=None,
            avg_confidence=0.93,
            avg_duration_seconds=25,
            token_budget="low",
            requires_network=True,
            tags=["repair", "ci", "tests", "syntax"],
        ),

        # ══════════════════════════════════════════════════
        # FEATURE SYNTHESIS RECIPES
        # ══════════════════════════════════════════════════

        PipelineRecipe(
            recipe_id="synthesis.new_architectural_feature",
            recipe_name="Deep Synthesis: New Architectural Feature / Complex Capability",
            intent="FEATURE_SYNTHESIS",
            trigger_patterns=[
                "build new feature", "design architecture", "implement capability",
                "add to system", "create component", "how to build", "design pattern for"
            ],
            problem_description="User or system demands a new complex capability or architectural component. The pipeline fingerprints the project, debates the best approach across multiple AI models, validates through truth hierarchy, and distills into a permanent skill.",
            pipeline_chain=[
                PipelineStep("radar.gap_miner.project_fingerprint", "Generate project DNA context map", [], "project_dna"),
                PipelineStep("radar.gap_miner.context_packager", "Package relevant code context for AI models", ["project_dna"], "context_package"),
                PipelineStep("intelligence.model_router_economist", "Select optimal AI models for this task complexity", ["context_package.complexity_score"], "model_selection"),
                PipelineStep("engine.knowledge_squeezer", "Multi-model adversarial debate and distillation", ["context_package", "model_selection"], "distilled_knowledge"),
                PipelineStep("knowledge_os.knowledge_quarantine", "Quarantine distilled knowledge", ["distilled_knowledge"], "quarantine_result"),
                PipelineStep("knowledge_os.truth_hierarchy", "Resolve conflicts and establish canonical truth", ["quarantine_result"], "truth_result"),
                PipelineStep("knowledge_os.knowledge_firewall", "Final security check before memory admission", ["truth_result"], "firewall_result"),
                PipelineStep("intelligence.skill_distiller", "Distill successful pattern into reusable skill", ["truth_result", "firewall_result"], "new_skill"),
            ],
            merge_strategy="sequential",
            success_criteria=["truth_result.confidence >= 0.90", "firewall_result.status == CLEAR", "new_skill is not None"],
            failure_fallback="synthesis.knowledge_injection_only",
            avg_confidence=0.94,
            avg_duration_seconds=120,
            token_budget="medium",
            requires_network=True,
            tags=["synthesis", "architecture", "multi-model", "knowledge"],
        ),

        PipelineRecipe(
            recipe_id="synthesis.knowledge_injection_only",
            recipe_name="Deep Synthesis: Knowledge Injection Only (No Code Change)",
            intent="FEATURE_SYNTHESIS",
            trigger_patterns=[
                "learn about", "understand", "what is best practice for",
                "store knowledge", "remember this", "inject knowledge"
            ],
            problem_description="Synthesize and permanently store expert knowledge into ai_memory without modifying code. Used for learning and knowledge enrichment.",
            pipeline_chain=[
                PipelineStep("engine.knowledge_squeezer", "Multi-model distillation on topic", [], "distilled_knowledge"),
                PipelineStep("knowledge_os.knowledge_quarantine", "Quarantine before storage", ["distilled_knowledge"], "quarantine_result"),
                PipelineStep("knowledge_os.truth_hierarchy", "Establish canonical truth", ["quarantine_result"], "truth_result"),
                PipelineStep("knowledge_os.knowledge_firewall", "Security gate before ai_memory", ["truth_result"], "firewall_result"),
            ],
            merge_strategy="sequential",
            success_criteria=["firewall_result.status == CLEAR", "truth_result.confidence >= 0.85"],
            failure_fallback=None,
            avg_confidence=0.91,
            avg_duration_seconds=60,
            token_budget="medium",
            requires_network=True,
            tags=["knowledge", "injection", "learning", "memory"],
        ),

        # ══════════════════════════════════════════════════
        # AUDIT RECIPES
        # ══════════════════════════════════════════════════

        PipelineRecipe(
            recipe_id="audit.full_health_check",
            recipe_name="Autonomous Audit: Full Project Health Radar",
            intent="AUDIT_RADAR",
            trigger_patterns=[
                "audit everything", "full health check", "project audit", "codebase scan",
                "weekly audit", "comprehensive review", "system health"
            ],
            problem_description="Complete autonomous audit of the SupremeAI codebase: gap detection, drift analysis, failure pattern mining, and memory revaluation. Run on weekly schedule.",
            pipeline_chain=[
                PipelineStep("radar.gap_finder", "Scan all code for gaps, security issues, dead code", [], "gap_report"),
                PipelineStep("radar.gap_miner.drift_detector", "Detect documentation/code drift", [], "drift_report"),
                PipelineStep("intelligence.failure_pattern_miner", "Mine recent CI failures for patterns", [], "failure_patterns"),
                PipelineStep("knowledge_os.knowledge_revalidator", "Revalidate stale ai_memory entries", [], "revaluation_result"),
                PipelineStep("intelligence.contradiction_hunter", "Hunt for contradictions in memory", [], "contradiction_report"),
            ],
            merge_strategy="parallel_merge",
            success_criteria=["gap_report.critical_count == 0", "drift_report.blocking_drifts == 0"],
            failure_fallback=None,
            avg_confidence=0.98,
            avg_duration_seconds=90,
            token_budget="zero",
            requires_network=False,
            tags=["audit", "health", "weekly", "comprehensive"],
        ),

        PipelineRecipe(
            recipe_id="audit.security_posture",
            recipe_name="Autonomous Audit: Security Posture Check",
            intent="AUDIT_RADAR",
            trigger_patterns=[
                "security audit", "vulnerability scan", "pen test", "security posture",
                "check for secrets", "owasp check", "threat model"
            ],
            problem_description="Security-focused audit scanning for hardcoded secrets, injection vulnerabilities, SSRF risks, authentication gaps, and memory isolation integrity.",
            pipeline_chain=[
                PipelineStep("radar.gap_finder", "Gap scan with security severity filter only", [], "security_gaps"),
                PipelineStep("knowledge_os.autonomous_safety_gate", "Run autonomous safety gate checks", [], "safety_gate_result"),
            ],
            merge_strategy="sequential",
            success_criteria=["security_gaps.critical_count == 0", "safety_gate_result.passed == True"],
            failure_fallback=None,
            avg_confidence=0.99,
            avg_duration_seconds=30,
            token_budget="zero",
            requires_network=False,
            tags=["security", "audit", "owasp", "offline"],
        ),

        # ══════════════════════════════════════════════════
        # EVOLUTION RECIPES
        # ══════════════════════════════════════════════════

        PipelineRecipe(
            recipe_id="evolution.governed_skill_creation",
            recipe_name="Governed Evolution: Auto Create New Skill",
            intent="EVOLUTION",
            trigger_patterns=[
                "create new skill", "auto-generate skill", "build tool from workflow",
                "skill creation", "distill to permanent skill"
            ],
            problem_description="Creates a new permanent skill from a proven workflow pattern. Goes through full governance, benchmarking, and canary promotion before production deployment.",
            pipeline_chain=[
                PipelineStep("intelligence.skill_distiller", "Distill workflow trace into skill definition", [], "skill_definition"),
                PipelineStep("shield.governance_policy", "Validate skill target path is allowlisted", ["skill_definition.target_path"], "governance_result"),
                PipelineStep("backend.evolution.benchmark_runner", "Benchmark new skill vs baseline", ["skill_definition"], "benchmark_result"),
                PipelineStep("backend.evolution.canary_manager", "Deploy at 10% canary traffic", ["skill_definition", "benchmark_result"], "canary_result"),
                PipelineStep("shield.artifact_integrity", "SHA-256 verify before full promotion", ["canary_result.artifact_path"], "integrity_result"),
            ],
            merge_strategy="sequential",
            success_criteria=["integrity_result.passed == True", "canary_result.error_rate < 0.01", "benchmark_result.delta > 0"],
            failure_fallback=None,
            avg_confidence=0.95,
            avg_duration_seconds=180,
            token_budget="zero",
            requires_network=False,
            tags=["evolution", "skill", "governed", "canary"],
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# COMPILER ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class PipelineRecipeCompiler:
    def __init__(self) -> None:
        self._memory_svc = None
        self._loaded = False

    def _load_memory(self) -> bool:
        if self._loaded:
            return self._memory_svc is not None
        try:
            from services.memory_service import CascadeMemoryService
            self._memory_svc = CascadeMemoryService()
            self._loaded = True
            return True
        except Exception as exc:
            print(f"[WARN] Could not load CascadeMemoryService: {exc}")
            self._loaded = True
            return False

    def compile_and_inject(self, recipes: list[PipelineRecipe], dry_run: bool = True) -> dict[str, Any]:
        results: dict[str, Any] = {
            "total": len(recipes),
            "injected": 0,
            "skipped": 0,
            "failed": 0,
            "dry_run": dry_run,
            "items": [],
        }

        has_memory = False if dry_run else self._load_memory()

        for recipe in recipes:
            content = recipe.to_memory_content()
            summary = recipe.to_summary()
            status = "DRY_RUN"

            if not dry_run:
                if has_memory and self._memory_svc:
                    try:
                        self._memory_svc.store_memory(
                            file_path=f"pipeline_recipes/{recipe.recipe_id}",
                            content=content,
                            summary=summary,
                            structure=json.dumps({
                                "recipe_id": recipe.recipe_id,
                                "intent": recipe.intent,
                                "trigger_patterns": recipe.trigger_patterns,
                                "pipeline_chain": [s.tool_id for s in recipe.pipeline_chain],
                                "avg_confidence": recipe.avg_confidence,
                                "token_budget": recipe.token_budget,
                                "requires_network": recipe.requires_network,
                                "failure_fallback": recipe.failure_fallback,
                            }),
                            session_id="pipeline_recipe_compiler_v1",
                            agent_type="pipeline_compiler",
                            task_type="recipe_registry",
                            metadata={
                                "recipe_id": recipe.recipe_id,
                                "intent": recipe.intent,
                                "injected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "version": "1.0.0",
                            },
                        )
                        status = "INJECTED"
                        results["injected"] += 1
                    except Exception as exc:
                        status = f"FAILED: {exc}"
                        results["failed"] += 1
                else:
                    status = "SKIPPED_NO_DB"
                    results["skipped"] += 1
            else:
                results["injected"] += 1

            results["items"].append({
                "recipe_id": recipe.recipe_id,
                "intent": recipe.intent,
                "status": status,
                "summary": summary,
                "steps": len(recipe.pipeline_chain),
            })

        return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SupremeAI Pipeline Recipe Compiler")
    parser.add_argument("--inject", action="store_true", help="Write recipes to ai_memory DB")
    parser.add_argument("--json", action="store_true", help="JSON output mode")
    parser.add_argument("--export", type=str, help="Export recipe registry to JSON file")
    args = parser.parse_args()

    recipes = build_recipes()
    compiler = PipelineRecipeCompiler()

    if args.export:
        export_data = {"version": "1.0.0", "recipes": [asdict(r) for r in recipes]}
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        print(f"[OK] Exported {len(recipes)} pipeline recipes to {args.export}")
        return

    dry_run = not args.inject
    results = compiler.compile_and_inject(recipes, dry_run=dry_run)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        mode = "DRY-RUN PREVIEW" if dry_run else "LIVE INJECTION"
        print("=" * 70)
        print(f"  SUPREMEAI PIPELINE RECIPE COMPILER — {mode}")
        print("=" * 70)
        print(f"  Total Recipes     : {results['total']}")
        print(f"  {'Previewed' if dry_run else 'Injected'} : {results['injected']}")
        print(f"  Skipped (no DB)   : {results['skipped']}")
        print(f"  Failed            : {results['failed']}")
        print("-" * 70)
        intent_map: dict[str, list[str]] = {}
        for item in results["items"]:
            intent_map.setdefault(item["intent"], []).append(
                f"  + [{item['steps']} steps] {item['recipe_id']}"
            )
        for intent, items in sorted(intent_map.items()):
            print(f"\n  [{intent}]")
            for line in items:
                print(line)
        print("=" * 70)


if __name__ == "__main__":
    main()
