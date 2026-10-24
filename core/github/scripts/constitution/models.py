"""Strong-typed data models for Constitution audit findings, rules, and exemptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from pathlib import Path
import json


class Severity(str, Enum):
    """Rule violation severity levels."""
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


class RuleCategory(str, Enum):
    """Top-level rule categories matching the constitution tree."""
    META = "meta"
    ARCHITECTURE = "arch"
    SECURITY = "sec"
    CONFIGURATION = "cfg"
    MCP_INTEGRATION = "mcp"
    RELIABILITY = "rel"
    COST = "cost"
    PERFORMANCE = "perf"
    CUSTOMER_UX = "ux"


@dataclass
class RuleDefinition:
    """Constitution rule definition."""
    rule_id: str  # e.g., "ARCH-001"
    category: RuleCategory
    title: str
    description: str
    severity: Severity
    fixable: bool = False
    details: Optional[str] = None


@dataclass
class AuditFinding:
    """A single audit finding from applying a rule."""
    rule_id: str
    severity: Severity
    file_path: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    message: str = ""
    code_snippet: Optional[str] = None
    remediation: Optional[str] = None
    confidence: float = 1.0  # 0.0 to 1.0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "message": self.message,
            "code_snippet": self.code_snippet,
            "remediation": self.remediation,
            "confidence": self.confidence,
        }


@dataclass
class Exemption:
    """An exemption record for a constitutional violation."""
    rule_id: str
    file_path: str
    owner: str  # GitHub username or team responsible
    reason: str  # Why this exemption exists
    expires: Optional[datetime] = None  # When exemption expires
    line_number: Optional[int] = None

    def is_expired(self) -> bool:
        """Check if exemption has expired."""
        if self.expires is None:
            return False
        return datetime.now() > self.expires

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "rule_id": self.rule_id,
            "file_path": self.file_path,
            "owner": self.owner,
            "reason": self.reason,
            "expires": self.expires.isoformat() if self.expires else None,
            "line_number": self.line_number,
        }


@dataclass
class AuditReport:
    """Complete audit report for a run."""
    findings: list[AuditFinding] = field(default_factory=list)
    exemptions_applied: list[Exemption] = field(default_factory=list)
    run_id: Optional[str] = None
    sha: Optional[str] = None
    branch: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def blocking_findings(self) -> list[AuditFinding]:
        """Return only findings with BLOCK severity."""
        return [f for f in self.findings if f.severity == Severity.BLOCK]

    def summary(self) -> dict:
        """Generate summary statistics."""
        return {
            "total_findings": len(self.findings),
            "blocking": len(self.blocking_findings()),
            "warnings": len([f for f in self.findings if f.severity == Severity.WARN]),
            "info": len([f for f in self.findings if f.severity == Severity.INFO]),
            "exemptions_applied": len(self.exemptions_applied),
            "run_id": self.run_id,
            "sha": self.sha,
            "branch": self.branch,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_jsonl(self) -> str:
        """Serialize findings to JSONL format."""
        lines = []
        for finding in self.findings:
            lines.append(json.dumps(finding.to_dict()))
        return "\n".join(lines)


def load_exemptions(path: Path) -> list[Exemption]:
    """Load exemptions from YAML file."""
    try:
        import yaml
    except ImportError:
        # Graceful fallback if yaml not available
        return []

    if not path.exists():
        return []

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    exemptions = []
    for item in data.get("exemptions", []):
        exp_str = item.get("expires")
        expires = datetime.fromisoformat(exp_str) if exp_str else None
        exemptions.append(
            Exemption(
                rule_id=item["rule_id"],
                file_path=item["file_path"],
                owner=item["owner"],
                reason=item["reason"],
                expires=expires,
                line_number=item.get("line_number"),
            )
        )
    return exemptions
