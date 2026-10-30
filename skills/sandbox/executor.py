"""Fail-closed skill script executor.

Runs a skill script in an ephemeral workspace with a sanitized
environment and a hard timeout. Network denial is a host-level control;
the sandbox makes the contract explicit via the SKILL_SANDBOX flag and
terminates anything that outlives its budget (never retries silently).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_S = 10.0


@dataclass
class SandboxResult:
    script: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    workdir: str


class SkillSandbox:
    """Execute one skill script under resource guards."""

    def __init__(self, skill_root: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.skill_root = Path(skill_root)
        self.timeout_s = timeout_s

    def run(
        self,
        script: str,
        args: Sequence[str] | None = None,
        timeout_s: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> SandboxResult:
        script_path = (self.skill_root / script).resolve()
        if self.skill_root.resolve() not in script_path.parents:
            raise ValueError("script escapes the skill root")
        if not script_path.is_file():
            raise FileNotFoundError(f"script not found: {script}")
        workdir = Path(tempfile.mkdtemp(prefix="skill-sandbox-"))
        try:
            shutil.copytree(self.skill_root, workdir / "skill", dirs_exist_ok=True)
            staged_script = workdir / "skill" / script
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(workdir),
                "PYTHONHASHSEED": "0",
                "SKILL_SANDBOX": "1",
                "LANG": "C.UTF-8",
            }
            if extra_env:
                env.update(extra_env)
            try:
                completed = subprocess.run(
                    [sys.executable, str(staged_script), *list(args or [])],
                    capture_output=True,
                    text=True,
                    timeout=timeout_s or self.timeout_s,
                    cwd=str(workdir),
                    env=env,
                    check=False,
                )
                return SandboxResult(
                    script=script,
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    timed_out=False,
                    workdir=str(workdir),
                )
            except subprocess.TimeoutExpired as exc:
                return SandboxResult(
                    script=script,
                    returncode=-1,
                    stdout=exc.stdout.decode("utf-8", errors="replace")
                    if isinstance(exc.stdout, bytes)
                    else (exc.stdout or ""),
                    stderr="sandbox timeout: script exceeded its budget and was terminated",
                    timed_out=True,
                    workdir=str(workdir),
                )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def run_entry(
        self, descriptor_entry: str | None, args: Sequence[str] | None = None
    ) -> SandboxResult:
        """Execute a capability's declared entry point."""
        if not descriptor_entry:
            raise ValueError("capability declares no entry script")
        return self.run(descriptor_entry, args=args)
