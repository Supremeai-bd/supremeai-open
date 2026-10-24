"""
SupremeAI Security Hardening & Dependency Auditor
================================================================
Automated security scanning and dependency management.

Features:
- Dependency vulnerability scanning
- Unused dependency detection
- Security best practices enforcement
- Automated security reports
- CI/CD integration ready

Author: SuperAI Enhancement Patch
Version: 2.0.0
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from core.logging_config import logger


class Severity(Enum):
    """Security severity levels"""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class VulnerabilityType(Enum):
    """Types of vulnerabilities"""

    DEPENDENCY = "dependency"  # Vulnerable dependency version
    CONFIGURATION = "configuration"  # Misconfigured setting
    CODE_PATTERN = "code_pattern"  # Insecure code pattern
    SECRET_LEAK = "secret_leak"  # Potential secret exposure
    PERMISSION = "permission"  # Overly permissive settings


@dataclass
class Vulnerability:
    """Security vulnerability finding"""

    id: str
    type: VulnerabilityType
    severity: Severity
    title: str
    description: str
    location: str  # File or package name
    remediation: str  # How to fix
    references: list[str] = field(default_factory=list)
    cvss_score: float | None = None  # CVSS score if available

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "remediation": self.remediation,
            "cvss_score": self.cvss_score,
        }


@dataclass
class DependencyInfo:
    """Information about a dependency"""

    name: str
    version: str
    required_version: str | None = None
    is_used: bool = True
    has_vulnerabilities: bool = False
    vulnerabilities: list[Vulnerability] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.is_used:
            return "UNUSED"
        if self.has_vulnerabilities:
            return "VULNERABLE"
        return "OK"


# Security patterns to detect in code
INSECURE_PATTERNS: list[dict[str, Any]] = [
    # ── Secret Exposure Risks ──────────────────────────────────────────
    {
        "id": "SEC001",
        "pattern": r'(?:api[_-]?key|secret|password|token)\s*=\s*["\'][^"\']{8,}["\']',
        "type": VulnerabilityType.SECRET_LEAK,
        "severity": Severity.CRITICAL,
        "title": "Hardcoded Secret Detected",
        "description": "A potential API key, secret, or password is hardcoded in source code",
        "remediation": "Move secrets to environment variables or use a secrets manager (Infisical)",
        "file_patterns": ["*.py", "*.js", "*.ts", "*.env", "*.yaml", "*.yml"],
    },
    {
        "id": "SEC002",
        "pattern": r"print\s*\(\s*(?:os\.environ|os\.getenv|getenv|environ)",
        "type": VulnerabilityType.SECRET_LEAK,
        "severity": Severity.HIGH,
        "title": "Potential Secret Logging",
        "description": "Environment variable being printed which may contain sensitive data",
        "remediation": "Remove debug printing or mask sensitive values",
        "file_patterns": ["*.py"],
    },
    # ── Insecure Code Patterns ─────────────────────────────────────────
    {
        "id": "SEC003",
        "pattern": r"eval\s*\(",
        "type": VulnerabilityType.CODE_PATTERN,
        "severity": Severity.CRITICAL,
        "title": "Use of eval()",
        "description": "eval() can execute arbitrary code and is a major security risk",
        "remediation": "Replace with safer alternatives (ast.literal_eval, json.loads)",
        "file_patterns": ["*.py"],
    },
    {
        "id": "SEC004",
        "pattern": r"exec\s*\(",
        "type": VulnerabilityType.CODE_PATTERN,
        "severity": Severity.CRITICAL,
        "title": "Use of exec()",
        "description": "exec() can execute arbitrary code and is a major security risk",
        "remediation": "Refactor to avoid dynamic code execution",
        "file_patterns": ["*.py"],
    },
    {
        "id": "SEC005",
        "pattern": r"subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True",
        "type": VulnerabilityType.CODE_PATTERN,
        "severity": Severity.HIGH,
        "title": "Shell Injection Risk",
        "description": "subprocess call with shell=True is vulnerable to shell injection",
        "remediation": "Use shell=False and pass arguments as list, or use shlex.quote()",
        "file_patterns": ["*.py"],
    },
    {
        "id": "SEC006",
        "pattern": r"pickle\.(loads?|dump)",
        "type": VulnerabilityType.CODE_PATTERN,
        "severity": Severity.HIGH,
        "title": "Insecure Deserialization",
        "description": "pickle can execute arbitrary code during deserialization",
        "remediation": "Use JSON or safer serialization formats",
        "file_patterns": ["*.py"],
    },
    # ── Configuration Issues ───────────────────────────────────────────
    {
        "id": "SEC007",
        "pattern": r'CORS_ORIGINS\s*=\s*["\'][*]',
        "type": VulnerabilityType.CONFIGURATION,
        "severity": Severity.HIGH,
        "title": "Overly Permissive CORS",
        "description": "CORS configured to allow all origins (*)",
        "remediation": "Specify exact allowed origins",
        "file_patterns": [".env*", "*.py", "*.yaml", "*.yml"],
    },
    {
        "id": "SEC008",
        "pattern": r"DEBUG\s*=\s*True",
        "type": VulnerabilityType.CONFIGURATION,
        "severity": Severity.MEDIUM,
        "title": "Debug Mode Enabled",
        "description": "Debug mode may expose sensitive information",
        "remediation": "Disable debug mode in production",
        "file_patterns": ["*.py", ".env*"],
    },
    {
        "id": "SEC009",
        "pattern": r'(?:ALLOWED_HOSTS|HOSTS)\s*=\s*["\']?\*?',
        "type": VulnerabilityType.CONFIGURATION,
        "severity": Severity.MEDIUM,
        "title": "Open Host Header",
        "description": "Host validation disabled or overly permissive",
        "remediation": "Specify allowed hosts explicitly",
        "file_patterns": ["*.py", ".env*"],
    },
]


class SecurityAuditor:
    """
    Comprehensive security auditing tool.

    Usage:
        auditor = SecurityAuditor()

        # Run full audit
        report = auditor.audit()

        # Check specific areas
        vulns = auditor.scan_code_patterns()
        deps = auditor.audit_dependencies()
    """

    def __init__(self, project_root: str | None = None):
        self.project_root = project_root or os.getcwd()
        self.vulnerabilities: list[Vulnerability] = []
        self.dependencies: dict[str, DependencyInfo] = {}

        # Statistics
        self.stats = {
            "files_scanned": 0,
            "vulnerabilities_found": 0,
            "by_severity": {},
            "by_type": {},
        }

    def audit(self) -> dict[str, Any]:
        """
        Run comprehensive security audit.

        Returns:
            Complete audit report
        """
        logger.info("🔒 Starting comprehensive security audit...")

        start_time = datetime.now()

        # Run all checks
        code_vulns = self.scan_code_patterns()
        dep_issues = self.audit_dependencies()
        config_issues = self.check_configurations()

        # Combine results
        all_vulns = code_vulns + dep_issues + config_issues
        self.vulnerabilities = all_vulns

        # Calculate stats
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        self.stats["vulnerabilities_found"] = len(all_vulns)
        self.stats["by_severity"] = self._count_by_severity(all_vulns)
        self.stats["by_type"] = self._count_by_type(all_vulns)
        self.stats["duration_seconds"] = duration

        # Generate report
        report = self.generate_report()

        logger.info(f"✅ Audit complete: {len(all_vulns)} issues found ({duration:.1f}s)")

        return report

    def scan_code_patterns(self) -> list[Vulnerability]:
        """
        Scan source files for insecure patterns.

        Returns:
            List of vulnerabilities found
        """
        vulnerabilities = []

        for pattern_info in INSECURE_PATTERNS:
            pattern = pattern_info["pattern"]

            # Find matching files
            for root, dirs, files in os.walk(self.project_root):
                # Skip common non-source directories
                dirs[:] = [
                    d
                    for d in dirs
                    if d
                    not in [
                        "__pycache__",
                        ".git",
                        "node_modules",
                        ".venv",
                        "venv",
                        ".cache",
                        "dist",
                        "build",
                    ]
                ]

                for file in files:
                    # Check file pattern match
                    if not self._matches_file_pattern(file, pattern_info.get("file_patterns", [])):
                        continue

                    filepath = os.path.join(root, file)

                    try:
                        with open(filepath, encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                            # Search for pattern
                            matches = re.finditer(pattern, content)
                            for match in matches:
                                line_num = content[: match.start()].count("\n") + 1

                                vuln = Vulnerability(
                                    id=pattern_info["id"],
                                    type=pattern_info["type"],
                                    severity=pattern_info["severity"],
                                    title=pattern_info["title"],
                                    description=pattern_info["description"],
                                    location=f"{filepath}:{line_num}",
                                    remediation=pattern_info["remediation"],
                                    references=pattern_info.get("references", []),
                                )
                                vulnerabilities.append(vuln)
                                current_scanned = int(str(self.stats.get("files_scanned", 0)))
                                self.stats["files_scanned"] = current_scanned + 1

                    except Exception as e:
                        logger.debug(f"Could not scan {filepath}: {e}")

        return vulnerabilities

    def _matches_file_pattern(self, filename: str, patterns: list[str]) -> bool:
        """Check if filename matches any of the patterns"""
        if not patterns:
            return True

        import fnmatch

        return any(fnmatch.fnmatch(filename, p) for p in patterns)

    def audit_dependencies(self) -> list[Vulnerability]:
        """
        Audit Python dependencies for known vulnerabilities.

        Returns:
            List of vulnerable dependencies
        """
        vulnerabilities = []

        # Try to get installed packages
        try:
            result = subprocess.run(
                ["pip", "list", "--format=json"], capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                packages = json.loads(result.stdout)

                for pkg in packages:
                    dep_info = DependencyInfo(name=pkg["name"].lower(), version=pkg["version"])

                    # Check for known vulnerable versions
                    vuln = self._check_known_vulnerabilities(dep_info)
                    if vuln:
                        vulnerabilities.append(vuln)
                        dep_info.has_vulnerabilities = True
                        dep_info.vulnerabilities.append(vuln)

                    self.dependencies[dep_info.name] = dep_info

        except Exception as e:
            logger.warning(f"Dependency audit failed: {e}")

        # Check for unused imports (basic check)
        unused = self._detect_unused_dependencies()
        for dep_name in unused:
            if dep_name in self.dependencies:
                self.dependencies[dep_name].is_used = False

        return vulnerabilities

    def _check_known_vulnerabilities(self, dep: DependencyInfo) -> Vulnerability | None:
        """
        Check against known vulnerability database.

        This is a simplified version - in production, integrate with:
        - OSV (Open Source Vulnerabilities)
        - GitHub Advisory Database
        - Snyk Vulnerability DB
        - PyPI advisory database
        """
        # Known vulnerable versions (simplified example)
        KNOWN_VULNS = {
            "requests": {"<2.31.0": ("SEC-VULN-001", "SSRF vulnerability in redirects")},
            "flask": {"<2.3.3": ("SEC-VULN-002", "Possible Open Redirect")},
            "django": {"<4.2.8": ("SEC-VULN-003", "Multiple CVEs including admin panel XSS")},
            "sqlalchemy": {"<2.0.23": ("SEC-VULN-004", "SQL injection in certain queries")},
            "pillow": {"<10.1.0": ("SEC-VULN-005", "Multiple DoS vulnerabilities")},
            "jinja2": {"<3.1.3": ("SEC-VULN-006", "ReDoS in template parsing")},
        }

        if dep.name in KNOWN_VULNS:
            for version_range, (vuln_id, description) in KNOWN_VULNS[dep.name].items():
                if self._version_in_range(dep.version, version_range):
                    return Vulnerability(
                        id=vuln_id,
                        type=VulnerabilityType.DEPENDENCY,
                        severity=Severity.HIGH,
                        title=f"Vulnerable Dependency: {dep.name}",
                        description=f"{description} (installed: {dep.version}, affected: {version_range})",
                        location=f"{dep.name}=={dep.version}",
                        remediation=f"Upgrade {dep.name} to latest safe version",
                        references=[
                            f"https://github.com/advisories?query={dep.name}",
                            f"https://pypi.org/project/{dep.name}/#history",
                        ],
                    )

        return None

    def _version_in_range(self, version: str, range_spec: str) -> bool:
        """Simple version range checking"""
        from packaging import version as v

        try:
            current = v.parse(version)

            if range_spec.startswith("<"):
                max_ver = v.parse(range_spec[1:].strip())
                return current < max_ver
            elif range_spec.startswith("<="):
                max_ver = v.parse(range_spec[2:].strip())
                return current <= max_ver
            elif range_spec.startswith(">"):
                min_ver = v.parse(range_spec[1:].strip())
                return current > min_ver
            elif range_spec.startswith(">="):
                min_ver = v.parse(range_spec[2:].strip())
                return current >= min_ver

        except Exception as exc:
            from core.logging_config import logger

            logger.warning(
                f"[SecurityAuditor] Version parsing failed for range '{range_spec}': {exc}"
            )

        return False

    def _detect_unused_dependencies(self) -> list[str]:
        """
        Basic detection of potentially unused dependencies.

        Note: This is a heuristic approach and may have false positives/negatives.
        For accurate analysis, use tools like `pipdeptree` or `vulture`.
        """
        unused = []

        try:
            # Get imports from Python files
            imported_modules = set()

            for root, dirs, files in os.walk(self.project_root):
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in ["__pycache__", ".git", "node_modules", ".venv", "venv", ".cache"]
                ]

                for file in files:
                    if file.endswith(".py"):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath) as f:
                                for line in f:
                                    # Match import statements
                                    imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", line)
                                    for imp in imports:
                                        # Get base module name
                                        base_module = imp.split(".")[0].lower()
                                        imported_modules.add(base_module)
                        except Exception as exc:
                            from core.logging_config import logger

                            logger.debug(
                                f"[SecurityAuditor] Could not scan imports in {filepath}: {exc}"
                            )

            # Compare with installed packages
            for dep_name, dep_info in self.dependencies.items():
                if dep_name not in imported_modules:
                    # Common false positives to exclude
                    if dep_name not in [
                        "setuptools",
                        "pip",
                        "wheel",
                        "pkg-resources",
                        "typing-extensions",
                        "certifi",
                    ]:
                        unused.append(dep_name)

        except Exception as e:
            logger.debug(f"Unused dependency detection failed: {e}")

        return unused

    def check_configurations(self) -> list[Vulnerability]:
        """
        Check configuration files for security issues.

        Returns:
            List of configuration-related vulnerabilities
        """
        vulnerabilities = []

        # Check .env.example for required vars
        env_example = os.path.join(self.project_root, ".env.example")
        if os.path.exists(env_example):
            with open(env_example) as f:
                content = f.read()

                # Check for insecure defaults
                if re.search(r"CORS_ORIGINS.*\*", content):
                    vulnerabilities.append(
                        Vulnerability(
                            id="SEC010",
                            type=VulnerabilityType.CONFIGURATION,
                            severity=Severity.MEDIUM,
                            title="Insecure CORS Default in .env.example",
                            description=".env.example shows wildcard CORS origin",
                            location=".env.example",
                            remediation="Update .env.example with secure default origins",
                        )
                    )

        # Check for presence of .env file (should be gitignored)
        env_file = os.path.join(self.project_root, ".env")
        if os.path.exists(env_file):
            # Check if it's in .gitignore
            gitignore_path = os.path.join(self.project_root, ".gitignore")
            should_ignore = False

            if os.path.exists(gitignore_path):
                with open(gitignore_path) as f:
                    if ".env" in f.read():
                        should_ignore = True

            if not should_ignore:
                vulnerabilities.append(
                    Vulnerability(
                        id="SEC011",
                        type=VulnerabilityType.SECRET_LEAK,
                        severity=Severity.HIGH,
                        title="Untracked .env File",
                        description=".env file exists but may not be in .gitignore",
                        location=".env",
                        remediation="Add .env to .gitignore immediately",
                    )
                )

        return vulnerabilities

    def generate_report(self) -> dict[str, Any]:
        """
        Generate comprehensive security report.

        Returns:
            Complete audit report as dictionary
        """
        critical = [v for v in self.vulnerabilities if v.severity == Severity.CRITICAL]
        high = [v for v in self.vulnerabilities if v.severity == Severity.HIGH]
        medium = [v for v in self.vulnerabilities if v.severity == Severity.MEDIUM]
        low = [v for v in self.vulnerabilities if v.severity == Severity.LOW]

        # Score calculation (100 = perfect, deductions for issues)
        score = 100
        score -= len(critical) * 25
        score -= len(high) * 10
        score -= len(medium) * 3
        score -= len(low) * 1
        score = max(0, score)

        return {
            "timestamp": datetime.now().isoformat(),
            "project_root": self.project_root,
            "score": score,
            "grade": self._calculate_grade(score),
            "summary": {
                "total_vulnerabilities": len(self.vulnerabilities),
                "critical": len(critical),
                "high": len(high),
                "medium": len(medium),
                "low": len(low),
                "dependencies_scanned": len(self.dependencies),
                "unused_dependencies": sum(1 for d in self.dependencies.values() if not d.is_used),
            },
            "vulnerabilities": [
                v.to_dict()
                for v in sorted(
                    self.vulnerabilities,
                    key=lambda x: (
                        {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
                    ).get(x.severity.value, 5),
                )
            ],
            "recommendations": self._generate_recommendations(critical, high, medium),
            "statistics": self.stats,
        }

    def _calculate_grade(self, score: int) -> str:
        """Convert numeric score to letter grade"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _generate_recommendations(
        self, critical: list[Vulnerability], high: list[Vulnerability], medium: list[Vulnerability]
    ) -> list[str]:
        """Generate prioritized recommendations"""
        recommendations = []

        if critical:
            recommendations.append(
                f"🚨 URGENT: Fix {len(critical)} critical security issues immediately"
            )

        if high:
            recommendations.append(f"⚠️ HIGH: Address {len(high)} high-severity issues this sprint")

        if medium:
            recommendations.append(f"📋 MEDIUM: Plan fixes for {len(medium)} medium issues")

        # General recommendations
        recommendations.extend(
            [
                "🔄 Set up automated security scanning in CI/CD pipeline",
                "📦 Regularly update dependencies (weekly recommended)",
                "🔐 Use environment variables for all secrets (never hardcode)",
                "📖 Follow OWASP Top 10 guidelines",
                "🧪 Implement security testing in development workflow",
            ]
        )

        return recommendations

    def _count_by_severity(self, items: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            sev = item.severity.value if hasattr(item, "severity") else "unknown"
            counts[sev] = counts.get(sev, 0) + 1
        return counts

    def _count_by_type(self, items: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            t = item.type.value if hasattr(item, "type") else "unknown"
            counts[t] = counts.get(t, 0) + 1
        return counts


def run_security_audit(project_root: str | None = None) -> dict[str, Any]:
    """
    Convenience function to run full security audit.

    Args:
        project_root: Root directory of project to audit

    Returns:
        Complete audit report
    """
    auditor = SecurityAuditor(project_root)
    return auditor.audit()


def print_security_report(report: dict[str, Any]) -> None:
    """Pretty-print security report to console"""
    from core.logging_config import logger

    logger.info("\n" + "=" * 70)
    from core.logging_config import logger

    logger.info("🔒 SUPREMEAI SECURITY AUDIT REPORT")
    from core.logging_config import logger

    logger.info("=" * 70)

    from core.logging_config import logger

    logger.info(f"\n📊 Overall Score: {report['score']}/100 (Grade: {report['grade']})")
    from core.logging_config import logger

    logger.info(f"   Timestamp: {report['timestamp']}")

    summary = report["summary"]
    from core.logging_config import logger

    logger.info("\n📋 Summary:")
    from core.logging_config import logger

    logger.info(f"   Total Vulnerabilities: {summary['total_vulnerabilities']}")
    from core.logging_config import logger

    logger.info(f"   🚨 Critical: {summary['critical']}")
    from core.logging_config import logger

    logger.info(f"   ⚠️  High: {summary['high']}")
    from core.logging_config import logger

    logger.info(f"   📋 Medium: {summary['medium']}")
    from core.logging_config import logger

    logger.info(f"   ℹ️  Low: {summary['low']}")
    from core.logging_config import logger

    logger.info(f"   Dependencies Scanned: {summary['dependencies_scanned']}")
    from core.logging_config import logger

    logger.info(f"   Unused Dependencies: {summary['unused_dependencies']}")

    if report["vulnerabilities"]:
        from core.logging_config import logger

        logger.info("\n🐛 Vulnerabilities Found:")
        from core.logging_config import logger

        logger.info("-" * 70)

        for vuln in report["vulnerabilities"][:20]:  # Show top 20
            severity_icon = {
                "CRITICAL": "🚨",
                "HIGH": "⚠️",
                "MEDIUM": "📋",
                "LOW": "ℹ️",
                "INFO": "💡",
            }.get(vuln["severity"], "❓")

            from core.logging_config import logger

            logger.info(f"\n{severity_icon} [{vuln['severity']}] {vuln['title']}")
            from core.logging_config import logger

            logger.info(f"   Location: {vuln['location']}")
            from core.logging_config import logger

            logger.info(f"   Issue: {vuln['description']}")
            from core.logging_config import logger

            logger.info(f"   Fix: {vuln['remediation']}")

    if report["recommendations"]:
        from core.logging_config import logger

        logger.info("\n💡 Recommendations:")
        for rec in report["recommendations"]:
            from core.logging_config import logger

            logger.info(f"   • {rec}")

    from core.logging_config import logger

    logger.info("\n" + "=" * 70 + "\n")


# CLI entry point
if __name__ == "__main__":
    import sys

    logger.debug("🔍 Running SupremeAI Security Audit...")
    logger.debug("=" * 60)

    project = sys.argv[1] if len(sys.argv) > 1 else None

    report = run_security_audit(project)
    print_security_report(report)

    # Exit with error code if critical/high issues found
    if report["summary"]["critical"] > 0:
        sys.exit(2)  # Critical issues
    elif report["summary"]["high"] > 0:
        sys.exit(1)  # High issues
    else:
        sys.exit(0)  # OK
