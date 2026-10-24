"""SupremeAI - SecretHunter Agent.

Scans codebase for hardcoded API keys, tokens, and passwords using
gitleaks patterns and AI-enhanced detection. Integrates with the
SupremeAI security pipeline.

Key Components:
- `SecretHunter`: Main agent class for secret scanning operations.
- `GitleaksRunner`: Wrapper for gitleaks-style pattern matching.
- `AISecretAnalyzer`: LLM-based secret detection for novel patterns.
- `SecretReport`: Structured reporting for found secrets.

Dependencies:
- `core.config`: For accessing application settings.
- `core.llm.llm_gateway`: For AI-powered analysis.
- `subprocess`: For running gitleaks binary.
- `re`: For regex pattern matching.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.contracts.security_policy import SEVERITY_LEVELS
from core.logging_config import logger

# বাংলা মন্তব্য: উইন্ডোজ টার্মিনালে ইউনিকোড/ইমোজি আউটপুট সাপোর্ট করার জন্য এনকোডিং কনফিগার করা হলো।
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

# --- Path Setup ---
try:
    from core.config import settings
    from core.llm.llm_gateway import llm_gateway
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from core.config import settings
    from core.llm.llm_gateway import llm_gateway


@dataclass
class SecretFinding:
    """Represents a single secret finding."""

    rule_id: str
    file_path: str
    line_number: int
    column_start: int
    column_end: int
    matched_text: str
    secret_type: str
    severity: str  # "critical", "high", "medium", "low"
    remediation: str = ""
    ai_confidence: float = 0.0


@dataclass
class SecretReport:
    """Structured report for secret scanning results."""

    scan_id: str
    scanned_at: str
    total_files: int = 0
    findings: list[SecretFinding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary format."""
        return {
            "scan_id": self.scan_id,
            "scanned_at": self.scanned_at,
            "total_files": self.total_files,
            "findings_count": len(self.findings),
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "file_path": f.file_path,
                    "line_number": f.line_number,
                    "column_start": f.column_start,
                    "column_end": f.column_end,
                    "matched_text": (
                        f.matched_text[:50] + "..." if len(f.matched_text) > 50 else f.matched_text
                    ),
                    "secret_type": f.secret_type,
                    "severity": f.severity,
                    "remediation": f.remediation,
                    "ai_confidence": f.ai_confidence,
                }
                for f in self.findings
            ],
            "summary": self.summary,
        }


