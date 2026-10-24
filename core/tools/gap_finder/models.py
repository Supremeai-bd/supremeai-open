from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    rule_id: str
    category: str
    severity: str
    confidence: float
    title: str
    message: str
    path: str | None = None
    line: int | None = None
    evidence: list[str] = field(default_factory=list)
    impact: str = ""
    remediation: str = ""
    verification: str = ""
    fingerprint: str = ""

    def finalize(self) -> Finding:
        raw = "||".join([
            self.rule_id,
            self.category,
            self.severity,
            self.title,
            self.path or "",
            str(self.line or ""),
            self.message,
        ])
        self.fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        return self


@dataclass
class AuditStats:
    files_scanned: int = 0
    text_files_scanned: int = 0
    python_files_scanned: int = 0
    total_lines: int = 0
    findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    manifests: dict[str, str] = field(default_factory=dict)


@dataclass
class AuditReport:
    tool: str
    version: str
    root: str
    generated_at: str
    duration_seconds: float
    profile: str
    stats: AuditStats
    findings: list[Finding]
    signals: dict[str, Any]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["findings"] = [asdict(f) for f in self.findings]
        return result


