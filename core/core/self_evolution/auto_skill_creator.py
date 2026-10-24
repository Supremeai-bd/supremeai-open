import asyncio

"""
Provides the `AutoSkillCreator` class, the core of the SupremeAI self-evolution engine.

This module orchestrates the autonomous generation, rigorous validation (including security analysis and

"""

import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

from core.errors.error_bus import with_error_bus
from core.messaging.event_bus import ErrorContext

# বাংলা মন্তব্য: রুটের 'skills' মডিউল লোড করার জন্য রিপোজিটরি রুট ডিরেক্টরি sys.path-এ যোগ করা হচ্ছে (Zero Breakage নীতি)।
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from core.logging_config import logger
from core.self_evolution.fitness_engine import FitnessEngine
from database.tenant_db import TenantAwareFirestore

try:
    try:
        from skills.installer import SkillInstaller
    except (ImportError, ModuleNotFoundError):
        from skills import SkillInstaller
except Exception:
    logger.warning(
        "⚠️ 'skills.installer' not found; dynamic SkillInstaller functionality will operate in fallback mode."
    )
    SkillInstaller = None

# বাংলা মন্তব্য: pytests বা isolated settings এ backend/tools কে রুটের tools/ ডিরেক্টরির উপরে অগ্রাধিকার দিতে sys.path.insert ব্যবহার করা হলো
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# isolated test বা path resolution জটিলতায় KeyError: 'tools' এড়াতে dynamic safety import
# P0 (Task 9-c2): FAIL-CLOSED security scanner import. The previous design
# silently defined a no-op `run_sandbox_ast_check` dummy when the import failed,
# which made the whole skill pipeline run UNSECURED without anyone noticing.
# The scanner is now a hard dependency: if it cannot be imported, skill creation
# must be unusable (never silently unsecured).
try:
    from tools.code.fuzz_sandbox import SecurityError, run_sandbox_ast_check
except Exception as _scanner_import_error:  # pragma: no cover - fail-closed path
    logger.critical(
        "P0: security scanner unavailable — skill creation FAILS CLOSED "
        f"(import error: {_scanner_import_error!r}). AutoSkillCreator cannot be used "
        "without tools.code.fuzz_sandbox; refusing to fall back to an unsecured dummy."
    )
    raise


class PersistenceUnavailableError(RuntimeError):
    """P0: raised when AutoSkillCreator has NO durable skill store available.

    Replaces the old silently-discarding MockRef sink: in non-test environments
    we now fail closed at creation time instead of writing skills into the void.
    """


# P0 (Task 9-c2): module-level record of writes performed through the test-env
# mock sink. Tests can assert against ``MOCKED_SKILL_WRITES`` — persistence in
# test mode is now EXPLICIT and observable, never a silent no-op.
MOCKED_SKILL_WRITES: list[dict[str, Any]] = []


class _RecordingMockDoc:
    """Test-env-only document mock that RECORDS writes instead of discarding."""

    def set(self, data=None, merge=False, **kwargs):  # noqa: ANN001, ANN003
        MOCKED_SKILL_WRITES.append({"data": data, "merge": merge, **kwargs})
        return None


