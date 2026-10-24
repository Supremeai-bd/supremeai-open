#!/usr/bin/env python3
"""Rollback rehearsal preflight (Wave 0.6 — issue #1232).

docs/deployment/ROLLBACK_PROCEDURE.md বলে: rollback path গুলো verified — কিন্তু
rehearsal কখনো হয়নি, আর rehearsal-এর কোনো executable prerequisite gate বা
মানসম্মত evidence log নেই। এই harness ওই ঘাটতি পূরণ করে (backup drill-এর
preflight-এর সাথে জোড়া লাগানো প্যাটার্ন — issue #1230):

* rehearsal-এর আগে rollback path-এর সব repo-level prerequisite read-only যাচাই
  (procedure doc, trigger tooling, deploy workflow, post-mortem target);
* Render API key presence শুধু INFO — মান কখনো output-এ আসে না;
* ``--template`` তারিখ-স্ট্যাম্প করা rehearsal evidence log প্রিন্ট করে —
  ওটাই ROLLBACK_PROCEDURE.md-র "## Rehearsal log"-এ append হবে;
* ``--self-test`` synthetic fixture-এ হার্নেসের নিজের লজিক যাচাই করে
  (network-free, CI-safe)।

Rehearsal execution নিজে owner-side (non-production Render service লাগবে)।

Usage:
    python scripts/deploy/rollback_rehearsal_preflight.py             # preflight
    python scripts/deploy/rollback_rehearsal_preflight.py --template  # log template
    python scripts/deploy/rollback_rehearsal_preflight.py --self-test # verify harness
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

ROLLBACK_DOC = Path("docs/deployment/ROLLBACK_PROCEDURE.md")
DRILL_DOC = Path("docs/deployment/BACKUP_RESTORE_DRILL.md")
TRIGGER_TOOL = Path("scripts/ci/render_trigger_deploy.py")
RENDER_TOOLS = (
    Path("scripts/deploy/check_render.py"),
    Path("scripts/deploy/disaster_recovery_test.py"),
)
DEPLOY_WORKFLOW = Path(".github/workflows/ci-deploy-production.yml")
POSTMORTEM_DIR = Path("docs/audits")
REQUIRED_DOC_MARKERS = (
    "Trigger criteria",
    "/health/ready",
    "After every rollback",
)
REHEARSAL_LOG_MARKER = "## Rehearsal log"

BLOCKING, INFO = "blocking", "info"


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    severity: str
    ok: bool
    detail: str


# ── check implementations (pure — root injectable for self-test) ────────────


def check_procedure_doc(root: Path) -> CheckResult:
    path = root / ROLLBACK_DOC
    if not path.is_file():
        return CheckResult(
            "procedure_doc", BLOCKING, False, f"{ROLLBACK_DOC} not found"
        )
    text = path.read_text(encoding="utf-8")
    missing = [
        m for m in (*REQUIRED_DOC_MARKERS, REHEARSAL_LOG_MARKER) if m not in text
    ]
    if missing:
        return CheckResult(
            "procedure_doc",
            BLOCKING,
            False,
            f"{ROLLBACK_DOC} missing markers: {missing}",
        )
    return CheckResult(
        "procedure_doc",
        BLOCKING,
        True,
        f"{ROLLBACK_DOC} present with triggers, canonical probes, rehearsal log",
    )


def check_drill_crossref(root: Path) -> CheckResult:
    path = root / DRILL_DOC
    if path.is_file():
        return CheckResult(
            "drill_crossref",
            BLOCKING,
            True,
            f"{DRILL_DOC} present — DB-rollback path resolvable",
        )
    return CheckResult(
        "drill_crossref",
        BLOCKING,
        False,
        f"{DRILL_DOC} missing — migration-rollback step points at it",
    )


def check_trigger_tooling(root: Path) -> CheckResult:
    missing = [
        str(p) for p in (TRIGGER_TOOL, *RENDER_TOOLS) if not (root / p).is_file()
    ]
    if missing:
        return CheckResult(
            "trigger_tooling", BLOCKING, False, f"missing tools: {missing}"
        )
    return CheckResult(
        "trigger_tooling", BLOCKING, True, "render trigger + check + DR tooling present"
    )


def check_deploy_workflow(root: Path) -> CheckResult:
    path = root / DEPLOY_WORKFLOW
    if path.is_file():
        return CheckResult(
            "deploy_workflow", BLOCKING, True, f"{DEPLOY_WORKFLOW} present"
        )
    return CheckResult(
        "deploy_workflow",
        BLOCKING,
        False,
        f"{DEPLOY_WORKFLOW} missing — last-known-good rebuild path unresolvable",
    )


def check_postmortem_target(root: Path) -> CheckResult:
    path = root / POSTMORTEM_DIR
    if path.is_dir():
        return CheckResult(
            "postmortem_target",
            BLOCKING,
            True,
            f"{POSTMORTEM_DIR}/ present — mandatory post-rollback note target",
        )
    return CheckResult(
        "postmortem_target",
        BLOCKING,
        False,
        f"{POSTMORTEM_DIR}/ missing — post-mortem convention target unresolvable",
    )


def check_render_api_key(root: Path) -> CheckResult:
    import os

    configured = bool((os.getenv("RENDER_API_KEY", "") or "").strip())
    return CheckResult(
        "render_api_key",
        INFO,
        True,
        "RENDER_API_KEY present in env (value never read)"
        if configured
        else "RENDER_API_KEY not in this shell — owner provides at rehearsal time",
    )


def run_checks(root: Path = REPO_ROOT) -> list[CheckResult]:
    return [
        check_procedure_doc(root),
        check_drill_crossref(root),
        check_trigger_tooling(root),
        check_deploy_workflow(root),
        check_postmortem_target(root),
        check_render_api_key(root),
    ]


# ── rehearsal evidence log template ──────────────────────────────────────────


def render_template(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    return f"""### Rehearsal — {stamp}

