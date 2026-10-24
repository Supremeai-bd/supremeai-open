from __future__ import annotations

import logging

"""
SupremeAI IDE Trio - Adapters for Gemini, Kilo Code, and Cline
===============================================================

Each adapter wraps its respective IDE AI tool and exposes a standardized
``run()`` coroutine so the pipeline orchestrator can chain them as:

    Gemini (Writer) -> Kilo (Reviewer) -> Cline (Checker)
"""


import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# loguru is optional — fall back to a lightweight stub so the adapters
# remain importable in bare / test environments (e.g. CI without backend deps).
try:
    from core.logging_config import logger
except ImportError:  # pragma: no cover
    from core.logging_config import logger

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())


@dataclass
class TrioAgentResult:
    """Standardized result returned by every IDE adapter."""

    role: str  # "writer" | "reviewer" | "checker"
    agent: str  # "gemini" | "kilo" | "cline"
    output: str  # full text response
    confidence: float  # 0.0 - 1.0
    issues: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "agent": self.agent,
            "output": self.output,
            "confidence": self.confidence,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Stage 1 - Code Writer  (Gemini)
# ═══════════════════════════════════════════════════════════════════════════


class GeminiWriter:
    """Stage 1: Code Writer using Gemini API (via backend LLMGateway).

    Uses the project's existing LLMGateway which already supports
    gemini/gemini-2.5-pro, gemini/gemini-2.5-flash via GEMINI_API_KEY.
    """

    def __init__(self, model: str | None = None) -> None:
        self.role = "writer"
        self.agent_name = "gemini"
        self.model = model

    async def run(
        self,
        prompt: str,
        language: str = "python",
        context: dict[str, Any] | None = None,
    ) -> TrioAgentResult:
        """Generate code using Gemini."""
        logger.info("[GeminiWriter] Generating code with Gemini ...")

        from core.llm.llm_gateway import get_llm_gateway

        llm = get_llm_gateway()

        system_prompt = (
            f"You are an expert {language} developer. "
            f"Write clean, production-ready code. "
            f"Return only the code, no markdown fences unless explicitly requested. "
            f"Include docstrings and type hints where applicable."
        )

        user_prompt = prompt
        if context:
            ctx_parts: list[str] = []
            if context.get("filePath"):
                ctx_parts.append(f"File: {context['filePath']}")
            if context.get("existingCode"):
                ctx_parts.append(f"Existing code:\n{context['existingCode']}")
            if context.get("projectContext"):
                ctx_parts.append(f"Project context:\n{context['projectContext']}")
            if ctx_parts:
                user_prompt = f"{prompt}\n\nContext:\n" + "\n".join(ctx_parts)

        try:
            request: dict[str, Any] = {
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "task_type": "coding",
                "timeout": 30.0,
            }
            if self.model:
                request["model"] = self.model
            response = await llm.acompletion(**request)
            code = response.get("text") or response.get("content", "")
            model = self.model or response.get("model", "runtime-selected")
            confidence = response.get("confidence", 0.9) if isinstance(response, dict) else 0.9

            return TrioAgentResult(
                role=self.role,
                agent=self.agent_name,
                output=code,
                confidence=confidence,
                metadata={"model": model, "language": language},
                suggestions=[f"Generated using Gemini model: {model}"],
            )

        except Exception as exc:
            logger.error(f"[GeminiWriter] Error: {exc}")
            return TrioAgentResult(
                role=self.role,
                agent=self.agent_name,
                output=f"[ERROR] Gemini failed: {exc}",
                confidence=0.0,
                issues=[{"type": "error", "message": str(exc), "severity": "error"}],
            )


# ═══════════════════════════════════════════════════════════════════════════
#  Stage 2 - Code Reviewer  (Kilo Code)
# ═══════════════════════════════════════════════════════════════════════════


