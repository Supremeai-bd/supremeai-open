# backend/verification/verifier.py
"""Deterministic Verification Engine (Audit Phase 4).

Guarantees that no task is marked 'COMPLETED' without objective, verifiable evidence.
Separates model self-confidence from external factual verification.
"""

from __future__ import annotations

import ast
import time
from typing import Any

from core.logging_config import logger
from core.task_contract import TaskContract, VerificationPolicy
from runtime.task_result import CriterionResult, VerificationSummary


class VerifierEngine:
    """Evaluates task execution output against constraints, AST syntax, and success criteria."""

    async def verify(
        self,
        task: TaskContract,
        candidate_output: Any,
        context: Any | None = None,
    ) -> VerificationSummary:
        """Run objective multi-point verification according to task policy."""
        start_time = time.perf_counter()
        criteria_results: list[CriterionResult] = []
        failures: list[str] = []
        warnings: list[str] = []
        evidence: list[str] = []

        output_str = str(candidate_output).strip() if candidate_output is not None else ""

        # 1. Non-empty check
        if not output_str or output_str == "None":
            failures.append("Output is completely empty or null")
            return VerificationSummary(
                verified=False,
                policy_used=task.verification_policy.value,
                score=0.0,
                criteria_results=[
                    CriterionResult(
                        criterion="Non-empty output",
                        passed=False,
                        evidence="Zero bytes returned",
                        is_required=True,
                    )
                ],
                failures=failures,
                recommendation="REJECT: No output produced",
                verification_time_ms=(time.perf_counter() - start_time) * 1000,
            )

        evidence.append(f"Output generated ({len(output_str)} chars)")
        criteria_results.append(
            CriterionResult(
                criterion="Non-empty output",
                passed=True,
                evidence=f"{len(output_str)} chars generated",
                is_required=True,
            )
        )

        # 2. Syntax check if code is required or present
        is_code_task = (
            "python" in task.required_capabilities
            or "def " in output_str
            or "class " in output_str
            or "```" in output_str
        )

        if is_code_task:
            code_to_check = output_str
            if "```python" in output_str:
                code_to_check = output_str.split("```python")[1].split("```")[0].strip()
            elif "```" in output_str:
                code_to_check = output_str.split("```")[1].split("```")[0].strip()

            try:
                ast.parse(code_to_check)
                evidence.append("Python AST tree parsed successfully without syntax errors")
                criteria_results.append(
                    CriterionResult(
                        criterion="Python AST Syntax Validation",
                        passed=True,
                        evidence="Valid AST syntax tree",
                        is_required=True,
                    )
                )
            except SyntaxError as syn_err:
                err_msg = f"Python Syntax Error: {syn_err.msg} at line {syn_err.lineno}"
                if task.verification_policy == VerificationPolicy.STRICT:
                    failures.append(err_msg)
                    criteria_results.append(
                        CriterionResult(
                            criterion="Python AST Syntax Validation",
                            passed=False,
                            evidence=err_msg,
                            is_required=True,
                        )
                    )
                else:
                    warnings.append(err_msg)
                    criteria_results.append(
                        CriterionResult(
                            criterion="Python AST Syntax Validation",
                            passed=False,
                            evidence=f"Partial/Markdown code accepted under standard policy: {err_msg}",
                            is_required=False,
                        )
                    )

        # 3. Explicit Success Criteria Evaluation
        for criterion in task.success_criteria:
            if criterion.lower() in output_str.lower():
                evidence.append(f"Found required pattern: '{criterion}'")
                criteria_results.append(
                    CriterionResult(
                        criterion=f"Match success criterion: {criterion}",
                        passed=True,
                        evidence="Matched in output",
                        is_required=True,
                    )
                )
            else:
                if task.verification_policy == VerificationPolicy.STRICT:
                    failures.append(f"Missing mandatory criterion: '{criterion}'")
                    criteria_results.append(
                        CriterionResult(
                            criterion=f"Match success criterion: {criterion}",
                            passed=False,
                            evidence="Pattern not found in output",
                            is_required=True,
                        )
                    )
                else:
                    warnings.append(f"Advisory criterion not strictly met: '{criterion}'")
                    criteria_results.append(
                        CriterionResult(
                            criterion=f"Match advisory criterion: {criterion}",
                            passed=False,
                            evidence="Advisory pattern not found in output",
                            is_required=False,
                        )
                    )

        # 4. Objective Score Computation
        total_criteria = len(criteria_results)
        passed_count = sum(1 for c in criteria_results if c.passed)
        score = round(passed_count / max(1, total_criteria), 2)

        # Mandatory failure check
        has_mandatory_failures = any(c.is_required and not c.passed for c in criteria_results)
        verified = not has_mandatory_failures and (
            score >= 0.8 if task.verification_policy == VerificationPolicy.STRICT else score >= 0.5
        )

        recommendation = "PROMOTE / PASS" if verified else "REJECT / REPLAN"
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            f"🔍 [Verifier] Task [{task.task_id}]: verified={verified}, score={score:.2f}, failures={len(failures)}"
        )

        return VerificationSummary(
            verified=verified,
            policy_used=task.verification_policy.value,
            score=score,
            criteria_results=criteria_results,
            failures=failures,
            warnings=warnings,
            evidence=evidence,
            recommendation=recommendation,
            verification_time_ms=elapsed_ms,
        )


# Global Singleton
_verifier_instance: VerifierEngine | None = None


def get_verifier() -> VerifierEngine:
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = VerifierEngine()
    return _verifier_instance
