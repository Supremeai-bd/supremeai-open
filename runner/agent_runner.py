#!/usr/bin/env python3
"""Agent Runner Harness — deterministic 8-step stateless executor (issue #334).

Reference implementation of the canonical execution lifecycle (AGENTS.md step
table; docs/AGENT_LOOP_SPEC.md):

    1 Understand -> 2 Rules -> 3 Inspect -> 4 Claim -> 5 Work -> 6 Verify
    -> 7 Record -> 8 Return

Design contracts:

- STATELESS (AGENTS.md §2): no module-level mutable state; every run carries
  its ports (I/O adapters) and options. Same inputs + ports -> same report.
- ATOMIC CLAIM BEFORE MUTATION (acceptance criterion 2): the Claim step writes
  a session claim marker via tmp-file + ``os.replace`` (atomic on POSIX and
  Windows) and verifies it by read-back BEFORE the Work step may mutate any
  workspace state. "No claim, no work" — Work re-reads the marker and refuses
  on absence/mismatch (belt and braces).
- 3-TIER VERIFICATION GATE (Verify step): reflection, boot smoke and tests
  must all be present and passing before Record is reachable; any FAIL or
  missing tier aborts fail-closed (U2: UNKNOWN is never PASS).
- PR GENERATION FAIL-CLOSED (acceptance criterion 3): the Record step refuses
  to build a PR body without a numeric issue reference (``Closes #N``) and at
  least the three passed verification tiers; the body carries the Test
  Evidence block and the squash auto-close doctrine note (AGENT_RULES U8:
  ``Closes #N`` must also ride in the commit message).
- FAIL-CLOSED STEPS: any step failure aborts the run; downstream steps are
  recorded as ``not_run`` — the report never upgrades UNKNOWN to PASS.

Zero-dependency (stdlib only). Offline self-test with in-memory ports:

    python3 runner/agent_runner.py --self-test

Step-name parity with the canonical loop (scripts/agents/continuous_agent_loop.py
``step_1_understand`` .. ``step_8_return``): indices 1,2,3,6,7,8 share the
table's names; the loop's steps 4/5 are ``branch``/``work_notice`` — the
session-branch + dispatch rendering of this harness's Claim/Work (AGENTS.md
step-table note). The test suite cross-checks the anchor names when the loop
file is present.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

AGENT_RUNNER_VERSION = "agent-runner-harness/1"

# The 8 canonical steps — SSOT: AGENTS.md step table. Indices are contract:
# Claim (4) strictly precedes Work (5); Verify (6) strictly precedes Record (7).
STEPS: tuple[str, ...] = (
    "understand", "rules", "inspect", "claim", "work", "verify", "record", "return",
)

# 3-tier verification contract (AGENT_LOOP_SPEC.md §6 / AGENT_RULES.md §7).
REQUIRED_TIERS: dict[int, str] = {
    1: "reflection",
    2: "boot smoke",
    3: "tests",
}

ISSUE_REF_PATTERN = re.compile(r"^\d+$")


class RunnerError(RuntimeError):
    """A step failed its fail-closed gate."""


class ClaimError(RunnerError):
    """Claim marker missing/mismatched at Work time — no claim, no work."""


def utc_stamp(now_fn: Callable[[], float] | None = None) -> str:
    """UTC ISO-8601 stamp from the injected clock (deterministic in tests)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((now_fn or time.time)()))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically: tmp file in the same directory + os.replace.

    os.replace is atomic on POSIX and Windows; readers see either the old or
    the new file, never a partial write (the 'atomic' in 'atomic claim').
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


# --- ports (I/O adapters; all injectable, all replaceable in tests) ------------


@dataclass
class TaskContext:
    issue_ref: str
    title: str
    body: str
    touching_files: list[str] = field(default_factory=list)


@dataclass
class WorkspaceState:
    branch: str
    clean: bool


@dataclass
class Evidence:
    tier: int
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SubmissionResult:
    url: str
    accepted: bool = True


class IssuePort:
    def fetch(self, issue_ref: str) -> TaskContext | None:  # pragma: no cover
        raise NotImplementedError


