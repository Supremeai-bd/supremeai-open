#!/usr/bin/env python3
"""Task Dashboard (#2573).

Real-time view of all tasks in the system:
- Task states
- Assignments
- Priorities
- Agent workload

Usage:
    python scripts/ci/task_dashboard.py
    python scripts/ci/task_dashboard.py --json
    python scripts/ci/task_dashboard.py --state task:ready
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dataclasses import dataclass, field
from enum import Enum

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")
STATE_LABEL_PREFIX = "task:"
TYPE_LABEL_PREFIX = "task-type:"


class TaskState(Enum):
    READY = "ready"
    WAITING_FOR_AGENT = "waiting"
    ASSIGNED = "assigned"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskType(Enum):
    AUDIT = "audit"
    FIX = "fix"
    REVIEW = "review"
    CI_FIX = "ci-fix"
    SECURITY = "security"
    CLEANUP = "cleanup"
    VERIFICATION = "verification"
    MERGE = "merge"


class TaskPriority(Enum):
    P0_CRITICAL = "P0-critical"
    P1_HIGH = "P1-high"
    P2_MEDIUM = "P2-medium"
    P3_LOW = "P3-low"


PRIORITY_LABELS = {p.value for p in TaskPriority}


@dataclass
class Task:
    task_id: str
    task_type: TaskType
    state: TaskState
    priority: TaskPriority
    title: str
    description: str = ""
    assigned_agent: str = ""
    group_name: str = ""
    depends_on: list[str] = field(default_factory=list)
    capabilities_required: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    issue_number: int | None = None
    pr_number: int | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "state": self.state.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "assigned_agent": self.assigned_agent,
            "group_name": self.group_name,
            "depends_on": self.depends_on,
            "capabilities_required": self.capabilities_required,
            "metadata": self.metadata,
            "issue_number": self.issue_number,
            "pr_number": self.pr_number,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def parse_task_labels(labels: list[str]) -> tuple[TaskState | None, TaskType | None, TaskPriority | None]:
    state = None
    task_type = None
    priority = None
    for label in labels:
        if label.startswith(STATE_LABEL_PREFIX):
            state_val = label[len(STATE_LABEL_PREFIX):]
            try:
                state = TaskState(state_val)
            except ValueError:
                pass
        elif label.startswith(TYPE_LABEL_PREFIX):
            type_val = label[len(TYPE_LABEL_PREFIX):]
            try:
                task_type = TaskType(type_val)
            except ValueError:
                pass
        elif label in PRIORITY_LABELS:
            try:
                priority = TaskPriority(label)
            except ValueError:
                pass
    return state, task_type, priority


def fetch_tasks_by_state(state: TaskState | None = None, repo_dir: Path = ROOT_DIR) -> list[Task]:
    res = run(["gh", "issue", "list", "--repo", REPO, "--state", "open", "--limit", "200", "--json", "number,title,labels,body,createdAt,assignees"])
    if res.returncode != 0 or not res.stdout.strip():
        return []
    tasks = []
    try:
        issues = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []
    for issue in issues:
        labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in issue.get("labels", [])]
        task_state, task_type, priority = parse_task_labels(labels)
        if not task_state or not task_type or not priority:
            continue
        if state and task_state != state:
            continue
        assignees = [a.get("login", "") for a in issue.get("assignees", []) if isinstance(a, dict)]
        task = Task(
            task_id=f"task-{issue['number']}",
            task_type=task_type,
            state=task_state,
            priority=priority,
            title=issue.get("title", ""),
            description=issue.get("body", "") or "",
            assigned_agent=assignees[0] if assignees else "",
            issue_number=issue.get("number"),
            created_at=issue.get("createdAt", ""),
            updated_at=issue.get("updatedAt", ""),
        )
        tasks.append(task)
    return tasks


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def get_all_tasks() -> list[Task]:
    tasks: list[Task] = []
    for state in TaskState:
        tasks.extend(fetch_tasks_by_state(state))
    return tasks


def get_agent_workload() -> dict[str, int]:
    res = run(["gh", "issue", "list", "--repo", REPO, "--label", "status:in-progress", "--state", "open", "--json", "assignees"])
    if res.returncode != 0:
        return {}
    try:
        issues = json.loads(res.stdout)
    except json.JSONDecodeError:
        return {}
    workload: dict[str, int] = defaultdict(int)
    for issue in issues:
        for assignee in issue.get("assignees", []):
            if isinstance(assignee, dict):
                workload[assignee.get("login", "")] += 1
    return dict(workload)


def render_dashboard(tasks: list[Task], agent_workload: dict[str, int]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("  📊 Task Dashboard — SupremeAI Task Engine")
    lines.append("=" * 70)
    lines.append("")
    by_state: dict[str, list[Task]] = defaultdict(list)
    for t in tasks:
        by_state[t.state.value].append(t)
    lines.append(f"Total Tasks: {len(tasks)}")
    lines.append("")
    lines.append("─" * 70)
    lines.append("  Tasks by State")
    lines.append("─" * 70)
    for state in TaskState:
        state_tasks = by_state.get(state.value, [])
        lines.append(f"  {state.value.upper():<20} {len(state_tasks):>3}")
    lines.append("")
    lines.append("─" * 70)
    lines.append("  Task Details")
    lines.append("─" * 70)
    for state in TaskState:
        state_tasks = by_state.get(state.value, [])
        if not state_tasks:
            continue
        lines.append(f"\n  [{state.value.upper()}]")
        for task in sorted(state_tasks, key=lambda t: t.priority.value):
            priority = task.priority.value
            task_type = task.task_type.value
            agent = task.assigned_agent or "unassigned"
            issue_ref = f"#{task.issue_number}" if task.issue_number else "no-issue"
            lines.append(f"    {issue_ref:<10} [{priority:<12}] [{task_type:<15}] {agent:<20} {task.title[:40]}")
    lines.append("")
    lines.append("─" * 70)
    lines.append("  Agent Workload")
    lines.append("─" * 70)
    if agent_workload:
        for agent, count in sorted(agent_workload.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {agent:<30} {count:>3} active task(s)")
    else:
        lines.append("  No active agent assignments found.")
    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def dashboard_to_json(tasks: list[Task], agent_workload: dict[str, int]) -> dict[str, Any]:
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in tasks:
        by_state[t.state.value].append(t.to_dict())
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_tasks": len(tasks),
        "by_state": dict(by_state),
        "agent_workload": agent_workload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Task Dashboard (#2573)")
    parser.add_argument("--state", help="Filter by state label (e.g. task:ready)")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()
    
    if args.state:
        state_label = args.state
        state_val = state_label.replace(STATE_LABEL_PREFIX, "")
        try:
            target_state = TaskState(state_val)
            tasks = fetch_tasks_by_state(target_state)
        except ValueError:
            tasks = get_all_tasks()
    else:
        tasks = get_all_tasks()
    
    agent_workload = get_agent_workload()
    
    if args.format == "json":
        print(json.dumps(dashboard_to_json(tasks, agent_workload), indent=2))
    else:
        print(render_dashboard(tasks, agent_workload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
