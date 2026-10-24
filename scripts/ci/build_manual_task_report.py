#!/usr/bin/env python3
"""Build a non-secret report for human-controlled release tasks.

This script verifies repository-local prerequisites only. It never reads secret
values, contacts production systems, mutates infrastructure, or marks a live
operation complete without owner-supplied evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def command_ok(root: Path, *args: str) -> bool:
    try:
        subprocess.run(
            list(args), cwd=root, check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def local_check(root: Path, paths: tuple[str, ...]) -> dict[str, object]:
    present = [path for path in paths if (root / path).exists()]
    return {"status": "passed" if len(present) == len(paths) else "blocked", "artifacts": present}


def build(root: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "production_mutation_performed": False,
        "secret_values_read": False,
        "tasks": {
            "deployment_command_owner_approval": {
                "status": "manual_pending",
                "evidence_required": ["owner identity", "approval timestamp", "approved command scope"],
                "local": local_check(root, ("scripts/ai/baseline_commands.json", "scripts/ai/baseline_commands.py")),
            },
            "ci_advisory_promotion": {
                "status": "manual_pending",
                "evidence_required": ["CI run URL", "deterministic failure review", "blocking-mode decision"],
                "local": local_check(root, (".github/workflows/ci.yml", "scripts/ci/release_acceptance_gate.py")),
            },
            "protected_path_review": {
                "status": "manual_pending",
                "evidence_required": ["business owner", "reviewed path registry", "decision log entry"],
                "local": local_check(root, (".github/CODEOWNERS", "config/merge_policy_registry.json")),
            },
            "environment_classification": {
                "status": "manual_pending",
                "evidence_required": ["deployment owner", "variable name inventory", "build/runtime classification"],
                "local": local_check(root, ("secrets_registry.yaml", "scripts/ci/check_required_secrets.py")),
            },
            "deployment_credentials_and_rollback": {
                "status": "manual_pending",
                "evidence_required": ["credential verification", "health check result", "rollback result"],
                "local": local_check(root, ("docs/ADMIN_TASKS/render-deploy-preflight.md", "scripts/deploy/blue_green_deploy.py")),
            },
            "database_restore_drill": {
                "status": "manual_pending",
                "evidence_required": ["backup timestamp", "restore target", "verification result", "rollback owner"],
                "local": local_check(root, ("scripts/backup/disaster_recovery_test.py", "docs/PRODUCTION_RELEASE_CHECKLIST.md")),
            },
            "artifact_retention_approval": {
                "status": "manual_pending",
                "evidence_required": ["retention period", "privacy review", "deletion owner"],
                "local": local_check(root, (".github/workflows/db-retention.yml", "docs/PRODUCTION_RELEASE_CHECKLIST.md")),
            },
            "detector_baseline_review": {
                "status": "manual_pending",
                "evidence_required": ["reviewed baseline dataset", "false-positive/negative decision", "gate owner"],
                "local": local_check(root, ("scripts/silent_errors_baseline.json", "scripts/feature_parity_baseline.json")),
            },
            "autonomy_promotion": {
                "status": "manual_pending",
                "evidence_required": ["engineering owner written approval", "risk assessment", "promotion scope"],
                "local": local_check(root, ("tools/autonomy/README.md", "tools/autonomy/tools/deploy_guard.py")),
            },
        },
        "local_safety_checks": {
            "git_available": command_ok(root, "git", "--version"),
            "python_available": command_ok(root, "python", "--version"),
        },
        "next_action": "Collect owner approvals and live evidence before production promotion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ci-reports/manual-task-report.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(root), indent=2) + "\n", encoding="utf-8")
    print(f"manual task report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
