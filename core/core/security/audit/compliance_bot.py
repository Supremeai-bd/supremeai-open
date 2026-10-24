"""SupremeAI - ComplianceBot Agent.

Ensures data handling compliance with GDPR and Bangladesh Digital
Security Act 2018. Provides automated compliance checking, data
retention policies, and consent management.

Key Components:
- `ComplianceBot`: Main compliance checking agent.
- `GDPRChecker`: GDPR-specific compliance validations.
- `DigitalSecurityActChecker`: Bangladesh DSA compliance checks.
- `ConsentManager`: User consent tracking and management.
- `DataRetentionPolicy`: Automated data retention enforcement.

Dependencies:
- `core.config`: For accessing application settings.
- `services.storage.gcp_firestore`: For Firestore database operations.
- `datetime`: For retention date calculations.
"""

from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from core.logging_config import logger

# বাংলা মন্তব্য: উইন্ডোজ টার্মিনালে ইউনিকোড/ইমোজি আউটপুট সাপোর্ট করার জন্য এনকোডিং কনফিগার করা হলো।
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

# --- Path Setup ---
try:
    from core.config import settings  # noqa: F401 -- শুধু importability probe (path-setup)
    from services.storage.gcp_firestore import get_firestore_client
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from services.storage.gcp_firestore import get_firestore_client


class RegulationType(Enum):
    """Supported compliance regulations."""

    GDPR = "gdpr"
    DIGITAL_SECURITY_ACT_BD = "digital_security_act_bd"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"


class ConsentType(Enum):
    """Types of user consent."""

    DATA_PROCESSING = "data_processing"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    THIRD_PARTY_SHARING = "third_party_sharing"
    LOCATION = "location"
    BIOMETRIC = "biometric"


@dataclass
class ConsentRecord:
    """Record of user consent."""

    user_id: str
    consent_type: ConsentType
    granted: bool
    granted_at: datetime
    expires_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    version: str = "1.0"
    withdrawn_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "consent_type": self.consent_type.value,
            "granted": self.granted,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "version": self.version,
            "withdrawn_at": (self.withdrawn_at.isoformat() if self.withdrawn_at else None),
        }

    def is_valid(self) -> bool:
        """Check if consent is still valid."""
        if not self.granted or self.withdrawn_at:
            return False
        if self.expires_at and datetime.now(UTC) > self.expires_at:
            return False
        return True


@dataclass
class ComplianceViolation:
    """Represents a compliance violation."""

    regulation: RegulationType
    severity: str  # "critical", "high", "medium", "low"
    category: str
    description: str
    affected_data: list[str] = field(default_factory=list)
    remediation: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "regulation": self.regulation.value,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "affected_data": self.affected_data,
            "remediation": self.remediation,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class ComplianceReport:
    """Complete compliance status report."""

    overall_compliant: bool
    regulations_checked: list[RegulationType]
    violations: list[ComplianceViolation]
    consent_status: dict[str, Any]
    data_retention_status: dict[str, Any]
    recommendations: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "overall_compliant": self.overall_compliant,
            "regulations_checked": [r.value for r in self.regulations_checked],
            "violations_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
            "consent_status": self.consent_status,
            "data_retention_status": self.data_retention_status,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }


