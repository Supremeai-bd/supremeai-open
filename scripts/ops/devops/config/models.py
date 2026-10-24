from dataclasses import field
from datetime import datetime
from enum import Enum


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class ValidationResult:
    """Result of a single validation check."""
    category: str
    check_name: str
    severity: Severity
    message: str
    value: str | None = None
    expected: str | None = None
    fix_suggestion: str | None = None
    auto_fixable: bool = False

    def to_dict(self) -> dict:
        return {
            'category': self.category,
            'check_name': self.check_name,
            'severity': self.severity.value,
            'message': self.message,
            'value': self.value,
            'expected': self.expected,
            'fix_suggestion': self.fix_suggestion,
            'auto_fixable': self.auto_fixable
        }

class ConfigValidationReport:
    """Complete validation report."""
    results: list[ValidationResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def critical_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.CRITICAL)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.INFO)

    @property
    def is_valid(self) -> bool:
        return self.critical_count == 0 and self.error_count == 0

    @property
    def total_issues(self) -> int:
        return self.critical_count + self.error_count + self.warning_count

    def to_dict(self) -> dict:
        return {
            'is_valid': self.is_valid,
            'summary': {
                'critical': self.critical_count,
                'errors': self.error_count,
                'warnings': self.warning_count,
                'info': self.info_count,
                'total_issues': self.total_issues
            },
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'results': [r.to_dict() for r in self.results]
        }
