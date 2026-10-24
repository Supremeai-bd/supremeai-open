"""
SupremeAI Mesh Node — Local Executors
=====================================
MESH-3 (issue #941) — Phase A

PC-1 (Dev Rig) ও PC-2 (Headless Tester) — উভয়ের জন্য local execution layer।
Tower থেকে task এসলে এই মডিউলের executor গুলো সেগুলো আসলে execute করে।

Executors (all real, no mocks):
  - run_bash(cmd)              → asyncio.subprocess দিয়ে আসল shell command
  - run_pytest(test_path)      → pytest subprocess + output parse
  - run_ollama(prompt, model)  → কনফিগারকৃত Ollama server এ httpx POST
  - git_commit_push(...)       → আসল git subprocess call (add → commit → push)

Design notes:
  - সব executor async — non-blocking। asyncio.subprocess দিয়ে।
  - Timeout প্রতিটি executor-এ enforce করা হয় (default 600s)।
  - Pydantic-নয় — stdlib dataclass ব্যবহার করা হয়েছে dependency কমানোর জন্য।
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Result dataclasses — প্রতিটি executor নির্দিষ্ট result type রিটার্ন করে।
# ---------------------------------------------------------------------------

@dataclass
class ExecResult:
    """run_bash() এর output — subprocess stdout/stderr/exit_code + timing।"""
    __test__ = False  # silence pytest collection warning (not a test class)
    cmd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    """run_pytest() এর output — parsed test summary + raw output।"""
    __test__ = False
    test_path: str
    exit_code: int
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    raw_output: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.failed == 0 and self.errors == 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GitResult:
    """git_commit_push() এর output — commit SHA + branch + push ok।"""
    __test__ = False
    branch: str
    commit_sha: str
    files_staged: int
    pushed: bool
    duration_seconds: float
    message: str

    @property
    def ok(self) -> bool:
        return bool(self.commit_sha) and self.pushed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Pytest output parser — pytest -v --tb=short এর stdout থেকে summary extract।
# ---------------------------------------------------------------------------

# pytest summary line looks like: "===== 3 passed, 1 skipped in 1.23s ====="
# or: "===== 1 failed, 2 passed, 3 errors in 2.5s ====="
# We use a simple pattern that matches each "<n> <kind>" pair independently —
# finditer yields one match per pair, so we can sum them up correctly.
_SUMMARY_PAIR_RE = re.compile(
    r"(\d+)\s+(passed|failed|errors|skipped|xfailed|xpassed|deselected)"
)


def parse_pytest_summary(raw: str) -> dict[str, int]:
    """pytest raw output থেকে {total, passed, failed, errors, skipped} extract করে।
    Multiple summary lines (collected/then final) handled: we sum ALL pairs found
    in the final summary line (the last `=====` bordered line)."""
    counts = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    # Find last summary line (the "===" bordered line, contains a counts keyword).
    summary_lines = [
        line for line in raw.splitlines()
        if line.startswith("=" * 5) and any(
            kw in line for kw in ("passed", "failed", "error", "no tests ran")
        )
    ]
    if not summary_lines:
        return counts
    summary = summary_lines[-1]
    for m in _SUMMARY_PAIR_RE.finditer(summary):
        n = int(m.group(1))
        kind = m.group(2)
        if kind == "passed":
            counts["passed"] = n
        elif kind == "failed":
            counts["failed"] = n
        elif kind == "errors":
            counts["errors"] = n
        elif kind == "skipped":
            counts["skipped"] = n
        elif kind == "xfailed":
            counts["skipped"] += n
        elif kind == "xpassed":
            counts["passed"] += n
        # 'deselected' is informational — not counted in total
    counts["total"] = (
        counts["passed"] + counts["failed"] + counts["errors"] + counts["skipped"]
    )
    return counts


# ---------------------------------------------------------------------------
# LocalExecutor — সব executor এক ক্লাসে, যাতে daemon inject করতে পারে।
# ---------------------------------------------------------------------------

class LocalExecutor:
    """
    Local task executor — bash / pytest / ollama / git।

    প্রতিটি method async এবং real subprocess বা HTTP call করে।
    Tests এ এই ক্লাসটি directly instantiate করে আসল subprocess চালানো যায়
    (kitchensink integration tests)। Daemon-এ এটি dependency inject করা হয়।
    """

    def __init__(
        self,
        workspace_dir: str = ".",
        # Constitution ARCH-001: .py তে localhost literal নেই — daemon এর
        # load_config প্রতিটি node-এর config.yaml / SUPREME_NODE_OLLAMA_URL env
        # থেকে আসল URL ঢোকায়। খালি হলে run_ollama clear error ছুঁড়ে দেয়।
        ollama_url: str = "",
        task_timeout_seconds: float = 600.0,
    ) -> None:
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.ollama_url = ollama_url.rstrip("/")
        self.task_timeout_seconds = task_timeout_seconds
        self._log = logging.getLogger("supreme_node.executor")

    # ------------------------------------------------------------------
    # 1. run_bash — generic shell command, non-blocking subprocess।
    # ------------------------------------------------------------------
    async def run_bash(self, cmd: str, timeout: float | None = None) -> ExecResult:
        """
        যেকোনো shell command execute করে। asyncio.subprocess দিয়ে।

        Returns ExecResult — exit_code, stdout, stderr, duration, timed_out।
        Timeout হলে process kill করে পরে timed_out=True।
        """
        timeout = timeout if timeout is not None else self.task_timeout_seconds
        start = time.monotonic()
        # সরাসরি shell দিয়ে চালানো হচ্ছে যাতে pipe / redirect / && কাজ করে।
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", "-c", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workspace_dir,
        )
        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                # প্রসেস ইতিমধ্যেই বেরিয়ে গেছে — kill দরকার নেই
                # (Constitution REL-001: observable log)।
                self._log.debug("pid %s ইতিমধ্যে exit করেছে — kill অপ্রয়োজনীয়", proc.pid)
            # Drain pipes so we don't leak
            try:
                stdout_b, stderr_b = await proc.communicate()
            except Exception as e:
                self._log.warning(
                    "drain pipes ব্যর্থ (pid %s): %s: %s",
                    proc.pid, type(e).__name__, e,
                )
                stdout_b, stderr_b = b"", b""
        duration = time.monotonic() - start
        exit_code = proc.returncode if proc.returncode is not None else -1
        return ExecResult(
            cmd=cmd,
            exit_code=exit_code,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            duration_seconds=round(duration, 3),
            timed_out=timed_out,
        )

    # ------------------------------------------------------------------
    # 2. run_pytest — pytest চালায় এবং output parse করে।
    # ------------------------------------------------------------------
    async def run_pytest(self, test_path: str, timeout: float | None = None) -> TestResult:
        """
        pytest -v --tb=short --color=no <test_path> চালায়।
        Output থেকে passed/failed/errors/skipped parse করে TestResult দেয়।
        """
        # সরাসরি run_bash ব্যবহার করে, কিন্তু output parse করে।
        cmd = f"python -m pytest -v --tb=short --color=no {shlex.quote(test_path)}"
        result = await self.run_bash(cmd, timeout=timeout)
        counts = parse_pytest_summary(result.stdout + "\n" + result.stderr)
        return TestResult(
            test_path=test_path,
            exit_code=result.exit_code,
            total=counts["total"],
            passed=counts["passed"],
            failed=counts["failed"],
            errors=counts["errors"],
            skipped=counts["skipped"],
            duration_seconds=result.duration_seconds,
            raw_output=result.stdout + ("\n--- STDERR ---\n" + result.stderr if result.stderr else ""),
        )

    # ------------------------------------------------------------------
    # 3. run_ollama — local Ollama server-এ prompt পাঠায়।
    # ------------------------------------------------------------------
    async def run_ollama(
        self,
        prompt: str,
        model: str = "llama3.2",
        timeout: float | None = None,
    ) -> str:
        """
        POST {ollama_url}/api/generate করে।
        Returns generated text। Ollama না চললে raise httpx.ConnectError।
        """
        if not self.ollama_url:
            # Constitution ARCH-001-এর সাথে সামঞ্জস্য — URL কনফিগ-ড্রিভেন,
            # তাই কনফিগার না থাকলে স্পষ্ট ব্যর্থতা (fail-fast, কোনো লুকানো
            # localhost fallback নেই)।
            raise RuntimeError(
                "ollama_url কনফিগার করা নেই — config.yaml এ ollama_url সেট "
                "করুন অথবা SUPREME_NODE_OLLAMA_URL env ব্যবহার করুন "
                "(অথবা node capabilities থেকে 'ollama' সরিয়ে দিন)"
            )
        timeout = timeout if timeout is not None else self.task_timeout_seconds
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    # ------------------------------------------------------------------
    # 4. git_commit_push — আসল git subprocess।
    # ------------------------------------------------------------------
    async def git_commit_push(
        self,
        branch: str,
        files: list[str],
        msg: str,
        push: bool = True,
        timeout: float | None = None,
    ) -> GitResult:
        """
        ১. checkout branch (না থাকলে create -b)
        ২. git add <files>
        ৩. git commit -m <msg>
        ৪. git push origin <branch>

        সব আসল git subprocess। Returns GitResult with commit_sha।
        """
        timeout = timeout if timeout is not None else self.task_timeout_seconds
        start = time.monotonic()

        # branch create-or-checkout
        # `git rev-parse --verify` দিয়ে check করি exists কিনা
        check = await self._git_run(["rev-parse", "--verify", branch], timeout=timeout)
        if check.exit_code != 0:
            # branch does not exist → create new
            create = await self._git_run(["checkout", "-b", branch], timeout=timeout)
            if create.exit_code != 0:
                return GitResult(
                    branch=branch, commit_sha="", files_staged=0,
                    pushed=False, duration_seconds=round(time.monotonic() - start, 3),
                    message=f"git checkout -b failed: {create.stderr.strip()}",
                )
        else:
            co = await self._git_run(["checkout", branch], timeout=timeout)
            if co.exit_code != 0:
                return GitResult(
                    branch=branch, commit_sha="", files_staged=0,
                    pushed=False, duration_seconds=round(time.monotonic() - start, 3),
                    message=f"git checkout failed: {co.stderr.strip()}",
                )

        # git add <files>
        if files:
            add_args = ["add", "--"] + list(files)
            add = await self._git_run(add_args, timeout=timeout)
            if add.exit_code != 0:
                return GitResult(
                    branch=branch, commit_sha="", files_staged=0,
                    pushed=False, duration_seconds=round(time.monotonic() - start, 3),
                    message=f"git add failed: {add.stderr.strip()}",
                )

        # count staged files for reporting
        diff = await self._git_run(["diff", "--cached", "--name-only"], timeout=timeout)
        staged_count = len([l for l in diff.stdout.splitlines() if l.strip()]) if diff.exit_code == 0 else 0

        # commit
        commit = await self._git_run(["commit", "-m", msg], timeout=timeout)
        if commit.exit_code != 0:
            # হতে পারে nothing to commit — সেটা ok, but commit_sha খালি থাকবে
            return GitResult(
                branch=branch, commit_sha="", files_staged=staged_count,
                pushed=False, duration_seconds=round(time.monotonic() - start, 3),
                message=f"git commit failed/empty: {commit.stderr.strip()}",
            )

        # get commit SHA
        rev = await self._git_run(["rev-parse", "HEAD"], timeout=timeout)
        commit_sha = rev.stdout.strip() if rev.exit_code == 0 else ""

        # push
        pushed = False
        if push:
            push_res = await self._git_run(["push", "origin", branch], timeout=timeout)
            pushed = push_res.exit_code == 0
            if not pushed:
                return GitResult(
                    branch=branch, commit_sha=commit_sha, files_staged=staged_count,
                    pushed=False, duration_seconds=round(time.monotonic() - start, 3),
                    message=f"git push failed: {push_res.stderr.strip()}",
                )

        return GitResult(
            branch=branch, commit_sha=commit_sha, files_staged=staged_count,
            pushed=pushed, duration_seconds=round(time.monotonic() - start, 3),
            message="ok",
        )

    # ------------------------------------------------------------------
    # Internal — single git command runner।
    # ------------------------------------------------------------------
    async def _git_run(
        self,
        args: list[str],
        timeout: float | None = None,
    ) -> ExecResult:
        """git subprocess — used by git_commit_push।"""
        timeout = timeout if timeout is not None else self.task_timeout_seconds
        cmd_args = ["git"] + list(args)
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workspace_dir,
        )
        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                # প্রসেস ইতিমধ্যেই বেরিয়ে গেছে — kill দরকার নেই (REL-001)।
                self._log.debug("pid %s ইতিমধ্যে exit করেছে — kill অপ্রয়োজনীয়", proc.pid)
            try:
                stdout_b, stderr_b = await proc.communicate()
            except Exception as e:
                self._log.warning(
                    "drain pipes ব্যর্থ (pid %s): %s: %s",
                    proc.pid, type(e).__name__, e,
                )
                stdout_b, stderr_b = b"", b""
        duration = time.monotonic() - start
        exit_code = proc.returncode if proc.returncode is not None else -1
        return ExecResult(
            cmd=" ".join(cmd_args),
            exit_code=exit_code,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            duration_seconds=round(duration, 3),
            timed_out=timed_out,
        )


# ---------------------------------------------------------------------------
# Convenience — task dispatch by executor type। daemon এই ব্যবহার করে।
# ---------------------------------------------------------------------------

VALID_TASK_TYPES = {"bash", "pytest", "ollama", "git_push"}


async def dispatch_task(
    executor: LocalExecutor,
    task: dict[str, Any],
) -> dict[str, Any]:
    """
    Tower থেকে আসা task dispatch করে।

    task schema (MESH-3 contract):
      {
        "task_id": "abc-123",
        "type": "bash" | "pytest" | "ollama" | "git_push",
        "payload": { ... type-specific ... },
        "timeout": 600  # optional override
      }

    Returns:
      {
        "task_id": ...,
        "status": "ok" | "error" | "timeout",
        "result": { ... executor output ... }
      }
    """
    task_id = task.get("task_id", "unknown")
    ttype = task.get("type")
    payload = task.get("payload") or {}
    timeout = task.get("timeout")

    if ttype not in VALID_TASK_TYPES:
        return {
            "task_id": task_id,
            "status": "error",
            "result": {"error": f"unknown task type: {ttype!r}"},
        }

    try:
        if ttype == "bash":
            r = await executor.run_bash(payload.get("cmd", ""), timeout=timeout)
            status = "timeout" if r.timed_out else ("ok" if r.ok else "error")
            return {"task_id": task_id, "status": status, "result": r.to_dict()}

        if ttype == "pytest":
            r = await executor.run_pytest(payload.get("test_path", "."), timeout=timeout)
            status = "ok" if r.ok else "error"
            return {"task_id": task_id, "status": status, "result": r.to_dict()}

        if ttype == "ollama":
            text = await executor.run_ollama(
                payload.get("prompt", ""),
                model=payload.get("model", "llama3.2"),
                timeout=timeout,
            )
            return {"task_id": task_id, "status": "ok", "result": {"text": text}}

        if ttype == "git_push":
            r = await executor.git_commit_push(
                branch=payload.get("branch", "main"),
                files=payload.get("files", []),
                msg=payload.get("message", "auto-commit by supreme-node"),
                push=payload.get("push", True),
                timeout=timeout,
            )
            status = "ok" if r.ok else "error"
            return {"task_id": task_id, "status": status, "result": r.to_dict()}

    except asyncio.TimeoutError:
        logging.getLogger("supreme_node.executor").warning(
            "task %s (%s) timeout — %.1fs অতিবাহিত",
            task_id, ttype, float(timeout or 0.0),
        )
        return {"task_id": task_id, "status": "timeout",
                "result": {"error": "task timed out"}}
    except httpx.HTTPError as e:
        logging.getLogger("supreme_node.executor").warning(
            "task %s http error: %s: %s", task_id, type(e).__name__, e
        )
        return {"task_id": task_id, "status": "error",
                "result": {"error": f"http: {type(e).__name__}: {e}"}}
    except Exception as e:
        logging.getLogger("supreme_node.executor").warning(
            "task %s unexpected error: %s: %s", task_id, type(e).__name__, e
        )
        return {"task_id": task_id, "status": "error",
                "result": {"error": f"{type(e).__name__}: {e}"}}

    # unreachable
    return {"task_id": task_id, "status": "error", "result": {"error": "unreachable"}}


__all__ = [
    "LocalExecutor",
    "ExecResult",
    "TestResult",
    "GitResult",
    "dispatch_task",
    "parse_pytest_summary",
    "VALID_TASK_TYPES",
]