class GitleaksRunner:
    """Runs gitleaks-style secret detection patterns."""

    # Extended pattern set beyond standard gitleaks
    PATTERNS: dict[str, dict[str, Any]] = {
        "aws-access-key": {
            "regex": r"(?<![A-Za-z0-9/+=])(AKIA[0-9A-Z]{16})(?![A-Za-z0-9/+=])",
            "type": "AWS Access Key ID",
            "severity": "critical",
        },
        "aws-secret-key": {
            "regex": r"(?i)(?:aws_secret_access_key|aws_secret_key|secret_access_key|aws_secret)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
            "type": "AWS Secret Key",
            "severity": "critical",
        },
        "google-api-key": {
            "regex": r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])",
            "type": "Google API Key",
            "severity": "high",
        },
        "github-token": {
            "regex": r"(?<![A-Za-z0-9_])(ghp_[A-Za-z0-9_]{36}|gho_[A-Za-z0-9_]{36}|ghu_[A-Za-z0-9_]{36}|ghs_[A-Za-z0-9_]{36}|ghr_[A-Za-z0-9_]{36})(?![A-Za-z0-9_])",
            "type": "GitHub Token",
            "severity": "critical",
        },
        "slack-token": {
            "regex": r"(?<![A-Za-z0-9])(xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[A-Za-z0-9]{24})(?![A-Za-z0-9])",
            "type": "Slack Token",
            "severity": "critical",
        },
        "generic-api-key": {
            "regex": r"(?i)(?:api[_-]?key|apikey|api[_-]?secret)[\s]*[:=][\s]*['\"]([A-Za-z0-9_\-]{16,64})['\"]",
            "type": "Generic API Key",
            "severity": "high",
        },
        "jwt-secret": {
            "regex": r"(?i)(?:jwt[_-]?secret|jwt[_-]?key|jwt[_-]?token)[\s]*[:=][\s]*['\"]([A-Za-z0-9_\-]{8,})['\"]",
            "type": "JWT Secret",
            "severity": "critical",
        },
        "private-key": {
            "regex": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            "type": "Private Key",
            "severity": "critical",
        },
        "firebase-url": {
            "regex": r"(?<![A-Za-z0-9])https?://[A-Za-z0-9_-]+\.firebaseio\.com(?![A-Za-z0-9])",
            "type": "Firebase Database URL",
            "severity": "medium",
        },
        "stripe-key": {
            "regex": r"(?<![A-Za-z0-9])(sk_live_[0-9a-zA-Z]{24,})(?![A-Za-z0-9])",
            "type": "Stripe Live Key",
            "severity": "critical",
        },
        "openai-key": {
            "regex": r"(?<![A-Za-z0-9])(sk-[A-Za-z0-9]{48})(?![A-Za-z0-9])",
            "type": "OpenAI API Key",
            "severity": "high",
        },
        "password-in-code": {
            "regex": r"(?i)(?:password|passwd|pwd)[\s]*[:=][\s]*['\"]([^'\"]{4,})['\"]",
            "type": "Hardcoded Password",
            "severity": "critical",
        },
        "discord-token": {
            "regex": r"(?<![A-Za-z0-9])([MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27})(?![A-Za-z0-9])",
            "type": "Discord Token",
            "severity": "high",
        },
        "supabase-key": {
            "regex": r"(?i)(?:supabase[_-]?key|supabase[_-]?anon)[\s]*[:=][\s]*['\"]([A-Za-z0-9_\-]{20,})['\"]",
            "type": "Supabase Key",
            "severity": "high",
        },
    }

    def __init__(self) -> None:
        """Initialize the gitleaks runner."""
        self.compiled_patterns: dict[str, re.Pattern[str]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for performance."""
        for rule_id, config in self.PATTERNS.items():
            try:
                self.compiled_patterns[rule_id] = re.compile(config["regex"])
            except re.error as e:
                logger.warning(f"Failed to compile pattern {rule_id}: {e}")

    def scan_file(self, file_path: Path) -> list[SecretFinding]:
        """Scan a single file for secrets."""
        findings: list[SecretFinding] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug(f"Cannot read {file_path}: {e}")
            return findings

        for line_num, line in enumerate(lines, start=1):
            for rule_id, pattern in self.compiled_patterns.items():
                for match in pattern.finditer(line):
                    config = self.PATTERNS[rule_id]
                    finding = SecretFinding(
                        rule_id=rule_id,
                        file_path=str(file_path),
                        line_number=line_num,
                        column_start=match.start(),
                        column_end=match.end(),
                        matched_text=match.group(0),
                        secret_type=config["type"],
                        severity=config["severity"],
                        remediation=f"Remove hardcoded {config['type']} and use environment variables or secret manager",
                    )
                    findings.append(finding)

        return findings

    def scan_directory(
        self, directory: Path, extensions: set[str] | None = None
    ) -> list[SecretFinding]:
        """Scan a directory recursively for secrets."""
        if extensions is None:
            extensions = {
                ".py",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".env",
                ".sh",
                ".dart",
            }

        findings: list[SecretFinding] = []
        total_files = 0

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix in extensions:
                # বাংলা মন্তব্য: ওয়ার্কস্পেস বা রুট পাথে 'tests' বা 'tmp_' থাকলে যেন ভুলবশত ফাইল স্ক্যানিং স্কিপ না হয়, সেজন্য রিলেটিভ পাথ ফিল্টারিং ব্যবহার করা হচ্ছে।
                try:
                    rel_parts = file_path.relative_to(directory).parts
                except ValueError:
                    rel_parts = file_path.parts

                if any(part.startswith(".") for part in rel_parts):
                    continue
                if any(part in {"node_modules", "__pycache__", "tests"} for part in rel_parts):
                    continue
                if any(part.startswith("tmp_") for part in rel_parts):
                    continue
                if file_path.name.startswith("test_"):
                    continue

                total_files += 1
                file_findings = self.scan_file(file_path)
                findings.extend(file_findings)

        logger.info(f"Scanned {total_files} files, found {len(findings)} potential secrets")
        return findings


class AISecretAnalyzer:
    """Uses LLM to detect novel secret patterns and validate findings."""

    ANALYSIS_PROMPT = """
You are a security expert analyzing code for potential secret leaks.
Review the following code snippet and determine if it contains any hardcoded secrets, API keys, tokens, or passwords.

Code snippet from {file_path} (line {line_number}):
```python
{code_context}
```
Pattern matched: {matched_text}
Rule: {rule_id}
Analyze:
Is this a TRUE positive (actual secret) or FALSE positive?
What type of secret is this?
What is the severity (critical/high/medium/low)?
Suggested remediation.
Respond in JSON format:
{{
"is_true_positive": true/false,
"secret_type": "description",
"severity": "critical/high/medium/low",
"confidence": 0.0-1.0,
"remediation": "specific action to fix"
}}
"""

    def __init__(self) -> None:
        """Initialize the AI analyzer."""
        self.gateway = llm_gateway

    async def analyze_finding(self, finding: SecretFinding, code_context: str) -> SecretFinding:
        """Analyze a finding with AI to reduce false positives."""
        try:
            prompt = self.ANALYSIS_PROMPT.format(
                file_path=finding.file_path,
                line_number=finding.line_number,
                code_context=code_context,
                matched_text=finding.matched_text,
                rule_id=finding.rule_id,
            )

            response = await self.gateway.acompletion(
                model=settings.gemini_model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            # Extract JSON from response
            content = response.choices[0].message.content or "{}"
            # Find JSON block
            json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1)

            result = json.loads(content)

            if not result.get("is_true_positive", True):
                # Mark as false positive by setting severity to info
                finding.severity = "info"
                finding.ai_confidence = 0.0
            else:
                finding.severity = result.get("severity", finding.severity)
                finding.secret_type = result.get("secret_type", finding.secret_type)
                finding.remediation = result.get("remediation", finding.remediation)
                finding.ai_confidence = result.get("confidence", 0.8)

        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.warning(f"AI analysis failed for finding: {e}")
            finding.ai_confidence = 0.5  # Default medium confidence

        return finding


class SecretHunter:
    """Main SecretHunter agent for scanning codebases for secrets."""

    def __init__(self) -> None:
        """Initialize the SecretHunter agent."""
        self.gitleaks = GitleaksRunner()
        self.ai_analyzer = AISecretAnalyzer()

    async def scan_codebase(
        self,
        directory: str | Path,
        use_ai: bool = True,
        min_severity: str = "medium",
    ) -> SecretReport:
        """Scan a codebase for secrets."""
        # বাংলা মন্তব্য: সিক্রেট হান্ট স্ক্যান আইডি জেনারেট এবং ডিরেক্টরি স্ক্যানিং ট্রিগার।
        scan_id = f"secret-hunt-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        target_dir = Path(directory) if isinstance(directory, str) else directory

        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {target_dir}")

        logger.info(f"Starting secret scan: {scan_id} on {target_dir}")

        # Run gitleaks-style scan
        findings = self.gitleaks.scan_directory(target_dir)

        # AI analysis for high-confidence filtering
        if use_ai:
            validated_findings: list[SecretFinding] = []
            for finding in findings:
                if finding.severity in {"critical", "high"}:
                    # Get code context
                    try:
                        file_path = Path(finding.file_path)
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        lines = content.split("\n")
                        start = max(0, finding.line_number - 3)
                        end = min(len(lines), finding.line_number + 2)
                        context = "\n".join(lines[start:end])
                    except OSError:
                        context = finding.matched_text

                    try:
                        finding = await self.ai_analyzer.analyze_finding(finding, context)
                    except Exception as e:
                        logger.warning(
                            f"AI secret analysis skipped due to network/API timeout: {e}"
                        )
                    if finding.severity != "info":  # Not a false positive
                        validated_findings.append(finding)
                else:
                    validated_findings.append(finding)
            findings = validated_findings

        # Filter by minimum severity
        # Issue #684 (H-04): ranks derived from the canonical severity ladder
        # (+1 offsets the extra "info" tier below "low") — identical values to
        # the previous local map, but now impossible to drift from the canon.
        severity_order = {"info": 0, **{name: rank + 1 for name, rank in SEVERITY_LEVELS.items()}}
        min_level = severity_order.get(min_severity, 2)
        findings = [f for f in findings if severity_order.get(f.severity, 0) >= min_level]

        # Generate summary
        severity_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
            type_counts[f.secret_type] = type_counts.get(f.secret_type, 0) + 1

        report = SecretReport(
            scan_id=scan_id,
            scanned_at=datetime.now(UTC).isoformat(),
            total_files=sum(1 for _ in target_dir.rglob("*") if _.is_file()),
            findings=findings,
            summary={
                "severity_distribution": severity_counts,
                "type_distribution": type_counts,
                "critical_count": severity_counts.get("critical", 0),
                "high_count": severity_counts.get("high", 0),
                "ai_validated": use_ai,
            },
        )

        logger.info(
            f"Scan complete: {len(findings)} findings "
            f"({severity_counts.get('critical', 0)} critical, "
            f"{severity_counts.get('high', 0)} high)"
        )

        return report

    def generate_pre_commit_hook(self) -> str:
        """Generate a pre-commit hook script for secret scanning."""
        hook = """#!/bin/bash
# SecretHunter Pre-Commit Hook
# Auto-generated by SupremeAI SecretHunter
echo "🔍 Running SecretHunter pre-commit scan..."
# Run secret scan on staged files
python -m core.security.scanning.secret_scanner --staged
if [ $? -ne 0 ]; then
echo "❌ Secret scan failed! Fix issues before committing."
exit 1
fi
echo "✅ No secrets detected."
exit 0
"""
        return hook


# Singleton instance
secret_hunter = SecretHunter()


# Issue #895: contract alias — `backend/tests/core/test_security_and_intelligence_contracts.py`
# `SecretScanner` নামে import করে, কিন্তু historicalভাবে এই মডিউলে class নাম `SecretHunter`।
# দুজনেই একই কাজ করে — codebase scan করে secret detect করা — তাই `SecretScanner` কে
# `SecretHunter`-এর alias হিসেবে expose করা হলো। No stub, no fake — same real implementation.
SecretScanner = SecretHunter
