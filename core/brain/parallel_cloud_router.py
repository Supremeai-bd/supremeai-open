import random
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger
from core.messaging.upstash_redis_queue import UpstashRedisQueue


class ParallelCloudRouter:
    """
    Parallel multi-cloud distribution.
    ALL providers are active simultaneously.
    Workload is distributed based on capacity, weight, and health.
    """

    PROVIDERS: dict[str, Any] = {
        "gcp_cloud_run": {
            "url": getattr(settings, "gcp_cloud_run_url", ""),
            "weight": 40.0,  # 40% traffic (highest - free tier)
            "capacity": 2000000,  # 2M requests/month
            "current_requests": 0,
            "status": "active",
            "region": "us-central1",
            "latency_ms": 50.0,
        },
        "railway": {
            "url": getattr(settings, "railway_url", ""),
            "weight": 35.0,  # 35% traffic
            "capacity": 500000,  # $5 = ~500K requests
            "current_requests": 0,
            "status": "active",
            "region": "us-east",
            "latency_ms": 80.0,
        },
        "render": {
            "url": getattr(settings, "render_url", ""),
            "weight": 25.0,  # 25% traffic
            "capacity": 180000,  # ~180K requests (750 hours free)
            "current_requests": 0,
            "status": "active",
            "region": "oregon",
            "latency_ms": 120.0,
        },
    }

    def __init__(self):
        self.redis_client = None
        self.upstash = UpstashRedisQueue()
        self.last_checked = 0.0
        redis_url = getattr(settings, "redis_url", None) or getattr(
            settings, "upstash_redis_url", None
        )
        if redis_url:
            try:
                import redis

                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                logger.info("Connected to Redis for ParallelCloudRouter state tracking.")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
        if self.upstash.configured:
            logger.info("Connected to Upstash Redis REST for ParallelCloudRouter state tracking.")
        self._health_check_all(force=True)

    def _get_current_requests(self, provider: str) -> int:
        if self.upstash.configured:
            val = self.upstash.get(f"parallel_router:requests:{provider}")
            return int(val) if val is not None else 0
        if self.redis_client:
            try:
                val = self.redis_client.get(f"parallel_router:requests:{provider}")
                return int(val) if val else 0
            except Exception as e:
                logger.error(f"Redis get requests failed: {e}")
        return self.PROVIDERS[provider]["current_requests"]

    def _increment_current_requests(self, provider: str) -> int:
        if self.upstash.configured:
            val = self.upstash.incr(f"parallel_router:requests:{provider}")
            return int(val) if val is not None else 0
        if self.redis_client:
            try:
                return self.redis_client.incr(f"parallel_router:requests:{provider}")
            except Exception as e:
                logger.error(f"Redis incr requests failed: {e}")
        self.PROVIDERS[provider]["current_requests"] += 1
        return self.PROVIDERS[provider]["current_requests"]

    def _decrement_current_requests(self, provider: str) -> int:
        if self.upstash.configured:
            val = self.upstash.decr(f"parallel_router:requests:{provider}")
            return max(0, int(val)) if val is not None else 0
        if self.redis_client:
            try:
                val = self.redis_client.decr(f"parallel_router:requests:{provider}")
                return max(0, val)
            except Exception as e:
                logger.error(f"Redis decr requests failed: {e}")
        self.PROVIDERS[provider]["current_requests"] = max(
            0, self.PROVIDERS[provider]["current_requests"] - 1
        )
        return self.PROVIDERS[provider]["current_requests"]

    def _get_status(self, provider: str) -> str:
        if self.upstash.configured:
            val = self.upstash.get(f"parallel_router:status:{provider}")
            return str(val) if val else str(self.PROVIDERS[provider]["status"])
        if self.redis_client:
            try:
                val = self.redis_client.get(f"parallel_router:status:{provider}")
                return str(val) if val else str(self.PROVIDERS[provider]["status"])
            except Exception as e:
                logger.error(f"Redis get status failed: {e}")
        return str(self.PROVIDERS[provider]["status"])

    def _set_status(self, provider: str, status: str):
        if self.upstash.configured:
            self.upstash.set(f"parallel_router:status:{provider}", status, ex=3600)
        if self.redis_client:
            try:
                self.redis_client.set(f"parallel_router:status:{provider}", status)
            except Exception as e:
                logger.error(f"Redis set status failed: {e}")
        self.PROVIDERS[provider]["status"] = status

    def _health_check_all(self, force: bool = False):
        """Check health of all providers (rate-limited to once per 60 seconds unless forced)."""
        import time

        now = time.time()
        if not force and now - self.last_checked < 60.0:
            return
        self.last_checked = now

        for name, config in self.PROVIDERS.items():
            if not config["url"]:
                self._set_status(name, "inactive")
                continue

            try:
                response = httpx.get(f"{config['url'].rstrip('/')}/health", timeout=5.0)
                if response.status_code == 200:
                    self._set_status(name, "active")
                    config["latency_ms"] = response.elapsed.total_seconds() * 1000
                else:
                    self._set_status(name, "degraded")
            except Exception as e:
                logger.warning(f"{name} health check failed: {e}")
                self._set_status(name, "down")

    def get_provider_for_request(self, task_type: str = "general") -> str:
        """
        Weighted selection with health awareness and Redis state mapping.
        """
        # Run rate-limited health check check on every routing request
        self._health_check_all()

        active_providers = {
            name: config
            for name, config in self.PROVIDERS.items()
            if self._get_status(name) in ["active", "degraded"] and config["url"]
        }

        if not active_providers:
            logger.warning("ALL PROVIDERS DOWN or unconfigured! Falling back to local/default.")
            configured = [name for name, config in self.PROVIDERS.items() if config["url"]]
            return configured[0] if configured else "gcp_cloud_run"

        is_latency_sensitive = (
            task_type in ["completion", "voice", "realtime"]
            or "realtime" in (task_type or "").lower()
        )

        total_weight = 0.0
        weights = {}

        for name, config in active_providers.items():
            current_reqs = self._get_current_requests(name)
            used_ratio = current_reqs / max(config["capacity"], 1)
            remaining_weight = config["weight"] * (1.0 - used_ratio)

            latency_penalty = 1.0
            if is_latency_sensitive and config["latency_ms"] > 150.0:
                latency_penalty = 0.1

            latency_boost = max(0.0, (200.0 - config["latency_ms"]) / 200.0)
            final_weight = remaining_weight * (1.0 + latency_boost) * latency_penalty

            weights[name] = max(final_weight, 0.1)
            total_weight += weights[name]

        pick = random.uniform(0.0, total_weight)
        current = 0.0

        for name, weight in weights.items():
            current += weight
            if pick <= current:
                self._increment_current_requests(name)
                return name

        selected = next(iter(active_providers.keys()))
        self._increment_current_requests(selected)
        return selected

    def route_parallel(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Route request to one provider.
        """
        provider = self.get_provider_for_request(payload.get("task_type", "general"))
        config = self.PROVIDERS[provider]
        url = f"{config['url'].rstrip('/')}{endpoint}"

        try:
            response = httpx.post(url, json=payload, timeout=30.0)
            result = response.json()
            result["_provider"] = provider
            result["_region"] = config["region"]
            return result
        except Exception as e:
            logger.error(f"{provider} failed: {e}")
            self._set_status(provider, "down")
            self._decrement_current_requests(provider)
            return self.route_parallel(endpoint, payload)

    def get_distribution_stats(self) -> dict[str, Any]:
        """Get current traffic distribution across all providers."""
        return {
            name: {
                "status": self._get_status(name),
                "current_requests": self._get_current_requests(name),
                "capacity_remaining": max(0, config["capacity"] - self._get_current_requests(name)),
                "utilization_pct": (self._get_current_requests(name) / max(config["capacity"], 1))
                * 100.0,
                "latency_ms": config["latency_ms"],
                "region": config["region"],
            }
            for name, config in self.PROVIDERS.items()
        }

    def rebalance(self):
        """
        Rebalance weights based on actual usage.
        """
        for name, config in self.PROVIDERS.items():
            status = self._get_status(name)
            if status != "active":
                continue
            current_reqs = self._get_current_requests(name)
            utilization = (current_reqs / max(config["capacity"], 1)) * 100.0
            if utilization > 80.0:
                config["weight"] *= 0.8
                logger.info(f"Reduced weight for {name} due to high utilization")
            elif utilization < 20.0:
                config["weight"] = min(config["weight"] * 1.2, 50.0)
                logger.info(f"Increased weight for {name} due to low utilization")

        active_provs = [
            c for name, c in self.PROVIDERS.items() if self._get_status(name) == "active"
        ]
        total = sum(p["weight"] for p in active_provs)
        if total > 0:
            for name, config in self.PROVIDERS.items():
                if self._get_status(name) == "active":
                    config["weight"] = (config["weight"] / total) * 100.0
