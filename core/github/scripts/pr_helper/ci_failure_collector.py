#!/usr/bin/env python3
"""
PR Helper — Phase 1: CI Failure Collector (issue #1034)
========================================================
একটি PR-এর সর্বশেষ failed CI run খুঁজে বের করে, প্রতিটি failed job-এর
লগ থেকে structured failure data extract করে।

কী কী collect করে:
  - failed test names (pytest AssertionError / ModuleNotFoundError / etc.)
  - error messages + stack traces (শেষ 4 KB of each failed job log)
  - lint violations (Ruff / Flake8 / mypy patterns)
  - import errors, syntax errors

GitHub API endpoints used (urllib + REST, কোনো extra dependency নেই):
  1. GET /repos/{repo}/actions/runs?head_sha={sha}&status=failure  → failed run list
  2. GET /repos/{repo}/actions/runs/{run_id}/jobs                  → failed job list
  3. GET /repos/{repo}/actions/jobs/{job_id}/logs                  → job log (text/plain)
  4. GET /repos/{repo}/pulls/{pr_number}                           → PR head SHA + changed files

Output (ci_failures.json):
  {
    "pr_number": 1234,
    "head_sha": "abc123",
    "run_id": 987654,
    "run_url": "https://github.com/...",
    "collected_at": "2025-01-01T12:00:00Z",
    "failed_jobs": [
      {
        "job_id": 111,
        "name": "test-backend (3.11)",
        "conclusion": "failure",
        "log_bytes": 4096,
        "failures": [
          {
            "type": "test_failure",          # test_failure | lint_violation | import_error | syntax_error | generic
            "test_name": "tests/test_x.py::test_y",
            "file_path": "backend/tests/test_x.py",
            "message": "AssertionError: assert ...",
            "stack_trace": "...",
            "log_excerpt": "..."            # প্রাসঙ্গিক লগের অংশ
          }
        ]
      }
    ],
    "summary": {
      "total_failed_jobs": 1,
      "total_failures": 3,
      "by_type": {"test_failure": 2, "import_error": 1}
    }
  }

Usage:
  python ci_failure_collector.py \\
    --repo SaifulHaqueNiloy/supremeai \\
    --pr 1046 \\
    --token "$GH_TOKEN" \\
    --output-json ci_failures.json

GitHub Actions outputs (GITHUB_OUTPUT):
  failed_jobs_count = N
  total_failures = M
  run_id = K
  has_failures = true|false
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# --- Constants --------------------------------------------------------------

GITHUB_API_BASE = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"
# প্রতিটি job log থেকে সর্বোচ্চ যতটুকু পড়বে (৮ KB — ample for stack trace)
MAX_LOG_BYTES_PER_JOB = 8192
# একসাথে সর্বোচ্চ কয়টি failure per job extract করবে
MAX_FAILURES_PER_JOB = 20

# লগ থেকে failure extract করার regex pattern-গুলো
# --- pytest failure: "FAILED tests/test_x.py::test_y - AssertionError: ..." ---
PYTEST_FAILED_RE = re.compile(
    r"(?:FAILED|ERROR)\s+(?P<test>[\w/.:\-\[\] ]+\.py(?:::[\w_\-]+(?:\[[\w\-]+\])?)*)\s*-\s*(?P<msg>.+)"
)
# --- Ruff lint: "backend/core/x.py:12:34: E501 line too long" ---
LINT_RE = re.compile(
    r"^(?P<file>[\w/.-]+\.py):(?P<line>\d+):(?P<col>\d+):\s*(?P<code>[A-Z]\d+)\s+(?P<msg>.+)$",
    re.MULTILINE,
)
# --- ImportError / ModuleNotFoundError ---
IMPORT_ERR_RE = re.compile(
    r"(?:ImportError|ModuleNotFoundError):\s*(?:No module named\s*['\"]?(?P<mod>[\w.]+)['\"]?|cannot import name\s*['\"]?(?P<name>\w+)['\"]?).*"
)
# --- SyntaxError ---
SYNTAX_ERR_RE = re.compile(r"SyntaxError:\s*(?P<msg>.+?)(?:$|\n)")
# --- Generic: AssertionError / Exception / Error: ... ---
GENERIC_ERR_RE = re.compile(
    r"(?P<exc>(?:AssertionError|RuntimeError|ValueError|TypeError|KeyError|AttributeError|Exception)):\s*(?P<msg>.+)"
)
# --- File path with line number: 'File "backend/core/x.py", line 42, in func' ---
PYFILE_LINE_RE = re.compile(
    r'File\s+"(?P<file>[\w/.-]+\.py)",\s*line\s*(?P<line>\d+),\s*in\s*(?P<func>\w+)'
)


# --- HTTP helper (urllib — no external deps) --------------------------------


def _gh_request(
    url: str,
    token: str,
    method: str = "GET",
    accept: str = ACCEPT_HEADER,
    body: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, dict | bytes, dict | None]:
    """GitHub REST API call. Returns (status, body, headers).

    বডি JSON হলে dict, অন্যথায় bytes (যেমন logs text). এরর হলে dict রিটার্ন।
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "supremeai-pr-helper/1.0",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
            resp_headers = dict(resp.headers)
    except urllib.error.HTTPError as exc:
        # Real urllib passes a file-like fp; tests may pass bytes directly.
        raw = b""
        try:
            raw = exc.read()
        except (AttributeError, TypeError, OSError):
            fp = getattr(exc, "fp", None)
            if isinstance(fp, (bytes, bytearray)):
                raw = bytes(fp)
            else:
                raw = b""
        status = exc.code
        resp_headers = dict(exc.headers) if exc.headers else {}
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, None

    if accept == ACCEPT_HEADER and raw:
        try:
            return status, json.loads(raw.decode("utf-8")), resp_headers
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, raw, resp_headers
    return status, raw, resp_headers


