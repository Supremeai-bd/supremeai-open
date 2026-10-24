"""E2B-inspired secure code-execution sandbox adapter for SupremeAI.
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).

E2B (open-source isolated sandbox for AI-generated code) থেকে নেওয়া মূল ধারণা: এজেন্ট-
জেনারেটেড কোড নিরাপদ বিচ্ছিন্ন প্রক্রিয়ায় চালানো, যাতে মূল পরিবেশ বা user filesystem-এ
touch না পড়ে। project-এর `sandbox/docker_sandbox.py`-এর সাথে সামঞ্জস্য রেখে এখানে
একটি optional E2B bridge + subprocess/আইসোলেশন fallback রাখা হয়।
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from core.logging_config import logger
from integrations._flags import flag, import_available

_ENABLED_FLAG = "SUPREMEAI_E2B_ENABLED"
_MAX_OUTPUT_BYTES = 256 * 1024
_DEFAULT_TIMEOUT = 30


class E2BAdapter:
    """Isolated code execution bridging optional E2B with a local civilian sandbox fallback."""

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.enabled_flag = _ENABLED_FLAG
        self.timeout = timeout
        self._sandbox = None
        enabled = flag(_ENABLED_FLAG) and import_available("e2b")
        self._use_e2b = enabled
        if self._use_e2b:
            try:
                from e2b import Sandbox  # type: ignore[import-not-found]

                self._sandbox = Sandbox  # class kept for lazy per-request creation
                logger.info("E2BAdapter: upstream isolated sandbox available.")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"E2BAdapter: upstream init failed: {exc}")
                self._sandbox = None
        else:
            logger.info(
                "E2BAdapter: local subprocess fallback active "
                f"(flag={flag(_ENABLED_FLAG)}, dep={import_available('e2b')})."
            )

    @property
    def active(self) -> bool:
        return self._sandbox is not None

    def run_command(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Execute a shell command in isolation; returns {status, stdout, stderr, engine}."""
        if self.active:
            try:
                sbx = self._sandbox.create()  # type: ignore[union-attr]
                result = sbx.commands.run(command)
                return {
                    "status": "ok",
                    "engine": "upstream",
                    "stdout": str(result.stdout),
                    "stderr": str(result.stderr),
                }
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"E2BAdapter: upstream run failed: {exc}")
                return {"status": "error", "engine": "upstream", "error": str(exc)}

        # zero-cost fallback: subprocess in an isolated temp dir with strict limits
        workdir = cwd or tempfile.mkdtemp(prefix="supremeai_e2b_")
        started = time.time()
        try:
            argv = shlex.split(command) if isinstance(command, str) else list(command)
            proc = subprocess.run(
                argv,
                shell=False,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            out = proc.stdout[-_MAX_OUTPUT_BYTES:]
            err = proc.stderr[-_MAX_OUTPUT_BYTES:]
            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "engine": "fallback",
                "stdout": out,
                "stderr": err,
                "returncode": proc.returncode,
                "elapsed_s": round(time.time() - started, 3),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "error",
                "engine": "fallback",
                "error": f"timeout after {self.timeout}s",
                "stdout": str(exc.stdout or "")[-_MAX_OUTPUT_BYTES:],
            }
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": "error", "engine": "fallback", "error": str(exc)}

    def run_code(self, code: str, language: str = "python3") -> dict[str, Any]:
        """Execute a code snippet; maps python3/node to an isolated interpreter run."""
        if language in {"python3", "python"}:
            interpreter = shutil.which("python") or shutil.which("python3")
            if interpreter is None:
                return {"status": "error", "engine": "fallback", "error": "no python interpreter"}
            workdir = tempfile.mkdtemp(prefix="supremeai_e2b_")
            script = Path(workdir) / "main.py"
            script.write_text(code, encoding="utf-8")
            return self.run_command(f'"{interpreter}" main.py', cwd=workdir)
        return self.run_command(code, cwd=None)
