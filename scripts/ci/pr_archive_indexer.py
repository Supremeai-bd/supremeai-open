#!/usr/bin/env python3
"""
SupremeAI PR Archive & Incident Indexer.

Indexes closed/merged/open pull requests across SupremeAI repositories into a structured
incident and provenance ledger with full git diffs. Enables instant diagnosis of
regressions, past errors, breaking changes, and cross-agent code stomping.

Usage:
  python scripts/ci/pr_archive_indexer.py --pr 3210 --with-diff
  python scripts/ci/pr_archive_indexer.py --sync-merged 30 --with-diff
  python scripts/ci/pr_archive_indexer.py --diagnose --file core/mcp_allowlist.py
  python scripts/ci/pr_archive_indexer.py --search-diff "STALE_BASE_ERROR"
  python scripts/ci/pr_archive_indexer.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO_ROOT / "docs" / "pr_archive"
DIFFS_DIR = ARCHIVE_DIR / "diffs"
INDEX_FILE = ARCHIVE_DIR / "pr_incident_index.json"


def ensure_archive_dir() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    DIFFS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({"version": 2, "records": []}, indent=2), encoding="utf-8")


def load_index() -> Dict[str, Any]:
    ensure_archive_dir()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 2, "records": []}


def save_index(data: Dict[str, Any]) -> None:
    ensure_archive_dir()
    INDEX_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_pr_diff(pr_num: int) -> str:
    """Fetch PR unified diff via gh CLI with UTF-8 safe decoding."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "diff", str(pr_num)],
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    return ""


