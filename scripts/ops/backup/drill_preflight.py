#!/usr/bin/env python3
"""Backup & restore drill preflight (Wave 0.2 — issue #1230).

docs/deployment/BACKUP_RESTORE_DRILL.md-এর নিয়ম: "A drill that has never been
restored is a rumour" — আর "A drill without written evidence did not happen".
এই harness ওই rule কে executable করে:

* drill-এর আগের সব prerequisite read-only ভাবে যাচাই করে (blocking checks);
* যে জিনিসগুলো owner drill-time-এ সেট করবে (DB URL ইত্যাদি) সেগুলো info —
  মান কখনো print/লগ হয় না, শুধু presence;
* ``--template`` দিলে তারিখ-স্ট্যাম্প করা drill-log টেমপ্লেট প্রিন্ট করে —
  ওটাই BACKUP_RESTORE_DRILL.md-র "## Drill log" section-এ append হবে;
* ``--self-test`` synthetic fixture-এর বিপরীতে harness-এর নিজের লজিক
  যাচাই করে (network-free, CI-safe)।

Stdlib-only — backup tooling-এর কোনো dependency টানে না।

Usage:
    python scripts/backup/drill_preflight.py             # preflight run
    python scripts/backup/drill_preflight.py --template  # print log template
    python scripts/backup/drill_preflight.py --self-test # verify the harness
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DRILL_DOC = Path("docs/deployment/BACKUP_RESTORE_DRILL.md")
ROLLBACK_DOC = Path("docs/deployment/ROLLBACK_PROCEDURE.md")
BACKUP_TOOL_DIR = Path("scripts/backup")
REQUIRED_DOC_MARKERS = ("Quarterly restore drill", "RTO", "## Drill log")
EXPECTED_BACKUP_TOOLS = ("superai_backup_manager.py", "auto_firestore_backup.py")
DB_URL_ENV_VARS = (
    "SUPABASE_DATABASE_URL_POOLER",
    "DATABASE_URL",
    "SUPABASE_DB_URL_POOLER",
)

BLOCKING, INFO = "blocking", "info"


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    severity: str  # BLOCKING | INFO
    ok: bool
    detail: str


# ── check implementations (pure — root injectable for self-test) ────────────


def check_drill_doc(root: Path) -> CheckResult:
    path = root / DRILL_DOC
    if not path.is_file():
        return CheckResult("drill_doc", BLOCKING, False, f"{DRILL_DOC} not found")
    text = path.read_text(encoding="utf-8")
    missing = [m for m in REQUIRED_DOC_MARKERS if m not in text]
    if missing:
        return CheckResult(
            "drill_doc", BLOCKING, False, f"{DRILL_DOC} missing markers: {missing}"
        )
    return CheckResult(
        "drill_doc",
        BLOCKING,
        True,
        f"{DRILL_DOC} present with procedure + drill-log section",
    )


def check_rollback_crossref(root: Path) -> CheckResult:
    path = root / ROLLBACK_DOC
    if path.is_file():
        return CheckResult(
            "rollback_crossref", BLOCKING, True, f"{ROLLBACK_DOC} present"
        )
    return CheckResult(
        "rollback_crossref",
        BLOCKING,
        False,
        f"{ROLLBACK_DOC} missing — migration-rollback path referenced by the drill doc",
    )


def check_backup_tools(root: Path) -> CheckResult:
    tool_dir = root / BACKUP_TOOL_DIR
    missing = [t for t in EXPECTED_BACKUP_TOOLS if not (tool_dir / t).is_file()]
    if missing:
        return CheckResult(
            "backup_tools", BLOCKING, False, f"missing backup tools: {missing}"
        )
    return CheckResult(
        "backup_tools", BLOCKING, True, f"{BACKUP_TOOL_DIR} tools present"
    )


def check_db_url_presence(root: Path) -> CheckResult:
    """Presence-only INFO check — env values are NEVER read into output."""
    configured = [name for name in DB_URL_ENV_VARS if os_getenv_nonempty(name)]
    if configured:
        return CheckResult(
            "db_url",
            INFO,
            True,
            f"DB URL env present in names={configured} (values never read)",
        )
    return CheckResult(
        "db_url",
        INFO,
        True,
        "no DB URL env in this shell — owner sets it at drill time (values never read)",
    )


def os_getenv_nonempty(name: str) -> bool:
    value = __import__("os").getenv(name, "")
    return bool(value and value.strip())


def run_checks(root: Path = REPO_ROOT) -> list[CheckResult]:
    return [
        check_drill_doc(root),
        check_rollback_crossref(root),
        check_backup_tools(root),
        check_db_url_presence(root),
    ]


# ── drill log template ───────────────────────────────────────────────────────


def render_template(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    return f"""### Drill — {stamp}

