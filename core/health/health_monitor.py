import asyncio
import time
from typing import Any

from core.logging_config import logger
from services.config_service import ConfigService

try:
    from prometheus_client import Gauge, Histogram, start_http_server

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


class HealthMonitor:
    """
    Monitors system health with Prometheus metrics export for Grafana dashboards.
    """

    def __init__(self, metrics_port: int = 9090):
        self.start_time = time.time()
        self.cpu_threshold = 85.0
        self.mem_threshold = 90.0
        self.metrics_port = metrics_port
        # বাংলা মন্তব্য: কাস্টম প্রোবস রেজিস্টার করার জন্য ডিকশনারি
        self.probes: dict[str, Any] = {}
        if _PROMETHEUS_AVAILABLE:
            self._setup_metrics()
            try:
                start_http_server(metrics_port)
                logger.info(f"Prometheus metrics server started on port {metrics_port}")
            except OSError as exc:
                logger.warning(f"Could not start metrics server: {exc}")

    def register_probe(self, name: str, probe_fn: Any) -> None:
        """Register a custom health check probe."""
        # বাংলা মন্তব্য: কাস্টম হেলথ চেক প্রোব রেজিস্টার করার জন্য
        self.probes[name] = probe_fn

    async def sync_from_db(self, db: Any) -> None:
        """Sync health thresholds from the database configuration."""
        try:
            default_config = {
                "cpu_threshold": self.cpu_threshold,
                "mem_threshold": self.mem_threshold,
            }
            configs = await ConfigService.get_config(
                db, "health_monitor_thresholds", default_config
            )
            if configs:
                self.cpu_threshold = float(configs.get("cpu_threshold", self.cpu_threshold))
                self.mem_threshold = float(configs.get("mem_threshold", self.mem_threshold))
                logger.info(
                    f"✅ Synced health_monitor_thresholds from DB. CPU={self.cpu_threshold}, Mem={self.mem_threshold}"
                )
        except Exception as e:
            logger.error(f"❌ Failed to sync health_monitor_thresholds from DB: {e}")

    def _setup_metrics(self):
        self.uptime_seconds = Gauge("supremeai_uptime_seconds", "Server uptime in seconds")
        self.cpu_usage_percent = Gauge("supremeai_cpu_usage_percent", "CPU usage percentage")
        self.memory_usage_percent = Gauge(
            "supremeai_memory_usage_percent", "Memory usage percentage"
        )
        self.memory_available_mb = Gauge("supremeai_memory_available_mb", "Available memory in MB")
        self.request_duration_seconds = Histogram(
            "supremeai_request_duration_seconds",
            "HTTP request latency in seconds",
            buckets=[0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.5, 5.0],
        )
        self.active_tasks = Gauge("supremeai_active_tasks", "Number of active asyncio tasks")
        self.status = Gauge("supremeai_health_status", "Health status (1=healthy, 0=degraded)")
        try:
            from prometheus_client import Counter

            self.error_count = Counter(
                "supremeai_errors_total", "Total error occurrences", ["error_type"]
            )
            self.token_usage = Counter(
                "supremeai_tokens_total", "Total tokens processed", ["provider", "type"]
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize optional Prometheus counters: {exc}")

    async def get_system_metrics(self) -> dict[str, Any]:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        status = "healthy"
        if cpu_percent > self.cpu_threshold or mem.percent > self.mem_threshold:
            status = "degraded"

        # বাংলা মন্তব্য: রেজিস্টার্ড কাস্টম প্রোবস সম্পাদন করা হচ্ছে
        probe_results = {}
        for name, fn in self.probes.items():
            try:
                res = fn()
                if asyncio.iscoroutine(res):
                    res = await res
                probe_results[name] = res
            except Exception as e:
                probe_results[name] = {"status": "error", "message": str(e)}

        result = {
            "status": status,
            "uptime_seconds": int(time.time() - self.start_time),
            "cpu_usage_percent": cpu_percent,
            "memory_usage_percent": mem.percent,
            "memory_available_mb": mem.available / (1024 * 1024),
            "active_tasks": len(asyncio.all_tasks()),
        }
        if probe_results:
            result["probes"] = probe_results
        if hasattr(self, "uptime_seconds"):
            try:
                self.uptime_seconds.set(result["uptime_seconds"])
                self.cpu_usage_percent.set(result["cpu_usage_percent"])
                self.memory_usage_percent.set(result["memory_usage_percent"])
                self.memory_available_mb.set(result["memory_available_mb"])
                self.active_tasks.set(result["active_tasks"])
                self.status.set(1 if status == "healthy" else 0)
            except Exception as exc:
                logger.debug(f"Prometheus metrics update failed: {exc}")
        return result

    async def is_ready(self) -> bool:
        metrics = await self.get_system_metrics()
        if metrics["status"] == "degraded":
            logger.warning("Readiness probe: system degraded")
            return True
        return True

    async def is_live(self) -> bool:
        return True

    def record_request_duration(self, duration_seconds: float) -> None:
        if hasattr(self, "request_duration_seconds"):
            try:
                self.request_duration_seconds.observe(duration_seconds)
            except Exception as exc:
                logger.debug(f"Failed to record request duration: {exc}")

    def record_error(self, error_type: str = "general") -> None:
        if hasattr(self, "error_count"):
            try:
                self.error_count.labels(error_type=error_type).inc()
            except Exception as exc:
                logger.debug(f"Failed to record error metric: {exc}")

    def record_token_usage(self, provider: str, token_type: str, count: int) -> None:
        if hasattr(self, "token_usage"):
            try:
                self.token_usage.labels(provider=provider, type=token_type).inc(count)
            except Exception as exc:
                logger.debug(f"Failed to record token usage metric: {exc}")


_health_monitor_instance = None


def get_health_monitor() -> HealthMonitor:
    global _health_monitor_instance
    if _health_monitor_instance is None:
        _health_monitor_instance = HealthMonitor()
    return _health_monitor_instance
