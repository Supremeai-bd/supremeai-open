"""This module provides real-time memory auditing for Docker containers within the SupremeAI ecosystem. It proactively monitors container resource usage, issuing warnings when memory utilization approaches 80% and automatically triggering a termination "kill chain" for containers exceeding 95% memory usage to prevent Out-Of-Memory (OOM) abuse and ensure system stability in a highly scalable environment.

Key Components:
- `ContainerAuditor`: Manages the continuous monitoring and enforcement of memory limits for Docker containers.
- `get_container_stats()`: Retrieves real-time memory and other statistics for all running Docker containers.
- `parse_memory_percent()`: Converts a memory percentage string into a float for numerical comparison.
- `audit_cycle()`: Executes a single round of container memory checks, logging warnings or initiating container termination as needed.
- `run()`: Starts the continuous asynchronous loop for periodic container auditing.
- `stop()`: Signals the continuous audit loop to gracefully terminate.

Dependencies:
- `asyncio`: For asynchronous programming and running blocking operations in a separate thread.
- `json`: For parsing JSON output from Docker commands.
- `subprocess`: For executing external Docker commands like `docker stats` and `docker kill`.
- `loguru`: For structured and colored logging throughout the auditing process.
- `core.messaging.event_bus`: For emitting standardized error and warning events to the system's central event bus."""

import asyncio
import json
import subprocess

from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus


class ContainerAuditor:
    """বাংলা মন্তব্য: রিয়েল-টাইম কন্টেইনার মেমরি অডিট।
    OOM অ্যাবিউস ঠেকাতে ৮০% এ অ্যালার্ট এবং ৯৫% এ কিল চেইন ট্রিগার করবে।
    Stateless invocation for Cron, no while sleep loop."""

    def __init__(self, check_interval_seconds: int = 30):
        self.check_interval_seconds = check_interval_seconds
        self.running = False

    def get_container_stats(self) -> list:
        try:
            cmd = ["docker", "stats", "--no-stream", "--format", "{{ json . }}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            if result.returncode != 0:
                logger.error(f"Failed to fetch docker stats: {result.stderr}")
                error_event_bus.emit(
                    ErrorEvent(
                        module="container_auditor",
                        error_type="DOCKER_STATS_FAILED",
                        message=result.stderr[:200],
                        severity="WARNING",
                        structured_context=ErrorContext(module="auto_fixed"),
                    )
                )
                return []

            stats = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    stats.append(json.loads(line))
            return stats
        except Exception as e:
            logger.error(f"Error executing docker stats: {e}")
            error_event_bus.emit(
                ErrorEvent(
                    module="container_auditor",
                    error_type="DOCKER_STATS_EXEC_ERROR",
                    message=str(e)[:200],
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                )
            )
            return []

    def parse_memory_percent(self, mem_perc_str: str) -> float:
        try:
            return float(mem_perc_str.replace("%", "").strip())
        except ValueError:
            return 0.0

    async def audit_cycle(self):
        """Single stateless audit cycle"""
        logger.info("🛡️ Running Container Audit Cycle...")
        try:
            stats = await asyncio.to_thread(self.get_container_stats)
            for container in stats:
                name = container.get("Name")
                mem_perc_str = container.get("MemPerc", "0.00%")
                mem_perc = self.parse_memory_percent(mem_perc_str)

                if mem_perc >= 95.0:
                    logger.error(
                        f"🚨 OOM Kill Chain Triggered: Container {name} is at {mem_perc}%. Terminating..."
                    )
                    try:
                        subprocess.run(
                            ["docker", "kill", name],
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
                    except Exception as e:
                        logger.error(f"Failed to kill container {name}: {e}")
                        error_event_bus.emit(
                            ErrorEvent(
                                module="container_auditor",
                                error_type="DOCKER_KILL_FAILED",
                                message=str(e)[:200],
                                severity="CRITICAL",
                                structured_context=ErrorContext(module="auto_fixed"),
                                context={"container_name": name},
                            )
                        )
                elif mem_perc >= 80.0:
                    logger.warning(
                        f"⚠️ Memory Warning: Container {name} is nearing capacity at {mem_perc}%."
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in container audit cycle: {e}")
            error_event_bus.emit(
                ErrorEvent(
                    module="container_auditor",
                    error_type="AUDIT_CYCLE_FAILED",
                    message=str(e)[:200],
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                )
            )

    async def run(self):
        """বাংলা মন্তব্য: Continuous audit loop — Cron-এর পরিবর্তে asyncio loop ব্যবহার করে।"""
        self.running = True
        while self.running:
            try:
                await self.audit_cycle()
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                self.running = False
                raise
            except Exception as e:
                logger.error(f"Container audit cycle failed: {e}")
                error_event_bus.emit(
                    ErrorEvent(
                        module="container_auditor",
                        error_type="AUDIT_LOOP_FAILED",
                        message=str(e)[:200],
                        severity="ERROR",
                        structured_context=ErrorContext(module="auto_fixed"),
                    )
                )
                self.running = False

    def stop(self):
        """বাংলা মন্তব্য: Audit loop বন্ধ করার জন্য signal."""
        self.running = False


if __name__ == "__main__":
    auditor = ContainerAuditor()
    asyncio.run(auditor.audit_cycle())
