"""Output reporters for audit findings (console, GitHub, SARIF)."""

from __future__ import annotations

from pathlib import Path

from .models import AuditReport, Severity


class ConsoleReporter:
    """Pretty-print findings to console."""

    def report(self, report: AuditReport) -> None:
        """Print findings to stdout."""
        if not report.findings:
            print("✅ No findings.")
            return

        for finding in report.findings:
            symbol = {
                Severity.BLOCK: "❌",
                Severity.WARN: "⚠️ ",
                Severity.INFO: "ℹ️ ",
            }.get(finding.severity, "•")

            print(f"{symbol} {finding.rule_id}: {finding.message}")
            print(f"   {finding.file_path}:{finding.line_number}")
            if finding.remediation:
                print(f"   💡 {finding.remediation}")


class GithubStepSummaryReporter:
    """Write findings to GitHub step summary."""

    def report(self, report: AuditReport, summary_path: Path) -> None:
        """Write findings to GITHUB_STEP_SUMMARY."""
        summary = report.summary()

        content = f"""
## 🛡️ Constitution Audit Report

**Summary:**
- Total Findings: {summary['total_findings']}
- Blocking: {summary['blocking']}
- Warnings: {summary['warnings']}
- Info: {summary['info']}
- Exemptions Applied: {summary['exemptions_applied']}

"""

        if report.blocking_findings():
            content += "### ❌ Blocking Issues\n\n"
            for finding in report.blocking_findings():
                content += f"- **{finding.rule_id}**: {finding.message}\n"
                content += f"  - File: {finding.file_path}:{finding.line_number}\n"
                if finding.remediation:
                    content += f"  - Remediation: {finding.remediation}\n"
            content += "\n"

        warnings = [f for f in report.findings if f.severity == Severity.WARN]
        if warnings:
            content += "### ⚠️ Warnings\n\n"
            for finding in warnings:
                content += f"- **{finding.rule_id}**: {finding.message}\n"
            content += "\n"

        with open(summary_path, "a") as f:
            f.write(content)


class SARIFReporter:
    """Write findings to SARIF v2.1 format (GitHub CodeQL integration)."""

    def report(self, report: AuditReport, sarif_path: Path) -> None:
        """Write findings to SARIF file."""
        import json

        sarif_report = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "SupremeAI Constitution Audit",
                            "version": "1.0.0",
                            "informationUri": "https://supremeai.dev/docs/constitution",
                            "rules": self._build_rules(),
                        }
                    },
                    "results": self._build_results(report),
                }
            ],
        }

        sarif_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sarif_path, "w") as f:
            json.dump(sarif_report, f, indent=2)

    def _build_rules(self) -> list[dict]:
        """Build SARIF rule definitions."""
        # Simplified; in production, import from models
        return [
            {
                "id": "ARCH-001",
                "shortDescription": {"text": "No Local-Machine Dependency"},
                "help": {"text": "Production code must not reference localhost or local paths."},
            },
            {
                "id": "SEC-001",
                "shortDescription": {"text": "Backend Authorization Is Final"},
                "help": {"text": "Authorization must be enforced on backend, not client-side."},
            },
            {
                "id": "SEC-002",
                "shortDescription": {"text": "No Secret Hardcoding"},
                "help": {"text": "Secrets must use environment variables or secret managers."},
            },
            {
                "id": "REL-001",
                "shortDescription": {"text": "No Silent Failure"},
                "help": {"text": "Exception handlers must log or re-raise, never silently pass."},
            },
            {
                "id": "CFG-001",
                "shortDescription": {"text": "No Policy Hardcoding"},
                "help": {"text": "Runtime policy values belong in the configuration control plane."},
            },
            {
                "id": "SEC-003",
                "shortDescription": {"text": "No Unsafe Privilege Elevation"},
                "help": {"text": "Privilege elevation requires explicit authorization."},
            },
            {
                "id": "REL-002",
                "shortDescription": {"text": "Error Observability"},
                "help": {"text": "Production errors must be logged, reported, or re-raised."},
            },
        ]

    def _build_results(self, report: AuditReport) -> list[dict]:
        """Build SARIF result objects from findings."""
        results = []
        for finding in report.findings:
            result = {
                "ruleId": finding.rule_id,
                "level": {Severity.BLOCK: "error", Severity.WARN: "warning", Severity.INFO: "note"}[finding.severity],
                "message": {"text": finding.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding.file_path},
                            "region": {
                                "startLine": finding.line_number or 1,
                                **({"startColumn": finding.column_number} if finding.column_number else {}),
                            },
                        }
                    }
                ],
            }
            if finding.remediation:
                result["fixes"] = [
                    {
                        "description": {"text": finding.remediation},
                        "artifactChanges": [
                            {
                                "artifactLocation": {"uri": finding.file_path},
                                "replacements": [
                                    {
                                        "deletedRegion": {"startLine": finding.line_number or 1},
                                        "insertedContent": {"text": finding.remediation},
                                    }
                                ],
                            }
                        ],
                    }
                ]

            results.append(result)

        return results