| Field | Value |
| --- | --- |
| Trigger | quarterly cadence (BACKUP_RESTORE_DRILL.md §Quarterly restore drill) |
| Freeze point (main SHA) | `<fill: git rev-parse HEAD>` |
| Infisical export timestamp | `<fill>` |
| Scratch target | `supremeai-drill-<date>` (NEVER production) |
| Snapshot restored | `<fill: Supabase backup/PITR id>` |
| Restore elapsed | `<fill>` |
| /health/ready after boot | `<fill: response or FAIL>` |
| Seeded login + chat round-trip | `<fill: PASS/FAIL>` |
| RTO | `<fill>` (target ≤ 2h) |
| RPO | `<fill>` (target ≤ 24h daily / ≤ 5min PITR) |
| Schema drift noted | `<fill: none or list>` |

**Verdict:** `<PASS / PASS-with-notes / FAIL — follow-up issue(s)>`
"""


# ── self-test (harness logic against synthetic fixtures) ─────────────────────


def self_test() -> int:
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1. empty tree → both blocking doc checks fail
        results = {r.check_id: r for r in run_checks(root)}
        if results["drill_doc"].ok:
            failures.append("empty tree: drill_doc must fail")
        if results["rollback_crossref"].ok:
            failures.append("empty tree: rollback_crossref must fail")
        if results["backup_tools"].ok:
            failures.append("empty tree: backup_tools must fail")

        # 2. doc present but missing the drill-log marker → fail
        (root / DRILL_DOC).parent.mkdir(parents=True, exist_ok=True)
        (root / DRILL_DOC).write_text(
            "Quarterly restore drill — RTO targets only (no log section)",
            encoding="utf-8",
        )
        if check_drill_doc(root).ok:
            failures.append("doc without '## Drill log' must fail")

        # 3. full fixture → blocking checks green; template renders dated
        (root / DRILL_DOC).write_text(
            "# Drill\n\nQuarterly restore drill\n\nRTO\n\n## Drill log\n",
            encoding="utf-8",
        )
        (root / ROLLBACK_DOC).parent.mkdir(parents=True, exist_ok=True)
        (root / ROLLBACK_DOC).write_text("# Rollback\n", encoding="utf-8")
        (root / BACKUP_TOOL_DIR).mkdir(parents=True, exist_ok=True)
        for tool in EXPECTED_BACKUP_TOOLS:
            (root / BACKUP_TOOL_DIR / tool).write_text("# tool\n", encoding="utf-8")

        results = {r.check_id: r for r in run_checks(root)}
        for check_id in ("drill_doc", "rollback_crossref", "backup_tools"):
            if not results[check_id].ok:
                failures.append(f"full fixture: {check_id} must pass")
        if "db_url" not in results:
            failures.append("db_url info check must always run")

        template = render_template(datetime(2026, 9, 25, tzinfo=UTC))
        if "Drill — 2026-09-25" not in template or "RTO" not in template:
            failures.append("template must render the fixed date + RTO/RPO fields")

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELF-TEST PASSED — harness logic verified against synthetic fixtures")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--template", action="store_true", help="print a dated drill-log template"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="verify harness logic (CI-safe)"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if args.template:
        print(render_template())
        return 0

    results = run_checks()
    blocking_failed = False
    print("Backup & restore drill preflight (Wave 0.2, issue #1230)")
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] ({r.severity}) {r.check_id}: {r.detail}")
        if r.severity == BLOCKING and not r.ok:
            blocking_failed = True

    if blocking_failed:
        print("PREFLIGHT FAILED — fix the blocking checks before running the drill.")
        return 1
    print(
        "PREFLIGHT OK — procedure prerequisites present. Execute the drill per "
        "docs/deployment/BACKUP_RESTORE_DRILL.md and append the --template log with evidence."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
