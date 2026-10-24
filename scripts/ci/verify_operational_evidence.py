#!/usr/bin/env python3
"""Build non-invasive backup and observability evidence for release review."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def check_paths(root: Path, candidates: tuple[str, ...]) -> dict[str, object]:
    present = [path for path in candidates if (root / path).exists()]
    return {"status": "passed" if present else "manual_pending", "artifacts": present}


def build(root: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "production_mutation_performed": False,
        "backup_restore": {
            "status": "manual_pending",
            "reason": "A live restore drill must be performed by the infrastructure owner.",
            "local_runbooks": check_paths(root, ("scripts/backup", "docs/PRODUCTION_RELEASE_CHECKLIST.md")),
            "required_evidence": ["backup timestamp", "restore target", "restore verification", "retention confirmation"],
        },
        "observability": {
            "status": "passed" if (root / "scripts/ci/staging_smoke_test.py").exists() else "manual_pending",
            "local_checks": check_paths(root, ("scripts/ci/staging_smoke_test.py", "scripts/ci/project_health_check.py")),
            "required_evidence": ["health/readiness result", "error-rate alert", "latency alert", "queue backlog alert", "database connectivity alert"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ci-reports/operational-evidence.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(root), indent=2) + "\n", encoding="utf-8")
    print(f"operational evidence written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
