import asyncio

from core.logging_config import logger


class CliProcessDelegator:
    """বাংলা মন্তব্য: Cohesion আপগ্রেড — এক্সটার্নাল CLI সাবপ্রসেস ও প্রসেস ডেলিগেশনের একক দায়িত্ব।"""

    def __init__(self, binary_path: str = "freebuff"):
        self.binary_path = binary_path

    async def delegate_task(self, command_args: list) -> dict:
        logger.info(f"📡 Delegating asynchronous workload to external CLI tool: {self.binary_path}")
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                *command_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
            }
        except Exception as e:
            logger.error(f"🔴 CLI execution failed: {e!s}")
            return {"success": False, "error": str(e)}


# Canonical alias for backward compatibility
FreebuffClient = CliProcessDelegator
