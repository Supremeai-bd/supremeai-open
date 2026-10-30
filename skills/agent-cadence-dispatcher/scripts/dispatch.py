#!/usr/bin/env python3
"""Entry point for the agent-cadence-dispatcher skill.

Prints due roles and, when requested, creates an empty-board audit issue.
Stdlib-only. Fail-closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "scripts" / "agents"))

import continuous_agent_loop as cal


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent cadence dispatcher skill")
    parser.add_argument(
        "--create-audit-issue",
        action="store_true",
        help="Create a full-project audit issue (empty-board handling)",
    )
    parser.add_argument(
        "--mark-run",
        metavar="ROLE",
        help="Record that ROLE just ran (update last_run store)",
    )
    args = parser.parse_args()

    cfg = cal.load_cadence_config()
    store = cal.load_last_run_store()
    now = __import__("time").time()
    due = cal.due_roles(store, now, cfg)
    print(json.dumps({"due_roles": due, "last_run": store}, indent=2, sort_keys=True))

    if args.create_audit_issue:
        num = cal.create_full_project_audit_issue()
        if num is None:
            print("audit issue creation: FAILED (see logs)", file=sys.stderr)
            return 1
        print(f"created audit issue: #{num}")

    if args.mark_run:
        cal.mark_role_run(args.mark_run, store, now, cfg)
        cal.save_last_run_store(store)
        print(f"marked run: {args.mark_run}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
