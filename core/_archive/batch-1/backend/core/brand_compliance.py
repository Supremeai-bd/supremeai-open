# backend/core/brand_compliance.py
"""
Brand Exclusivity Enforcement Module
=====================================

Ensures SupremeAI maintains brand neutrality by:
1. Sanitizing AI responses to remove provider mentions
2. Detecting brand leaks before they reach users
3. Providing compliant alternative phrasings
4. Logging potential violations for audit

AGENTS.md Policy:
- Never mention OpenAI, Groq, Anthropic, Claude, Gemini in user-facing text
- Always say "SupremeAI" or "AI assistant"
- If asked "what model are you?", say "I'm SupremeAI's intelligent assistant"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from core.logging_config import logger


class Severity(Enum):
    """Severity of brand violation."""

    CRITICAL = "critical"  # Direct attribution ("I am GPT-4")
    HIGH = "high"  # Powered-by mentions
    MEDIUM = "medium"  # Technical references in user-facing text
    LOW = "low"  # Internal comments/docs
    INFO = "info"  # Acceptable technical context


@dataclass
class BrandViolation:
    """A detected brand violation."""

    original_text: str
    violation_type: str
    severity: Severity
    suggested_replacement: str
    position: tuple[int, int]  # start, end


# Patterns that indicate brand violations
# Format: (pattern, severity, replacement_template)
BRAND_PATTERNS: list[tuple[re.Pattern, Severity, str]] = [
    # Critical: Direct identity claims
    (
        re.compile(
            r"(?i)(?:i am|i\'m)\s+(?:gpt|chatgpt|claude|gemini|groq)\s*-?\d*", re.IGNORECASE
        ),
        Severity.CRITICAL,
        "I'm SupremeAI's intelligent assistant",
    ),
    (
        re.compile(
            r"(?i)(?:i am|i\'m)\s+(?:powered?|built)?\s*(?:by|on|with)\s+(?:openai|anthropic|google)",
            re.IGNORECASE,
        ),
        Severity.CRITICAL,
        "I'm SupremeAI's intelligent assistant",
    ),
    # High: Powered-by statements
    (
        re.compile(r"(?i)powered\s+by\s+(?:openai|anthropic|google|meta|groq)", re.IGNORECASE),
        Severity.HIGH,
        "powered by SupremeAI",
    ),
    (
        re.compile(r"(?i)built\s+(?:with|using|on)\s+(?:gpt|claude|gemini|groq)", re.IGNORECASE),
        Severity.HIGH,
        "built with SupremeAI technology",
    ),
    (
        re.compile(r"(?i)made\s+by\s+(?:openai|anthropic|google)", re.IGNORECASE),
        Severity.HIGH,
        "developed by SupremeAI",
    ),
    # Medium: Model name mentions in user-facing text
    (
        re.compile(
            r"(?i)(?:using|running|based on)\s+(?:gpt-?\d*|claude-?\d*|gemini-?\d*)", re.IGNORECASE
        ),
        Severity.MEDIUM,
        "using SupremeAI's advanced capabilities",
    ),
    (
        re.compile(
            r"(?i)(?:an?|the)\s+(?:openai|anthropic|google)\s+(?:model|ai|system)", re.IGNORECASE
        ),
        Severity.MEDIUM,
        "a SupremeAI model",
    ),
    # Low: Technical references that might slip through
    (
        re.compile(r"(?i)(?:as)\s+(?:gpt|claude|gemini)", re.IGNORECASE),
        Severity.LOW,
        "as an AI assistant",
    ),
]


class BrandComplianceChecker:
    """
    Checks and enforces brand compliance in AI responses.
    """

    def __init__(self, strict_mode: bool = True):
        """
        Initialize checker.

        Args:
            strict_mode: If True, block responses with violations. If False, just sanitize.
        """
        self.strict_mode = strict_mode
        self.violation_log: list[BrandViolation] = []
        self.stats = {
            "total_checked": 0,
            "violations_found": 0,
            "responses_sanitized": 0,
            "responses_blocked": 0,
        }

    def check(self, text: str, is_user_facing: bool = True) -> tuple[bool, list[BrandViolation]]:
        """
        Check text for brand violations.

        Args:
            text: Text to check
            is_user_facing: If True, apply stricter checking

        Returns:
            Tuple of (is_compliant, list_of_violations)
        """
        self.stats["total_checked"] += 1
        violations = []

        for pattern, severity, replacement in BRAND_PATTERNS:
            # Skip low severity for non-user-facing text
            if not is_user_facing and severity in (Severity.LOW, Severity.INFO):
                continue

            match = pattern.search(text)
            if match:
                violations.append(
                    BrandViolation(
                        original_text=match.group(),
                        violation_type=pattern.pattern,
                        severity=severity,
                        suggested_replacement=replacement,
                        position=(match.start(), match.end()),
                    )
                )

        if violations:
            self.stats["violations_found"] += len(violations)

        return len(violations) == 0, violations

    def sanitize(self, text: str) -> str:
        """
        Remove brand violations from text by replacing them.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text
        """
        sanitized = text
        replacements_made = 0

        for pattern, severity, replacement in BRAND_PATTERNS:
            matches = list(pattern.finditer(sanitized))
            if matches:
                # Replace in reverse order to maintain positions
                for match in reversed(matches):
                    sanitized = sanitized[: match.start()] + replacement + sanitized[match.end() :]
                    replacements_made += 1

                    self.violation_log.append(
                        BrandViolation(
                            original_text=match.group(),
                            violation_type=pattern.pattern,
                            severity=severity,
                            suggested_replacement=replacement,
                            position=(match.start(), match.end()),
                        )
                    )

        if replacements_made > 0:
            self.stats["responses_sanitized"] += 1
            logger.info(f"🛡️ Sanitized {replacements_made} brand references")

        return sanitized

    def check_and_sanitize(
        self, text: str, is_user_facing: bool = True
    ) -> tuple[str, bool, list[BrandViolation]]:
        """
        Combined check and sanitize operation.

        Returns:
            Tuple of (sanitized_text, was_clean, original_violations)
        """
        is_clean, violations = self.check(text, is_user_facing)

        if not is_clean:
            if self.strict_mode and any(v.severity == Severity.CRITICAL for v in violations):
                self.stats["responses_blocked"] += 1
                return text, False, violations

            sanitized = self.sanitize(text)
            return sanitized, True, violations

        return text, True, []

    def get_stats(self) -> dict:
        """Get compliance statistics."""
        return {
            **self.stats,
            "recent_violations": len(self.violation_log),
            "strict_mode": self.strict_mode,
        }

    def clear_log(self):
        """Clear violation log."""
        self.violation_log.clear()


# Module-level singleton
_checker_instance: BrandComplianceChecker | None = None


def get_brand_checker(strict_mode: bool = True) -> BrandComplianceChecker:
    """Get or create global brand compliance checker."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = BrandComplianceChecker(strict_mode=strict_mode)
    return _checker_instance


# FastAPI dependency for easy injection
async def brand_compliance_dependency(request):
    """FastAPI dependency that adds brand checking to routes."""
    return get_brand_checker()
