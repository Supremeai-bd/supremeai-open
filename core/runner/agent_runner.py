#!/usr/bin/env python3
"""SupremeAI deterministic 8-step agent runner harness — issue #334.

Spec SSOT chain:
  - docs/AGENT_LOOP_SPEC.md (task-envelope-v1, §2 envelope, §4 verification tiers)
  - AGENTS.md §3 8-step table: Understand → Rules → Inspect → Claim → Work
    → Verify → Record → Return
  - AGENTS.md (Single Door SSOT): 5 Universal Invariants — Dual-Rebase,
    Boundary, Superior Replacement, Verification & PR Blueprint, P0
    Drainage & Anti-Stampede
    (``Closes #N`` rides in the PR description — squash auto-close doctrine)

The runner CONSUMES the canonical task envelope emitted by
``scripts/agents/continuous_agent_loop.py --task-envelope`` — it never
redefines the contract. One envelope in, one deterministic 8-step execution
out, with automated evidence capture and the strict 3-tier pre-PR
verification gate (reflection → boot smoke → test suite). Step 7 (Record)
is fail-closed: it refuses to produce a submission package unless all three
verification tiers passed. Step 5 (Work) is claim-gated: no claim marker,
no filesystem mutation ("no claim, no work", AGENTS.md §3 step 4).

House style (mirrors examples/gateway_client.py and the telemetry logger):
- offline-safe import: module import performs zero file/network I/O;
  all I/O happens on explicit construction/run/CLI action
- zero third-party dependencies (house doctrine — AGENTS.md)
- honest errors: every contract violation names the offending field/step/path
- credentials and payloads are never echoed — captured command output is
  secret-redacted before it enters the evidence ledger

Contract (বাংলা মন্তব্য — runner-চুক্তি):
- ইনপুট: task-envelope-v1 JSON (--envelope PATH, '-' মানে stdin); চুক্তির
  বাইরের কোনো envelope হলে EnvelopeError — কোনো অনুমান নয়, fail-closed
- ৮ ধাপ কঠোর ক্রমে চলে; যেকোনো ধাপ ব্যর্থ হলে পরের ধাপ চলে না এবং পুরো
  evidence লেজারসহ সৎ fail রিপোর্ট হয়
- Step 4 (Claim) ছাড়া Step 5 (Work) অসম্ভব — claim marker ফাইল ছাড়া
  কোনো mutation নয় ("no claim, no work")
- Step 6 (Verify) = ঠিক ৩টি টিয়ার: reflection → boot smoke → test suite;
  একটিও fail করলে Step 7 (Record) fail-closed ব্লকড
- Step 7 issue_reference_required হলে PR body-তে "Closes #N" নিশ্চিত করে
  এবং commit message-এও রাখে (U8 squash auto-close doctrine)
- secret/ক্রেডেনশিয়াল কখনো evidence-এ যায় না — ক্যাপচার করা আউটপুট
  redact হয়; runner শুধু প্রমাণ রাখে, কনটেন্ট কখনো ফেরত দেয় না

CLI self-test (offline, hermetic — কোনো নেটওয়ার্ক নয়):
    python runner/agent_runner.py --self-test

Full run (offline demo / plan-only):
    python scripts/agents/continuous_agent_loop.py --issue 334 --task-envelope > env.json
    python runner/agent_runner.py --envelope env.json --plan-only

Exit codes: 0 = সব ধাপ পাশ; 1 = চুক্তি/যাচাই ব্যর্থতা; 2 = usage/envelope ত্রুটি
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# Frozen contract constants
# ---------------------------------------------------------------------------

ENVELOPE_FORMAT = "task-envelope-v1"
ENVELOPE_VERSION = 1
AGENT_LOOP_SPEC_SSOT = "docs/AGENT_LOOP_SPEC.md §4"
RUNNER_CONTRACT_VERSION = "agent-runner-contract/1"

# AGENTS.md §3 — the canonical 8 steps, in execution order.
STEPS = (
    "understand",
    "rules",
    "inspect",
    "claim",
    "work",
    "verify",
    "record",
    "return",
)
STEP_TITLES = {
    "understand": "Understand",
    "rules": "Rules",
    "inspect": "Inspect",
    "claim": "Claim",
    "work": "Work",
    "verify": "Verify",
    "record": "Record",
    "return": "Return",
}

# Issue #334 Verification Contract — exactly three tiers, in order.
VERIFY_TIERS = ("reflection", "boot-smoke", "test-suite")

# docs/AGENT_LOOP_SPEC.md §2 envelope scope defaults — forbidden always wins.
FORBIDDEN_DEFAULTS = (".env*", "secrets/**", "credentials/**", "vault/**")

EVIDENCE_FILE_PREFIX = "runner-evidence"
CLAIM_FILE_PREFIX = "claim"
MAX_OUTPUT_TAIL = 2000
DEFAULT_TIMEOUT_S = 60

SECRET_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Bearer first: the keyword pattern below would otherwise consume only the
    # scheme word ("Authorization: Bearer" -> "Authorization=<redacted>") and
    # strand the credential itself. Fail-closed ordering: longest-secret first.
    (re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"), "Bearer <redacted>"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd|authorization|credential)\b\s*[=:]\s*\S+"
        ),
        r"\1=<redacted>",
    ),
    (
        re.compile(r"\b([A-Z][A-Z0-9_]*_(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD))\s*=\s*\S+"),
        r"\1=<redacted>",
    ),
)


# ---------------------------------------------------------------------------
# Errors — honest, path/step-annotated, fail-closed
# ---------------------------------------------------------------------------


class RunnerError(RuntimeError):
    """Base error: names the step and (when known) the offending path."""

    def __init__(self, message: str, *, step: str = "", path: str = "") -> None:
        self.step = step
        self.path = path
        suffix = ""
        if step:
            suffix += f" [step: {step}]"
        if path:
            suffix += f" [path: {path}]"
        super().__init__(f"{message}{suffix}")


class EnvelopeError(RunnerError):
    """The task envelope violates task-envelope-v1 (docs/AGENT_LOOP_SPEC.md §2)."""


class ScopeViolation(RunnerError):
    """A work-manifest path is outside scope.touching_files (AGENTS.md U1)."""


class ClaimError(RunnerError):
    """Work attempted without a held claim marker ('no claim, no work')."""


class VerificationError(RunnerError):
    """A verification tier failed; Record stays blocked until all pass."""


# ---------------------------------------------------------------------------
# Envelope loading + validation (fail-closed, field-path annotated)
# ---------------------------------------------------------------------------


def load_envelope(raw: str | bytes, path: str = "<stdin>") -> dict[str, Any]:
    """Parse and validate a task-envelope-v1 payload. Raises EnvelopeError."""
    try:
        doc = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvelopeError(f"envelope is not valid JSON: {exc}", path=path) from exc
    if not isinstance(doc, dict):
        raise EnvelopeError("envelope root must be a JSON object", path=path)
    env = doc.get("task_envelope", doc)
    if not isinstance(env, dict):
        raise EnvelopeError("task_envelope must be a JSON object", path=path)
    validate_envelope(env, path=path)
    return env


def _require_str(env: dict[str, Any], key: str, path: str) -> str:
    val = env.get(key)
    if not isinstance(val, str) or not val.strip():
        raise EnvelopeError(
            f"envelope field '{key}' must be a non-empty string", path=path
        )
    return val


def validate_envelope(env: dict[str, Any], path: str = "<envelope>") -> None:
    """Validate the frozen v1 fields. Missing anything = EnvelopeError."""
    version = env.get("envelope_version")
    if version != ENVELOPE_VERSION:
        raise EnvelopeError(
            f"envelope_version must be {ENVELOPE_VERSION}, got {version!r}", path=path
        )
    fmt = env.get("output_format")
    if fmt != ENVELOPE_FORMAT:
        raise EnvelopeError(
            f"output_format must be '{ENVELOPE_FORMAT}', got {fmt!r}", path=path
        )
    _require_str(env, "task_id", path)
    _require_str(env, "objective", path)

    submission = env.get("submission")
    if not isinstance(submission, dict):
        raise EnvelopeError("envelope field 'submission' must be an object", path=path)
    _require_str(submission, "pathway", f"{path}.submission")
    _require_str(submission, "base_branch", f"{path}.submission")
    _require_str(submission, "pr_title_prefix", f"{path}.submission")

    scope = env.get("scope")
    if not isinstance(scope, dict):
        raise EnvelopeError("envelope field 'scope' must be an object", path=path)
    touching = scope.get("touching_files")
    if not isinstance(touching, list) or not touching or not all(
        isinstance(t, str) and t.strip() for t in touching
    ):
        raise EnvelopeError(
            "scope.touching_files must be a non-empty list of non-empty strings",
            path=f"{path}.scope",
        )

    if submission.get("issue_reference_required"):
        issue = env.get("issue")
        if issue in (None, "", 0):
            raise EnvelopeError(
                "submission.issue_reference_required=true but envelope field "
                "'issue' is missing — Closes #N could never ride (AGENTS.md U8)",
                path=f"{path}.submission",
            )


def build_envelope_from_issue(
    *,
    task_id: str,
    issue: str | int,
    objective: str,
    touching_files: Iterable[str],
    pr_title_prefix: str = "feat(open):",
    pathway: str = "bridge_submit_patch",
    forbidden_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Convenience builder — the minimal valid envelope the runner accepts.

    Real runs should consume the loop's ``--task-envelope`` output; this
    builder exists so tests, demos, and tooling can construct the same
    shape without tribal knowledge.
    """
    return {
        "envelope_version": ENVELOPE_VERSION,
        "output_format": ENVELOPE_FORMAT,
        "task_id": task_id,
        "issue": str(issue),
        "objective": objective,
        "scope": {
            "touching_files": list(touching_files),
            "forbidden_paths": list(forbidden_paths) if forbidden_paths else list(FORBIDDEN_DEFAULTS),
        },
        "submission": {
            "pathway": pathway,
            "base_branch": "main",
            "pr_title_prefix": pr_title_prefix,
            "issue_reference_required": True,
        },
    }


