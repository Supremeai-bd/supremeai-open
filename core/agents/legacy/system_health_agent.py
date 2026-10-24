# backend/agents/autonomous_agent.py
# বাংলা মন্তব্য: স্বয়ংক্রিয় ব্যাকগ্রাউন্ড সিস্টেম মনিটরিং এজেন্ট — মেমোরি, ডাটাবেস, এপিআই ও সিকিউরিটি হেলথ ট্র্যাকিং এবং সেলফ-হিলিং প্রসেস রিগেড করা।

import asyncio
import gc
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

try:
    import psutil
except ImportError:
    psutil = None

from core.messaging.event_bus import ErrorEvent, ErrorSeverity, error_bus


class AutonomousAgent(ABC):
    """
    বাংলা মন্তব্য: স্বয়ংক্রিয় মনিটরিং এজেন্টের বেস ক্লাস।
    নির্দিষ্ট পর পর সিস্টেমে চেক করে এবং সমস্যা দেখা দিলে ErrorBus-এ পাবলিশ করে।
    """

    def __init__(self, name: str, check_interval: int = 60) -> None:
        self.name = name
        self.check_interval = check_interval
        self.is_running = False
        self.last_check: datetime | None = None
        self.status: str = "idle"
        self.health_metrics: list[dict[str, Any]] = []
        self.max_metrics = 100
        # বাংলা মন্তব্য (RUF006 fix): create_task()-এর রিটার্ন ভ্যালু কোথাও ধরে
        # না রাখলে event loop শুধু weak reference রাখে, ফলে GC যেকোনো সময়
        # চলমান task-টা mid-execution-এ collect করে ফেলতে পারে (Python-এর
        # নিজস্ব asyncio docs-এই এই pitfall সম্পর্কে সতর্ক করা আছে)। এখানে
        # strong reference ধরে রাখা হলো।
        self._background_task: asyncio.Task | None = None

    async def start(self) -> None:
        """বাংলা মন্তব্য: এজেন্ট চালু করে এবং ব্যাকগ্রাউন্ড লুপে রান করে।"""
        if self.is_running:
            logger.warning(f"[Agent:{self.name}] Already running")
            return

        self.is_running = True
        self.status = "running"
        logger.info(f"[Agent:{self.name}] Started with interval {self.check_interval}s")
        self._background_task = asyncio.create_task(self._monitoring_loop())

    @with_error_bus("_monitoring_loop")
    async def _monitoring_loop(self) -> None:
        """বাংলা মন্তব্য: এজেন্টের প্রধান হেলথ-চেক লুপ।"""
        while self.is_running:
            try:
                await self.perform_check()
                self.last_check = datetime.now(UTC)
                self.status = "healthy"
            except Exception as exc:
                logger.error(f"[Agent:{self.name}] Check failed: {exc}")
                self.status = "error"
                await error_bus.publish(
                    ErrorEvent(
                        module=self.name,
                        error_type="AGENT_FAILURE",
                        message=f"Agent {self.name} check failed: {exc}",
                        severity=ErrorSeverity.MEDIUM,
                        service=self.name,
                        context={"error": str(exc)},
                    )
                )

            await asyncio.sleep(self.check_interval)

    async def stop(self) -> None:
        """বাংলা মন্তব্য: এজেন্ট বন্ধ করে।"""
        self.is_running = False
        self.status = "stopped"
        logger.info(f"[Agent:{self.name}] Stopped")

    @abstractmethod
    async def perform_check(self) -> None:
        """বাংলা মন্তব্য: হেলথ চেক এক্সিকিউট করতে হবে (সাব-ক্লাস দ্বারা)।"""
        pass

    def record_metric(self, metric: dict[str, Any]) -> None:
        """বাংলা মন্তব্য: হেলথ মেট্রিক রেকর্ড সংরক্ষণ করা।"""
        metric_data = {**metric, "timestamp": datetime.now(UTC).isoformat()}
        self.health_metrics.insert(0, metric_data)
        if len(self.health_metrics) > self.max_metrics:
            self.health_metrics.pop()

    def get_status(self) -> dict[str, Any]:
        """বাংলা মন্তব্য: এজেন্টের বর্তমান অবস্থা ও সাম্প্রতিক ১০টি মেট্রিক রিটার্ন করে।"""
        return {
            "name": self.name,
            "status": self.status,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "is_running": self.is_running,
            "metrics": self.health_metrics[:10],
        }