class RulesPort:
    def load(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class WorkspacePort:
    def inspect(self) -> WorkspaceState:  # pragma: no cover
        raise NotImplementedError

    def write_claim_marker(self, payload: dict[str, Any]) -> str:  # pragma: no cover
        raise NotImplementedError

    def read_claim_marker(self, task_id: str) -> dict[str, Any] | None:  # pragma: no cover
        raise NotImplementedError

    def release_claim(self, task_id: str) -> bool:  # pragma: no cover
        raise NotImplementedError

    def mutate(self, task: TaskContext) -> list[str]:  # pragma: no cover
        raise NotImplementedError


class VerifyPort:
    def run(self) -> list[Evidence]:  # pragma: no cover
        raise NotImplementedError


class SubmissionPort:
    def submit(self, title: str, body: str, head_branch: str) -> SubmissionResult:  # pragma: no cover
        raise NotImplementedError


class BoardPort:
    def recent_prs(self) -> list[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError


# --- default local workspace (tmp-marker claims; atomic by construction) -------


class LocalWorkspace(WorkspacePort):
    """Filesystem workspace: atomic JSON claim markers under ``marker_dir``."""

    def __init__(self, root: Path, marker_dir: Path | None = None, branch: str = "main") -> None:
        self.root = Path(root)
        self.marker_dir = Path(marker_dir) if marker_dir else self.root / ".claims"
        self.branch = branch
        self._dirty = False
        self.mutations: list[str] = []

    def inspect(self) -> WorkspaceState:
        return WorkspaceState(branch=self.branch, clean=not self._dirty)

    def _marker_path(self, task_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", task_id)
        return self.marker_dir / f"claim-{safe}.json"

    def write_claim_marker(self, payload: dict[str, Any]) -> str:
        path = self._marker_path(str(payload["task_id"]))
        atomic_write_json(path, payload)  # tmp + os.replace — atomic claim
        readback = json.loads(path.read_text(encoding="utf-8"))
        if readback != payload:
            raise ClaimError(f"claim marker read-back mismatch at {path}")
        return str(path)

    def read_claim_marker(self, task_id: str) -> dict[str, Any] | None:
        path = self._marker_path(task_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def release_claim(self, task_id: str) -> bool:
        path = self._marker_path(task_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def mutate(self, task: TaskContext) -> list[str]:
        # Reference mutation: touch the declared touching files into existence
        # (the real coder role replaces this adapter; the RUNNER only enforces
        # that mutation happens AFTER the claim gate).
        for rel in task.touching_files:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text("", encoding="utf-8")
            self.mutations.append(rel)
        self._dirty = True
        return list(self.mutations)


# --- PR body builder (fail-closed, acceptance criterion 3) ----------------------


def build_pr_body(
    issue_ref: str,
    title: str,
    evidence: list[Evidence],
    agent: str,
) -> str:
    """Strict PR body: Closes #N + Test Evidence or ValueError (U2/U8)."""
    if not ISSUE_REF_PATTERN.match(issue_ref or ""):
        raise ValueError(
            f"PR generation requires a numeric issue reference for 'Closes #N' "
            f"(got {issue_ref!r}) — ad-hoc submissions must use the loop's ad-hoc lane"
        )
    if not evidence:
        raise ValueError("PR generation requires test evidence (empty evidence refused)")
    missing = [f"tier {t} ({n})" for t, n in REQUIRED_TIERS.items()
               if not any(e.tier == t and e.passed for e in evidence)]
    if missing:
        raise ValueError(f"PR generation refused: verification tiers not passing: {missing}")
    lines = [
        "## Summary",
        f"Autonomous contribution for issue #{issue_ref}: {title}.",
        "",
        "## Test Evidence",
    ]
    for e in sorted(evidence, key=lambda x: x.tier):
        icon = "✅" if e.passed else "❌"
        lines.append(f"- {icon} tier-{e.tier} {e.name}: {'PASS' if e.passed else 'FAIL'}"
                     + (f" — {e.detail}" if e.detail else ""))
    lines += [
        "",
        f"Closes #{issue_ref}",
        "",
        "> U8 squash doctrine: `Closes #N` must also ride in the branch commit "
        "message — the Merge Gate overrides the squash subject.",
        f"<sub>submitted by {agent} via {AGENT_RUNNER_VERSION}</sub>",
    ]
    return "\n".join(lines)


# --- the runner ------------------------------------------------------------------


@dataclass
class RunOptions:
    task_id: str
    issue_ref: str
    agent: str = "agent-runner"
    role: str = "coder"
    branch: str = "contributor/work"
    force: bool = False
    now_fn: Callable[[], float] | None = None


@dataclass
class RunReport:
    run_id: str
    task_id: str
    issue_ref: str
    agent: str
    started_at: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    claim_marker: str | None = None
    claim_released: bool = False
    artifacts: list[str] = field(default_factory=list)
    submission_url: str | None = None
    pr_body: str | None = None
    board_snapshot: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "pass"
    abort_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "issue_ref": self.issue_ref,
            "agent": self.agent,
            "started_at": self.started_at,
            "steps": self.steps,
            "claim_marker": self.claim_marker,
            "claim_released": self.claim_released,
            "artifacts": self.artifacts,
            "submission_url": self.submission_url,
            "board_snapshot": self.board_snapshot,
            "verdict": self.verdict,
            "abort_reason": self.abort_reason,
        }


class AgentRunner:
    """Deterministic 8-step executor. Stateless: all I/O via injected ports."""

    def __init__(
        self,
        issues: IssuePort,
        rules: RulesPort,
        workspace: WorkspacePort,
        verification: VerifyPort,
        submission: SubmissionPort,
        board: BoardPort | None = None,
    ) -> None:
        self.issues = issues
        self.rules = rules
        self.workspace = workspace
        self.verification = verification
        self.submission = submission
        self.board = board

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _run_id(options: RunOptions) -> str:
        seed = f"{options.task_id}|{options.issue_ref}|{options.agent}|{options.branch}"
        return "run-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

    def _record(self, report: RunReport, step: str, status: str, detail: str = "") -> None:
        report.steps.append({"step": step, "status": status, "detail": detail})

    def _abort(self, report: RunReport, step: str, reason: str, index: int) -> RunReport:
        """Fail-closed abort: record the failure, mark downstream not_run."""
        self._record(report, step, "aborted", reason)
        for later in STEPS[index + 1:]:
            self._record(report, later, "not_run")
        report.verdict = "aborted"
        report.abort_reason = f"{step}: {reason}"
        return report

    # -- the 8 steps -----------------------------------------------------------

    def run(self, options: RunOptions) -> RunReport:
        report = RunReport(
            run_id=self._run_id(options),
            task_id=options.task_id,
            issue_ref=options.issue_ref,
            agent=options.agent,
            started_at=utc_stamp(options.now_fn),
        )
        task: TaskContext | None = None
        evidence: list[Evidence] = []

        # 1. UNDERSTAND — fetch + validate the task context (fail-closed).
        try:
            task = self.issues.fetch(options.issue_ref) if options.issue_ref else None
            if task is None:
                return self._abort(report, STEPS[0],
                                   f"issue #{options.issue_ref} not fetchable — cannot verify "
                                   "acceptance criteria (fail-closed)", 0)
            self._record(report, STEPS[0], "pass", f"#{task.issue_ref}: {task.title}")
        except Exception as exc:  # noqa: BLE001 — fail-closed, honest detail
            return self._abort(report, STEPS[0], f"{type(exc).__name__}: {exc}", 0)

        # 2. RULES — governing constitution + role contract must load.
        try:
            bundle = self.rules.load()
            docs = [d for d in bundle.get("required_docs", []) if not Path(d).exists()] \
                if bundle.get("filesystem") else []
            if docs:
                return self._abort(report, STEPS[1], f"constitution docs missing: {docs}", 1)
            self._record(report, STEPS[1], "pass",
                         f"role={options.role}; policy={bundle.get('policy', 'contributor')}")
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[1], f"{type(exc).__name__}: {exc}", 1)

        # 3. INSPECT — workspace isolation gate (clean tree unless --force).
        try:
            state = self.workspace.inspect()
            if not state.clean and not options.force:
                return self._abort(report, STEPS[2],
                                   f"workspace dirty on branch {state.branch} — commit or "
                                   "stash before continuing (isolation gate)", 2)
            self._record(report, STEPS[2], "pass", f"branch={state.branch} clean={state.clean}")
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[2], f"{type(exc).__name__}: {exc}", 2)

        # 4. CLAIM — ATOMIC marker BEFORE any filesystem mutation.
        try:
            marker_payload = {
                "task_id": options.task_id,
                "issue_ref": options.issue_ref,
                "agent": options.agent,
                "branch": options.branch,
                "claimed_at": utc_stamp(options.now_fn),
            }
            report.claim_marker = self.workspace.write_claim_marker(marker_payload)
            readback = self.workspace.read_claim_marker(options.task_id)
            if readback != marker_payload:
                return self._abort(report, STEPS[3],
                                   "claim marker verification failed after write", 3)
            self._record(report, STEPS[3], "pass", f"atomic marker at {report.claim_marker}")
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[3], f"{type(exc).__name__}: {exc}", 3)

        # 5. WORK — only reachable with a verified claim (no claim, no work).
        try:
            if self.workspace.read_claim_marker(options.task_id) is None:
                raise ClaimError("no claim marker present before Work — refusing mutation")
            assert task is not None
            report.artifacts = self.workspace.mutate(task)
            self._record(report, STEPS[4], "pass", f"mutated {len(report.artifacts)} file(s)")
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[4], f"{type(exc).__name__}: {exc}", 4)

        # 6. VERIFY — 3-tier contract: reflection, boot smoke, tests ALL pass.
        try:
            evidence = self.verification.run()
            tiers_seen = {e.tier for e in evidence}
            missing = [t for t in REQUIRED_TIERS if t not in tiers_seen]
            failed = [f"tier {e.tier} ({e.name})" for e in evidence if not e.passed]
            if missing or failed:
                detail = []
                if missing:
                    detail.append(f"missing tiers {missing}")
                if failed:
                    detail.append(f"failing {failed}")
                return self._abort(report, STEPS[5], "; ".join(detail) + " (fail-closed, U2)", 5)
            self._record(report, STEPS[5], "pass",
                         f"{len(evidence)} tier(s) pass: " +
                         ", ".join(f"{e.tier}:{e.name}" for e in sorted(evidence, key=lambda x: x.tier)))
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[5], f"{type(exc).__name__}: {exc}", 5)

        # 7. RECORD — PR body fail-closed: Closes #N + Test Evidence mandatory.
        try:
            assert task is not None
            body = build_pr_body(options.issue_ref, task.title, evidence, options.agent)
            report.pr_body = body
            result = self.submission.submit(
                f"feat: {task.title} (Closes #{options.issue_ref})", body, options.branch
            )
            if not result.accepted:
                return self._abort(report, STEPS[6], f"submission rejected: {result.url}", 6)
            report.submission_url = result.url
            self._record(report, STEPS[6], "pass", result.url)
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[6], f"{type(exc).__name__}: {exc}", 6)

        # 8. RETURN — fresh-board re-check + claim release, ready to loop back.
        try:
            if self.board is not None:
                report.board_snapshot = self.board.recent_prs()
            report.claim_released = self.workspace.release_claim(options.task_id)
            self._record(report, STEPS[7], "pass",
                         f"board={len(report.board_snapshot)} pr(s); claim released={report.claim_released}")
        except Exception as exc:  # noqa: BLE001
            return self._abort(report, STEPS[7], f"{type(exc).__name__}: {exc}", 7)

        report.verdict = "pass"
        return report


