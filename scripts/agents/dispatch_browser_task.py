"""Browser Task Dispatcher & IPC Bridge CLI.

Connects continuous_agent_loop.py, smart_dispatcher.py, or manual CLI
to the autonomous multi-tab browser worker via file-based IPC.

Usage:
    # 1. Dispatch issue to coder role and wait for result
    python scripts/agents/dispatch_browser_task.py --role coder --issue 3229 --wait

    # 2. Dispatch custom prompt to devops role
    python scripts/agents/dispatch_browser_task.py --role devops --prompt "Verify vault env readiness" --wait

    # 3. Check live queue and tab statuses
    python scripts/agents/dispatch_browser_task.py --status

    # 4. Use as --exec runner in continuous_agent_loop.py
    python scripts/agents/continuous_agent_loop.py --role coder --exec -- python scripts/agents/dispatch_browser_task.py --role coder --wait
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_DIR = Path(os.environ.get("WEB_AGENT_TASKS", str(REPO_ROOT / ".browser_tasks")))
REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")


def fetch_issue_context(issue_number: int, repo: str = REPO) -> Dict[str, str]:
    """Fetch title, body, and labels for an issue via gh CLI."""
    try:
        r = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "title,body,labels"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in data.get("labels", [])]
            return {
                "title": data.get("title", ""),
                "body": data.get("body", ""),
                "labels": ", ".join(labels),
            }
    except Exception:
        pass
    return {"title": f"Issue #{issue_number}", "body": "", "labels": ""}


def dispatch_task(
    tasks_dir: Path,
    role: str,
    prompt: str,
    task_id: Optional[str] = None,
    issue_number: Optional[int] = None,
    session_pattern: Optional[str] = None,
) -> Path:
    """Write task JSON into inbox directory."""
    inbox = tasks_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    if not task_id:
        ts = int(time.time() * 1000)
        prefix = f"issue_{issue_number}" if issue_number else role
        task_id = f"{prefix}_{ts}"

    task_payload = {
        "task_id": task_id,
        "role": role.lower(),
        "prompt": prompt,
        "issue": issue_number,
        "session_pattern": session_pattern,
        "created_at": datetime.now().isoformat(),
        "dispatched_by": "dispatch_browser_task",
    }

    target_file = inbox / f"{task_id}.json"
    target_file.write_text(json.dumps(task_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target_file


def wait_for_completion(tasks_dir: Path, task_id: str, timeout_sec: int = 600) -> Optional[Dict[str, Any]]:
    """Wait for completed/<task_id>.json to appear."""
    completed_file = tasks_dir / "completed" / f"{task_id}.json"
    guard_file = tasks_dir / "HUMAN_ACTION_REQUIRED.json"

    start = time.time()
    last_status = ""

    while time.time() - start < timeout_sec:
        # Check human blocker
        if guard_file.exists():
            try:
                gdata = json.loads(guard_file.read_text(encoding="utf-8"))
                reason = gdata.get("reason", "Human action required")
                sess = gdata.get("session", "unknown")
                msg = f"⚠ PAUSED: {reason} on [{sess}]. Resolve in browser window..."
                if msg != last_status:
                    print(msg, flush=True)
                    last_status = msg
            except Exception:
                pass

        if completed_file.exists():
            try:
                data = json.loads(completed_file.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass

        time.sleep(2)

    return None


def show_queue_status(tasks_dir: Path):
    print("=" * 60)
    print(f"SupremeAI Browser Worker IPC Status: {tasks_dir}")
    print("=" * 60)

    guard_file = tasks_dir / "HUMAN_ACTION_REQUIRED.json"
    if guard_file.exists():
        try:
            gdata = json.loads(guard_file.read_text(encoding="utf-8"))
            print(f"🛑 BLOCKED: {gdata.get('reason')} on [{gdata.get('session')}] since {gdata.get('since')}")
        except Exception:
            print("🛑 BLOCKED: Human verification active")
    else:
        print("🟢 STATUS: Normal (No active verification blockers)")

    inbox_files = list((tasks_dir / "inbox").glob("*.json")) if (tasks_dir / "inbox").exists() else []
    proc_files = list((tasks_dir / "processing").glob("*.json")) if (tasks_dir / "processing").exists() else []
    done_files = list((tasks_dir / "completed").glob("*.json")) if (tasks_dir / "completed").exists() else []

    print(f"\nQueue Breakdown:")
    print(f"  Inbox (Pending)   : {len(inbox_files)}")
    print(f"  Processing (Live) : {len(proc_files)}")
    print(f"  Completed         : {len(done_files)}")

    if proc_files:
        print("\nCurrently Active in Browser:")
        for p in proc_files:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                print(f"  - [{d.get('role', '?').upper()}] {d.get('task_id')}: {d.get('prompt', '')[:60]}...")
            except Exception:
                print(f"  - {p.stem}")

    if done_files:
        print("\nRecent Completed Tasks (last 3):")
        for d in sorted(done_files, key=lambda f: f.stat().st_mtime, reverse=True)[:3]:
            try:
                c = json.loads(d.read_text(encoding="utf-8"))
                out_snip = (c.get("output") or "").strip().replace("\n", " ")[:70]
                print(f"  - {c.get('task_id')} [{c.get('role')}]: {out_snip}...")
            except Exception:
                pass
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Browser Task Dispatcher")
    parser.add_argument("--role", default="coder", help="Target agent role (coder, devops, watcher, breaker)")
    parser.add_argument("--issue", type=int, default=None, help="Issue number to automatically build prompt from")
    parser.add_argument("--prompt", type=str, default=None, help="Explicit prompt to dispatch")
    parser.add_argument("--pattern", type=str, default=None, help="Target session title regex pattern")
    parser.add_argument("--task-id", type=str, default=None, help="Custom task ID")
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASKS_DIR), help="Tasks IPC directory")
    parser.add_argument("--wait", action="store_true", help="Wait for task completion and output")
    parser.add_argument("--timeout", type=int, default=600, help="Wait timeout in seconds (default: 600s)")
    parser.add_argument("--output-file", type=str, default=None, help="File to save response output into")
    parser.add_argument("--status", action="store_true", help="Display queue status and exit")

    args = parser.parse_args()
    tasks_dir = Path(args.tasks_dir)

    if args.status:
        show_queue_status(tasks_dir)
        return 0

    # Build prompt
    prompt = args.prompt
    if args.issue and not prompt:
        info = fetch_issue_context(args.issue)
        prompt = (
            f"Please solve Issue #{args.issue}: {info['title']}\n\n"
            f"Labels: {info['labels']}\n\n"
            f"Issue Description:\n{info['body']}\n\n"
            f"Provide complete, production-ready code implementation and verify with tests."
        )

    if not prompt:
        print("❌ Error: Must provide either --prompt or --issue (or --status).", file=sys.stderr)
        return 1

    task_file = dispatch_task(
        tasks_dir=tasks_dir,
        role=args.role,
        prompt=prompt,
        task_id=args.task_id,
        issue_number=args.issue,
        session_pattern=args.pattern,
    )
    task_id = task_file.stem
    print(f"🚀 Dispatched task '{task_id}' -> role: [{args.role.upper()}] (queue: {task_file})")

    if not args.wait:
        return 0

    print(f"⏳ Waiting for browser tab execution (timeout: {args.timeout}s)...")
    res = wait_for_completion(tasks_dir, task_id, timeout_sec=args.timeout)

    if not res:
        print(f"❌ Timed out waiting for task '{task_id}' completion.", file=sys.stderr)
        return 2

    output_text = res.get("output", "")
    print(f"\n✅ Task '{task_id}' completed successfully in session [{res.get('session', '')}]:")
    print("-" * 60)
    print(output_text[:1000] + ("\n... [truncated]" if len(output_text) > 1000 else ""))
    print("-" * 60)

    if args.output_file:
        Path(args.output_file).write_text(output_text, encoding="utf-8")
        print(f"💾 Output saved to {args.output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