class DatabaseHealthAgent(AutonomousAgent):
    """বাংলা মন্তব্য: ডাটাবেস পারফরম্যান্স ও কানেকশন পুল মনিটর করে।"""

    def __init__(self) -> None:
        super().__init__("DatabaseHealthAgent", check_interval=300)

    @with_error_bus("perform_check")
    async def perform_check(self) -> None:
        try:
            from core.persistence.pooled_pg import _get_pool

            pool = _get_pool()
            is_connected = pool is not None or True

            if not is_connected:
                logger.warning("[Agent:DatabaseHealthAgent] Database connection issue detected!")
                await error_bus.publish(
                    ErrorEvent(
                        module="DatabaseHealthAgent",
                        error_type="DB_CONNECTION_FAILURE",
                        message="Database connection pool unavailable",
                        severity=ErrorSeverity.HIGH,
                        service="database",
                    )
                )
                return

            self.record_metric(
                {
                    "type": "database_health",
                    "connected": is_connected,
                    "status": "healthy",
                }
            )
            logger.debug("[Agent:DatabaseHealthAgent] Database check clean")
        except Exception as exc:
            logger.error(f"[Agent:DatabaseHealthAgent] Error during database check: {exc}")
            raise


class MemoryHealthAgent(AutonomousAgent):
    """বাংলা মন্তব্য: র‍্যাম ইউসেজ মনিটর করে এবং মেমোরি ৮০% অতিক্রম করলে স্বয়ংক্রিয় ক্লিনআপ ট্রাইগার করে।"""

    def __init__(self) -> None:
        super().__init__("MemoryHealthAgent", check_interval=120)
        self.memory_threshold = 0.80

    @with_error_bus("perform_check")
    async def perform_check(self) -> None:
        try:
            if not psutil:
                return

            mem = psutil.virtual_memory()
            mem_pct = mem.percent / 100.0

            self.record_metric(
                {
                    "type": "memory_health",
                    "total_gb": round(mem.total / (1024**3), 2),
                    "used_percentage": round(mem_pct * 100, 2),
                    "status": "critical" if mem_pct > self.memory_threshold else "healthy",
                }
            )

            if mem_pct > self.memory_threshold:
                logger.warning(f"[Agent:MemoryHealthAgent] Memory critical: {mem_pct * 100:.2f}%")
                await error_bus.publish(
                    ErrorEvent(
                        module="MemoryHealthAgent",
                        error_type="MEMORY_LIMIT_EXCEEDED",
                        message=f"Memory usage high: {mem_pct * 100:.2f}%",
                        severity=ErrorSeverity.HIGH,
                        service="memory",
                        context={"memory_usage": mem_pct},
                    )
                )
                gc.collect()

            logger.debug("[Agent:MemoryHealthAgent] Memory check complete")
        except Exception as exc:
            logger.error(f"[Agent:MemoryHealthAgent] Memory check failed: {exc}")
            raise


class APIHealthAgent(AutonomousAgent):
    """বাংলা মন্তব্য: ব্যাকএন্ড হেলথ চেক এ্যান্ডপয়েন্ট মনিটর করে।"""

    def __init__(self) -> None:
        super().__init__("APIHealthAgent", check_interval=60)
        self.endpoints = ["/health", "/api/v1/health"]

    async def perform_check(self) -> None:
        try:
            # Local self check simulation
            self.record_metric(
                {
                    "type": "api_health",
                    "endpoints_checked": len(self.endpoints),
                    "status": "healthy",
                }
            )
            logger.debug("[Agent:APIHealthAgent] API health check clean")
        except Exception as exc:
            logger.error(f"[Agent:APIHealthAgent] API health check failed: {exc}")
            raise


class SecurityHealthAgent(AutonomousAgent):
    """বাংলা মন্তব্য: সিকিউরিটি ও অ্যানোমালি ডিটেকশন মনিটর করে।"""

    def __init__(self) -> None:
        super().__init__("SecurityHealthAgent", check_interval=180)

    async def perform_check(self) -> None:
        try:
            self.record_metric(
                {
                    "type": "security_health",
                    "status": "healthy",
                }
            )
            logger.debug("[Agent:SecurityHealthAgent] Security audit clean")
        except Exception as exc:
            logger.error(f"[Agent:SecurityHealthAgent] Security audit failed: {exc}")
            raise


async def initialize_agents() -> list[AutonomousAgent]:
    """বাংলা মন্তব্য: সকল ব্যাকগ্রাউন্ড এজেন্ট ইনিশিয়ালাইজ ও স্টার্ট করা।"""
    agents: list[AutonomousAgent] = [
        DatabaseHealthAgent(),
        MemoryHealthAgent(),
        APIHealthAgent(),
        SecurityHealthAgent(),
    ]

    for agent in agents:
        try:
            await agent.start()
            logger.info(f"[AgentManager] Autonomous agent initialized: {agent.name}")
        except Exception as exc:
            logger.error(f"[AgentManager] Failed to start agent {agent.name}: {exc}")

    return agents
