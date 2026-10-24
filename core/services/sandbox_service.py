import asyncio
from typing import Any

from docker.errors import ContainerError

import docker
from core.logging_config import logger


class SandboxService:
    """
    Server-side Docker sandbox for executing heavy data analysis or GitHub tasks.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.active_sandboxes: dict[str, dict[str, Any]] = {}
        try:
            self.client = docker.from_env()
            logger.info("Docker client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self.client = None

    def create_sandbox(self, task_id: str, language: str = "python") -> str:
        """Create and track a new sandbox instance."""
        import uuid

        sandbox_id = f"sb_{uuid.uuid4().hex[:8]}"
        self.active_sandboxes[sandbox_id] = {
            "id": sandbox_id,
            "task_id": task_id,
            "language": language,
            "status": "created",
        }
        return sandbox_id

    def execute(self, sandbox_id: str, code: str) -> dict[str, Any]:
        """Execute code in a sandbox (synchronous helper wrapper).

        Issue #446/#448 doctrine (real work or loud failure, never fabricated
        success): the old implementation returned a fabricated
        ``status: SUCCESS`` with fake stdout without executing anything.
        Real execution lives in :meth:`execute_in_docker` (requires a Docker
        daemon); this wrapper now reports an honest NOT_EXECUTED result and
        never claims success it did not earn.
        """
        sandbox = self.active_sandboxes.get(sandbox_id)
        if not sandbox:
            return {"status": "FAILED", "error": "Sandbox not found"}
        if self.client is None:
            logger.warning(
                "SandboxService.execute refused: Docker daemon unavailable — "
                "code was NOT executed (honest failure, issue #446)."
            )
            return {
                "status": "NOT_EXECUTED",
                "error": "SANDBOX_RUNTIME_UNAVAILABLE",
                "message": (
                    "No Docker runtime is available on this instance, so the code "
                    "was not executed. Use execute_in_docker() on a Docker-capable "
                    "host or configure a remote sandbox provider."
                ),
                "sandbox_id": sandbox_id,
            }
        logger.warning(
            "SandboxService.execute is a metadata-only wrapper and does not run "
            "code — use execute_in_docker() for real execution (issue #446)."
        )
        return {
            "status": "NOT_EXECUTED",
            "error": "MOCK_NOT_EXECUTED",
            "message": (
                "This wrapper never executes code. Real execution requires "
                "execute_in_docker() with a healthy Docker daemon."
            ),
            "sandbox_id": sandbox_id,
        }

    def destroy(self, sandbox_id: str) -> bool:
        """Destroy and remove a sandbox instance."""
        if sandbox_id in self.active_sandboxes:
            del self.active_sandboxes[sandbox_id]
            return True
        return False

    def list_sandboxes(self) -> list[dict[str, Any]]:
        """List all active sandbox metadata dicts."""
        return list(self.active_sandboxes.values())

    def get_sandbox(self, sandbox_id: str) -> dict[str, Any] | None:
        """Get sandbox metadata dict if exists."""
        return self.active_sandboxes.get(sandbox_id)

    async def execute_in_docker(self, code: str, language: str = "python") -> dict[str, Any]:
        """
        Executes code in an isolated Docker container with strict timeouts
        to prevent infinite loops.
        """
        if not self.client:
            return {
                "status": "FAILED",
                "stdout": "",
                "stderr": "Docker is not running or accessible.",
                "execution_time_ms": 0,
            }

        logger.info(f"Executing {language} code in Docker Sandbox (timeout: {self.timeout}s)...")

        image = "python:3.11-slim"
        if language != "python":
            return {
                "status": "FAILED",
                "stderr": f"Unsupported language: {language}",
                "execution_time_ms": 0,
            }

        start_time = asyncio.get_event_loop().time()

        try:
            # Run blocking docker call in thread pool to not block asyncio
            loop = asyncio.get_event_loop()

            def run_container():
                return self.client.containers.run(
                    image,
                    command=["python", "-c", code],
                    remove=True,
                    stderr=True,
                    stdout=True,
                    mem_limit="128m",
                    network_mode="none",  # Strict isolation
                    # In python docker SDK, timeout is handled via wait() or similar,
                    # but here we rely on asyncio.wait_for
                )

            # Execute with timeout
            output_bytes = await asyncio.wait_for(
                loop.run_in_executor(None, run_container), timeout=self.timeout
            )

            execution_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return {
                "status": "SUCCESS",
                "stdout": (
                    output_bytes.decode("utf-8")
                    if isinstance(output_bytes, bytes)
                    else str(output_bytes)
                ),
                "stderr": "",
                "execution_time_ms": execution_time,
            }

        except TimeoutError:
            logger.error(f"Execution exceeded timeout of {self.timeout}s")
            return {
                "status": "TIMEOUT",
                "stdout": "",
                "stderr": f"Execution exceeded {self.timeout}s timeout.",
                "execution_time_ms": int((asyncio.get_event_loop().time() - start_time) * 1000),
            }
        except ContainerError as e:
            logger.error(f"Container execution error: {e}")
            return {
                "status": "FAILED",
                "stdout": "",
                "stderr": (str(e.stderr.decode("utf-8")) if getattr(e, "stderr", None) else str(e)),
                "execution_time_ms": int((asyncio.get_event_loop().time() - start_time) * 1000),
            }
        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {
                "status": "FAILED",
                "stdout": "",
                "stderr": str(e),
                "execution_time_ms": int((asyncio.get_event_loop().time() - start_time) * 1000),
            }


sandbox_service = SandboxService()