class GDPRChecker:
    """GDPR compliance checker."""

    REQUIRED_CONSENTS: list[ConsentType] = [
        ConsentType.DATA_PROCESSING,
        ConsentType.ANALYTICS,
    ]

    def __init__(self) -> None:
        """Initialize GDPR checker."""
        self.db = get_firestore_client()

    def check_lawful_basis(self, user_id: str, purpose: str) -> ComplianceViolation | None:
        """Check if processing has lawful basis."""
        # Check for consent
        consent = self._get_consent(user_id, ConsentType.DATA_PROCESSING)
        if not consent or not consent.is_valid():
            return ComplianceViolation(
                regulation=RegulationType.GDPR,
                severity="critical",
                category="lawful_basis",
                description=f"No valid consent for data processing (purpose: {purpose})",
                affected_data=["user_data"],
                remediation="Obtain explicit user consent before processing",
            )
        return None

    def check_data_minimization(
        self, data_fields: list[str], purpose: str
    ) -> ComplianceViolation | None:
        """Check data minimization principle."""
        excessive_fields = self._identify_excessive_fields(data_fields, purpose)
        if excessive_fields:
            return ComplianceViolation(
                regulation=RegulationType.GDPR,
                severity="medium",
                category="data_minimization",
                description=f"Excessive data collection for purpose '{purpose}'",
                affected_data=excessive_fields,
                remediation=f"Limit collection to necessary fields only. Remove: {excessive_fields}",
            )
        return None

    def check_retention_limit(
        self, data_age_days: int, data_type: str
    ) -> ComplianceViolation | None:
        """Check if data is retained beyond necessary period."""
        limits = {
            "session_logs": 30,
            "analytics": 365,
            "user_profile": 2555,  # 7 years
            "transaction": 2555,
            "chat_history": 90,
        }

        limit = limits.get(data_type, 365)
        if data_age_days > limit:
            return ComplianceViolation(
                regulation=RegulationType.GDPR,
                severity="high",
                category="retention_limit",
                description=f"Data retained for {data_age_days} days, exceeds limit of {limit} days",
                affected_data=[data_type],
                remediation=f"Delete or anonymize data older than {limit} days",
            )
        return None

    def check_right_to_deletion(self, user_id: str) -> ComplianceViolation | None:
        """Check if user deletion request is pending."""
        pending = self._get_pending_deletion_requests(user_id)
        if pending:
            return ComplianceViolation(
                regulation=RegulationType.GDPR,
                severity="critical",
                category="right_to_deletion",
                description=f"Pending deletion request for user {user_id}",
                affected_data=["user_data", "user_content"],
                remediation="Execute deletion request within 30 days",
            )
        return None

    def _get_consent(self, user_id: str, consent_type: ConsentType) -> ConsentRecord | None:
        """Get consent record from database."""
        try:
            doc = self.db.collection("consents").document(f"{user_id}_{consent_type.value}").get()
            if doc.exists:
                data = doc.to_dict()
                return ConsentRecord(
                    user_id=data["user_id"],
                    consent_type=ConsentType(data["consent_type"]),
                    granted=data["granted"],
                    granted_at=datetime.fromisoformat(data["granted_at"]),
                    expires_at=(
                        datetime.fromisoformat(data["expires_at"])
                        if data.get("expires_at")
                        else None
                    ),
                    version=data.get("version", "1.0"),
                )
        except Exception as e:
            logger.error(f"Error fetching consent: {e}")
        return None

    def _identify_excessive_fields(self, fields: list[str], purpose: str) -> list[str]:
        """Identify fields that are excessive for the purpose."""
        minimal_requirements = {
            "authentication": ["email", "password_hash"],
            "payment": ["email", "payment_method_token"],
            "analytics": ["session_id", "event_type", "timestamp"],
            "profile": ["name", "email", "phone"],
        }

        required = minimal_requirements.get(purpose, [])
        return [f for f in fields if f not in required]

    def _get_pending_deletion_requests(self, user_id: str) -> list[dict[str, Any]]:
        """Get pending deletion requests."""
        try:
            docs = (
                self.db.collection("deletion_requests")
                .where("user_id", "==", user_id)
                .where("status", "==", "pending")
                .stream()
            )
            return [d.to_dict() for d in docs]
        except Exception as e:
            logger.error(f"Error fetching deletion requests: {e}")
            return []