| Field | Value |
| --- | --- |
| Scope | backend service rollback on a NON-PRODUCTION Render service |
| Trigger simulated | `<fill: /health/ready 503 window / error-rate / broken shell>` |
| Last-known-good SHA | `<fill: git rev-parse <sha>>` |
| Bad SHA deployed | `<fill>` |
| Redeploy trigger | `<fill: render_trigger_deploy / dashboard>` |
| Detection lag | `<fill>` |
| Rollback lag (decision → /health/ready green) | `<fill>` |
| Canonical probes after rollback | `<fill: /health/live + /health/ready outputs>` |
| Post-mortem note | `<fill: docs/audits/<file>.md>` |

**Verdict:** `<PASS / PASS-with-notes / FAIL — follow-up issue(s)>`
"""


# ── self-test ────────────────────────────────────────────────────────────────


def self_test() -> int:
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1. empty tree → every blocking check fails
        for r in run_checks(root):
            if r.severity == BLOCKING and r.ok:
                failures.append(f"empty tree: {r.check_id} must fail")

        # 2. doc without rehearsal-log marker → fail
        (root / ROLLBACK_DOC).parent.mkdir(parents=True, exist_ok=True)
        (root / ROLLBACK_DOC).write_text(
            "Trigger criteria\n/health/ready\nAfter every rollback (no log section)",
            encoding="utf-8",
        )
        if check_procedure_doc(root).ok:
            failures.append("doc without '## Rehearsal log' must fail")

        # 3. full fixture → blocking checks green
        (root / ROLLBACK_DOC).write_text(
            "# Rollback\nTrigger criteria\n/health/ready\nAfter every rollback\n"
            f"{REHEARSAL_LOG_MARKER}\n",
            encoding="utf-8",
        )
        (root / DRILL_DOC).write_text("# Drill\n", encoding="utf-8")
        (root / TRIGGER_TOOL).parent.mkdir(parents=True, exist_ok=True)
        (root / TRIGGER_TOOL).write_text("# tool\n", encoding="utf-8")
        for tool in RENDER_TOOLS:
            (root / tool).parent.mkdir(parents=True, exist_ok=True)
            (root / tool).write_text("# tool\n", encoding="utf-8")
        (root / DEPLOY_WORKFLOW).parent.mkdir(parents=True, exist_ok=True)
        (root / DEPLOY_WORKFLOW).write_text(
            "name: ci-deploy-production\n", encoding="utf-8"
        )
        (root / POSTMORTEM_DIR).mkdir(parents=True, exist_ok=True)

        results = {r.check_id: r for r in run_checks(root)}
        for check_id in (
            "procedure_doc",
            "drill_crossref",
            "trigger_tooling",
            "deploy_workflow",
            "postmortem_target",
        ):
            if not results[check_id].ok:
                failures.append(f"full fixture: {check_id} must pass")

        template = render_template(datetime(2026, 9, 25, tzinfo=UTC))
        if "Rehearsal — 2026-09-25" not in template or "Rollback lag" not in template:
            failures.append("template must render the fixed date + lag fields")

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
        "--template", action="store_true", help="print a dated rehearsal-log template"
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
    print("Rollback rehearsal preflight (Wave 0.6, issue #1232)")
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"  [{mark}] ({r.severity}) {r.check_id}: {r.detail}")
        if r.severity == BLOCKING and not r.ok:
            blocking_failed = True

    if blocking_failed:
        print("PREFLIGHT FAILED — fix the blocking checks before the rehearsal.")
        return 1
    print(
        "PREFLIGHT OK — rollback path prerequisites present. Execute the rehearsal per "
        "docs/deployment/ROLLBACK_PROCEDURE.md on a NON-PRODUCTION service and append "
        "the --template log with evidence."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