# --- Failure parsing --------------------------------------------------------


def _classify_failure(text: str) -> str:
    """লগ অংশ থেকে failure type classify করে।"""
    if IMPORT_ERR_RE.search(text):
        return "import_error"
    if SYNTAX_ERR_RE.search(text):
        return "syntax_error"
    if LINT_RE.search(text):
        return "lint_violation"
    if PYTEST_FAILED_RE.search(text) or GENERIC_ERR_RE.search(text):
        return "test_failure"
    return "generic"


def _extract_test_name(text: str) -> str:
    """লগ থেকে failing test name extract করে।"""
    m = PYTEST_FAILED_RE.search(text)
    if m:
        return m.group("test").strip()
    # বিকল্প: "tests/test_x.py::test_y" pattern
    m = re.search(r"(\btests/[\w/.-]+\.py(?:::[\w_\-]+)?)", text)
    return m.group(1).strip() if m else ""


def _extract_file_path(text: str) -> str:
    """লগ থেকে source file path extract করে।"""
    m = PYFILE_LINE_RE.search(text)
    if m:
        return m.group("file")
    # বিকল্প: ruff-style "backend/core/x.py:12:34:"
    m = re.search(r"\b(backend/[\w/.-]+\.py|src/[\w/.-]+\.py|tests/[\w/.-]+\.py)", text)
    return m.group(1) if m else ""


def _extract_message(text: str) -> str:
    """লগ থেকে error message extract করে।"""
    # প্রথমে pytest FAILED line
    m = PYTEST_FAILED_RE.search(text)
    if m:
        return m.group("msg").strip()[:500]
    # তারপর ImportError
    m = IMPORT_ERR_RE.search(text)
    if m:
        return m.group(0).strip()[:500]
    # তারপর SyntaxError
    m = SYNTAX_ERR_RE.search(text)
    if m:
        return m.group(0).strip()[:500]
    # তারপর generic exception
    m = GENERIC_ERR_RE.search(text)
    if m:
        return f"{m.group('exc')}: {m.group('msg')}".strip()[:500]
    # fallback: প্রথম নন-empty line
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("::", "##", "Note:")):
            return line[:500]
    return "unknown error"


def _extract_stack_trace(text: str, max_lines: int = 15) -> str:
    """পাইthon traceback ব্লক extract করে।"""
    # সাধারণ traceback: "Traceback (most recent call last):" থেকে শুরু
    m = re.search(
        r"(Traceback \(most recent call last\):.*?)(?:\n\n|\Z)",
        text,
        re.DOTALL,
    )
    if m:
        lines = m.group(1).splitlines()
        return "\n".join(lines[:max_lines])
    # বিকল্প: "File ... line ... in ..." pattern-এর sequence
    matches = PYFILE_LINE_RE.findall(text)
    if matches:
        return "\n".join(f'  File "{f}", line {l}, in {fn}' for f, l, fn in matches[:max_lines])
    return ""


def _extract_lint_violations(text: str) -> list[dict]:
    """Ruff/flake8/mypy violation pattern extract করে।"""
    violations = []
    seen: set[tuple[str, int, str]] = set()
    for m in LINT_RE.finditer(text):
        key = (m.group("file"), int(m.group("line")), m.group("code"))
        if key in seen:
            continue
        seen.add(key)
        violations.append(
            {
                "type": "lint_violation",
                "test_name": "",
                "file_path": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "rule_code": m.group("code"),
                "message": m.group("msg").strip(),
                "log_excerpt": m.group(0),
            }
        )
        if len(violations) >= MAX_FAILURES_PER_JOB:
            break
    return violations