class DigitalSecurityActChecker:
    """Bangladesh Digital Security Act 2018 compliance checker."""

    def __init__(self) -> None:
        """Initialize DSA checker."""
        self.db = get_firestore_client()

    def check_data_localization(self, data_location: str) -> ComplianceViolation | None:
        """Check if sensitive data is stored within Bangladesh."""
        sensitive_data_types = ["nid", "biometric", "financial"]
        if data_location not in {"bd", "bangladesh"}:
            return ComplianceViolation(
                regulation=RegulationType.DIGITAL_SECURITY_ACT_BD,
                severity="critical",
                category="data_localization",
                description="Sensitive Bangladesh citizen data stored outside Bangladesh",
                affected_data=sensitive_data_types,
                remediation="Migrate sensitive data to Bangladesh-based servers",
            )
        return None

    def check_content_moderation(self, content: str) -> ComplianceViolation | None:
        """Check content against DSA prohibited categories."""
        prohibited_patterns = [
            r"(?i)defamatory\s+(?:statement|content)",
            r"(?i)hurting\s+religious\s+sentiment",
            r"(?i)cyber\s+terrorism",
            r"(?i)hacking\s+(?:government|bank)",
        ]

        matches = []
        for pattern in prohibited_patterns:
            if re.search(pattern, content):
                matches.append(pattern)

        if matches:
            return ComplianceViolation(
                regulation=RegulationType.DIGITAL_SECURITY_ACT_BD,
                severity="critical",
                category="content_moderation",
                description="Content may violate Digital Security Act Section 25, 28, or 31",
                affected_data=["user_generated_content"],
                remediation="Flag for human review, potentially remove content",
            )
        return None

    def check_lawful_interception_readiness(self) -> ComplianceViolation | None:
        """Check if system supports lawful interception requirements."""
        # Verify logging and audit capabilities exist
        has_audit_logs = self._check_audit_infrastructure()
        if not has_audit_logs:
            return ComplianceViolation(
                regulation=RegulationType.DIGITAL_SECURITY_ACT_BD,
                severity="high",
                category="lawful_interception",
                description="Insufficient audit logging for lawful interception requirements",
                affected_data=["system_logs"],
                remediation="Implement comprehensive audit logging with tamper-proof storage",
            )
        return None

    def check_cybersecurity_reporting(self) -> ComplianceViolation | None:
        """Check if incident reporting procedures exist."""
        has_incident_response = self._check_incident_response_plan()
        if not has_incident_response:
            return ComplianceViolation(
                regulation=RegulationType.DIGITAL_SECURITY_ACT_BD,
                severity="high",
                category="incident_reporting",
                description="No incident response plan for reporting to BGD e-GOV CIRT",
                affected_data=["security_incidents"],
                remediation="Establish incident response plan with 24-hour reporting to CIRT",
            )
        return None

    def _check_audit_infrastructure(self) -> bool:
        """Check if audit infrastructure exists."""
        try:
            # Check if audit_logs collection exists with recent entries
            docs = list(self.db.collection("audit_logs").limit(1).stream())
            return len(docs) > 0
        except Exception as e:
            logger.error(f"Audit check failed: {e}")
            return False

    def _check_incident_response_plan(self) -> bool:
        """Check if incident response plan exists."""
        try:
            doc = self.db.collection("system_config").document("incident_response").get()
            return doc.exists
        except Exception as e:
            logger.error(f"Incident response check failed: {e}")
            return False


class ConsentManager:
    """Manages user consent records."""

    def __init__(self) -> None:
        """Initialize consent manager."""
        self.db = get_firestore_client()

    def record_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
        granted: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
        expires_days: int | None = None,
    ) -> ConsentRecord:
        """Record user consent."""
        now = datetime.now(UTC)
        expires = None
        if expires_days:
            expires = now + timedelta(days=expires_days)

        record = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
            granted_at=now,
            expires_at=expires,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Store in Firestore
        self.db.collection("consents").document(f"{user_id}_{consent_type.value}").set(
            record.to_dict()
        )

        logger.info(f"Consent recorded: {user_id} - {consent_type.value} = {granted}")
        return record

    def withdraw_consent(self, user_id: str, consent_type: ConsentType) -> ConsentRecord | None:
        """Withdraw user consent."""
        try:
            doc_ref = self.db.collection("consents").document(f"{user_id}_{consent_type.value}")
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                data["granted"] = False
                data["withdrawn_at"] = datetime.now(UTC).isoformat()
                doc_ref.set(data)
                logger.info(f"Consent withdrawn: {user_id} - {consent_type.value}")
                return ConsentRecord(
                    user_id=user_id,
                    consent_type=consent_type,
                    granted=False,
                    granted_at=datetime.fromisoformat(data["granted_at"]),
                    withdrawn_at=datetime.now(UTC),
                )
        except Exception as e:
            logger.error(f"Error withdrawing consent: {e}")
        return None

    def get_consent_status(self, user_id: str) -> dict[str, Any]:
        """Get complete consent status for a user."""
        status = {}
        try:
            docs = self.db.collection("consents").where("user_id", "==", user_id).stream()
            for doc in docs:
                data = doc.to_dict()
                c_type = data.get("consent_type")
                if c_type:
                    status[c_type] = data.get("granted", False)
        except Exception as e:
            logger.error(f"Error fetching consent status: {e}")
        return status


