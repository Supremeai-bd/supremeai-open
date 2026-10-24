"""
SupremeAI 2.0 — Latency-Aware Weighted Round-Robin Provider Router
===================================================================
বাংলা মন্তব্য: প্রোভাইডারদের রিয়েলটাইম ল্যাটেন্সি এবং সাকসেস রেট ট্র্যাক করে ডায়নামিক ওয়েটেড স্কোরিং ও সার্কিট ব্রেকার হ্যান্ডলার।
"""

import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass, field

from core.config import settings


@dataclass
class ProviderStats:
    name: str
    base_weight: float
    ready: bool = False
    readiness_status: str = "UNVALIDATED"
    latencies: deque = field(default_factory=lambda: deque(maxlen=settings.LATENCY_WINDOW_SIZE))
    successes: int = 0
    failures: int = 0
    circuit_open_until: float = 0.0

    def record(self, latency_ms: float, success: bool):
        self.latencies.append(latency_ms)
        if success:
            self.successes += 1
        else:
            self.failures += 1

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total else 1.0

    def is_circuit_open(self) -> bool:
        return time.monotonic() < self.circuit_open_until

    def trip_circuit(self, cooldown_seconds: float):
        self.circuit_open_until = time.monotonic() + cooldown_seconds


class LatencyAwareWeightedRouter:
    """
    Effective weight formula:
        effective_weight = base_weight * success_rate / (1 + normalized_latency)
    """

    def __init__(self, providers: dict[str, float] | None = None):
        default_providers = providers or {"openai": 5.0, "anthropic": 3.0, "groq": 2.0}
        self.stats: dict[str, ProviderStats] = {
            name: ProviderStats(name=name, base_weight=weight)
            for name, weight in default_providers.items()
        }
        self._lock = asyncio.Lock()
        self._readiness_enforced = False

    async def set_readiness(self, provider: str, ready: bool, status: str = "READY") -> None:
        """Allow provider health checks to gate routing without exposing credentials."""
        async with self._lock:
            stats = self.stats.setdefault(provider, ProviderStats(name=provider, base_weight=1.0))
            stats.ready = ready
            stats.readiness_status = status
            self._readiness_enforced = True

    async def readiness(self) -> dict[str, dict[str, str | bool]]:
        async with self._lock:
            return {
                name: {"ready": stats.ready, "status": stats.readiness_status}
                for name, stats in self.stats.items()
            }

    def _effective_weight(self, s: ProviderStats) -> float:
        if self._readiness_enforced and not s.ready:
            return 0.0
        if s.is_circuit_open():
            return 0.0
        normalized_latency = s.avg_latency_ms / settings.LATENCY_NORMALIZATION_MS
        score = s.base_weight * s.success_rate / (1 + normalized_latency)
        return max(score, settings.MIN_PROVIDER_WEIGHT)

    async def select_provider(self) -> str:
        async with self._lock:
            candidates = [
                (name, self._effective_weight(s))
                for name, s in self.stats.items()
                if not s.is_circuit_open()
            ]
            if not candidates:
                fallback = min(self.stats.values(), key=lambda s: s.circuit_open_until)
                return fallback.name

            names, weights = zip(*candidates, strict=False)
            return random.choices(names, weights=weights, k=1)[0]

    async def record_result(self, name: str, latency_ms: float, success: bool):
        async with self._lock:
            if name not in self.stats:
                self.stats[name] = ProviderStats(name=name, base_weight=1.0)
            s = self.stats[name]
            s.record(latency_ms, success)
            if not success:
                if (
                    s.failures >= settings.CIRCUIT_FAILURE_THRESHOLD
                    and s.success_rate < settings.CIRCUIT_SUCCESS_RATE_FLOOR
                ):
                    s.trip_circuit(settings.CIRCUIT_COOLDOWN_SECONDS)


router_instance = LatencyAwareWeightedRouter()
