"""
SupremeAI — Compliance Monitor Agent
====================================
Automated compliance checking against regulations (GDPR, BD Digital Security Act, etc.)
Scans configurations, data handling, and audit logs for compliance violations.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.cache import get_cache
from core.logging_config import logger

COMPLIANCE_CACHE_TTL = 3600  # 1 hour


class ComplianceFramework(StrEnum):
    GDPR = "gdpr"
    BD_DIGITAL_SECURITY = "bd_digital_security"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    CUSTOM = "custom"


class ComplianceSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True)
class ComplianceRule:
    """Immutable compliance rule definition."""

    id: str
    framework: ComplianceFramework
    description: str
    severity: ComplianceSeverity
    pattern: str  # Regex or keyword pattern
    remediation: str


@dataclass(frozen=True)
class ComplianceViolation:
    """Immutable compliance violation record."""

    rule_id: str
    framework: ComplianceFramework
    description: str
    severity: ComplianceSeverity
    location: str
    content_preview: str
    detected_at: datetime
    remediation: str


@dataclass(frozen=True)
class ComplianceReport:
    """Immutable compliance audit report."""

    framework: ComplianceFramework
    total_rules_checked: int
    violations: list[ComplianceViolation]
    pass_rate: float
    overall_status: str
    generated_at: datetime


# Built-in compliance rules
DEFAULT_RULES: list[tuple[ComplianceFramework, list[dict[str, Any]]]] = [
    (
        ComplianceFramework.GDPR,
        [
            {
                "id": "gdpr-001",
                "description": "Personal data must be encrypted at rest",
                "severity": ComplianceSeverity.CRITICAL,
                "pattern": r"(?i)(password|secret|token|api_key|credit_card).*?=[^\\n]*?['\"][^'\"]+['\"]",
                "remediation": "Encrypt sensitive fields using field-level encryption (AES-256-GCM)",
            },
            {
                "id": "gdpr-002",
                "description": "Data retention policy must be defined",
                "severity": ComplianceSeverity.HIGH,
                "pattern": r"(?i)(retention|ttl|expire|delete_after)",
                "remediation": "Define data retention policies with auto-expiry for personal data",
            },
            {
                "id": "gdpr-003",
                "description": "Consent required for data processing",
                "severity": ComplianceSeverity.HIGH,
                "pattern": r"(?i)(consent|opt.?in|privacy_policy|data_subject)",
                "remediation": "Implement consent management with explicit opt-in mechanisms",
            },
            {
                "id": "gdpr-004",
                "description": "Right to erasure must be supported",
                "severity": ComplianceSeverity.MEDIUM,
                "pattern": r"(?i)(delete_user|remove_data|anonymize|erase)",
                "remediation": "Implement 'right to be forgotten' API endpoint",
            },
        ],
    ),
    (
        ComplianceFramework.BD_DIGITAL_SECURITY,
        [
            {
                "id": "bd-dsa-001",
                "description": "User data must be stored within Bangladesh jurisdiction",
                "severity": ComplianceSeverity.CRITICAL,
                "pattern": r"(?i)(data_residency|location|bangladesh|bd_region|dhaka)",
                "remediation": "Ensure data storage in Bangladesh-based servers or regions",
            },
            {
                "id": "bd-dsa-002",
                "description": "Digital signatures must comply with BD standards",
                "severity": ComplianceSeverity.HIGH,
                "pattern": r"(?i)(digital_signature|e.?signature|electronic_signature)",
                "remediation": "Implement BD-standard compliant digital signatures",
            },
            {
                "id": "bd-dsa-003",
                "description": "Content filtering and blocking mechanisms required",
                "severity": ComplianceSeverity.MEDIUM,
                "pattern": r"(?i)(content_filter|moderate|censor|block_content)",
                "remediation": "Implement content moderation layer for BD legal requirements",
            },
        ],
    ),
    (
        ComplianceFramework.HIPAA,
        [
            {
                "id": "hipaa-001",
                "description": "PHI must be encrypted in transit and at rest",
                "severity": ComplianceSeverity.CRITICAL,
                "pattern": r"(?i)(phi|protected_health|medical|patient|health_record)",
                "remediation": "Encrypt all PHI with AES-256 and enforce TLS 1.3 for transmission",
            },
            {
                "id": "hipaa-002",
                "description": "Access controls and audit trails required",
                "severity": ComplianceSeverity.HIGH,
                "pattern": r"(?i)(audit_log|access_control|rbac|user_role|permission)",
                "remediation": "Implement comprehensive audit logging and role-based access control",
            },
        ],
    ),
]


class ComplianceRuleEngine:
    """
    Evaluates compliance rules against configurations and data.
    """

    def __init__(self, custom_rules: list[dict[str, Any]] | None = None) -> None:
        self.rules: dict[ComplianceFramework, list[ComplianceRule]] = {}
        for framework, rule_list in DEFAULT_RULES:
            self.rules[framework] = [
                ComplianceRule(
                    id=r["id"],
                    framework=framework,
                    description=r["description"],
                    severity=r["severity"],
                    pattern=r["pattern"],
                    remediation=r["remediation"],
                )
                for r in rule_list
            ]
        if custom_rules:
            for r in custom_rules:
                fw = ComplianceFramework(r.get("framework", "custom"))
                self.rules.setdefault(fw, []).append(ComplianceRule(**r))

    def check_content(
        self, content: str, framework: ComplianceFramework
    ) -> list[ComplianceViolation]:
        """Check content against compliance rules for a framework."""
        violations = []
        for rule in self.rules.get(framework, []):
            matches = re.findall(rule.pattern, content)
            if not matches:
                # Rule not satisfied - potential violation
                violations.append(
                    ComplianceViolation(
                        rule_id=rule.id,
                        framework=framework,
                        description=rule.description,
                        severity=rule.severity,
                        location="config/data scan",
                        content_preview=content[:100] if content else "",
                        detected_at=datetime.now(UTC),
                        remediation=rule.remediation,
                    )
                )
        return violations

    def list_available_frameworks(self) -> list[ComplianceFramework]:
        return list(self.rules.keys())


class ComplianceMonitorAgent:
    """
    Automated compliance checking agent.
    Monitors configurations, data handling, and audit logs.
    """

    def __init__(self, rule_engine: ComplianceRuleEngine | None = None) -> None:
        self.engine = rule_engine or ComplianceRuleEngine()
        self.cache = get_cache()
        self._violations_history: list[ComplianceViolation] = []

    def _cache_key(self, framework: ComplianceFramework) -> str:
        raw = f"compliance:{framework.value}:{datetime.now(UTC).strftime('%Y%m%d%H')}"
        return f"compliance:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    async def audit_configuration(
        self,
        config_content: str,
        frameworks: list[ComplianceFramework] | None = None,
    ) -> ComplianceReport:
        """Audit a configuration file against compliance frameworks."""
        if frameworks is None:
            frameworks = self.engine.list_available_frameworks()

        all_violations = []
        total_rules = 0

        for fw in frameworks:
            violations = self.engine.check_content(config_content, fw)
            all_violations.extend(violations)
            total_rules += len(self.engine.rules.get(fw, []))

        pass_rate = 1.0 - (len(all_violations) / total_rules) if total_rules > 0 else 1.0
        status = "pass" if pass_rate >= 0.9 else "warning" if pass_rate >= 0.7 else "fail"

        return ComplianceReport(
            framework=frameworks[0] if frameworks else ComplianceFramework.CUSTOM,
            total_rules_checked=total_rules,
            violations=all_violations,
            pass_rate=round(pass_rate, 2),
            overall_status=status,
            generated_at=datetime.now(UTC),
        )

    async def check_data_handling(
        self, data_sample: dict[str, Any], framework: ComplianceFramework
    ) -> list[ComplianceViolation]:
        """Check data handling practices for compliance."""
        content = json.dumps(data_sample, default=str)
        return self.engine.check_content(content, framework)

    async def generate_report(self, framework: ComplianceFramework) -> ComplianceReport:
        """Generate a comprehensive compliance report for a framework."""
        cache_key = self._cache_key(framework)
        cached = await self.cache.get(cache_key)
        if cached:
            return ComplianceReport(**cached)

        rules = self.engine.rules.get(framework, [])
        violations = [v for v in self._violations_history if v.framework == framework]
        pass_rate = 1.0 - (len(violations) / len(rules)) if rules else 1.0

        report = ComplianceReport(
            framework=framework,
            total_rules_checked=len(rules),
            violations=violations,
            pass_rate=round(pass_rate, 2),
            overall_status="pass"
            if pass_rate >= 0.9
            else "warning"
            if pass_rate >= 0.7
            else "fail",
            generated_at=datetime.now(UTC),
        )

        await self.cache.set(
            cache_key,
            {
                "framework": report.framework.value,
                "total_rules_checked": report.total_rules_checked,
                "violations": [
                    {
                        "rule_id": v.rule_id,
                        "framework": v.framework.value,
                        "description": v.description,
                        "severity": v.severity.value,
                        "location": v.location,
                        "content_preview": v.content_preview,
                        "detected_at": v.detected_at.isoformat(),
                        "remediation": v.remediation,
                    }
                    for v in report.violations
                ],
                "pass_rate": report.pass_rate,
                "overall_status": report.overall_status,
                "generated_at": report.generated_at.isoformat(),
            },
            ttl=COMPLIANCE_CACHE_TTL,
        )

        return report

    def record_violation(self, violation: ComplianceViolation) -> None:
        """Record a compliance violation."""
        self._violations_history.append(violation)
        logger.warning(
            "Compliance violation recorded: %s - %s", violation.rule_id, violation.description
        )


# Singleton
_compliance_instance: ComplianceMonitorAgent | None = None


def get_compliance_monitor() -> ComplianceMonitorAgent:
    """Get or create the singleton ComplianceMonitorAgent."""
    global _compliance_instance
    if _compliance_instance is None:
        _compliance_instance = ComplianceMonitorAgent()
    return _compliance_instance