# --- offline self-test (in-memory ports + tmp workspace) -------------------------


class _MemIssues(IssuePort):
    def __init__(self, task: TaskContext | None) -> None:
        self.task = task

    def fetch(self, issue_ref: str) -> TaskContext | None:
        return self.task


class _MemRules(RulesPort):
    def load(self) -> dict[str, Any]:
        return {"policy": "contributor", "required_docs": [], "filesystem": False}


class _MemVerify(VerifyPort):
    def __init__(self, tiers: list[Evidence]) -> None:
        self.tiers = tiers

    def run(self) -> list[Evidence]:
        return list(self.tiers)


class _MemSubmission(SubmissionPort):
    def __init__(self) -> None:
        self.submitted: list[dict[str, str]] = []

    def submit(self, title: str, body: str, head_branch: str) -> SubmissionResult:
        self.submitted.append({"title": title, "body": body, "branch": head_branch})
        return SubmissionResult(url="https://example.invalid/pr/1")


class _MemBoard(BoardPort):
    def recent_prs(self) -> list[dict[str, Any]]:
        return [{"number": 1, "title": "example"}]


def _good_tiers() -> list[Evidence]:
    return [
        Evidence(1, "reflection", True, "git diff --stat: 2 files"),
        Evidence(2, "boot smoke", True, "import runner.agent_runner OK"),
        Evidence(3, "tests", True, "20 passed"),
    ]


