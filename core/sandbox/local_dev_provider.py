"""backend.core.sandbox.local_dev_provider
=========================================
Local development process executor.

CRITICAL ARCHITECTURAL WARNING:
This provider uses local subprocess execution and is strictly intended for
local/offline development and test harnesses. It is NOT a security boundary
and MUST NOT be treated as a trusted sandbox for arbitrary untrusted code in production.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from core.logging_config import logger
from core.sandbox.base import ExecutionResult, SandboxConfig, SandboxProvider


class LocalDevSandboxProvider(SandboxProvider):
    """Development-only local process runner with resource limits and secret stripping."""

    @property
    def provider_name(self) -> str:
        return "local_dev"

    @property
    def is_trusted_boundary(self) -> bool:
        # Honest security posture: subprocess isolation on the host is NOT a trusted boundary
        return False

    async def health_check(self) -> bool:
        """Local python/node runtime check."""
        return bool(sys.executable and os.path.exists(sys.executable))

    async def execute(
        self,
        code: str,
        language: str = "python",
        config: SandboxConfig | None = None,
    ) -> ExecutionResult:
        cfg = config or SandboxConfig()

        if language.lower() not in cfg.allowed_languages:
            return ExecutionResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr=f"Language '{language}' is not allowed by sandbox policy. Allowed: {cfg.allowed_languages}",
                duration_ms=0,
                provider_metadata={"provider": self.provider_name},
            )

        start_time = time.perf_counter()
        sanitized_env = cfg.sanitize_environment()

        with tempfile.TemporaryDirectory(prefix="supremeai_sandbox_") as tmp_dir:
            file_name = "script.py" if language.lower() == "python" else "script.js"
            script_path = Path(tmp_dir) / file_name
            script_path.write_text(code, encoding="utf-8")

            if language.lower() == "python":
                cmd = [sys.executable, str(script_path)]
            elif language.lower() in ("javascript", "node"):
                node_bin = shutil.which("node") or "node"
                cmd = [node_bin, str(script_path)]
            elif language.lower() == "bash":
                bash_bin = shutil.which("bash") or "bash"
                cmd = [bash_bin, str(script_path)]
            else:
                return ExecutionResult(
                    success=False,
                    exit_code=1,
                    stdout="",
                    stderr=f"Unsupported runtime executable for language: {language}",
                    duration_ms=0,
                )

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmp_dir,
                    env=sanitized_env,
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=float(cfg.timeout_seconds),
                    )
                    timed_out = False
                except TimeoutError:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                    stdout_bytes, stderr_bytes = await proc.communicate()
                    timed_out = True

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                stdout_text = stdout_bytes.decode("utf-8", errors="replace")[: cfg.max_output_bytes]
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")[: cfg.max_output_bytes]

                if timed_out:
                    stderr_text += f"\n[Execution Timed Out after {cfg.timeout_seconds}s]"

                exit_code = proc.returncode if proc.returncode is not None else -1

                return ExecutionResult(
                    success=(exit_code == 0 and not timed_out),
                    exit_code=exit_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    duration_ms=duration_ms,
                    timed_out=timed_out,
                    resource_exceeded=False,
                    provider_metadata={
                        "provider": self.provider_name,
                        "trusted_boundary": self.is_trusted_boundary,
                    },
                )

            except Exception as exc:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning("LocalDevSandbox execution failed with exception: %s", exc)
                return ExecutionResult(
                    success=False,
                    exit_code=1,
                    stdout="",
                    stderr=f"Execution error: {exc}",
                    duration_ms=duration_ms,
                    provider_metadata={"provider": self.provider_name, "error": str(exc)},
                )