# ---------------------------------------------------------------------------
# Scope matching + redaction helpers
# ---------------------------------------------------------------------------


def normalize_path(path: str) -> str:
    """Repo-relative POSIX path; rejects traversal and absolute escapes."""
    p = (path or "").strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("/") or ".." in p.split("/"):
        raise ScopeViolation(f"path escapes the repository workspace: {path!r}", path=path)
    return p.rstrip("/")


def path_matches(path: str, pattern: str) -> bool:
    """fnmatch with directory-prefix support ('runner' matches 'runner/x.py')."""
    norm = normalize_path(path)
    pat = pattern.strip().replace("\\", "/").rstrip("/")
    if not pat:
        return False
    if fnmatch.fnmatch(norm, pat):
        return True
    if fnmatch.fnmatch(norm, pat + "/*") or fnmatch.fnmatch(norm, pat + "/**"):
        return True
    return norm == pat


def path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(path_matches(path, pat) for pat in patterns)


def redact(text: str) -> str:
    """Best-effort secret redaction for captured output (never a leak channel)."""
    out = text or ""
    for pattern, replacement in SECRET_HINTS:
        out = pattern.sub(replacement, out)
    return out


def run_command(
    cmd: list[str], cwd: str | Path, timeout_s: int = DEFAULT_TIMEOUT_S
) -> dict[str, Any]:
    """Run one verification command; capture redacted tail + exit + duration."""
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv list, never a shell
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        tail = redact(proc.stdout or "")
        err_tail = redact(proc.stderr or "")
        combined = (tail + ("\n" + err_tail if err_tail.strip() else "")).strip()
        return {
            "command": " ".join(shlex.quote(c) for c in cmd),
            "exit_code": proc.returncode,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output_tail": combined[-MAX_OUTPUT_TAIL:],
            "passed": proc.returncode == 0,
        }
    except FileNotFoundError:
        return {
            "command": " ".join(shlex.quote(c) for c in cmd),
            "exit_code": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output_tail": f"executable not found: {cmd[0]!r}",
            "passed": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(shlex.quote(c) for c in cmd),
            "exit_code": None,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output_tail": f"timed out after {timeout_s}s",
            "passed": False,
        }


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------


