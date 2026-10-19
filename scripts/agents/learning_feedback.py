#!/usr/bin/env python3
"""Learning feedback loop (plan §5 step 6, §10.3).

On a successful, verified merge, record the verified solution so future compatible
skills/agents can reuse it. Stdlib-only. Fail-closed on IO errors (logged, never crash).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIED_SOLUTIONS_PATH = REPO_ROOT / ".verified_solutions.jsonl"


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_verified_solution(
    issue_ref: int | str,
    scope_paths: list[str],
    digests: dict[str, str] | None = None,
    agent_id: str = "unknown-agent",
    reflection_why: str = "",
    alternatives_rejected: list[str] | None = None,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Append a verified solution record. Returns the record on success, None on failure."""
    target = path or VERIFIED_SOLUTIONS_PATH
    record = {
        "schema": "verified-solution/1",
        "issue_ref": issue_ref,
        "scope_paths": list(scope_paths or []),
        "digests": dict(digests or {}),
        "agent_id": agent_id,
        "reflection_why": reflection_why,
        "alternatives_rejected": list(alternatives_rejected or []),
        "recorded_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    record["record_id"] = hashlib.sha256(
        json.dumps(record, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        return record
    except (OSError, UnicodeDecodeError):
        return None


def load_verified_solutions(path: Path | None = None) -> list[dict[str, Any]]:
    """Load all verified solution records (fail-closed: skip malformed lines)."""
    target = path or VERIFIED_SOLUTIONS_PATH
    out: list[dict[str, Any]] = []
    if not target.exists():
        return out
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("schema") == "verified-solution/1":
                    out.append(obj)
    except (OSError, UnicodeDecodeError):
        return out
    return out


def promote_to_skill_draft(
    solution: dict[str, Any],
    skill_name: str,
    staging_dir: Path,
) -> Path | None:
    """Create a SKILL.md draft from a verified solution in staging_dir. Returns path or None."""
    if not solution or not skill_name:
        return None
    name = skill_name.strip().lower().replace(" ", "-")
    if not name:
        return None
    try:
        skill_dir = staging_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        scope = ", ".join(solution.get("scope_paths", [])) or "(see solution)"
        body = (
            "---\n"
            f"name: {name}\n"
            "version: 0.1.0\n"
            f"description: Reusable procedure promoted from verified solution for issue #{solution.get('issue_ref')}.\n"
            "triggers: [promoted, verified-solution]\n"
            "permission_level: read\n"
            "memory_policy: write\n"
            "owner: supremeai-skills\n"
            "verification_required: true\n"
            "---\n\n"
            "# Promoted Skill (draft)\n\n"
            f"Promoted from verified solution issue #{solution.get('issue_ref')}.\n\n"
            f"## Scope\n{scope}\n\n"
            f"## Rationale\n{solution.get('reflection_why', '')}\n"
        )
        (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
        return skill_dir / "SKILL.md"
    except (OSError, UnicodeDecodeError):
        return None


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Learning feedback loop")
    parser.add_argument("--list", action="store_true", help="list verified solutions")
    parser.add_argument("--record-issue", type=int, help="issue ref to record (demo)")
    args = parser.parse_args()

    if args.list:
        sols = load_verified_solutions()
        print(json.dumps({"count": len(sols), "solutions": sols}, indent=2, sort_keys=True))
        return 0
    if args.record_issue is not None:
        rec = record_verified_solution(args.record_issue, scope_paths=[])
        print(json.dumps(rec, indent=2, sort_keys=True) if rec else "FAILED")
        return 0 if rec else 1
    print("nothing to do; use --list or --record-issue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
