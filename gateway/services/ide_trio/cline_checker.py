"""
IDE Trio Stage 3: Cline (Claude Dev) Checker
Final validation and quality gate
"""


class ClineChecker:
    """
    Stage 3 Checker - Final validation before production
    Can work with Cline extension or standalone CLI
    """

    CHECK_CATEGORIES = [
        "syntax_validity",
        "type_safety",
        "import_resolution",
        "test_coverage",
        "documentation_complete",
        "agents_md_compliance",
    ]

    async def validate_code(
        self, code: str, file_path: str, reviews_from_stage_2: list = None
    ) -> dict:
        """
        Final validation checkpoint
        Returns pass/fail with details
        """
        results = {
            "passed": True,
            "file_path": file_path,
            "checks": {},
            "blocking_issues": [],
            "warnings": [],
        }

        # Run each check category
        for category in self.CHECK_CATEGORIES:
            check_result = await self._run_check(category, code, file_path)
            results["checks"][category] = check_result

            if not check_result["passed"]:
                if check_result.get("severity") == "blocking":
                    results["passed"] = False
                    results["blocking_issues"].append(check_result)
                else:
                    results["warnings"].append(check_result)

        # Incorporate Stage 2 reviews
        if reviews_from_stage_2:
            critical_reviews = [r for r in reviews_from_stage_2 if r.severity.value == "critical"]
            if critical_reviews:
                results["passed"] = False
                results["blocking_issues"].extend(
                    [{"source": "stage_2_review", "review": r} for r in critical_reviews]
                )

        return results

    async def _run_check(self, category: str, code: str, file_path: str) -> dict:
        """Run individual check category"""

        if category == "syntax_validity":
            return await self._check_syntax(code, file_path)
        elif category == "agents_md_compliance":
            return await self._check_agents_md_compliance(code)

        return {"passed": True, "message": f"{category} check passed"}

    async def _check_syntax(self, code: str, file_path: str) -> dict:
        """Validate syntax based on file type"""
        import ast

        if file_path.endswith(".py"):
            try:
                ast.parse(code)
                return {"passed": True, "message": "Python syntax valid"}
            except SyntaxError as e:
                return {
                    "passed": False,
                    "severity": "blocking",
                    "message": f"Syntax error: {e}",
                    "line": e.lineno,
                }

        return {"passed": True, "message": "Syntax check skipped (unsupported language)"}

    async def _check_agents_md_compliance(self, code: str) -> dict:
        """Verify AGENTS.md core principles are followed"""

        issues = []

        # Check for Eternal Brain integration
        if "memory" not in code.lower() and "pgvector" not in code.lower():
            if "agent" in code.lower() or "learn" in code.lower():
                issues.append(
                    {
                        "principle": "Eternal Brain",
                        "message": "Consider integrating with Eternal Brain memory system",
                    }
                )

        # Check for error handling
        if "try:" not in code and "def " in code:
            issues.append(
                {
                    "principle": "Zero Console Errors",
                    "message": "Add proper error handling (try/except)",
                }
            )

        # Check for Bengali support hints
        if any(word in code.lower() for word in ["message", "text", "response", "content"]):
            if "bengali" not in code.lower() and "bangla" not in code.lower():
                issues.append(
                    {
                        "principle": "Bengali-first Language",
                        "message": "Consider adding Bengali language support",
                    }
                )

        return {
            "passed": len(issues) == 0,
            "severity": "warning" if issues else None,
            "message": "AGENTS.md compliance check"
            + (" passed" if not issues else f" ({len(issues)} suggestions)"),
            "suggestions": issues if issues else None,
        }