class AgentRunner:
    """Deterministic executor of the 8-step cycle for one task envelope.

    The runner never writes repository files itself: Step 5 (Work) either
    delegates to ``work_callable`` or scope-checks a caller-supplied
    ``work_manifest`` (the list of paths the work produced). This keeps the
    harness honest — it orchestrates, gates, and records; it does not code.
    """

    def __init__(
        self,
        envelope: dict[str, Any],
        *,
        repo_root: str | Path = ".",
        evidence_dir: str | Path | None = None,
        session: str = "agent-runner",
        work_callable: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        reflection_command: list[str] | None = None,
        boot_command: list[str] | None = None,
        test_command: list[str] | None = None,
        verify_timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        validate_envelope(envelope, path="<constructed-envelope>")
        self.env = envelope
        self.repo_root = Path(repo_root).resolve()
        self.evidence_dir = (
            Path(evidence_dir).resolve()
            if evidence_dir
            else self.repo_root / ".runner-evidence"
        )
        self.session = session
        self.work_callable = work_callable
        self.verify_timeout_s = verify_timeout_s
        self._reflection_command = reflection_command
        self._boot_command = boot_command
        self._test_command = test_command

        self.steps: list[dict[str, Any]] = []
        self.tiers: list[dict[str, Any]] = []
        self.tiers_passed = False
        self.claim: dict[str, Any] | None = None
        self.claim_released = False
        self._work_result: dict[str, Any] = {}
        self.record: dict[str, Any] | None = None
        self.outcome: dict[str, Any] | None = None
        self._fingerprint: str = ""
        self._head: str = ""
        self._branch: str = ""

    # -- identity -----------------------------------------------------------

    @property
    def task_id(self) -> str:
        return str(self.env["task_id"])

    @property
    def issue(self) -> str:
        return str(self.env.get("issue", ""))

    @property
    def run_id(self) -> str:
        """Deterministic run identity: task_id + repo state fingerprint.

        Same task on the same repo state always yields the same run_id —
        evidence files are reproducible, never random (U2 truth & evidence).
        """
        material = f"{self.task_id}:{self._fingerprint or 'unfingerprinted'}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    def _record_step(self, name: str, status: str, detail: dict[str, Any], started: float) -> None:
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "name": STEP_TITLES[name],
                "status": status,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "detail": detail,
            }
        )

    # -- step 1: Understand --------------------------------------------------

    def step_understand(self) -> dict[str, Any]:
        started = time.monotonic()
        problem = self.env.get("problem_statement")
        detail = {
            "task_id": self.task_id,
            "issue": self.issue,
            "objective": self.env["objective"],
            "task_type": self.env.get("task_type", ""),
            "group": self.env.get("group", ""),
            "priority": self.env.get("priority", ""),
            "problem_statement_presented": isinstance(problem, dict),
        }
        self._record_step("understand", "passed", detail, started)
        return detail

    # -- step 2: Rules -------------------------------------------------------

    def step_rules(self) -> dict[str, Any]:
        started = time.monotonic()
        scope = self.env["scope"]
        forbidden = list(scope.get("forbidden_paths") or [])
        missing_defaults = [p for p in FORBIDDEN_DEFAULTS if p not in forbidden]
        forbidden.extend(missing_defaults)
        scope["forbidden_paths"] = forbidden

        # AGENT_RULES.md was deleted by #1526 — the Single Door SSOT is
        # AGENTS.md now (authority-pointer sweep, #1642). Pointers are the
        # real top-level sections of the live constitution, not a dead twin.
        rules_path = self.repo_root / "AGENTS.md"
        rule_pointers: list[str] = []
        rules_source = "absent"
        if rules_path.is_file():
            try:
                text = rules_path.read_text(encoding="utf-8", errors="replace")
                rule_pointers = sorted(set(re.findall(r"^## (.+?)\s*$", text, re.M)))
                rules_source = "AGENTS.md"
            except OSError as exc:
                rule_pointers = []
                rules_source = f"unreadable: {exc}"
        detail = {
            "rules_source": rules_source,
            "rule_pointers": rule_pointers,
            "forbidden_paths": forbidden,
            "defaults_added": missing_defaults,
        }
        self._record_step("rules", "passed", detail, started)
        return detail

    # -- step 3: Inspect (read-only) ------------------------------------------

    def _git(self, *args: str) -> str | None:
        try:
            proc = subprocess.run(  # noqa: S603
                ["git", *args],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()

    def step_inspect(self) -> dict[str, Any]:
        started = time.monotonic()
        head = self._git("rev-parse", "HEAD")
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD")
        dirty = self._git("status", "--porcelain")
        git_available = head is not None
        self._head = head or ""
        self._branch = branch or ""
        self._fingerprint = (
            head
            or hashlib.sha256(str(self.repo_root).encode("utf-8")).hexdigest()[:16]
        )
        detail = {
            "git_available": git_available,
            "branch": self._branch or None,
            "head": self._head or None,
            "dirty_entries": (len(dirty.splitlines()) if dirty else 0),
            "fingerprint": self._fingerprint,
            "run_id": self.run_id,
        }
        self._record_step("inspect", "passed", detail, started)
        return detail

    # -- step 4: Claim (atomic marker) ----------------------------------------

    @property
    def claim_path(self) -> Path:
        return self.evidence_dir / f"{CLAIM_FILE_PREFIX}-{self.run_id}.json"

    def step_claim(self) -> dict[str, Any]:
        started = time.monotonic()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        claim = {
            "claim_id": f"claim-{self.run_id}",
            "task_id": self.task_id,
            "issue": self.issue,
            "session": self.session,
            "head": self._head or None,
            "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rule": "no claim, no work (AGENTS.md §3 step 4)",
        }
        tmp = self.claim_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(claim, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.claim_path)  # atomic marker: never half-written
        self.claim = claim
        self.claim_released = False
        detail = {"claim_id": claim["claim_id"], "marker": str(self.claim_path)}
        self._record_step("claim", "passed", detail, started)
        return detail

    def release_claim(self) -> bool:
        """Release the held claim (Step 8). Returns True if a marker was removed."""
        if self.claim is None:
            return False
        try:
            self.claim_path.unlink(missing_ok=True)
        except OSError:
            return False
        self.claim = None
        self.claim_released = True
        return True

    # -- step 5: Work (claim-gated, scope-guarded) -----------------------------

    def step_work(self, work_manifest: Iterable[str] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        if self.claim is None:
            raise ClaimError(
                "no claim marker held — work refused ('no claim, no work'); "
                "run step_claim() first",
                step="work",
            )
        manifest = [normalize_path(p) for p in (work_manifest or [])]
        touching = list(self.env["scope"]["touching_files"])
        forbidden = list(self.env["scope"].get("forbidden_paths") or [])
        for path in manifest:
            if path_matches_any(path, forbidden):
                raise ScopeViolation(
                    f"work manifest path hits forbidden_paths: '{path}' — "
                    "forbidden always wins over touching_files",
                    step="work",
                    path=path,
                )
            if not path_matches_any(path, touching):
                raise ScopeViolation(
                    f"work manifest path outside scope.touching_files: '{path}' "
                    f"(allowed: {touching})",
                    step="work",
                    path=path,
                )
        callable_result: dict[str, Any] = {}
        if self.work_callable is not None:
            raw = self.work_callable(self.env)
            if not isinstance(raw, dict):
                raise RunnerError(
                    "work_callable must return a JSON-serializable dict",
                    step="work",
                )
            callable_result = raw
        detail = {
            "manifest": manifest,
            "scope_check": "passed" if manifest else "plan-only (empty manifest)",
            "delegated": self.work_callable is not None,
            "callable_result": callable_result,
        }
        self._record_step("work", "passed", detail, started)
        self._work_result = detail
        return detail

    # -- step 6: Verify (3-tier gate) ------------------------------------------

    def _default_reflection_command(self) -> list[str]:
        paths = sorted(
            {
                p.split("/")[0] if "/" in p else p
                for p in self.env["scope"]["touching_files"]
            }
        )
        return ["git", "diff", "--stat", "--", *paths]

    def _default_boot_command(self) -> list[str]:
        return [sys.executable, "-c", "import runner.agent_runner"]

    def _default_test_command(self) -> list[str]:
        try:
            import pytest  # noqa: F401

            return [sys.executable, "-m", "pytest", "tests/test_agent_runner.py", "-q"]
        except ImportError:
            return [sys.executable, "tests/test_agent_runner.py"]

    def step_verify(self) -> dict[str, Any]:
        started = time.monotonic()
        tiers_spec = (
            ("reflection", self._reflection_command or self._default_reflection_command()),
            ("boot-smoke", self._boot_command or self._default_boot_command()),
            ("test-suite", self._test_command or self._default_test_command()),
        )
        self.tiers = []
        failures: list[str] = []
        for tier_name, cmd in tiers_spec:
            result = run_command(list(cmd), self.repo_root, self.verify_timeout_s)
            result["tier"] = tier_name
            result["evidence_ssot"] = AGENT_LOOP_SPEC_SSOT
            self.tiers.append(result)
            if not result["passed"]:
                failures.append(
                    f"{tier_name}: exit={result['exit_code']} ({result['command']})"
                )
        self.tiers_passed = not failures
        detail = {
            "tiers": self.tiers,
            "tier_count": len(self.tiers),
            "ssot": AGENT_LOOP_SPEC_SSOT,
            "failures": failures,
        }
        if failures:
            self._record_step("verify", "failed", detail, started)
            raise VerificationError(
                "verification tiers failed — Record stays blocked: "
                + "; ".join(failures),
                step="verify",
            )
        self._record_step("verify", "passed", detail, started)
        return detail

    # -- step 7: Record (fail-closed submission package) ------------------------

    def step_record(self) -> dict[str, Any]:
        started = time.monotonic()
        if not self.tiers_passed:
            raise VerificationError(
                "Record refused: the 3-tier verification gate has not passed "
                "(AGENTS.md U7) — no submission package may be produced",
                step="record",
            )
        submission = self.env["submission"]
        prefix = submission["pr_title_prefix"].strip()
        objective = self.env["objective"].strip()
        pr_title = f"{prefix} {objective}".strip()
        if len(pr_title) > 240:
            pr_title = pr_title[:237].rstrip() + "..."
        body = submission.get("pr_body_template") or ""
        closes = f"Closes #{self.issue}" if self.issue else ""
        if closes and closes not in body:
            body = (body.rstrip() + "\n\n" + closes).strip()
        commit_message = "\n".join(
            part for part in (pr_title, closes, "") if part
        )
        evidence_ref = (
            f"{EVIDENCE_FILE_PREFIX}-{self._task_slug()}-{self.run_id}.json"
        )
        commit_message += (
            f"\n8-step runner evidence: {evidence_ref} "
            f"(contract {RUNNER_CONTRACT_VERSION}, tiers SSOT {AGENT_LOOP_SPEC_SSOT})"
        )
        self.record = {
            "pr_title": pr_title,
            "pr_body": body,
            "commit_message": commit_message,
            "closes_line": closes,
            "issue_reference_required": bool(submission.get("issue_reference_required")),
            "evidence_file": evidence_ref,
            "pathway": submission["pathway"],
        }
        detail = {"record": self.record}
        self._record_step("record", "passed", detail, started)
        return detail

    # -- step 8: Return ---------------------------------------------------------

    def step_return(self) -> dict[str, Any]:
        started = time.monotonic()
        released = self.release_claim()
        detail = {
            "claim_released": released,
            "board_recheck": (
                "offline-skip — the live loop re-polls the fresh board "
                "(AGENTS.md freshness doctrine, #4177) before the next task"
            ),
            "status": "completed",
        }
        self._record_step("return", "passed", detail, started)
        return detail

    # -- orchestration -----------------------------------------------------------

    def _task_slug(self) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]", "_", self.task_id).strip("._")
        return slug or "task"

    def run(
        self,
        *,
        work_manifest: Iterable[str] | None = None,
        plan_only: bool = False,
    ) -> dict[str, Any]:
        """Execute all 8 steps in order. Fail-closed: first failure stops the run.

        Returns the outcome dict (also stored on ``self.outcome``); raises
        RunnerError subclasses on contract violations, after recording evidence.
        """
        step_methods = (
            self.step_understand,
            self.step_rules,
            self.step_inspect,
            self.step_claim,
            lambda: self.step_work([] if plan_only else work_manifest),
            self.step_verify,
            self.step_record,
            self.step_return,
        )
        status = "completed"
        error: str = ""
        try:
            for method in step_methods:
                method()
        except RunnerError as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            if exc.step == "verify":
                self.steps.append(
                    {
                        "step": len(self.steps) + 1,
                        "name": "Verify",
                        "status": "failed",
                        "duration_ms": 0,
                        "detail": {"tiers": self.tiers, "ssot": AGENT_LOOP_SPEC_SSOT},
                    }
                )
            self.release_claim()
        self.outcome = {
            "runner_contract": RUNNER_CONTRACT_VERSION,
            "task_id": self.task_id,
            "issue": self.issue,
            "run_id": self.run_id,
            "status": status,
            "steps": self.steps,
            "tiers_passed": self.tiers_passed,
            "claim_released": self.claim_released,
            "error": error,
            "record": self.record,
        }
        return self.outcome

    def write_evidence(self) -> Path:
        """Persist the evidence ledger as one JSON file; returns its path."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self.evidence_dir / (
            f"{EVIDENCE_FILE_PREFIX}-{self._task_slug()}-{self.run_id}.json"
        )
        payload = self.outcome or {
            "runner_contract": RUNNER_CONTRACT_VERSION,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "steps": self.steps,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic 8-step agent runner harness (issue #334). "
        "Consumes a task-envelope-v1 payload."
    )
    parser.add_argument(
        "--envelope",
        help="path to the task-envelope JSON ('-' reads stdin; required unless --self-test)",
    )
    parser.add_argument("--repo-root", default=".", help="repository root (default: cwd)")
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="evidence ledger directory (default: <repo-root>/.runner-evidence)",
    )
    parser.add_argument(
        "--work-manifest",
        default=None,
        help="JSON file holding the list of paths the work produced (scope-checked)",
    )
    parser.add_argument(
        "--test-command",
        default=None,
        help="override the tier-3 test suite command (shell-split string)",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="run Work with an empty manifest (deterministic offline demo)",
    )
    parser.add_argument(
        "--session", default="agent-runner", help="session identity recorded in the claim"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the offline hermetic self-test and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        checks = self_test()
        print(f"SELF-TEST OK: {checks} checks passed")
        return 0

    if not args.envelope:
        parser.error("--envelope is required (or use --self-test)")
        return 2

    try:
        if args.envelope == "-":
            raw = sys.stdin.read()
            path_label = "<stdin>"
        else:
            env_path = Path(args.envelope)
            raw = env_path.read_text(encoding="utf-8")
            path_label = str(env_path)
        envelope = load_envelope(raw, path=path_label)
    except (OSError, EnvelopeError) as exc:
        print(f"ENVELOPE ERROR: {exc}", file=sys.stderr)
        return 2

    manifest: list[str] = []
    if args.work_manifest:
        try:
            loaded = json.loads(Path(args.work_manifest).read_text(encoding="utf-8"))
            if not isinstance(loaded, list) or not all(isinstance(p, str) for p in loaded):
                raise ValueError("work manifest must be a JSON array of strings")
            manifest = loaded
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"WORK MANIFEST ERROR: {exc}", file=sys.stderr)
            return 2

    runner = AgentRunner(
        envelope,
        repo_root=args.repo_root,
        evidence_dir=args.evidence_dir,
        session=args.session,
        test_command=shlex.split(args.test_command) if args.test_command else None,
    )
    try:
        outcome = runner.run(work_manifest=manifest, plan_only=args.plan_only)
    except RunnerError as exc:  # defensive: run() records internally
        outcome = {
            "runner_contract": RUNNER_CONTRACT_VERSION,
            "task_id": runner.task_id,
            "status": "failed",
            "error": str(exc),
            "steps": runner.steps,
        }
    evidence_path = runner.write_evidence()
    outcome["evidence_path"] = str(evidence_path)
    print(json.dumps(outcome, indent=2, ensure_ascii=False))
    return 0 if outcome.get("status") == "completed" else 1


# ---------------------------------------------------------------------------
# Self-test (hermetic, offline, tmp dirs only)
# ---------------------------------------------------------------------------


def self_test() -> int:
    """Offline self-test. Returns the number of checks performed (≥18)."""
    import tempfile

    checks = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise AssertionError(f"self-test check {checks} failed: {msg}")

    # 1. constants contract
    ok(len(STEPS) == 8, "exactly 8 steps")
    ok(
        tuple(STEP_TITLES[s] for s in STEPS)
        == ("Understand", "Rules", "Inspect", "Claim", "Work", "Verify", "Record", "Return"),
        "step titles match AGENTS.md §3 table",
    )
    ok(VERIFY_TIERS == ("reflection", "boot-smoke", "test-suite"), "3 verify tiers (issue #334)")
    ok(RUNNER_CONTRACT_VERSION.startswith("agent-runner-contract/"), "contract version shape")

    good_env = build_envelope_from_issue(
        task_id="task-selftest",
        issue="334",
        objective="prove the 8-step harness deterministically",
        touching_files=["runner/**", "tests/test_agent_runner.py"],
    )

    # 2. happy-path load (nested + flat)
    ok(load_envelope(json.dumps({"task_envelope": good_env}))["task_id"] == "task-selftest", "nested envelope loads")
    ok(load_envelope(json.dumps(good_env))["task_id"] == "task-selftest", "flat envelope loads")

    # 3-6. fail-closed envelope rejections
    for mutate, label in (
        (lambda e: e.pop("task_id"), "missing task_id"),
        (lambda e: e.update(envelope_version=2), "bad envelope_version"),
        (lambda e: e.update(output_format="task-envelope-v2"), "bad output_format"),
        (lambda e: e["scope"].update(touching_files=[]), "empty touching_files"),
        (
            lambda e: e["submission"].update(issue_reference_required=True) or e.pop("issue"),
            "issue_reference_required without issue",
        ),
    ):
        broken = json.loads(json.dumps(good_env))
        mutate(broken)
        try:
            load_envelope(json.dumps(broken))
            ok(False, f"envelope rejection: {label}")
        except EnvelopeError:
            ok(True, f"envelope rejection: {label}")

    # 7. forbidden defaults filled
    runner0 = AgentRunner(good_env, repo_root=".", evidence_dir="unused")
    ok(
        ".env*" in runner0.env["scope"]["forbidden_paths"],
        "forbidden defaults auto-filled",
    )

    # 8. scope matching semantics
    ok(path_matches("runner/a/b.py", "runner/**"), "dir glob match")
    ok(path_matches("runner/x.py", "runner"), "dir prefix match")
    ok(not path_matches("docs/x.md", "runner/**"), "outside scope no match")
    ok(not path_matches("runner_evil/x.py", "runner"), "sibling prefix no match")
    try:
        normalize_path("../escape.py")
        ok(False, "traversal rejected")
    except ScopeViolation:
        ok(True, "traversal rejected")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "AGENTS.md").write_text(
            "# AGENTS\n## The Single Door\n## The 5 Universal Invariants (Must Follow vs Must Avoid)\n",
            encoding="utf-8",
        )
        pass_cmd = [sys.executable, "-c", "print('tier ok')"]
        fail_cmd = [sys.executable, "-c", "import sys; sys.exit(3)"]
        noop_callable: Callable[[dict[str, Any]], dict[str, Any]] = lambda env: {"worked": True}

        def fresh_runner(**kw: Any) -> AgentRunner:
            base = dict(
                repo_root=root,
                evidence_dir=root / "ev",
                reflection_command=pass_cmd,
                boot_command=pass_cmd,
                test_command=pass_cmd,
                work_callable=noop_callable,
            )
            base.update(kw)
            return AgentRunner(good_env, **base)

        # 9. claim gate
        r = fresh_runner()
        try:
            r.step_work(["runner/agent_runner.py"])
            ok(False, "work without claim refused")
        except ClaimError:
            ok(True, "work without claim refused")

        # 10-11. claim marker lifecycle
        r.step_inspect()
        r.step_claim()
        ok(r.claim_path.is_file(), "claim marker written")
        ok(r.release_claim() and not r.claim_path.exists(), "claim released removes marker")

        # 12. scope violation named
        r2 = fresh_runner()
        r2.step_inspect()
        r2.step_claim()
        try:
            r2.step_work(["docs/elsewhere.md"])
            ok(False, "scope violation raised")
        except ScopeViolation as exc:
            ok("docs/elsewhere.md" in str(exc), "scope violation names the path")

        # 13. forbidden wins over touching
        env_forbidden = json.loads(json.dumps(good_env))
        env_forbidden["scope"]["touching_files"].append(".env*")
        rf = AgentRunner(
            env_forbidden,
            repo_root=root,
            evidence_dir=root / "ev",
            reflection_command=pass_cmd,
            boot_command=pass_cmd,
            test_command=pass_cmd,
        )
        rf.step_inspect()
        rf.step_claim()
        try:
            rf.step_work([".env.production"])
            ok(False, "forbidden wins over touching")
        except ScopeViolation:
            ok(True, "forbidden wins over touching")

        # 14. record blocked before verify
        try:
            r2.step_record()
            ok(False, "record blocked before tiers")
        except VerificationError:
            ok(True, "record blocked before tiers")

        # 15. verify failure names the tier
        r3 = fresh_runner(test_command=fail_cmd)
        r3.step_inspect()
        r3.step_claim()
        r3.step_work([])
        try:
            r3.step_verify()
            ok(False, "failing tier raises")
        except VerificationError as exc:
            ok("test-suite" in str(exc), "failing tier named")
        ok(r3.claim is not None, "claim still held after verify fail (release is run/return's job)")

        # 16. full happy run → 8 steps, record, evidence roundtrip
        r4 = fresh_runner()
        outcome = r4.run(work_manifest=["runner/agent_runner.py"])
        ok(outcome["status"] == "completed", "full run completed")
        ok(len(outcome["steps"]) == 8, "all 8 steps recorded")
        ok(outcome["tiers_passed"] and outcome["record"] is not None, "tiers passed + record built")
        ok(f"Closes #334" in outcome["record"]["pr_body"], "Closes line embedded")
        ok("Closes #334" in outcome["record"]["commit_message"], "U8: Closes in commit message")
        ev_path = r4.write_evidence()
        ok(ev_path.is_file(), "evidence file written")
        reloaded = json.loads(ev_path.read_text(encoding="utf-8"))
        ok(reloaded["task_id"] == "task-selftest", "evidence roundtrip")
        ok(outcome["claim_released"], "claim released on return step")

        # 17. run_id deterministic (fingerprint is set by step_inspect)
        r_probe = fresh_runner()
        r_probe.step_inspect()
        ok(r4.run_id == r_probe.run_id, "run_id deterministic (same repo state)")

        # 18. full failing run → fail-closed, claim released, ≤7 steps
        r5 = fresh_runner(reflection_command=fail_cmd)
        outcome5 = r5.run(plan_only=True)
        ok(outcome5["status"] == "failed", "failing run honest")
        ok(len(outcome5["steps"]) <= 8 and not outcome5["tiers_passed"], "fail before record")
        ok(outcome5["claim_released"], "claim released even on failure")

    # 19. redaction
    leaked = "api_key=sk-supersecret123 Authorization: Bearer abcdef.ghi.jklmnop SUPREMEAI_TOKEN=xyz999"
    red = redact(leaked)
    ok("sk-supersecret123" not in red, "api_key value redacted")
    ok("abcdef.ghi.jklmnop" not in red, "bearer token redacted")
    ok("xyz999" not in red, "env token redacted")

    # 20. builder sanity
    ok(good_env["submission"]["pathway"] == "bridge_submit_patch", "builder pathway default")

    return checks


if __name__ == "__main__":
    sys.exit(main())
