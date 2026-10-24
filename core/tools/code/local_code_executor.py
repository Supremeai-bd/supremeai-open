import asyncio

from core.config import settings
from core.logging_config import logger
from tools.devops.docker_sandbox import (
    DockerSandbox,  # আমাদের এক্সিস্টিং সুনির্দিষ্ট টুল
)


class LocalCodeExecutor:
    """বাংলা মন্তব্য: Cohesion আপগ্রেড — লোকাল ডকার ও সাবপ্রসেস এক্সিকিউশনের একক দায়িত্ব।"""

    def __init__(self, use_docker: bool = True):
        self.use_docker = use_docker
        self.docker_sandbox = DockerSandbox() if use_docker else None

    async def execute_local_code(self, code: str, timeout_seconds: int = 30) -> dict:
        """Execute code via Docker sandbox (or secure host fallback in dev).

        বাংলা (M06 P-A ৮/৮ RunType adoption): প্রতিটি code-নির্বাহ ক্যানোনিকাল
        ``run_type="code"`` রান হিসেবেও পর্যবেক্ষিত (flag-gated, best-effort);
        production security-refusal সহ ``success=False``-ই রান-ব্যর্থতার সত্য।
        """
        from runs.run_scope import observe_run

        async with observe_run(
            run_type="code",
            title=f"code:{code[:60]!r}",
            source_type="code",
        ) as run_ctx:
            result = await self._execute_local_code_impl(code, timeout_seconds)
            if run_ctx is not None and result.get("success") is False:
                run_ctx.finish("failed")
            return result

    async def _execute_local_code_impl(self, code: str, timeout_seconds: int = 30) -> dict:
        """Original execute_local_code body — run-observation wrapper-এর ভিতরে চলে।"""
        env = getattr(settings, "env", "development").lower()

        if self.use_docker and self.docker_sandbox:
            try:
                logger.info("🐳 Running code inside tight Docker Sandbox Container...")
                if hasattr(self.docker_sandbox, "run_secure"):
                    res = await self.docker_sandbox.run_secure(code, timeout=timeout_seconds)
                    if res and (
                        res.get("success") or (isinstance(res, dict) and "success" not in res)
                    ):
                        if "stdout" in res and "output" not in res:
                            res["output"] = res["stdout"]
                        if "stderr" in res and "error" not in res:
                            res["error"] = res["stderr"]
                        return res
            except Exception as exc:
                logger.warning(f"🐳 Docker execution failure: {exc}")

        if env == "production":
            return {
                "success": False,
                "error": "CRITICAL SECURITY: Host subprocess execution is strictly disabled in production.",
                "stderr": "CRITICAL SECURITY: Host subprocess execution is strictly disabled in production.",
                "stdout": "",
                "output": "",
            }

        logger.info("🔌 Falling back to secure Host Subprocess execution layer...")
        return await self._run_host_subprocess(code, timeout_seconds)

    async def _run_host_subprocess(self, code: str, timeout: int) -> dict:
        logger.warning("⚠️ CRITICAL SECURITY NOTE: Running code directly on Host Subprocess!")
        try:
            from tools.code.fuzz_sandbox import run_sandbox_ast_check

            if not run_sandbox_ast_check(code):
                return {
                    "success": False,
                    "error": "Host execution blocked: Code failed AST security layout check.",
                }

            # অসিঙ্ক্রোনাসভাবে লোকাল হোস্ট প্রসেস এক্সিকিউট করা হচ্ছে
            proc = await asyncio.create_subprocess_exec(
                "python",
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "output": stdout.decode().strip(),
                "error": stderr.decode().strip(),
            }
        except TimeoutError:
            logger.error("🔴 Host subprocess timed out!")
            return {"success": False, "error": "Execution TimeoutExpired"}