class _RecordingMockRef:
    """Test-env-only collection mock that RECORDS writes instead of discarding."""

    def document(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _RecordingMockDoc()


class _DurableFirestoreShim:
    """M17 P-C: কাঁচা firestore ক্লায়েন্টকে db-চুক্তির আকৃতিতে মোড়ানো।

    HITLEngine/FitnessEngine একটি স্টোর প্রত্যাশা করে যার ``.client`` ও
    ``.collection()`` আছে। db=None-পথে _resolve_firestore_client() থেকে
    পাওয়া কাঁচা ক্লায়েন্ট সরাসরি self.db-তে বসালে সেই চুক্তি পূরণ হত না —
    এই shim এটি পূরণ করে (নীরব no-op নয়, প্রকৃত স্টোর-প্রবেশ)।
    """

    def __init__(self, client: Any) -> None:
        self.client = client

    def collection(self, name: str):
        return self.client.collection(name)


def _resolve_firestore_client():
    """Resolve the shared Firestore client (or None).

    Kept as a module-level function so tests can monkeypatch the resolution
    strategy (``monkeypatch.setattr(auto_skill_creator, "_resolve_firestore_client", ...)``).
    """
    try:
        from services.storage.gcp_firestore import get_firestore_client

        return get_firestore_client()
    except Exception as e:
        try:
            from core.messaging.event_bus import ErrorEvent, error_event_bus

            error_event_bus.emit(
                ErrorEvent(
                    module="auto_skill_creator",
                    error_type="FIRESTORE_INIT_FAILED",
                    message=str(e),
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as emit_err:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {emit_err}")
        return None


def _is_test_env() -> bool:
    """P0: explicit test-environment detection for the MOCK persistence sink.

    Production ALWAYS wins: a production environment is never treated as test
    (mirrors core.degraded_mode.is_test_context / utils.environment).
    """
    try:
        from core.degraded_mode import is_production

        if is_production():
            return False
    except Exception as prod_err:  # pragma: no cover - defensive
        logger.debug(f"is_production check failed in auto_skill_creator: {prod_err}")
    if (os.getenv("ENV", "") or "").lower() in ("test", "testing"):
        return True
    if (os.getenv("TESTING", "") or "").lower() == "true":
        return True
    try:
        from core.config import settings

        if bool(getattr(settings, "testing", False)):
            return True
        if str(getattr(settings, "env", "") or "").lower() in ("test", "testing"):
            return True
    except Exception as settings_err:  # pragma: no cover - defensive
        logger.debug(f"settings test check failed in auto_skill_creator: {settings_err}")
    return False


class AutoSkillCreator:
    """
    Self-Evolution Engine Core.
    Autonomously generates, validates, and provisions dynamic AI skills/tools on-the-fly.
    """

    @with_error_bus("__init__")
    def __init__(self, db: TenantAwareFirestore | None = None, **kwargs: Any):
        # 🛡️ এখন আর সরাসরি firestore.Client() কল হবে না!
        self.db = db
        self.skills_ref = None
        if db is not None:
            self.skills_ref = self.db.collection("supreme_dynamic_skills")
        else:
            # P0 (Task 9-c2): resolve a durable store; NEVER install a silent
            # no-op sink. Test env → explicit recording mock (writes captured
            # in MOCKED_SKILL_WRITES); otherwise fail closed at creation time.
            client = _resolve_firestore_client()
            if client is not None:
                self.skills_ref = client.collection("supreme_dynamic_skills")
                # M17 P-C: durable store-টি self.db-তেও বসানো হয় — HITL
                # সাসপেন্স (HITLEngine(db=self.db)) ও FitnessEngine এখন সত্য
                # স্টোর পায়। আগে self.db None থেকে প্রোডাকশন-পথের সফল
                # skill-জেনারেশনও HITL-ধাপে AttributeError-এ মারা যেত —
                # অর্থাৎ কোনো skill কখনো অনুমোদন-পাইপলাইনে পৌঁছাতই না।
                self.db = _DurableFirestoreShim(client)
            elif _is_test_env():
                logger.error(
                    "[P0] skill persistence is MOCKED (test env): writes are recorded "
                    "in core.self_evolution.auto_skill_creator.MOCKED_SKILL_WRITES and "
                    "are NOT persisted anywhere."
                )
                self.skills_ref = _RecordingMockRef()
            else:
                raise PersistenceUnavailableError(
                    "[P0] no durable skill store available for AutoSkillCreator "
                    "(Firestore unresolvable and no db provided) — refusing to run "
                    "with a silent no-op sink (fail-closed)."
                )
        # Initialize FitnessEngine for telemetry
        self.fitness_engine = FitnessEngine(db=self.db)

    def analyze_demand_patterns(
        self, task_history: list[dict[str, Any]], rules_engine: Any = None
    ) -> list[str]:
        """
        Merged from legacy: Analyze task history and rules to find repeating patterns or failures.
        """
        pattern_source = []
        if rules_engine and hasattr(rules_engine, "rules"):
            pattern_source.extend(rules_engine.rules.get("patterns", {}).get("repeated_tasks", []))
        failed = list(
            {
                str(t.get("task"))
                for t in task_history
                if t.get("success") is False and t.get("task")
            }
        )
        return list(set(pattern_source + failed))

    async def generate_and_deploy_skill(self, user_demand: str, skill_name: str) -> dict:
        import json
        import shutil
        import uuid
        from pathlib import Path

        start_time = time.time()

        from skills.schema import UniversalSkillSchema

        from core.llm.llm_gateway import llm_gateway

        logger.info(
            f"🧠 Self-Evolution Triggered: Designing skill '{skill_name}' for demand: '{user_demand}'"
        )

        trace_id = uuid.uuid4().hex
        generation_timestamp = datetime.now(UTC).isoformat()

        # ১. এআই ডিরেক্টিভ প্রম্পট - যা সুনির্দিষ্ট ও কঠোর JSON ফরম্যাটে কোড ও USS জেনারেট করবে
        system_prompt = (
            "You are the SupremeAI 2.0 Self-Evolution Engine. Your job is to output a single structured JSON object "
            "representing a dynamic skill and its metadata schema.\n\n"
            "You must return ONLY a valid JSON block. No markdown explanations outside the JSON block.\n\n"
            "The JSON structure must match this template exactly:\n"
            "{\n"
            '  "code": "python code containing a class matching the skill_name. '
            "The class must implement an async def execute(self, kwargs) -> dict method. "
            "Do not use banned keywords like eval, exec, compile, getattr, setattr, "
            'globals, locals.",\n'
            '  "schema": {\n'
            '    "metadata": {\n'
            '      "name": "skill_name",\n'
            '      "version": "1.0.0",\n'
            '      "description": "description of what the skill does",\n'
            '      "author": "supremeai_agent_id",\n'
            '      "tags": []\n'
            "    },\n"
            '    "interface": {\n'
            '      "input_schema": {\n'
            '        "type": "object",\n'
            '        "properties": {},\n'
            '        "required": []\n'
            "      },\n"
            '      "output_schema": {\n'
            '        "type": "object",\n'
            '        "properties": {}\n'
            "      }\n"
            "    },\n"
            '    "execution": {\n'
            '      "runtime": "python3.11",\n'
            '      "entry_point": "main.execute",\n'
            '      "dependencies": [],\n'
            '      "timeout_seconds": 30\n'
            "    },\n"
            '    "validation": {\n'
            '      "tests": [\n'
            "        {\n"
            '          "input": {},\n'
            '          "expected_output": {}\n'
            "        }\n"
            "      ],\n"
            '      "security_level": "sandboxed"\n'
            "    }\n"
            "  }\n"
            "}\n\n"
            f"Requirements:\n"
            f"- User Demand: {user_demand}\n"
            f"- Skill Name / Class Name: {skill_name}\n"
        )

        # Base directories path setup
        base_dir = Path(__file__).resolve().parent.parent.parent
        quarantine_dir = base_dir / "skills" / "quarantine" / skill_name

        try:
            # ২. অন-দি-ফ্লাই কোড জেনারেশন
            # বাংলা মন্তব্য: সরাসরি গুগল নেটিভ ক্লায়েন্ট কল না করে ইউনিভার্সাল llm_gateway ব্যবহার করে এপিআই কল করা হচ্ছে
            response = await llm_gateway.acompletion(
                prompt=system_prompt, task_type="coding", stream=False
            )
            raw_content = response.get("text", "") if isinstance(response, dict) else str(response)
            raw_content = raw_content.strip()

            # Extract JSON block
            if "```json" in raw_content:
                json_str = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                json_str = raw_content.split("```")[1].split("```")[0].strip()
            else:
                json_str = raw_content

            # Parse generated JSON
            data = json.loads(json_str)
            code_block = data.get("code", "")
            schema_dict = data.get("schema", {})

            # Traceability enhancements
            schema_dict["metadata"]["tags"] = [
                *schema_dict["metadata"].get("tags", []),
                f"trace_id:{trace_id}",
            ]
            schema_dict["metadata"]["author"] = f"supremeai_agent_id:{trace_id}"
            schema_dict["metadata"]["description"] = (
                schema_dict["metadata"].get("description", "")
                + f" (Generated at {generation_timestamp})"
            )

            # 🛡️ ৩. দ্য আলটিমেট স্যান্ডবক্স গেটকিপার ভ্যালিডেশন (The Iron Cage Check)
            # P0 (Task 9-c2): explicit FAIL-CLOSED gate — a missing scanner, a
            # scanner that throws, or ANY verdict that is not exactly True all
            # reject the candidate. The historical "Security Sandbox Violation"
            # error text is preserved for downstream compatibility.
            if run_sandbox_ast_check is None:  # pragma: no cover - hard import guards this
                logger.critical(
                    "🚨 [EVOLUTION BLOCKED] security scanner unavailable — candidate "
                    "rejected (fail-closed)."
                )
                raise SecurityError(
                    "Security Sandbox Violation: security scanner unavailable — "
                    "candidate rejected (fail-closed)"
                )
            try:
                is_safe = run_sandbox_ast_check(code_block)
            except SecurityError as sec_err:
                logger.critical(
                    f"🚨 [EVOLUTION BLOCKED] AI generated a dangerous skill payload! Threat defused: {sec_err!s}"
                )
                raise SecurityError(f"Security Sandbox Violation: {sec_err!s}") from sec_err
            except Exception as scan_err:
                logger.critical(
                    "🚨 [EVOLUTION BLOCKED] security scanner crashed — candidate rejected "
                    f"(fail-closed): {scan_err!s}"
                )
                raise SecurityError(
                    "Security Sandbox Violation: security scanner failure — candidate "
                    f"rejected (fail-closed): {scan_err!s}"
                ) from scan_err
            if is_safe is not True:
                reason = (
                    "Generated code failed AST layout normalization."
                    if is_safe is False
                    else f"Unexpected scanner verdict {is_safe!r} — treating as unsafe."
                )
                logger.critical(
                    f"🚨 [EVOLUTION BLOCKED] AI generated a dangerous skill payload! Threat defused: {reason}"
                )
                raise SecurityError(f"Security Sandbox Violation: {reason}")

            # ৪. USS Pydantic Schema Validation
            # 🛡️ Governance Gate Pre-Validation
            from core.security.governance_policy import get_governance_policy

            is_valid, reason = get_governance_policy().validate_evolution_target(
                f"skills/{skill_name}"
            )
            if not is_valid:
                logger.critical(
                    f"🚨 Skill target 'skills/{skill_name}' blocked by governance policy: {reason}"
                )
                raise SecurityError(f"Governance violation: {reason}")

            try:
                uss = UniversalSkillSchema(**schema_dict)
            except Exception as e:
                logger.error(f"❌ USS Validation failed: {e}")
                return {
                    "success": False,
                    "error": f"USS Validation Exception: {e!s}",
                }

            # ৫. Quarantine Zone & Automated Testing Loop
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            entry_file = quarantine_dir / "main.py"
            schema_file = quarantine_dir / "schema.json"

            from core.security.resource_guard import ResourceGuard

            ResourceGuard.write_text(entry_file, code_block)
            ResourceGuard.write_text(schema_file, json.dumps(schema_dict, indent=4))

            # Load module from quarantine and execute validation tests inside the restricted Docker Sandbox
            # বাংলা মন্তব্য: এআই জেনারেটেড কোডটি সরাসরি লোকাল ইন্টারপ্রেটারে রান না করিয়ে
            # Dockerized Cloud Sandbox এর সাহায্যে সিকিউর এনভায়রনমেন্টে রান করানো হচ্ছে।
            from tools.code.local_code_executor import LocalCodeExecutor

            sandbox = LocalCodeExecutor()

            # Execute validation tests loop inside the sandbox
            for idx, test in enumerate(uss.validation.tests):
                logger.info(
                    f"Running validation test case {idx + 1}/{len(uss.validation.tests)} inside the secure sandbox..."
                )

                # Sanitize skill_name to prevent code injection via name
                import re as _re

                safe_skill_name = _re.sub(r"[^a-zA-Z0-9_]", "", skill_name)
                if not safe_skill_name:
                    raise SecurityError("Invalid skill name detected.")

                input_json_str = json.dumps(test.input)
                # Construct executable script to evaluate inputs and output results to stdout as JSON
                sandbox_script = f"""{code_block}

import json
import asyncio

async def _supreme_test_run():
    test_data = json.loads({input_json_str!r})
    target_cls = globals().get({safe_skill_name!r})
    if not target_cls:
        raise ValueError(f"Skill class '{{safe_skill_name}}' not found in executed code.")
    instance = target_cls()
    res = await instance.execute(test_data)
    logger.debug("RESULT:" + json.dumps(res))

asyncio.run(_supreme_test_run())
"""
                is_safe_test = run_sandbox_ast_check(sandbox_script)
                if is_safe_test is not True:
                    # P0 (Task 9-c2): ANY non-True verdict rejects the harness.
                    raise SecurityError("Generated test harness failed AST layout normalization.")
                run_res = await sandbox.execute_local_code(sandbox_script)
                if not run_res.get("success"):
                    err_msg = run_res.get("error", run_res.get("stderr"))
                    raise ValueError(
                        f"Validation test {idx + 1} crashed or timed out in sandbox. Error: {err_msg}"
                    )

                # In execute_local_code, standard output is usually under 'output' not 'stdout'
                run_res["stdout"] = run_res.get("output", "")

                # Parse stdout logs for output result
                output_line = [
                    line for line in run_res["stdout"].splitlines() if line.startswith("RESULT:")
                ]
                if not output_line:
                    raise ValueError(
                        f"Validation test {idx + 1} did not produce executable result in sandbox. Stdout: {run_res['stdout']}"
                    )

                res_val = json.loads(output_line[0][7:])
                if res_val != test.expected_output:
                    raise ValueError(
                        f"Validation test {idx + 1} failed in sandbox. Expected {test.expected_output}, got {res_val}"
                    )

            logger.info(
                f"✅ All {len(uss.validation.tests)} validation tests passed for skill '{skill_name}' inside the sandbox!"
            )

            # 1. Multi-factor Evidence-Backed Fitness Evaluation
            from evolution.artifact_integrity import ArtifactIntegrityGate, canonical_artifact_hash
            from evolution.benchmark_runner import get_benchmark_runner
            from evolution.change_proposal import ChangeType, ProposalState, get_change_manager
            from evolution.fitness_evaluator import get_fitness_evaluator

            elapsed_ms = (time.time() - start_time) * 1000.0
            fitness_eval = get_fitness_evaluator().evaluate_skill_execution(
                passed_tests=len(uss.validation.tests),
                total_tests=len(uss.validation.tests),
                ast_security_passed=True,
                latency_ms=elapsed_ms,
            )
            candidate_fitness = fitness_eval.composite_fitness

            # 2. Canonical Pre-Deployment Governance Gate (Fail-Closed Safety)
            proposal_mgr = get_change_manager()
            proposal = proposal_mgr.create_proposal(
                title=f"Dynamic Skill Creation: {skill_name}",
                description=uss.metadata.description or user_demand,
                change_type=ChangeType.NEW_SKILL,
                diff_content={
                    "code": code_block,
                    "schema": schema_dict,
                    "artifact_hash": canonical_artifact_hash(code_block, schema_dict),
                },
                target_module=f"skills/{skill_name}",
                current_fitness=candidate_fitness,
            )

            async def _skill_security_scan(prop):
                # P0 (Task 9-c2): fail-closed verdict for the governance gate.
                verdict = run_sandbox_ast_check(code_block)
                if verdict is not True:
                    raise SecurityError(
                        f"Security Sandbox Violation: scanner verdict={verdict!r} — promotion refused."
                    )
                return verdict

            async def _skill_benchmark(prop):
                decision = get_benchmark_runner().compare_and_decide(
                    proposal=prop,
                    candidate_eval=fitness_eval,
                    baseline_fitness=0.70,
                )
                if not decision.eligible:
                    raise ValueError(f"Benchmark Decision Rejected: {decision.reason}")
                return decision.candidate_fitness

            promoted = await proposal_mgr.evaluate_and_promote(
                proposal_id=proposal.proposal_id,
                security_scanner_cb=_skill_security_scan,
                benchmarker_cb=_skill_benchmark,
            )

            if not promoted or proposal.state != ProposalState.PROMOTED:
                raise RuntimeError(
                    f"Governance Gate Blocked Skill Deployment: {proposal.rejection_reason or 'Governance check failed'}"
                )

            # 3. Cryptographic Artifact Integrity Verification at Installer Boundary
            authorized = ArtifactIntegrityGate.verify_and_authorize(
                proposal_id=proposal.proposal_id,
                code_to_deploy=code_block,
                schema_to_deploy=schema_dict,
            )
            if not authorized:
                raise RuntimeError(
                    f"Artifact Integrity Violation for Proposal [{proposal.proposal_id}]. Deployment Aborted."
                )

            logger.info(
                f"📜 Governed ChangeProposal [{proposal.proposal_id}] PROMOTED with Verified Integrity."
            )

            # 4. Suspend for Human-in-the-Loop (HITL) Approval
            from services.hitl.engine import HITLEngine

            payload = {
                "skill_name": skill_name,
                "demand_justification": user_demand,
                "code": code_block,
                "version": uss.metadata.version,
                "description": uss.metadata.description,
                "dependencies": uss.execution.dependencies,
                "uss": schema_dict,
                "proposal_id": proposal.proposal_id,
            }

            hitl_engine = HITLEngine(db=self.db)
            record_id = hitl_engine.suspend_for_approval(
                target_resource=f"skills/{skill_name}", payload=payload
            )

            # Clean up quarantine directory
            if quarantine_dir.exists():
                shutil.rmtree(quarantine_dir)

            logger.info(
                f"🛡️ Skill '{skill_name}' successfully governed and suspended for HITL approval (Record ID: {record_id})."
            )

            # Record successful experience for future pattern matching
            try:
                from adaptive_engine.experience_db import Experience, ExperienceDatabase

                exp_db = ExperienceDatabase()
                exp_db.record_experience(
                    Experience(request=user_demand, generated_code=code_block, result="success")
                )
            except Exception as exp_e:
                logger.warning(f"Failed to record verified skill experience: {exp_e}")

            latency = time.time() - start_time
            self.fitness_engine.track_execution(skill_name, success=True, latency=latency)
            return {
                "success": True,
                "skill_name": skill_name,
                "status": "pending_approval",
                "record_id": record_id,
                "message": "Autonomous evolution loop completed. Skill suspended for Admin approval.",
            }

        except Exception as e:
            logger.error(f"❌ Self-Evolution loop crashed: {e!s}")
            latency = time.time() - start_time
            self.fitness_engine.track_execution(skill_name, success=False, latency=latency)
            # Cleanup quarantine on failure
            if quarantine_dir.exists():
                shutil.rmtree(quarantine_dir)
            return {"success": False, "error": str(e)}
