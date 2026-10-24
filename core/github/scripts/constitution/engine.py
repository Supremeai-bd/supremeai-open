"""Constitution audit engine — main CLI and orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .models import AuditReport, Severity
from .reporters import ConsoleReporter, GithubStepSummaryReporter
from .rules.arch001_no_local_machine import NoLocalMachineRule
from .rules.rel001_no_silent_failure import NoSilentFailureRule
from .rules.sec001_backend_auth import BackendAuthFinalRule
from .rules.sec002_no_secret_hardcoding import NoSecretHardcodingRule
from .rules.cfg001_no_policy_hardcoding import NoPolicyHardcodingRule
from .rules.sec003_unsafe_privilege import UnsafePrivilegeElevationRule
from .rules.rel002_error_observability import ErrorObservabilityRule


class ConstitutionAuditEngine:
    """Main audit engine orchestrator."""

    def __init__(self):
        """Initialize the engine."""
        self.rules = [
            NoLocalMachineRule(),
            NoSecretHardcodingRule(),
            NoSilentFailureRule(),
            BackendAuthFinalRule(),
            NoPolicyHardcodingRule(),
            UnsafePrivilegeElevationRule(),
            ErrorObservabilityRule(),
        ]

    def get_pr_diff_files(self, base_ref: str = "origin/main") -> list[Path]:
        """Get list of source files changed in PR."""
        source_extensions = {".py", ".ts", ".tsx", ".js", ".jsx"}
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref, "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                files = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
                return [
                    f for f in files
                    if f.exists()
                    and f.suffix in source_extensions
                    and not any(
                        x in str(f)
                        for x in [".git", "node_modules", ".venv", "__pycache__", "_archive"]
                    )
                ]
        except Exception as e:
            print(f"Warning: Could not get git diff: {e}")

        return []

    def get_all_source_files(self) -> list[Path]:
        """Get all source files in the repository."""
        files = []
        for pattern in ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]:
            for path in Path.cwd().glob(pattern):
                # Skip certain directories
                # _archive = versioned quarantine of dead modules
                # (MAINTAINABILITY_PLAN §2) — not production code; auditing
                # it re-flags pre-existing content on every archive batch.
                if any(
                    x in str(path)
                    for x in [".git", "node_modules", ".venv", "__pycache__", "_archive"]
                ):
                    continue
                    continue
                files.append(path)

        return files

    def run_audit(
        self,
        files: Optional[list[Path]] = None,
        pr_diff: bool = False,
        base_ref: str = "origin/main",
    ) -> AuditReport:
        """Run complete audit on files."""
        if files is None:
            files = self.get_pr_diff_files(base_ref) if pr_diff else self.get_all_source_files()

        report = AuditReport()
        report.run_id = os.getenv("GITHUB_RUN_ID")
        report.sha = os.getenv("GITHUB_SHA")
        report.branch = os.getenv("GITHUB_REF_NAME")

        for rule in self.rules:
            findings = rule.audit(files)
            report.findings.extend(findings)

        return report

    def save_report(self, report: AuditReport, output_path: Path) -> None:
        """Save audit report to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            for finding in report.findings:
                f.write(json.dumps(finding.to_dict()) + "\n")

    def print_summary(self, report: AuditReport) -> None:
        """Print summary to console and GitHub step summary."""
        summary = report.summary()
        print("\n" + "=" * 60)
        print("SupremeAI Constitution Audit Report")
        print("=" * 60)
        print(f"Findings: {summary['total_findings']}")
        print(f"  - Blocking: {summary['blocking']}")
        print(f"  - Warnings: {summary['warnings']}")
        print(f"  - Info: {summary['info']}")
        print(f"Exemptions Applied: {summary['exemptions_applied']}")
        print("=" * 60 + "\n")

        # Write to GitHub step summary if available
        step_summary = os.getenv("GITHUB_STEP_SUMMARY")
        if step_summary:
            reporter = GithubStepSummaryReporter()
            reporter.report(report, Path(step_summary))

    def get_exit_code(self, report: AuditReport) -> int:
        """Determine exit code based on findings."""
        if report.blocking_findings():
            return 1
        return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SupremeAI Constitution Audit Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  constitution-audit --pr-diff              # Audit PR changes vs origin/main
  constitution-audit --all                  # Audit entire repository
  constitution-audit --pr-diff --output findings.jsonl
        """,
    )

    parser.add_argument(
        "--pr-diff",
        action="store_true",
        help="Audit only PR-changed files (vs origin/main)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Audit all source files in repository",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git reference for diff baseline (default: origin/main)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write findings to JSONL file",
    )
    parser.add_argument(
        "--fix-safe",
        action="store_true",
        help="Auto-fix safe violations (future: not yet implemented)",
    )
    parser.add_argument(
        "--sarif",
        type=Path,
        help="Write SARIF v2.1 report (future: not yet implemented)",
    )

    args = parser.parse_args()

    # Default to PR diff if nothing specified
    if not args.pr_diff and not args.all:
        args.pr_diff = True

    engine = ConstitutionAuditEngine()
    report = engine.run_audit(pr_diff=args.pr_diff, base_ref=args.base_ref)

    engine.print_summary(report)

    if args.output:
        engine.save_report(report, args.output)
        print(f"Report saved to {args.output}")

    if args.sarif:
        from .reporters import SARIFReporter
        SARIFReporter().report(report, args.sarif)
        print(f"SARIF report saved to {args.sarif}")

    exit_code = engine.get_exit_code(report)
    if exit_code != 0:
        msg = "\n[FAILED] Constitution audit FAILED — blocking findings detected."
    else:
        msg = "\n[PASSED] Constitution audit PASSED."
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
