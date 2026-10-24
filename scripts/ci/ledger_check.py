#!/usr/bin/env python3
"""Task Outcome Ledger Validator (#4271 Phase 0 — roadmap 7.6 → 9.0).

বাংলা সারসংক্ষেপ:
  স্কোরকার্ড বলেছিল — "agent নিজে কাজ শেষ বললেই সেটি সফল নয়"। এই ledger
  প্রতিটি কাজের issue → agent → commit → tests → PR → deployment → runtime →
  independent verifier → outcome একটি append-only রেকর্ডে বাঁধে। Validator
  fail-closed: schema ভাঙলে, enum ভাঙলে, SHA/URL ভাঙলে, verifier-independence
  ভাঙলে, বা historical line delete/modify হলে exit 1 — কখনো exit 0 নয়।

Schema (docs/ledger/task-outcomes.jsonl — one JSON object per line):
  task_id              T-NNNN, unique, required
  date                 ISO-8601 date, required
  issue_url            github issues URL, required
  agent                implementing identity, required (non-empty)
  pr_url               github pull URL, required
  merge_sha            40-hex full SHA, required
  test_evidence        suites + counts + run URL, required non-empty
  deployment           {station, sha, at} | null
  runtime_verification string | null
  verifier             {identity, verdict, at} | null — identity MUST differ
                       from agent (independent verification law)
  outcome              SUCCESS | SUCCESS_WITH_RETRIES | FAILED | REVERTED
  first_pass           true | false | null (null only when backfilled + note)
  cost                 {ci_minutes, agent_rounds, wall_clock} | null
  backfilled           bool, required
  notes                string, optional

Usage:
  python scripts/ci/ledger_check.py                          # schema only
  python scripts/ci/ledger_check.py --base origin/main       # + append-only
  python scripts/ci/ledger_check.py --stats                  # evidence summary

Exit codes: 0 = ledger sound; 1 = violations (fail-closed); 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date as _date
from pathlib import Path

LEDGER_PATH = "docs/ledger/task-outcomes.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[2]

OUTCOME_ENUM = {"SUCCESS", "SUCCESS_WITH_RETRIES", "FAILED", "REVERTED"}
TASK_ID_RE = re.compile(r"^T-\d{4}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GITHUB_ISSUE_RE = re.compile(
    r"^https://github\.com/(SaifulHaqueNiloy|paykaribazaronline)/supremeai/issues/\d+$"
)
GITHUB_PULL_RE = re.compile(
    r"^https://github\.com/(SaifulHaqueNiloy|paykaribazaronline)/supremeai/pull/\d+$"
)

REQUIRED_STR_FIELDS = (
    "task_id",
    "date",
    "issue_url",
    "agent",
    "pr_url",
    "merge_sha",
    "test_evidence",
)


class Violations:
    """Collector — keeps going after the first defect so one red run shows all."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, msg: str) -> None:
        self.items.append(msg)

    @property
    def ok(self) -> bool:
        return not self.items


def _validate_record(rec: dict, lineno: int, seen_ids: set[str], v: Violations) -> None:
    where = f"line {lineno}"

    for field in REQUIRED_STR_FIELDS:
        val = rec.get(field)
        if not isinstance(val, str) or not val.strip():
            v.add(f"{where}: required field '{field}' missing/empty")
            return  # format checks below need the strings

    task_id = rec["task_id"]
    if not TASK_ID_RE.match(task_id):
        v.add(f"{where}: task_id '{task_id}' must match T-NNNN")
    if task_id in seen_ids:
        v.add(f"{where}: duplicate task_id '{task_id}'")
    seen_ids.add(task_id)

    if not ISO_DATE_RE.match(rec["date"]):
        v.add(f"{where}: date '{rec['date']}' must be YYYY-MM-DD")
    else:
        try:
            _date.fromisoformat(rec["date"])
        except ValueError:
            v.add(f"{where}: date '{rec['date']}' is not a real calendar date")

    if not GITHUB_ISSUE_RE.match(rec["issue_url"]):
        v.add(f"{where}: issue_url must be a supremeai issues URL")
    if not GITHUB_PULL_RE.match(rec["pr_url"]):
        v.add(f"{where}: pr_url must be a supremeai pull URL")
    if not SHA40_RE.match(rec["merge_sha"]):
        v.add(f"{where}: merge_sha must be a full 40-hex SHA")

    if rec.get("outcome") not in OUTCOME_ENUM:
        v.add(f"{where}: outcome must be one of {sorted(OUTCOME_ENUM)}")

    fp = rec.get("first_pass", "MISSING")
    if fp == "MISSING":
        v.add(f"{where}: 'first_pass' required (true/false/null)")
    elif fp is None:
        if not rec.get("backfilled"):
            v.add(f"{where}: first_pass null allowed only for backfilled records")
        elif not (rec.get("notes") or "").strip():
            v.add(
                f"{where}: first_pass null on a backfilled record requires "
                "an explanatory note"
            )
    elif not isinstance(fp, bool):
        v.add(f"{where}: first_pass must be true/false/null, got {fp!r}")

    if not isinstance(rec.get("backfilled"), bool):
        v.add(f"{where}: 'backfilled' must be a bool")

    verifier = rec.get("verifier")
    if verifier is not None:
        if not isinstance(verifier, dict):
            v.add(f"{where}: verifier must be an object or null")
        else:
            vid = verifier.get("identity")
            if not isinstance(vid, str) or not vid.strip():
                v.add(f"{where}: verifier.identity required when verifier present")
            elif vid == rec["agent"]:
                v.add(
                    f"{where}: verifier-independence violated — verifier "
                    f"'{vid}' == implementing agent '{rec['agent']}' "
                    "(no self-verification, ever)"
                )
            if not (verifier.get("verdict") or "").strip():
                v.add(f"{where}: verifier.verdict required when verifier present")
            vat = verifier.get("at")
            if not isinstance(vat, str) or not ISO_DATE_RE.match(vat):
                v.add(f"{where}: verifier.at must be YYYY-MM-DD")

    deployment = rec.get("deployment")
    if deployment is not None:
        if not isinstance(deployment, dict):
            v.add(f"{where}: deployment must be an object or null")
        else:
            for key in ("station", "sha", "at"):
                if not str(deployment.get(key) or "").strip():
                    v.add(f"{where}: deployment.{key} required when deployment present")
            dsha = str(deployment.get("sha") or "")
            if dsha and not (SHA40_RE.match(dsha) or re.match(r"^[0-9a-f]{7,40}$", dsha)):
                v.add(f"{where}: deployment.sha must be a git SHA")