class KiloReviewer:
    """Stage 2: Code Reviewer using Kilo Code.

    Delegates to the existing ``GuardianAgent`` and ``ReflectionAgent``
    from ``crew_departments.py`` which implement Kilo Code's rule-based
    review logic. Falls back to the ``kilocode`` CLI / local rules.
    """

    def __init__(self) -> None:
        self.role = "reviewer"
        self.agent_name = "kilo"

    async def run(
        self,
        code: str,
        language: str = "python",
        filepath: str = "",
        writer_result: TrioAgentResult | None = None,
    ) -> TrioAgentResult:
        """Review code using Kilo Code's review logic."""
        logger.info("[KiloReviewer] Reviewing code with Kilo Code ...")

        issues: list[dict[str, Any]] = []
        suggestions: list[str] = []
        review_notes: list[str] = []
        confidence = 0.9

        # Strategy 1: Backend GuardianAgent + ReflectionAgent
        try:
            from core.orchestration.crew_departments import (
                GuardianAgent,
                ReflectionAgent,
            )
            from models.shared_workspace import SharedWorkspace

            workspace = SharedWorkspace(
                task_id=f"review-{datetime.now(UTC).timestamp()}",
                original_prompt=f"Review {language} code in {filepath or 'untitled'}",
            )
            workspace.work_product["code_to_review"] = code
            workspace.work_product["language"] = language
            workspace.work_product["filepath"] = filepath

            guardian = GuardianAgent()
            reflection = ReflectionAgent()

            try:
                approved, feedback = await guardian.validate(workspace, "default_user")
                review_notes.append(f"Guardian review: approved={approved}")
                if feedback:
                    review_notes.append(f"Guardian feedback: {feedback}")
                    if "violation" in feedback.lower() or "issue" in feedback.lower():
                        issues.append(
                            {
                                "type": "guardian_violation",
                                "message": feedback[:500],
                                "severity": "warning",
                                "source": "kilo-guardian",
                            }
                        )
                    else:
                        suggestions.append(feedback)
            except Exception as exc:
                logger.debug(f"[KiloReviewer] Guardian.validate unavailable: {exc}")

            try:
                await reflection.run(workspace, "default_user")
                reflection_output = workspace.work_product.get("reflection_output", "")
                if reflection_output:
                    review_notes.append(f"Reflection: {reflection_output[:500]}")
                    suggestions.append(reflection_output[:200])
            except Exception as exc:
                logger.debug(f"[KiloReviewer] Reflection.run unavailable: {exc}")

        except ImportError:
            logger.info("[KiloReviewer] Backend GuardianAgent not available, trying CLI ...")

        # Strategy 2: Try kilocode CLI
        if not issues and not suggestions:
            cli_result = await self._try_kilocode_cli(code, language, filepath)
            if cli_result:
                issues.extend(cli_result.get("issues", []))
                suggestions.extend(cli_result.get("suggestions", []))
                review_notes.append(f"kilocode CLI: {cli_result.get('summary', '')}")

        # Strategy 3: Local rule-based review (safety net)
        local_issues, local_suggestions = self._basic_review(code, language, filepath)
        issues.extend(local_issues)
        suggestions.extend(local_suggestions)

        # Aggregate
        if not issues:
            review_output = "✅ Code passed review. No critical issues found."
        else:
            review_output = (
                f"## Review Summary ({len(issues)} issue(s))\n\n"
                + "\n".join(
                    f"- **{i.get('severity', 'warning').upper()}**: {i['message']}" for i in issues
                )
                + "\n\n"
                + "\n\n".join(review_notes)
            )

        return TrioAgentResult(
            role=self.role,
            agent=self.agent_name,
            output=review_output,
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
            metadata={
                "language": language,
                "filepath": filepath,
                "issues_count": len(issues),
            },
        )

    async def _try_kilocode_cli(
        self, code: str, language: str, filepath: str
    ) -> dict[str, Any] | None:
        """Attempt to run the ``kilocode`` CLI for a review."""
        kilocode_bin = shutil.which("kilocode")
        if not kilocode_bin:
            return None

        prompt = (
            f"Review this {language} code for bugs, security issues, "
            f"style violations, and best practices. Return JSON: "
            f'{{"issues": [{{"type", "message", "severity", "line"}}], '
            f'"suggestions": [...], "summary": "..."}}. '
            f"Code:\n{code}"
        )

        try:
            result = subprocess.run(
                [kilocode_bin, "ask", prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip().split("\n")[-1])
                return data
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning(f"[KiloReviewer] kilocode CLI failed: {exc}")

        return None

    def _basic_review(
        self, code: str, language: str, filepath: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Lightweight local rule-based review (always available)."""
        import re

        issues: list[dict[str, Any]] = []
        suggestions: list[str] = []
        lines = code.split("\n")

        # Robust secret detection: KEY = VALUE  (handles spaces around =)
        secret_re = re.compile(
            r"(api[_-]?key|secret|password|token|private[_-]?key)\s*=\s*['\"][^'\"]+['\"]",
            re.IGNORECASE,
        )

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            comment_prefixes = (
                "#",
                "//",
                "/*",
                "*",
                "import",
                "env",
                "os.",
                "config.",
                "settings.",
            )

            # Security: hardcoded secrets
            if secret_re.search(stripped) and not stripped.startswith(comment_prefixes):
                issues.append(
                    {
                        "type": "hardcoded_secret",
                        "message": f"Potential hardcoded secret on line {i}",
                        "severity": "high",
                        "line": i,
                        "source": "kilo-basic-review",
                    }
                )

            if "eval(" in stripped and not stripped.startswith("#"):
                issues.append(
                    {
                        "type": "eval_usage",
                        "message": f"Usage of eval() on line {i} - potential security risk",
                        "severity": "high",
                        "line": i,
                        "source": "kilo-basic-review",
                    }
                )

            if ("console.log" in stripped or "print(" in stripped) and "logger" not in stripped:
                issues.append(
                    {
                        "type": "debug_statement",
                        "message": f"Debug statement on line {i}",
                        "severity": "low",
                        "line": i,
                        "source": "kilo-basic-review",
                    }
                )

            if stripped.upper().startswith(("TODO", "FIXME")):
                issues.append(
                    {
                        "type": "todo_comment",
                        "message": f"TODO/FIXME on line {i}",
                        "severity": "info",
                        "line": i,
                        "source": "kilo-basic-review",
                    }
                )

            if "except:" in stripped:
                issues.append(
                    {
                        "type": "bare_except",
                        "message": f"Bare 'except:' on line {i} - catches all exceptions",
                        "severity": "medium",
                        "line": i,
                        "source": "kilo-basic-review",
                    }
                )

        if not issues:
            suggestions.append("Code follows basic best practices for the detected patterns.")

        return issues, suggestions


# ═══════════════════════════════════════════════════════════════════════════
#  Stage 3 - Production Checker  (Cline)
# ═══════════════════════════════════════════════════════════════════════════


class ClineChecker:
    """Stage 3: Production readiness checker using Cline.

    Tries the ``cline`` CLI first. If unavailable, falls back to
    local linting, type-checking, and security scanning utilities.
    """

    def __init__(self) -> None:
        self.role = "checker"
        self.agent_name = "cline"

    async def run(
        self,
        code: str,
        language: str = "python",
        filepath: str = "",
        reviewer_result: TrioAgentResult | None = None,
    ) -> TrioAgentResult:
        """Check production readiness of the reviewed code."""
        logger.info("[ClineChecker] Running production checks ...")

        checks: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        suggestions: list[str] = []
        passed_checks: list[str] = []

        # Strategy 1: Try Cline CLI
        cli_result = await self._try_cline_cli(code, language, filepath)
        if cli_result:
            checks.append({"check": "cline_cli", "result": "passed", "details": cli_result})
            passed_checks.append("Cline CLI production readiness check")
        else:
            checks.append({"check": "cline_cli", "result": "not_available"})

        # Strategy 2: Local production checks
        local_results = await self._run_local_checks(code, language, filepath)
        for check_name, result in local_results.items():
            checks.append(
                {
                    "check": check_name,
                    "result": "passed" if result["passed"] else "failed",
                    "details": result.get("output", ""),
                }
            )
            if result["passed"]:
                passed_checks.append(check_name)
            else:
                issues.append(
                    {
                        "type": f"prod_check_{check_name}",
                        "message": result.get("output", "Check failed"),
                        "severity": "medium",
                        "source": "cline-local-check",
                    }
                )

        confidence = 0.85 if len(passed_checks) >= len(checks) * 0.7 else 0.5

        report_lines = [
            "## Production Readiness Report",
            f"**Checks run:** {len(checks)}",
            f"**Passed:** {len(passed_checks)}/{len(checks)}",
            "",
        ]
        for check in checks:
            if check["result"] == "passed":
                report_lines.append(f"✅ **{check['check']}**: passed")
            elif check["result"] == "not_available":
                report_lines.append(f"⚠️ **{check['check']}**: not available")
            else:
                report_lines.append(f"❌ **{check['check']}**: failed")

        if issues:
            report_lines.append("\n### Issues Found:")
            for issue in issues:
                report_lines.append(f"  - {issue['message']}")

        if passed_checks:
            report_lines.append("\n### Passed Checks:")
            for check in passed_checks:
                report_lines.append(f"  ✅ {check}")

        ready_for_production = len(issues) == 0 and len(passed_checks) >= 2

        return TrioAgentResult(
            role=self.role,
            agent=self.agent_name,
            output="\n".join(report_lines),
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
            metadata={
                "language": language,
                "filepath": filepath,
                "ready_for_production": ready_for_production,
                "checks": checks,
            },
        )

    async def _try_cline_cli(self, code: str, language: str, filepath: str) -> str | None:
        """Attempt to run the ``cline`` CLI for production checks."""
        cline_cmd = shutil.which("cline")

        if not cline_cmd:
            npx = shutil.which("npx")
            if npx:
                cline_cmd = npx
                args = ["npx", "@cline/CLI", "ask"]
            else:
                return None
        else:
            args = [cline_cmd, "ask"]

        prompt = (
            f"Check this {language} code for production readiness. "
            f"Check: 1) No debug statements, 2) No hardcoded secrets, "
            f"3) Error handling is comprehensive, 4) Code follows best practices, "
            f"5) Dependencies are properly declared. "
            f"Code:\n{code}"
        )

        full_cmd = [*args, prompt]

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug(f"[ClineChecker] cline CLI not available: {exc}")

        return None

    async def _run_local_checks(
        self, code: str, language: str, filepath: str
    ) -> dict[str, dict[str, Any]]:
        """Run local production-readiness checks as fallback."""
        import re

        results: dict[str, dict[str, Any]] = {}
        lines = code.split("\n")

        debug_issues = []
        for i, line in enumerate(lines, 1):
            if ("console.log" in line or "print(" in line) and "logger" not in line.lower():
                debug_issues.append(f"  Line {i}: {line.strip()}")
        results["no_debug_statements"] = {
            "passed": len(debug_issues) == 0,
            "output": "\n".join(debug_issues) if debug_issues else "No debug statements found",
        }

        has_try_except = "try:" in code
        results["error_handling"] = {
            "passed": has_try_except or "except" in code,
            "output": "Error handling present" if has_try_except else "No try/except found",
        }

        secret_re = re.compile(
            r"(api[_-]?key|secret|password|token|private[_-]?key)\s*=\s*['\"][^'\"]+['\"]",
            re.IGNORECASE,
        )
        found_secrets = []
        for i, line in enumerate(lines, 1):
            if secret_re.search(line) and not line.strip().startswith(
                ("#", "//", "import", "os.", "env")
            ):
                found_secrets.append(f"  Line {i}: potential secret")
        results["no_hardcoded_secrets"] = {
            "passed": len(found_secrets) == 0,
            "output": "\n".join(found_secrets) if found_secrets else "No hardcoded secrets found",
        }

        results["no_eval"] = {
            "passed": "eval(" not in code,
            "output": "No eval() usage" if "eval(" not in code else "eval() found - security risk!",
        }

        if language in ("python", "py"):
            has_type_hints = any(
                t in code for t in ("->", ": str", ": int", ": bool", ": list", ": dict")
            )
            results["type_hints"] = {
                "passed": has_type_hints,
                "output": "Type hints present"
                if has_type_hints
                else "No type hints found - recommended for production",
            }

        return results
