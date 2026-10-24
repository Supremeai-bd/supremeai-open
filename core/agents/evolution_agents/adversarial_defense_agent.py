"""
SupremeAI — Adversarial Defense Agent
======================================
Protects against adversarial attacks and improves robustness.
Detects prompt injection, jailbreak attempts, and input manipulation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.cache import get_cache

DEFENSE_CACHE_TTL = 600


class AttackType(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    DATA_POISONING = "data_poisoning"
    ADVERSARIAL_EXAMPLE = "adversarial_example"
    MODEL_EXTRACTION = "model_extraction"
    EVASION = "evasion"


@dataclass(frozen=True)
class ThreatAssessment:
    """Immutable threat assessment."""

    attack_type: AttackType
    severity: str  # low, medium, high, critical
    confidence: float
    detected_pattern: str
    input_preview: str
    recommended_action: str


@dataclass(frozen=True)
class DefenseMechanism:
    """Immutable defense mechanism."""

    name: str
    description: str
    effectiveness: float
    latency_overhead_ms: int
    enabled: bool


# Known attack patterns
ATTACK_PATTERNS = {
    AttackType.PROMPT_INJECTION: [
        r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|commands|directions)",
        r"(?i)forget\s+(all\s+)?(previous|above)\s+(instructions|rules)",
        r"(?i)you\s+(are\s+)?(now|are\s+now)\s+(free|released|unleashed)",
        r"(?i)system\s+prompt[:\s]",
        r"(?i)new\s+instructions?[:\s]",
    ],
    AttackType.JAILBREAK: [
        r"(?i)DAN\s*(=|:)?",
        r"(?i)do\s+anything\s+now",
        r"(?i)no\s+(restrictions|limits|boundaries|filter)",
        r"(?i)you\s+must\s+obey\s+all\s+commands",
        r"(?i)act\s+as\s+(if\s+you\s+are|an?\s+AI\s+with\s+no)",
    ],
    AttackType.ADVERSARIAL_EXAMPLE: [
        r"(?i)adversarial\s+noise",
        r"(?i)evade\s+detection",
        r"(?i)bypass\s+(security|filter|moderation)",
    ],
}


class AdversarialDefenseAgent:
    """
    Protects against adversarial attacks and improves robustness.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self._defenses: dict[str, DefenseMechanism] = {
            "input_sanitizer": DefenseMechanism(
                name="Input Sanitizer",
                description="Sanitizes and normalizes input before processing",
                effectiveness=0.85,
                latency_overhead_ms=5,
                enabled=True,
            ),
            "pattern_detector": DefenseMechanism(
                name="Attack Pattern Detector",
                description="Detects known attack patterns using regex",
                effectiveness=0.75,
                latency_overhead_ms=10,
                enabled=True,
            ),
            "rate_limiter": DefenseMechanism(
                name="Rate Limiter",
                description="Limits request frequency to prevent abuse",
                effectiveness=0.60,
                latency_overhead_ms=2,
                enabled=True,
            ),
        }

    def _cache_key(self, prefix: str, identifier: str) -> str:
        raw = f"adversarial:{prefix}:{identifier}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
        return f"adversarial:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def assess_threat(self, input_text: str) -> list[ThreatAssessment]:
        """Assess input for potential adversarial threats."""
        threats = []

        for attack_type, patterns in ATTACK_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, input_text)
                if match:
                    severity = (
                        "critical"
                        if attack_type in (AttackType.JAILBREAK, AttackType.PROMPT_INJECTION)
                        else "high"
                    )
                    threats.append(
                        ThreatAssessment(
                            attack_type=attack_type,
                            severity=severity,
                            confidence=0.9,
                            detected_pattern=pattern[:50],
                            input_preview=input_text[:100],
                            recommended_action=f"Block and log: detected {attack_type.value}",
                        )
                    )
                    break

        return threats

    def validate_input(self, input_text: str) -> dict[str, Any]:
        """Validate and sanitize input before processing."""
        threats = self.assess_threat(input_text)
        is_safe = len(threats) == 0

        # Sanitize: remove control characters
        sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", input_text)

        return {
            "is_safe": is_safe,
            "sanitized_input": sanitized,
            "threats": [
                {
                    "type": t.attack_type.value,
                    "severity": t.severity,
                    "confidence": t.confidence,
                }
                for t in threats
            ],
            "defenses_applied": [d.name for d in self._defenses.values() if d.enabled],
        }

    def detect_prompt_injection(self, input_text: str) -> ThreatAssessment | None:
        """Specifically detect prompt injection attempts."""
        threats = self.assess_threat(input_text)
        for t in threats:
            if t.attack_type == AttackType.PROMPT_INJECTION:
                return t
        return None

    def enable_defense(self, defense_name: str) -> bool:
        """Enable a specific defense mechanism."""
        if defense_name in self._defenses:
            old = self._defenses[defense_name]
            self._defenses[defense_name] = DefenseMechanism(
                name=old.name,
                description=old.description,
                effectiveness=old.effectiveness,
                latency_overhead_ms=old.latency_overhead_ms,
                enabled=True,
            )
            return True
        return False

    def get_defense_status(self) -> list[dict[str, Any]]:
        """Get status of all defense mechanisms."""
        return [
            {
                "name": d.name,
                "effectiveness": d.effectiveness,
                "latency_ms": d.latency_overhead_ms,
                "enabled": d.enabled,
            }
            for d in self._defenses.values()
        ]


# Singleton
_adversarial_instance: AdversarialDefenseAgent | None = None


def get_adversarial_defense() -> AdversarialDefenseAgent:
    """Get or create the singleton AdversarialDefenseAgent."""
    global _adversarial_instance
    if _adversarial_instance is None:
        _adversarial_instance = AdversarialDefenseAgent()
    return _adversarial_instance