def check_append_only(old_lines: list[str], new_lines: list[str], v: Violations) -> None:
    """Append-only law: every historical line must survive byte-identical.

    Deletion OR modification of an existing line is a violation — the ledger
    records evidence; rewriting evidence is fabrication (roadmap Section 1).
    """
    old_set = set(line.strip() for line in old_lines if line.strip())
    new_set = set(line.strip() for line in new_lines if line.strip())
    for line in sorted(old_set - new_set):
        v.add(f"append-only violated — historical line removed/modified: {line[:120]}...")


def _git_lines(base_ref: str) -> list[str]:
    """Old ledger content from git, or [] if the file did not exist at base."""
    try:
        res = subprocess.run(
            ["git", "show", f"{base_ref}:{LEDGER_PATH}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=True,
        )
        return res.stdout.splitlines()
    except subprocess.CalledProcessError:
        return []  # bootstrap PR: nothing at base yet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--file", default=LEDGER_PATH, help=f"ledger path (default {LEDGER_PATH})"
    )
    parser.add_argument(
        "--base",
        default=None,
        help="git ref to enforce append-only against (e.g. origin/main)",
    )
    parser.add_argument("--stats", action="store_true", help="print evidence summary")
    args = parser.parse_args(argv)

    ledger_file = REPO_ROOT / args.file
    if not ledger_file.exists():
        print(f"::error::ledger file missing: {args.file}")
        return 1
    text = ledger_file.read_text(encoding="utf-8")

    v = Violations()
    seen_ids: set[str] = set()
    records: list[dict] = []
    new_lines = text.splitlines()

    parsed = []
    for i, raw in enumerate(new_lines, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
            if not isinstance(rec, dict):
                raise ValueError("not a JSON object")
            parsed.append(rec)
            records.append(rec)
        except (json.JSONDecodeError, ValueError) as exc:
            v.add(f"line {i}: invalid JSONL ({exc})")

    for lineno, rec in enumerate(records, start=1):
        _validate_record(rec, lineno, seen_ids, v)

    if args.base:
        old_lines = _git_lines(args.base)
        check_append_only(old_lines, new_lines, v)

    if args.stats:
        total = len(records)
        verified = sum(1 for r in records if r.get("verifier"))
        first_pass = sum(1 for r in records if r.get("first_pass") is True)
        outcomes: dict[str, int] = {}
        for r in records:
            outcomes[r.get("outcome", "?")] = outcomes.get(r.get("outcome", "?"), 0) + 1
        print(f"ledger stats: records={total} verifier-signed={verified} "
              f"({verified * 100 // total if total else 0}%) first_pass={first_pass}")
        print(f"outcomes: {json.dumps(outcomes, sort_keys=True)}")

    if not v.ok:
        for item in v.items:
            print(f"::error::ledger_check: {item}")
        print(f"ledger_check: {len(v.items)} violation(s) — FAIL-CLOSED")
        return 1

    print(f"ledger_check: OK ({len(records)} records, append-only "
          f"{'enforced vs ' + args.base if args.base else 'schema-only mode'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