def parse_job_log(log_text: str) -> list[dict]:
    """একটি job log থেকে structured failures extract করে।

    কৌশল:
      1. Lint violation pattern (file:line:col: CODE msg) আগে খুঁজি
      2. বাকি অংশ থেকে pytest FAILED / Error / ImportError খুঁজি
      3. প্রতিটি failure-এর জন্য test_name, file_path, message, stack_trace extract করি
    """
    if not log_text:
        return []

    failures: list[dict] = []

    # Layer 1: lint violations
    failures.extend(_extract_lint_violations(log_text))
    if len(failures) >= MAX_FAILURES_PER_JOB:
        return failures[:MAX_FAILURES_PER_JOB]

    # Layer 2: pytest FAILED lines (প্রতিটির জন্য চারপাশের context নিয়ে stack trace)
    seen_test_names: set[str] = set()
    for m in PYTEST_FAILED_RE.finditer(log_text):
        test_name = m.group("test").strip()
        # শুধু একই test_name একাধিকবার extract হওয়া রোধ করি (overlap check নয়)
        if test_name in seen_test_names:
            continue
        seen_test_names.add(test_name)

        start = max(0, m.start() - 1500)
        end = min(len(log_text), m.end() + 1500)
        context = log_text[start:end]
        failures.append(
            {
                "type": "test_failure",
                "test_name": test_name,
                "file_path": _extract_file_path(context),
                "message": m.group("msg").strip()[:500],
                "stack_trace": _extract_stack_trace(context),
                "log_excerpt": context[-1000:],
            }
        )
        if len(failures) >= MAX_FAILURES_PER_JOB:
            return failures[:MAX_FAILURES_PER_JOB]

    # Layer 3: generic exceptions / import / syntax errors (যদি Layer 2 কিছু না পায়)
    if not failures:
        # ৪ KB উইন্ডোতে দেখি — বড় log-এ একাধিক error থাকতে পারে
        window = (
            log_text[-MAX_LOG_BYTES_PER_JOB:] if len(log_text) > MAX_LOG_BYTES_PER_JOB else log_text
        )
        ftype = _classify_failure(window)
        if ftype != "generic" or "Error" in window:
            failures.append(
                {
                    "type": ftype,
                    "test_name": _extract_test_name(window),
                    "file_path": _extract_file_path(window),
                    "message": _extract_message(window),
                    "stack_trace": _extract_stack_trace(window),
                    "log_excerpt": window[-1000:],
                }
            )

    return failures[:MAX_FAILURES_PER_JOB]


# --- Collector core ---------------------------------------------------------


def _fetch_pr_head_sha(repo: str, pr_number: int, token: str) -> tuple[str, list[str]]:
    """PR head SHA + changed files list fetch করে।"""
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
    status, data, _ = _gh_request(url, token)
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"PR fetch failed (status={status}): {data}")
    head_sha = data.get("head", {}).get("sha", "")
    if not head_sha:
        raise RuntimeError(f"PR {pr_number}: head sha missing")
    # changed files: আলাদা endpoint থেকে আসে
    files_url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}/files?per_page=100"
    _, files_data, _ = _gh_request(files_url, token)
    changed = []
    if isinstance(files_data, list):
        changed = [f.get("filename", "") for f in files_data if isinstance(f, dict)]
    return head_sha, changed


def _fetch_failed_runs(repo: str, head_sha: str, token: str) -> dict | None:
    """head_sha-এর জন্য সর্বশেষ failed workflow run খুঁজে আনে।"""
    encoded = urllib.parse.quote(head_sha, safe="")
    url = (
        f"{GITHUB_API_BASE}/repos/{repo}/actions/runs?head_sha={encoded}&status=failure&per_page=10"
    )
    status, data, _ = _gh_request(url, token)
    if status != 200 or not isinstance(data, dict):
        return None
    runs = data.get("workflow_runs", [])
    if not runs:
        return None
    # সবচেয়ে সাম্প্রতিক run প্রথমে থাকে — তবে created_at দিয়ে verify করি
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[0]


def _fetch_failed_jobs(repo: str, run_id: int, token: str) -> list[dict]:
    """একটি run-এর failed job তালিকা আনে।"""
    url = f"{GITHUB_API_BASE}/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    status, data, _ = _gh_request(url, token)
    if status != 200 or not isinstance(data, dict):
        return []
    jobs = data.get("jobs", [])
    return [j for j in jobs if j.get("conclusion") == "failure"]