def parse_pr_details(pr_data: Dict[str, Any], diff_text: str = "") -> Dict[str, Any]:
    body = pr_data.get("body", "") or ""
    number = pr_data.get("number")
    title = pr_data.get("title", "")
    state = pr_data.get("state", "UNKNOWN")
    author = pr_data.get("author", {}).get("login", "unknown") if isinstance(pr_data.get("author"), dict) else str(pr_data.get("author"))

    # Extract reflection evidence
    why_m = re.search(r"-\s*\*\*why:\*\*\s*([^\n]+)", body, re.IGNORECASE)
    why = why_m.group(1).strip() if why_m else ""

    alt_m = re.search(r"-\s*\*\*alternatives_rejected:\*\*\s*([^\n]+)", body, re.IGNORECASE)
    alt = alt_m.group(1).strip() if alt_m else ""

    # Extract agent identity
    agent_m = re.search(r"##\s*Agent Identity\s*\n+([^\n#]+)", body, re.IGNORECASE)
    agent_id = agent_m.group(1).strip() if agent_m else author

    # Extract changed files from diff or files list
    touched_files: List[str] = []
    if "files" in pr_data and isinstance(pr_data["files"], list):
        touched_files = [f.get("path", "") for f in pr_data["files"] if f.get("path")]
    elif diff_text:
        touched_files = list(set(re.findall(r"^diff --git a/(.+?) b/", diff_text, re.MULTILINE)))

    record = {
        "pr_number": number,
        "title": title,
        "state": state,
        "author": author,
        "agent_identity": agent_id,
        "reflection_why": why,
        "alternatives_rejected": alt,
        "touched_files": touched_files,
        "has_verification_signature": bool("## Reflection Evidence" in body and ("3-Tier" in body or "Test Evidence" in body)),
        "diff_path": f"diffs/pr_{number}.diff" if diff_text else None,
        "diff_size_bytes": len(diff_text.encode("utf-8")) if diff_text else 0,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    return record


def index_pr(pr_num: int, include_diff: bool = True) -> bool:
    print(f"[*] Fetching metadata for PR #{pr_num}...")
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", str(pr_num), "--json", "number,title,state,body,author,files"],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip() if proc.stderr else "Unknown error"
            print(f"[-] Failed to fetch PR #{pr_num}: {err}")
            return False

        out_text = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else "{}"
        pr_data = json.loads(out_text)
        diff_text = ""
        if include_diff:
            print(f"[*] Fetching git diff for PR #{pr_num}...")
            diff_text = fetch_pr_diff(pr_num)
            if diff_text:
                diff_file = DIFFS_DIR / f"pr_{pr_num}.diff"
                diff_file.write_text(diff_text, encoding="utf-8")

        record = parse_pr_details(pr_data, diff_text)

        index_data = load_index()
        records = [r for r in index_data.get("records", []) if r.get("pr_number") != pr_num]
        records.append(record)
        index_data["records"] = sorted(records, key=lambda x: x.get("pr_number", 0), reverse=True)
        save_index(index_data)

        print(f"[+] Successfully indexed PR #{pr_num} (Agent: {record['agent_identity']}, State: {record['state']}, Diff: {record['diff_size_bytes']} bytes)")
        return True
    except Exception as e:
        print(f"[-] Error indexing PR #{pr_num}: {e}")
        return False


def sync_merged_prs(limit: int = 20, include_diff: bool = True) -> int:
    """Batch fetch and index recently merged PRs with UTF-8 safe decoding."""
    print(f"[*] Fetching last {limit} merged PRs from repository...")
    proc = subprocess.run(
        ["gh", "pr", "list", "--state", "merged", "--limit", str(limit), "--json", "number,title"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip() if proc.stderr else "Unknown error"
        print(f"[-] Failed to fetch merged PR list: {err}")
        return 0

    out_text = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else "[]"
    prs = json.loads(out_text)
    count = 0
    for p in prs:
        num = p.get("number")
        if num and index_pr(num, include_diff=include_diff):
            count += 1
    print(f"\n[+] Completed syncing {count} merged PRs into the incident archive.")
    return count


def search_diffs(query: str) -> None:
    """Search for code changes, error strings, or tokens across all stored diffs."""
    ensure_archive_dir()
    diff_files = list(DIFFS_DIR.glob("pr_*.diff"))
    print(f"\n🔍 Searching for '{query}' across {len(diff_files)} archived PR diffs...\n" + "-" * 60)
    matches_found = 0
    for df in diff_files:
        try:
            content = df.read_text(encoding="utf-8")
            if query.lower() in content.lower():
                matches_found += 1
                pr_num = df.stem.replace("pr_", "")
                print(f"[MATCH] Found in PR #{pr_num} ({df.name}):")
                # Show matching lines
                lines = content.splitlines()
                for i, l in enumerate(lines):
                    if query.lower() in l.lower():
                        snippet = "\n".join(lines[max(0, i - 1):min(len(lines), i + 2)])
                        print(f"  {snippet}\n")
                        break
        except Exception:
            continue
    if matches_found == 0:
        print("No matches found in archived diffs.")


def diagnose_file(file_path: str) -> None:
    norm_path = file_path.replace("\\", "/").lstrip("/")
    index_data = load_index()
    records = index_data.get("records", [])

    matches = [r for r in records if any(norm_path in tf for tf in r.get("touched_files", []))]

    print(f"\n🔍 Incident Diagnosis for: {norm_path}")
    print(f"Total historical PR occurrences: {len(matches)}\n" + "-" * 60)
    if not matches:
        print("No historical PR records touch this file in the current archive.")
        return

    for m in matches:
        pr_id = m.get("pr_number")
        state = m.get("state")
        agent = m.get("agent_identity")
        why = m.get("reflection_why") or "N/A"
        sig = "✅ Verified Signature" if m.get("has_verification_signature") else "⚠️ Missing Signature"
        diff_info = f"Diff: {m.get('diff_path')} ({m.get('diff_size_bytes', 0)} bytes)" if m.get("diff_path") else "No diff stored"
        print(f"PR #{pr_id} [{state}] by {agent} | {sig} | {diff_info}")
        print(f"  Reason: {why}")
        print(f"  Indexed: {m.get('indexed_at')}\n")


def run_self_test() -> int:
    print("[self-test] Running PR Archive & Incident Indexer self-test...")
    sample_pr = {
        "number": 9999,
        "title": "feat(test): synthetic test pr",
        "state": "MERGED",
        "author": {"login": "synthetic-agent"},
        "body": "## Reflection Evidence\n- **why:** testing archive mechanism\n- **alternatives_rejected:** none\n\n## 3-Tier Verify Evidence\nAll checks passed.\n\n## Agent Identity\nsynthetic-test-bot\n",
        "files": [{"path": "core/sample.py"}, {"path": "gateway/service.py"}],
    }
    sample_diff = "diff --git a/core/sample.py b/core/sample.py\n--- a/core/sample.py\n+++ b/core/sample.py\n@@ -1 +1 @@\n-old_error_code\n+new_fixed_code\n"

    record = parse_pr_details(sample_pr, sample_diff)
    assert record["pr_number"] == 9999, "Failed PR number parse"
    assert record["agent_identity"] == "synthetic-test-bot", "Failed agent identity parse"
    assert record["reflection_why"] == "testing archive mechanism", "Failed why parse"
    assert record["has_verification_signature"] is True, "Failed signature detection"
    assert "core/sample.py" in record["touched_files"], "Failed touched files parse"
    assert record["diff_path"] == "diffs/pr_9999.diff", "Failed diff path recording"

    print("[self-test] PASS - All parsing, diff tracking & contract invariants verified.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI PR Archive & Incident Indexer")
    parser.add_argument("--pr", type=int, help="Index a specific PR number")
    parser.add_argument("--with-diff", action="store_true", default=True, help="Fetch and store full unified git diff")
    parser.add_argument("--sync-merged", type=int, metavar="LIMIT", help="Batch index recent merged PRs with diffs")
    parser.add_argument("--diagnose", action="store_true", help="Diagnose PR history for a file")
    parser.add_argument("--file", type=str, help="Relative path to file for diagnosis")
    parser.add_argument("--search-diff", type=str, help="Search for code or error string across all archived diffs")
    parser.add_argument("--self-test", action="store_true", help="Run contract verification self-test")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.sync_merged:
        sync_merged_prs(limit=args.sync_merged, include_diff=args.with_diff)
        return 0

    if args.pr:
        success = index_pr(args.pr, include_diff=args.with_diff)
        return 0 if success else 1

    if args.search_diff:
        search_diffs(args.search_diff)
        return 0

    if args.diagnose:
        if not args.file:
            print("Error: --diagnose requires --file <path>")
            return 1
        diagnose_file(args.file)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
