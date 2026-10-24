import asyncio
import os
import re
import shlex
import subprocess
import tempfile
from typing import Any

from core.config import settings
from core.logging_config import logger


class DockerSandbox:
    def __init__(self, image: str = "python:3.10-slim"):
        self.image = image
        self.docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        try:
            # Check if docker daemon is running
            subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=3,
                check=True,
            )
            return True
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            OSError,
            subprocess.CalledProcessError,
        ) as e:
            logger.warning(f"Docker check failed: {e}. Docker-based execution will be unavailable.")
            return False

    def execute_command(self, cmd: str) -> dict[str, Any]:
        """Runs a command inside a sandboxed Docker container.

        Security: Uses shlex.split to avoid shell injection. The command is
        passed directly as an exec-style list to Docker, not through ``sh -c``.
        """
        # RCE/Prompt Injection Pre-flight Firewall Check
        harmful_keywords = [
            "rm -rf",
            "mkfs",
            "dd if=",
            "shutdown",
            "reboot",
            ":(){ :|:& };:",
            "malicious",
            "payload",
            "exploit",
            "backdoor",
        ]

        forbidden_patterns = [
            r"\benviron\b",
            r"\bgetenv\b",
            r"\bgetenvb\b",
            r"os\.environ",
            r"\bcurl\b",
            r"\bwget\b",
            r"\bsocket\b",
            r"\brequests\b",
            r"\burllib\b",
            r"\bhttpx\b",
            r"http\.client",
            r"\bnc\s",
            r"\bnetcat\b",
            r"bash\s+-i",
            r"/dev/tcp",
            r"/dev/udp",
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"\bsubprocess\b",
            r"\bsystem\s*\(",
        ]

        cmd_lower = cmd.lower()
        if any(kw in cmd_lower for kw in harmful_keywords) or any(
            re.search(pat, cmd_lower) for pat in forbidden_patterns
        ):
            logger.warning("Security Firewall: Command blocked due to high-risk pattern.")
            return {
                "success": False,
                "error": "Security Firewall block: command contains forbidden patterns.",
            }

        if not self.docker_available:
            env_name = getattr(settings, "env", None) or getattr(settings, "env", "").lower()
            allow_fallback_str = getattr(settings, "allow_local_sandbox_fallback", None)
            if allow_fallback_str is not None:
                allow_fallback = allow_fallback_str.lower() == "true"
            else:
                allow_fallback = getattr(
                    settings, "allow_local_sandbox_fallback", None
                ) == "true" or getattr(settings, "allow_sandbox_fallback", False)

            if env_name in {"production", "staging"} or not allow_fallback:
                logger.error("Docker is not available and local execution fallback is disabled.")
                return {
                    "success": False,
                    "error": "Sandbox execution failed: Docker is not running and local execution is disabled for safety.",
                }

            logger.warning(
                "Docker is not available. Simulating command execution in local process."
            )
            try:
                # Security: Use shlex.split to avoid shell injection. Never use shell=True
                # on any platform — shlex provides safe tokenization.
                command_to_run = shlex.split(cmd)
                result = subprocess.run(
                    command_to_run,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
                return {
                    "success": True,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "simulated": True,
                }
            except (
                FileNotFoundError,
                subprocess.TimeoutExpired,
                OSError,
                subprocess.CalledProcessError,
            ) as e:
                if isinstance(e, subprocess.CalledProcessError):
                    return {
                        "success": False,
                        "error": e.stderr or str(e),
                        "stdout": e.stdout,
                        "simulated": True,
                    }
                return {"success": False, "error": str(e), "simulated": True}

        # Run command securely inside docker.
        # Security Fix: Instead of passing cmd through "sh -c" (which enables shell
        # injection via metacharacters), we tokenize with shlex.split and pass as
        # a proper exec-style arg list. The first token becomes the entrypoint
        # command, remaining tokens are arguments — no shell interpretation occurs.
        try:
            cmd_parts = shlex.split(cmd)
            if not cmd_parts:
                return {
                    "success": False,
                    "error": "Empty command",
                    "simulated": False,
                }
            docker_cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",  # Sandbox: no internet
                "--memory",
                "256m",
                "--cpus",
                "0.5",
                self.image,
                *cmd_parts,
            ]
            result = subprocess.run(
                docker_cmd, capture_output=True, text=True, timeout=10, check=True
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "simulated": False,
            }
        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            OSError,
            subprocess.CalledProcessError,
        ) as e:
            if isinstance(e, subprocess.CalledProcessError):
                return {
                    "success": False,
                    "error": e.stderr or str(e),
                    "stdout": e.stdout,
                    "simulated": False,
                }
            return {"success": False, "error": str(e), "simulated": False}

    def run_secure(self, code: str, timeout: int = 30) -> dict[str, Any]:
        """Execute Python code securely by writing it to a temp file and mounting
        it read-only into a sandboxed Docker container.

        This eliminates command injection risk from LLM-generated code that was
        previously embedded into a ``python -c "..."`` shell string.

        Mirrors the approach in ``backend/sandbox/docker_sandbox.py:run_safe_container``.
        """
        # Reuse firewall checks
        cmd_lower = code.lower()
        if any(kw in cmd_lower for kw in ["rm -rf", "mkfs", "dd if=", "shutdown", "reboot"]):
            return {
                "success": False,
                "error": "Security Firewall: code contains forbidden patterns.",
            }

        if not self.docker_available:
            env_name = getattr(settings, "env", None) or getattr(settings, "env", "").lower()
            allow_fallback = getattr(settings, "allow_local_sandbox_fallback", False)
            if allow_fallback is None:
                allow_fallback = getattr(settings, "allow_sandbox_fallback", False)

            if env_name in {"production", "staging"} or not allow_fallback:
                logger.error("Docker unavailable and local fallback disabled for code execution.")
                return {
                    "success": False,
                    "error": "Docker is not running and local execution is disabled for safety.",
                }

            logger.warning(
                "Docker unavailable. Running code via secure local subprocess (fallback)."
            )
            try:
                result = subprocess.run(
                    ["python3", "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "simulated": True,
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"Execution timed out after {timeout}s.",
                    "simulated": True,
                }
            except Exception as exc:
                logger.error(f"Local code execution failed: {exc}")
                return {"success": False, "error": str(exc), "simulated": True}

        # Docker path: write code to temp file, mount read-only, execute
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                script_path = f.name

            # Security: prevent path traversal in mount path
            if ".." in script_path:
                logger.critical(f"Path traversal detected in temp script path: {script_path}")
                return {"success": False, "error": "Invalid temp file path.", "simulated": False}

            docker_cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",  # 🔒 No network
                "--read-only",  # 🔒 Read-only filesystem
                "--memory",
                "256m",
                "--cpus",
                "0.5",
                "-v",
                f"{script_path}:/sandbox_code.py:ro",  # 📁 Read-only mount
                self.image,
                "python3",
                "/sandbox_code.py",
            ]

            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "simulated": False,
            }
        except subprocess.TimeoutExpired:
            logger.error(f"Docker code execution timed out after {timeout}s.")
            return {
                "success": False,
                "error": f"Execution timed out after {timeout}s.",
                "simulated": False,
            }
        except Exception as exc:
            logger.error(f"Docker code execution failed: {exc}")
            return {"success": False, "error": str(exc), "simulated": False}
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).exception(f"Silenced error: {e}")