def _fetch_job_logs(repo: str, job_id: int, token: str) -> str:
    """একটি job-এর লগ fetch করে (text/plain; শেষ ৮ KB পড়ে)."""
    url = f"{GITHUB_API_BASE}/repos/{repo}/actions/jobs/{job_id}/logs"
    status, raw, _ = _gh_request(url, token, accept="text/plain")
    if status != 200 or not isinstance(raw, bytes):
        return ""
    try:
        return raw.decode("utf-8", errors="replace")
    except (UnicodeDecodeError, AttributeError):
        return ""


def collect_failures(
    repo: str,
    pr_number: int,
    token: str,
    head_sha: str | None = None,
    changed_files: list[str] | None = None,
) -> dict:
    """PR-এর জন্য সম্পূর্ণ CI failure data সংগ্রহ করে।

    প্যারামিটার head_sha / changed_files দিলে PR fetch স্কিপ হয় (test-friendly).
    """
    if not head_sha or changed_files is None:
        head_sha, changed_files = _fetch_pr_head_sha(repo, pr_number, token)

    run = _fetch_failed_runs(repo, head_sha, token)
    if not run:
        return {
            "pr_number": pr_number,
            "head_sha": head_sha,
            "run_id": None,
            "run_url": None,
            "collected_at": datetime.now(UTC).isoformat(),
            "failed_jobs": [],
            "changed_files": changed_files,
            "summary": {
                "total_failed_jobs": 0,
                "total_failures": 0,
                "by_type": {},
            },
        }

    run_id = run.get("id")
    failed_jobs_raw = _fetch_failed_jobs(repo, run_id, token)

    failed_jobs: list[dict] = []
    by_type: dict[str, int] = {}
    total_failures = 0

    for job in failed_jobs_raw:
        job_id = job.get("id")
        job_name = job.get("name", "")
        log_text = _fetch_job_logs(repo, job_id, token)
        # লগ অনেক বড় হতে পারে — শেষ ৮ KB-তে সাধারণত failure থাকে
        log_tail = (
            log_text[-MAX_LOG_BYTES_PER_JOB:] if len(log_text) > MAX_LOG_BYTES_PER_JOB else log_text
        )
        failures = parse_job_log(log_tail)
        for f in failures:
            ftype = f.get("type", "generic")
            by_type[ftype] = by_type.get(ftype, 0) + 1
        total_failures += len(failures)
        failed_jobs.append(
            {
                "job_id": job_id,
                "name": job_name,
                "conclusion": job.get("conclusion", "failure"),
                "log_bytes": len(log_text),
                "failures": failures,
            }
        )

    return {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "run_id": run_id,
        "run_url": run.get("html_url"),
        "collected_at": datetime.now(UTC).isoformat(),
        "failed_jobs": failed_jobs,
        "changed_files": changed_files,
        "summary": {
            "total_failed_jobs": len(failed_jobs),
            "total_failures": total_failures,
            "by_type": by_type,
        },
    }


# --- CLI --------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper — CI Failure Collector (#1034)")
    parser.add_argument(
        "--repo", required=True, help="owner/repo (e.g. SaifulHaqueNiloy/supremeai)"
    )
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument(
        "--token", default=os.getenv("GH_TOKEN", ""), help="GitHub token (default: $GH_TOKEN)"
    )
    parser.add_argument("--head-sha", default="", help="Override HEAD SHA (skip PR fetch)")
    parser.add_argument("--output-json", default="ci_failures.json", help="Output JSON path")
    args = parser.parse_args()

    if not args.token:
        print("::error::GitHub token missing — set GH_TOKEN or pass --token", file=sys.stderr)
        return 2

    try:
        result = collect_failures(args.repo, args.pr, args.token, args.head_sha or None)
    except Exception as exc:
        print(f"::error::CI failure collection failed: {exc}", file=sys.stderr)
        return 1

    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("CI failure collection complete:")
    print(f"  PR: #{result['pr_number']}  head_sha: {result['head_sha'][:7]}")
    print(f"  Run: {result.get('run_id')}  ({result.get('run_url', '')})")
    print(f"  Failed jobs: {result['summary']['total_failed_jobs']}")
    print(f"  Total failures: {result['summary']['total_failures']}")
    by_type = result["summary"]["by_type"]
    if by_type:
        print(f"  By type: {by_type}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"failed_jobs_count={result['summary']['total_failed_jobs']}\n")
            f.write(f"total_failures={result['summary']['total_failures']}\n")
            f.write(f"run_id={result.get('run_id') or ''}\n")
            f.write(f"has_failures={str(result['summary']['total_failures'] > 0).lower()}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