class DataRetentionPolicy:
    """Enforces data retention policies by deleting or anonymizing expired data."""

    def __init__(self) -> None:
        """Initialize data retention policy."""
        self.db = get_firestore_client()

    def enforce_retention(self, data_type: str, retention_days: int) -> int:
        """Anonymize or delete data exceeding retention period."""
        # বাংলা মন্তব্য: রিটেনশন পলিসি ভায়োলেট করা পুরনো ডেটা মুছে ফেলা।
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)
        count = 0
        try:
            docs = (
                self.db.collection(data_type)
                .where("created_at", "<", cutoff_date.isoformat())
                .stream()
            )
            for doc in docs:
                doc.reference.delete()
                count += 1
            logger.info(
                f"Enforced retention for {data_type}: Deleted {count} records older than {retention_days} days."
            )
        except Exception as e:
            logger.error(f"Error enforcing retention on {data_type}: {e}")
        return count


class ComplianceBot:
    """Main ComplianceBot agent for GDPR and DSA compliance checks."""

    def __init__(self) -> None:
        """Initialize ComplianceBot."""
        self.gdpr = GDPRChecker()
        self.dsa = DigitalSecurityActChecker()
        self.consent_mgr = ConsentManager()
        self.retention = DataRetentionPolicy()

    def run_compliance_check(
        self,
        user_id: str,
        data_fields: list[str],
        purpose: str,
        content: str,
        data_location: str,
    ) -> ComplianceReport:
        """Runs all compliance checks and generates a compliance report."""
        # বাংলা মন্তব্য: জিডিপিআর ও ডিজিটাল নিরাপত্তা আইনের রুলস ভ্যালিডেশন লুপ।
        violations: list[ComplianceViolation] = []

        # GDPR checks
        lawful_basis_violation = self.gdpr.check_lawful_basis(user_id, purpose)
        if lawful_basis_violation:
            violations.append(lawful_basis_violation)

        data_minimization_violation = self.gdpr.check_data_minimization(data_fields, purpose)
        if data_minimization_violation:
            violations.append(data_minimization_violation)

        right_to_deletion_violation = self.gdpr.check_right_to_deletion(user_id)
        if right_to_deletion_violation:
            violations.append(right_to_deletion_violation)

        # DSA checks
        localization_violation = self.dsa.check_data_localization(data_location)
        if localization_violation:
            violations.append(localization_violation)

        content_violation = self.dsa.check_content_moderation(content)
        if content_violation:
            violations.append(content_violation)

        lawful_interception_violation = self.dsa.check_lawful_interception_readiness()
        if lawful_interception_violation:
            violations.append(lawful_interception_violation)

        reporting_violation = self.dsa.check_cybersecurity_reporting()
        if reporting_violation:
            violations.append(reporting_violation)

        overall_compliant = len(violations) == 0

        # Recommendations based on violations
        recommendations = []
        for v in violations:
            if v.remediation and v.remediation not in recommendations:
                recommendations.append(v.remediation)

        if overall_compliant:
            recommendations.append("Continue current data practices. Keep monitoring regulations.")

        return ComplianceReport(
            overall_compliant=overall_compliant,
            regulations_checked=[
                RegulationType.GDPR,
                RegulationType.DIGITAL_SECURITY_ACT_BD,
            ],
            violations=violations,
            consent_status=self.consent_mgr.get_consent_status(user_id),
            data_retention_status={
                "session_logs_limit_days": 30,
                "analytics_limit_days": 365,
                "chat_history_limit_days": 90,
            },
            recommendations=recommendations,
        )


# Singleton instance
compliance_bot = ComplianceBot()