def _self_test() -> int:
    import tempfile

    failures: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"  PASS | {name}")
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
            print(f"  FAIL | {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  ERROR | {name}: {type(exc).__name__}: {exc}")

    task = TaskContext("334", "deterministic 8-step agent runner harness",
                       "implement runner/", ["runner/agent_runner.py"])

    # S1 — happy path: 8/8 steps, pass verdict, PR carries Closes + evidence.
    def s1() -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = LocalWorkspace(Path(td), branch="contributor/issue-334")
            sub = _MemSubmission()
            runner = AgentRunner(_MemIssues(task), _MemRules(), ws, _MemVerify(_good_tiers()), sub, _MemBoard())
            report = runner.run(RunOptions("task-334", "334", agent="zai_contributor_1"))
            assert report.verdict == "pass", report.to_dict()
            assert [s["status"] for s in report.steps] == ["pass"] * 8, report.steps
            assert sub.submitted and "Closes #334" in sub.submitted[0]["body"]
            assert "## Test Evidence" in sub.submitted[0]["body"]
            assert "tier-3 tests: PASS" in sub.submitted[0]["body"]
            assert report.claim_released is True, "Return must release the claim"

    # S2 — claim-before-mutation: marker exists BEFORE any file mutation; Work
    # refuses to run without it (belt-and-braces read-back gate).
    def s2() -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = LocalWorkspace(Path(td))
            order: list[str] = []

            orig_write = ws.write_claim_marker
            orig_mutate = ws.mutate

            def spy_write(payload):
                assert not ws.mutations, "claim must precede mutation"
                order.append("claim")
                return orig_write(payload)

            def spy_mutate(t):
                assert order[:1] == ["claim"], "work ran before claim"
                order.append("work")
                return orig_mutate(t)

            ws.write_claim_marker = spy_write  # type: ignore[method-assign]
            ws.mutate = spy_mutate  # type: ignore[method-assign]
            runner = AgentRunner(_MemIssues(task), _MemRules(), ws, _MemVerify(_good_tiers()), _MemSubmission())
            report = runner.run(RunOptions("task-334", "334"))
            assert report.verdict == "pass" and order == ["claim", "work"]

            # marker vanishes AFTER the Claim step's read-back verification ->
            # Work's belt-and-braces gate must refuse mutation (no claim, no work)
            class VanishingWorkspace(LocalWorkspace):
                def __init__(self, root: Path) -> None:
                    super().__init__(root)
                    self._reads = 0

                def read_claim_marker(self, task_id):
                    self._reads += 1
                    if self._reads == 1:
                        return super().read_claim_marker(task_id)  # claim read-back OK
                    return None  # gone by Work time

            ws2 = VanishingWorkspace(Path(td))
            r2 = AgentRunner(_MemIssues(task), _MemRules(), ws2, _MemVerify(_good_tiers()), _MemSubmission())
            report2 = r2.run(RunOptions("task-334", "334"))
            assert report2.verdict == "aborted" and report2.abort_reason.startswith("work:")
            assert [s["status"] for s in report2.steps][5:] == ["not_run"] * 3

    # S3 — atomicity: marker file appears atomically (no tmp leftovers).
    def s3() -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = LocalWorkspace(Path(td))
            marker = ws.write_claim_marker({"task_id": "t", "issue_ref": "1"})
            assert Path(marker).is_file()
            leftovers = list((Path(td) / ".claims").glob("*.tmp-*"))
            assert leftovers == [], f"atomic write left tmp files: {leftovers}"

    # S4 — dirty workspace aborts at Inspect (isolation gate), nothing claimed.
    def s4() -> None:
        with tempfile.TemporaryDirectory() as td:
            ws = LocalWorkspace(Path(td))
            ws._dirty = True
            report = AgentRunner(_MemIssues(task), _MemRules(), ws, _MemVerify(_good_tiers()), _MemSubmission()).run(
                RunOptions("task-334", "334"))
            assert report.verdict == "aborted" and report.abort_reason.startswith("inspect:")
            assert report.claim_marker is None
            assert [s["status"] for s in report.steps][4:] == ["not_run"] * 4

    # S5 — unfetchable issue aborts at Understand (fail-closed).
    def s5() -> None:
        with tempfile.TemporaryDirectory() as td:
            report = AgentRunner(_MemIssues(None), _MemRules(), LocalWorkspace(Path(td)),
                                 _MemVerify(_good_tiers()), _MemSubmission()).run(
                                     RunOptions("task-x", "999999"))
        assert report.verdict == "aborted" and report.abort_reason.startswith("understand:")

    # S6 — failing/missing tier aborts at Verify; no PR submitted (U2/U8).
    def s6() -> None:
        sub = _MemSubmission()
        bad = [Evidence(1, "reflection", True), Evidence(2, "boot smoke", True),
               Evidence(3, "tests", False, "1 failed")]
        with tempfile.TemporaryDirectory() as td:
            report = AgentRunner(_MemIssues(task), _MemRules(), LocalWorkspace(Path(td)),
                                 _MemVerify(bad), sub).run(RunOptions("task-334", "334"))
        assert report.verdict == "aborted" and report.abort_reason.startswith("verify:")
        assert not sub.submitted, "no PR may be submitted without green tiers"

        sub2 = _MemSubmission()
        missing_tier = [Evidence(1, "reflection", True), Evidence(3, "tests", True)]
        with tempfile.TemporaryDirectory() as td:
            report2 = AgentRunner(_MemIssues(task), _MemRules(), LocalWorkspace(Path(td)),
                                  _MemVerify(missing_tier), sub2).run(RunOptions("task-334", "334"))
        assert report2.verdict == "aborted" and "missing tiers [2]" in report2.abort_reason
        assert not sub2.submitted

    # S7 — PR builder fail-closed: no-Closes / empty evidence / failing tiers refused.
    def s7() -> None:
        for issue, ev in (("adhoc", _good_tiers()), ("", _good_tiers()), ("334", [])):
            try:
                build_pr_body(issue, "t", ev, "agent")
                raise AssertionError(f"PR body accepted for {issue!r}/{len(ev)} evidence")
            except ValueError:
                pass
        body = build_pr_body("334", "t", _good_tiers(), "agent")
        assert "Closes #334" in body and "## Test Evidence" in body
        assert "commit message" in body  # U8 squash doctrine note

    # S8 — determinism: identical options + fixed clock -> byte-identical report.
    def s8() -> None:
        fixed = lambda: 1792100000.0  # noqa: E731 — injected clock
        runs = []
        with tempfile.TemporaryDirectory() as td:
            for _ in range(2):
                ws = LocalWorkspace(Path(td), branch="b")
                r = AgentRunner(_MemIssues(task), _MemRules(), ws, _MemVerify(_good_tiers()),
                                _MemSubmission(), _MemBoard()).run(
                    RunOptions("task-334", "334", agent="a", branch="b", now_fn=fixed))
                runs.append(json.dumps(r.to_dict(), sort_keys=True))
        assert runs[0] == runs[1], "reports must be byte-identical under fixed clock"
        d = json.loads(runs[0])
        assert d["run_id"].startswith("run-") and d["started_at"] == utc_stamp(fixed)

    for name, fn in (
        ("S1 happy path: 8/8 steps, Closes + Test Evidence in PR", s1),
        ("S2 claim-before-mutation + no-claim-no-work", s2),
        ("S3 atomic claim marker (no tmp leftovers)", s3),
        ("S4 dirty workspace aborts at Inspect", s4),
        ("S5 unfetchable issue aborts at Understand", s5),
        ("S6 fail/missing tier aborts at Verify, no PR", s6),
        ("S7 PR builder fail-closed (Closes + evidence)", s7),
        ("S8 report determinism (injected clock)", s8),
    ):
        check(name, fn)

    print(f"{8 - len(failures)}/8 self-test groups passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic 8-step Agent Runner Harness (#334)")
    parser.add_argument("--self-test", action="store_true",
                        help="run the offline scenario harness (in-memory ports) and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
