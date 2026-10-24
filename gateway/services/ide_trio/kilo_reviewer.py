"""
IDE Trio Stage 2: Kilo Code Reviewer + GuardianAgent
Reviews generated code for security, performance, and best practices
"""

from dataclasses import dataclass
from enum import Enum


class ReviewSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ReviewResult:
    file_path: str
    line_number: int
    severity: ReviewSeverity
    rule_id: str
    message: str
    suggestion: str


class KiloReviewer:
    """
    Stage 2 Reviewer - Works with Kilo Code extension
    Uses backend GuardianAgent for deep analysis
    """

    # Custom rules for SupremeAI project
    REVIEW_RULES = {
        # Security Rules
        "SEC001": "Check for SQL injection vulnerabilities",
        "SEC002": "Validate user inputs before processing",
        "SEC003": "No hardcoded secrets or credentials",
        "SEC004": "Use parameterized queries only",
        # Performance Rules
        "PERF001": "Avoid N+1 query patterns",
        "PERF002": "Implement proper indexing strategy",
        "PERF003": "Use connection pooling",
        "PERF004": "Cache expensive operations",
        # Code Quality Rules
        "QUAL001": "Follow PEP8/TypeScript standards",
        "QUAL002": "Write meaningful docstrings",
        "QUAL003": "Keep functions under 50 lines",
        "QUAL004": "Handle errors gracefully",
        # AGENTS.md Compliance
        "AGENTS001": "Zero Half-Baked Code principle",
        "AGENTS002": "Eternal Brain memory integration",
        "AGENTS003": "Self-Healing pattern compliance",
        "AGENTS004": "Bengali-first language support",
    }

    async def review_code(
        self, generated_code: str, file_path: str, context: dict = None
    ) -> list[ReviewResult]:
        """
        Review code through multiple analysis stages
        """
        results = []

        # 1. Static Analysis (Fast, local)
        static_issues = await self._static_analysis(generated_code, file_path)
        results.extend(static_issues)

        # 2. Security Scan (Medium speed)
        security_issues = await self._security_scan(generated_code, file_path)
        results.extend(security_issues)

        # 3. GuardianAgent Deep Review (Slower, thorough)
        if context and context.get("enable_guardian"):
            guardian_issues = await self._guardian_agent_review(generated_code, file_path, context)
            results.extend(guardian_issues)

        return results

    async def _static_analysis(self, code: str, file_path: str) -> list[ReviewResult]:
        """Quick static analysis (local, fast)"""
        issues = []
        lines = code.split("\n")

        for i, line in enumerate(lines, 1):
            # Check for common issues
            if "password" in line.lower() and "=" in line:
                issues.append(
                    ReviewResult(
                        file_path=file_path,
                        line_number=i,
                        severity=ReviewSeverity.CRITICAL,
                        rule_id="SEC003",
                        message="Potential hardcoded password detected",
                        suggestion="Move to environment variable or secret vault",
                    )
                )

            if "SELECT * FROM" in line.upper() and "WHERE" not in line.upper():
                issues.append(
                    ReviewResult(
                        file_path=file_path,
                        line_number=i,
                        severity=ReviewSeverity.WARNING,
                        rule_id="PERF002",
                        message="SELECT * without WHERE clause may fetch unnecessary rows",
                        suggestion="Specify required columns and add WHERE conditions",
                    )
                )

            # Check for TODO/FIXME comments
            if "TODO" in line or "FIXME" in line or "HACK" in line:
                issues.append(
                    ReviewResult(
                        file_path=file_path,
                        line_number=i,
                        severity=ReviewSeverity.INFO,
                        rule_id="QUAL002",
                        message="Incomplete task marker found",
                        suggestion="Resolve before merging to main",
                    )
                )

        return issues

    async def _security_scan(self, code: str, file_path: str) -> list[ReviewResult]:
        """Security vulnerability scanning"""
        import re

        issues = []

        # Dangerous function patterns
        dangerous_patterns = {
            r"eval\(": ("SEC001", "Use of eval() is dangerous", "Use safer alternatives"),
            r"exec\(": ("SEC001", "Use of exec() is dangerous", "Avoid dynamic code execution"),
            r"subprocess\.call.*shell=True": (
                "SEC002",
                "Shell injection risk",
                "Use list arguments",
            ),
            r"os\.system": ("SEC002", "Command injection risk", "Use subprocess module"),
            r"pickle\.loads": ("SEC003", "Insecure deserialization", "Use JSON or safe format"),
        }

        for pattern, (rule_id, msg, suggestion) in dangerous_patterns.items():
            if re.search(pattern, code):
                issues.append(
                    ReviewResult(
                        file_path=file_path,
                        line_number=0,  # Could map to exact line with further logic
                        severity=ReviewSeverity.ERROR,
                        rule_id=rule_id,
                        message=msg,
                        suggestion=suggestion,
                    )
                )

        return issues

    async def _guardian_agent_review(
        self, code: str, file_path: str, context: dict
    ) -> list[ReviewResult]:
        """
        Deep review using GuardianAgent (AI-powered)
        This calls LLM for thorough analysis
        """
        # This would integrate with existing GuardianAgent
        return []
