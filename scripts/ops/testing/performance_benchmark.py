# --- Merged from performance_benchmark.py ---

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
SupremeAI 2.0 — Performance Benchmark Suite
============================================================================
উদ্দেশ্য: সিস্টেমের পারফরম্যান্স মেজার, বেঞ্চমার্ক এবং লোড টেস্ট চালায়।

বৈশিষ্ট্য:
  - HTTP API latency & throughput benchmarking
  - Database query performance analysis
  - LLM inference speed comparison across providers
  - Memory & CPU profiling
  - Concurrent user simulation (locust-style)
  - Prometheus metrics export
  - Historical trend analysis
  - Auto-regression detection

ব্যবহার:
  python scripts/testing/performance_benchmark.py --target api
  python scripts/testing/performance_benchmark.py --target llm --providers gemini,deepseek,groq
  python scripts/testing/performance_benchmark.py --target db --duration 300
  python scripts/testing/performance_benchmark.py --load-test --users 100 --spawn-rate 10

লেখক: SupremeAI Architecture Team
তারিখ: July 20, 2026
============================================================================
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import tracemalloc

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

# বাংলা মন্তব্য: sys.path হ্যাক এড়াতে ক্লিন ইমপোর্ট
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_ROOT = _PROJECT_ROOT / "backend"

# Ensure backend/ is on sys.path so 'core.*' imports work in CI
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Also ensure project root is on sys.path for 'backend.*' imports in local dev
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from core.config import settings  # noqa: F401 — best-effort config import
    from core.llm.llm_gateway import get_llm_gateway
except ImportError:
    try:
        from backend.core.config import settings  # noqa: F401
        from backend.core.llm.llm_gateway import get_llm_gateway
    except ImportError:
        # Running without backend installed — define stub for scripts that need it
        settings = None  # type: ignore[assignment]
        get_llm_gateway = None  # type: ignore[assignment]


# ── Configuration ──────────────────────────────────────────────────────────
DEFAULT_DURATION = int(os.getenv("BENCH_DURATION", "60"))
DEFAULT_CONCURRENCY = int(os.getenv("BENCH_CONCURRENCY", "10"))
DEFAULT_WARMUP = int(os.getenv("BENCH_WARMUP", "5"))
REPORT_DIR = Path(os.getenv("BENCH_REPORT_DIR", "tests/reports/performance"))
def _resolve_default_api_base_url() -> str:
    env_val = os.getenv("API_BASE_URL")
    if env_val:
        return env_val.rstrip("/")
    if settings is not None:
        if getattr(settings, "backend_url", None):
            return settings.backend_url.rstrip("/")
        if getattr(settings, "auto_backend_url", None):
            return settings.auto_backend_url.rstrip("/")
        if hasattr(settings, "is_local") and settings.is_local():
            return "http://localhost:8000"
    if os.getenv("ENV") in ("local", "dev", "development") or os.getenv("CI"):
        return "http://localhost:8000"
    raise ValueError("API base URL must be configured via settings or API_BASE_URL environment variable.")

API_BASE_URL = _resolve_default_api_base_url()


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """বাংলা মন্তব্য: একক বেঞ্চমার্ক রানের ফলাফল"""
    name: str
    target: str
    metric: str  # latency | throughput | memory | cpu
    samples: list[float] = field(default_factory=list)
    unit: str = "ms"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def mean(self) -> float:
        return statistics.mean(self.samples) if self.samples else 0.0

    @property
    def median(self) -> float:
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def stddev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0.0

    @property
    def min_val(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max_val(self) -> float:
        return max(self.samples) if self.samples else 0.0

    @property
    def p95(self) -> float:
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    @property
    def p99(self) -> float:
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.99)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "metric": self.metric,
            "unit": self.unit,
            "mean": self.mean,
            "median": self.median,
            "stddev": self.stddev,
            "min": self.min_val,
            "max": self.max_val,
            "p95": self.p95,
            "p99": self.p99,
            "samples_count": len(self.samples),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class LoadTestResult:
    """বাংলা মন্তব্য: লোড টেস্টের ফলাফল"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration: float = 0.0
    requests_per_second: float = 0.0
    avg_response_time: float = 0.0
    min_response_time: float = float("inf")
    max_response_time: float = 0.0
    response_times: list[float] = field(default_factory=list)
    status_codes: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def p95_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]


# ── Benchmark Base Class ─────────────────────────────────────────────────

class BenchmarkBase:
    """
    বাংলা মন্তব্য: সব বেঞ্চমার্কের বেস ক্লাস। Common functionality প্রোভাইড করে।
    """

    def __init__(self, duration: int = DEFAULT_DURATION, warmup: int = DEFAULT_WARMUP):
        self.duration = duration
        self.warmup = warmup
        self.results: list[BenchmarkResult] = []

    async def warmup_phase(self) -> None:
        """বাংলা মন্তব্য: JIT compilation ও cache warm-up এর জন্য warm-up phase"""
        if self.warmup > 0:
            logger.info(f"Warming up for {self.warmup}s...")
            await asyncio.sleep(self.warmup)

    def record(self, name: str, target: str, metric: str, value: float, unit: str = "ms", metadata: dict | None = None) -> None:
        """বাংলা মন্তব্য: একক মেজারমেন্ট রেকর্ড করে"""
        existing = next((r for r in self.results if r.name == name and r.target == target and r.metric == metric), None)
        if existing:
            existing.samples.append(value)
        else:
            self.results.append(BenchmarkResult(
                name=name,
                target=target,
                metric=metric,
                samples=[value],
                unit=unit,
                metadata=metadata or {},
            ))

    def get_results(self) -> list[BenchmarkResult]:
        return self.results


# ── API Benchmark ──────────────────────────────────────────────────────────

class APIBenchmark(BenchmarkBase):
    """
    বাংলা মন্তব্য: FastAPI endpoints-এর latency ও throughput মেজার করে।
    """

    ENDPOINTS = {
        "health": {"method": "GET", "path": "/health", "body": None},
        "auth_login": {"method": "POST", "path": "/api/v1/auth/login", "body": {"email": "test@test.com", "password": "test123"}},
        "chat": {"method": "POST", "path": "/api/v1/chat", "body": {"message": "Hello, how are you?", "session_id": "test-session"}},
        "tenant_info": {"method": "GET", "path": "/api/v1/tenant/info", "body": None},
        "skills_list": {"method": "GET", "path": "/api/v1/skills", "body": None},
    }

    def __init__(self, base_url: str = API_BASE_URL, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url

    async def run(self, endpoints: list[str] | None = None) -> list[BenchmarkResult]:
        """বাংলা মন্তব্য: নির্দিষ্ট endpoints বেঞ্চমার্ক করে"""
        targets = endpoints or list(self.ENDPOINTS.keys())

        await self.warmup_phase()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint_name in targets:
                if endpoint_name not in self.ENDPOINTS:
                    logger.warning(f"Unknown endpoint: {endpoint_name}")
                    continue

                config = self.ENDPOINTS[endpoint_name]
                await self._benchmark_endpoint(client, endpoint_name, config)

        return self.results

    async def _benchmark_endpoint(self, client: httpx.AsyncClient, name: str, config: dict) -> None:
        """বাংলা মন্তব্য: একক endpoint বেঞ্চমার্ক করে"""
        logger.info(f"Benchmarking endpoint: {name} ({config['method']} {config['path']})")

        start_time = time.time()
        request_count = 0
        consecutive_failures = 0
        # বাংলা মন্তব্য: সার্ভার একেবারেই আনরিচেবল হলে (e.g. CI job-এ backend চালু নেই)
        # পুরো duration ধরে tight-loop-এ হাজার হাজার failed request পাঠানো অর্থহীন এবং
        # CI সময় নষ্ট করে। কয়েকটা পরপর connection failure হলেই এই endpoint স্কিপ করা হচ্ছে।
        MAX_CONSECUTIVE_FAILURES = 5

        while time.time() - start_time < self.duration:
            req_start = time.perf_counter()
            try:
                if config["method"] == "GET":
                    response = await client.get(f"{self.base_url}{config['path']}")
                else:
                    response = await client.post(
                        f"{self.base_url}{config['path']}",
                        json=config.get("body", {}),
                    )

                latency = (time.perf_counter() - req_start) * 1000  # ms
                self.record(name, config["path"], "latency", latency, "ms",
                           metadata={"status_code": response.status_code, "method": config["method"]})
                request_count += 1
                consecutive_failures = 0

            except Exception as e:
                consecutive_failures += 1
                logger.warning(f"Request failed for {name}: {e}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(
                        f"  {name}: {consecutive_failures} consecutive connection failures — "
                        f"server unreachable at {self.base_url}, skipping remaining duration for this endpoint"
                    )
                    break
                # বাংলা: পরবর্তী রিট্রাই-এর আগে সামান্য বিরতি, যাতে busy-loop CPU না পোড়ায়
                await asyncio.sleep(min(0.5 * consecutive_failures, 2.0))

        elapsed = time.time() - start_time
        throughput = request_count / elapsed if elapsed > 0 else 0
        self.record(name, config["path"], "throughput", throughput, "req/s",
                   metadata={"total_requests": request_count, "duration": elapsed})

        logger.info(f"  {name}: {request_count} requests in {elapsed:.1f}s ({throughput:.1f} req/s)")


# ── LLM Benchmark ──────────────────────────────────────────────────────────

class LLMBenchmark(BenchmarkBase):
    """
    বাংলা মন্তব্য: বিভিন্ন LLM provider-এর inference speed ও quality মেজার করে।
    """

    TEST_PROMPTS = [
        {"name": "short", "prompt": "What is 2+2?", "expected_tokens": 10},
        {"name": "medium", "prompt": "Explain quantum computing in simple terms.", "expected_tokens": 150},
        {"name": "long", "prompt": "Write a Python function to implement a binary search tree with insert, delete, and search operations. Include docstrings and type hints.", "expected_tokens": 500},
        {"name": "bangla", "prompt": "বাংলাদেশের ইতিহাস সম্পর্কে একটি সংক্ষিপ্ত প্রবন্ধ লিখুন।", "expected_tokens": 300},
    ]

    def __init__(self, providers: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.providers = providers or ["gemini", "deepseek", "groq"]
        self.gateway = None

    async def initialize(self) -> None:
        """বাংলা মন্তব্য: LLM Gateway ইনিশিয়ালাইজ করে"""
        self.gateway = get_llm_gateway()

    async def run(self) -> list[BenchmarkResult]:
        """বাংলা মন্তব্য: সব provider ও prompt এর জন্য বেঞ্চমার্ক রান করে"""
        await self.warmup_phase()

        for provider in self.providers:
            for test in self.TEST_PROMPTS:
                await self._benchmark_llm(provider, test)

        return self.results

    async def _benchmark_llm(self, provider: str, test: dict) -> None:
        """বাংলা মন্তব্য: একক LLM provider + prompt combination বেঞ্চমার্ক করে"""
        name = f"{provider}_{test['name']}"
        logger.info(f"Benchmarking LLM: {name}")

        latencies = []
        tokens_per_second = []

        for _ in range(max(3, self.duration // 10)):  # At least 3 runs
            start = time.perf_counter()
            try:
                response = await self.gateway.acompletion(
                    prompt=test["prompt"],
                    task_type="benchmark",
                    max_tokens=test["expected_tokens"],
                    temperature=0.7,
                    provider=provider,
                )
                elapsed = time.perf_counter() - start
                latency = elapsed * 1000  # ms

                text = response.get("text", "")
                tokens_generated = len(text) // 4  # Rough estimate
                tps = tokens_generated / elapsed if elapsed > 0 else 0

                latencies.append(latency)
                tokens_per_second.append(tps)

            except Exception as e:
                logger.warning(f"LLM benchmark failed for {name}: {e}")

        if latencies:
            for lat in latencies:
                self.record(name, provider, "latency", lat, "ms",
                           metadata={"prompt_type": test["name"], "provider": provider})
            for tps in tokens_per_second:
                self.record(name, provider, "tokens_per_second", tps, "tokens/s",
                           metadata={"prompt_type": test["name"], "provider": provider})

            avg_latency = statistics.mean(latencies)
            avg_tps = statistics.mean(tokens_per_second)
            logger.info(f"  {name}: avg latency={avg_latency:.1f}ms, avg tps={avg_tps:.1f}")


# ── Database Benchmark ─────────────────────────────────────────────────────

class DatabaseBenchmark(BenchmarkBase):
    """
    বাংলা মন্তব্য: Firestore query performance মেজার করে।
    Read, write, aggregation — সব অপারেশন বেঞ্চমার্ক করে।
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = None

    async def initialize(self) -> None:
        """বাংলা মন্তব্য: Firestore client ইনিশিয়ালাইজ করে"""
        try:
            from google.cloud import firestore
            self.db = firestore.Client()
        except Exception as e:
            logger.warning(f"Firestore unavailable: {e}")

    async def run(self) -> list[BenchmarkResult]:
        """বাংলা মন্তব্য: Database operations বেঞ্চমার্ক করে"""
        if not self.db:
            logger.error("Database not available for benchmarking")
            return self.results

        await self.warmup_phase()

        test_collection = self.db.collection("_benchmark_test")

        await self._benchmark_writes(test_collection)
        await self._benchmark_reads(test_collection)
        await self._benchmark_queries(test_collection)
        await self._cleanup(test_collection)

        return self.results

    async def _benchmark_writes(self, collection) -> None:
        """বাংলা মন্তব্য: Write operation latency মেজার করে"""
        logger.info("Benchmarking Firestore writes...")
        doc_count = min(100, self.duration * 2)

        for i in range(doc_count):
            start = time.perf_counter()
            doc_ref = collection.document(f"bench_{i}")
            await doc_ref.set({
                "index": i,
                "data": "x" * 1000,  # 1KB payload
                "timestamp": datetime.now(UTC),
                "metadata": {"test": True, "benchmark": True},
            })
            latency = (time.perf_counter() - start) * 1000
            self.record("firestore_write", "firestore", "latency", latency, "ms",
                       metadata={"operation": "write", "payload_size": 1000})

    async def _benchmark_reads(self, collection) -> None:
        """বাংলা মন্তব্য: Read operation latency মেজার করে"""
        logger.info("Benchmarking Firestore reads...")

        for i in range(min(100, self.duration * 2)):
            start = time.perf_counter()
            doc = await collection.document(f"bench_{i}").get()
            latency = (time.perf_counter() - start) * 1000
            self.record("firestore_read", "firestore", "latency", latency, "ms",
                       metadata={"operation": "read", "exists": doc.exists})

    async def _benchmark_queries(self, collection) -> None:
        """বাংলা মন্তব্য: Query operation latency মেজার করে"""
        logger.info("Benchmarking Firestore queries...")

        for _ in range(min(50, self.duration)):
            start = time.perf_counter()
            query = collection.where("test", "==", True).limit(10)
            docs = await query.get()
            latency = (time.perf_counter() - start) * 1000
            self.record("firestore_query", "firestore", "latency", latency, "ms",
                       metadata={"operation": "query", "results": len(docs)})

    async def _cleanup(self, collection) -> None:
        """বাংলা মন্তব্য: বেঞ্চমার্ক ডেটা ক্লিনআপ করে"""
        logger.info("Cleaning up benchmark data...")
        docs = await collection.limit(500).get()
        for doc in docs:
            await doc.reference.delete()


# ── Load Test Engine ─────────────────────────────────────────────────────

class LoadTestEngine:
    """
    বাংলা মন্তব্য: Locust-style load testing engine।
    Concurrent users simulate করে real-world traffic pattern তৈরি করে।
    """

    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.results = LoadTestResult()
        self._stop_event = asyncio.Event()

    async def run(self, users: int, spawn_rate: float, duration: int, endpoint: str = "/health") -> LoadTestResult:
        """বাংলা মন্তব্য: নির্দিষ্ট সংখ্যক concurrent user দিয়ে লোড টেস্ট চালায়।"""
        logger.info(f"Starting load test: {users} users, {spawn_rate}/s spawn rate, {duration}s duration")

        self.results = LoadTestResult()
        start_time = time.time()

        tasks = []
        spawned = 0

        while spawned < users and not self._stop_event.is_set():
            batch_size = min(int(spawn_rate), users - spawned)
            for _ in range(batch_size):
                task = asyncio.create_task(self._user_worker(endpoint, start_time, duration))
                tasks.append(task)
            spawned += batch_size
            await asyncio.sleep(1.0)

        await asyncio.sleep(max(0, duration - (time.time() - start_time)))
        self._stop_event.set()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.results.total_duration = time.time() - start_time
        if self.results.total_duration > 0:
            self.results.requests_per_second = self.results.total_requests / self.results.total_duration
        if self.results.response_times:
            self.results.avg_response_time = statistics.mean(self.results.response_times)

        return self.results

    async def _user_worker(self, endpoint: str, test_start: float, duration: int) -> None:
        """বাংলা মন্তব্য: একজন virtual user এর কাজ — continuously request করে"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            while not self._stop_event.is_set():
                if time.time() - test_start > duration:
                    break

                req_start = time.perf_counter()
                try:
                    response = await client.get(f"{self.base_url}{endpoint}")
                    latency = (time.perf_counter() - req_start) * 1000

                    self.results.total_requests += 1
                    self.results.response_times.append(latency)
                    self.results.status_codes[response.status_code] += 1

                    if response.status_code < 400:
                        self.results.successful_requests += 1
                    else:
                        self.results.failed_requests += 1

                    self.results.min_response_time = min(self.results.min_response_time, latency)
                    self.results.max_response_time = max(self.results.max_response_time, latency)

                except Exception as e:
                    self.results.total_requests += 1
                    self.results.failed_requests += 1
                    self.results.errors.append(str(e))

                await asyncio.sleep(0.1)


# ── Memory Profiler ──────────────────────────────────────────────────────

class MemoryProfiler:
    """
    বাংলা মন্তব্য: Python মেমোরি usage ট্র্যাক করে। tracemalloc ব্যবহার করে।
    """

    def __init__(self):
        self.snapshots: list[Any] = []

    def start(self) -> None:
        """বাংলা মন্তব্য: মেমোরি ট্রেসিং শুরু করে"""
        tracemalloc.start()
        logger.info("Memory profiling started")

    def snapshot(self, label: str = "") -> dict[str, Any]:
        """বাংলা মন্তব্য: মেমোরি স্ন্যাপশট নেয়"""
        current, peak = tracemalloc.get_traced_memory()
        snapshot = tracemalloc.take_snapshot()
        self.snapshots.append((label, snapshot))

        return {
            "label": label,
            "current_mb": current / 1024 / 1024,
            "peak_mb": peak / 1024 / 1024,
            "top_allocations": [
                {
                    "file": stat.traceback.format()[-1] if stat.traceback.format() else "unknown",
                    "size_mb": stat.size / 1024 / 1024,
                    "count": stat.count,
                }
                for stat in snapshot.statistics("lineno")[:5]
            ],
        }

    def stop(self) -> None:
        """বাংলা মন্তব্য: মেমোরি ট্রেসিং বন্ধ করে"""
        tracemalloc.stop()
        logger.info("Memory profiling stopped")

    def compare_snapshots(self, idx1: int = 0, idx2: int = -1) -> list[dict[str, Any]]:
        """বাংলা মন্তব্য: দুটি স্ন্যাপশটের মধ্যে পার্থক্য দেখায়"""
        if len(self.snapshots) < 2:
            return []

        _, snap1 = self.snapshots[idx1]
        _, snap2 = self.snapshots[idx2]

        top_stats = snap2.compare_to(snap1, "lineno")

        return [
            {
                "file": stat.traceback.format()[-1] if stat.traceback.format() else "unknown",
                "size_diff_mb": stat.size_diff / 1024 / 1024,
                "count_diff": stat.count_diff,
            }
            for stat in top_stats[:10]
        ]


# ── Report Generator ─────────────────────────────────────────────────────

class PerformanceReportGenerator:
    """
    বাংলা মন্তব্য: বেঞ্চমার্ক রেজাল্ট থেকে comprehensive report তৈরি করে।
    """

    def __init__(self, output_dir: Path = REPORT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, benchmark_results: list[BenchmarkResult], load_results: LoadTestResult | None = None, memory_results: list[dict] | None = None) -> str:
        """বাংলা মন্তব্য: সম্পূর্ণ পারফরম্যান্স রিপোর্ট জেনারেট করে"""
        report_data = {
            "project": "SupremeAI 2.0",
            "report_type": "performance_benchmark",
            "timestamp": datetime.now(UTC).isoformat(),
            "benchmarks": [r.to_dict() for r in benchmark_results],
        }

        if load_results:
            report_data["load_test"] = {
                "total_requests": load_results.total_requests,
                "successful": load_results.successful_requests,
                "failed": load_results.failed_requests,
                "success_rate": load_results.success_rate,
                "requests_per_second": load_results.requests_per_second,
                "avg_response_time": load_results.avg_response_time,
                "p95_response_time": load_results.p95_response_time,
                "min_response_time": load_results.min_response_time if load_results.min_response_time != float("inf") else 0,
                "max_response_time": load_results.max_response_time,
                "status_codes": dict(load_results.status_codes),
            }

        if memory_results:
            report_data["memory_profile"] = memory_results

        json_file = self.output_dir / f"performance_report_{datetime.now(UTC):%Y%m%d_%H%M%S}.json"
        json_file.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")

        self._print_console_summary(benchmark_results, load_results)

        return str(json_file)

    def _print_console_summary(self, benchmark_results: list[BenchmarkResult], load_results: LoadTestResult | None) -> None:
        """বাংলা মন্তব্য: কনসোলে সুন্দর সারসংক্ষেপ প্রিন্ট করে"""
        print("\n" + "=" * 70)
        print("🏎️  SupremeAI Performance Benchmark Summary")
        print("=" * 70)

        by_target = defaultdict(list)
        for r in benchmark_results:
            by_target[r.target].append(r)

        for target, results in by_target.items():
            print(f"\n📍 {target}")
            print("-" * 50)
            for r in results:
                print(f"  {r.name:30} | Mean: {r.mean:8.2f}{r.unit} | P95: {r.p95:8.2f}{r.unit} | P99: {r.p99:8.2f}{r.unit}")

        if load_results:
            print("\n🌊 Load Test Results")
            print("-" * 50)
            print(f"  Total Requests : {load_results.total_requests}")
            print(f"  Success Rate   : {load_results.success_rate:.1f}%")
            print(f"  Req/Second     : {load_results.requests_per_second:.1f}")
            print(f"  Avg Response   : {load_results.avg_response_time:.1f}ms")
            print(f"  P95 Response   : {load_results.p95_response_time:.1f}ms")
            print(f"  Min/Max        : {load_results.min_response_time:.1f}ms / {load_results.max_response_time:.1f}ms")

        print("\n" + "=" * 70)


# ── Regression Detector ────────────────────────────────────────────────────

class RegressionDetector:
    """
    বাংলা মন্তব্য: Historical benchmark data-এর সাথে তুলনা করে regression ডিটেক্ট করে।
    যদি কোনো metric threshold-এর উপরে যায়, alert তৈরি করে।
    """

    REGRESSION_THRESHOLD = 1.2  # 20% degradation threshold

    def __init__(self, history_file: Path | None = None):
        self.history_file = history_file or REPORT_DIR / "benchmark_history.jsonl"
        self.history: list[dict] = []
        self._load_history()

    def _load_history(self) -> None:
        """বাংলা মন্তব্য: Historical data লোড করে"""
        if self.history_file.exists():
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.history.append(json.loads(line))

    def detect(self, current_results: list[BenchmarkResult]) -> list[dict[str, Any]]:
        """বাংলা মন্তব্য: Regression চেক করে"""
        regressions = []

        for result in current_results:
            baseline = self._get_baseline(result.name, result.target, result.metric)
            if baseline is None:
                continue

            is_latency = result.metric in ("latency",)
            current_mean = result.mean

            if is_latency:
                if current_mean > baseline * self.REGRESSION_THRESHOLD:
                    regressions.append({
                        "name": result.name,
                        "target": result.target,
                        "metric": result.metric,
                        "baseline": baseline,
                        "current": current_mean,
                        "degradation_pct": ((current_mean - baseline) / baseline) * 100,
                        "severity": "HIGH" if current_mean > baseline * 1.5 else "MEDIUM",
                    })
            else:
                if current_mean < baseline / self.REGRESSION_THRESHOLD:
                    regressions.append({
                        "name": result.name,
                        "target": result.target,
                        "metric": result.metric,
                        "baseline": baseline,
                        "current": current_mean,
                        "degradation_pct": ((baseline - current_mean) / baseline) * 100,
                        "severity": "HIGH" if current_mean < baseline / 1.5 else "MEDIUM",
                    })

        return regressions

    def _get_baseline(self, name: str, target: str, metric: str) -> float | None:
        """বাংলা মন্তব্য: Historical baseline mean বের করে"""
        matching = [
            r for r in self.history
            if any(b.get("name") == name and b.get("target") == target and b.get("metric") == metric
            for b in r.get("benchmarks", []))
        ]

        if not matching:
            return None

        recent = matching[-5:]
        values = []
        for run in recent:
            for b in run.get("benchmarks", []):
                if b.get("name") == name and b.get("target") == target and b.get("metric") == metric:
                    values.append(b.get("mean", 0))

        return statistics.mean(values) if values else None

    def save_run(self, results: list[BenchmarkResult]) -> None:
        """বাংলা মন্তব্য: Current run historical data-তে সেভ করে"""
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "benchmarks": [r.to_dict() for r in results],
        }
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


# ── Main Benchmark Runner ──────────────────────────────────────────────────

class PerformanceBenchmarkRunner:
    """
    বাংলা মন্তব্য: মূল অরকেস্ট্রেটর। সব বেঞ্চমার্ক টাইপ একসাথে চালায়।
    """

    def __init__(self, duration: int, concurrency: int, warmup: int, base_url: str | None = None):
        self.duration = duration
        self.concurrency = concurrency
        self.warmup = warmup
        self.base_url = base_url or API_BASE_URL
        self.all_results: list[BenchmarkResult] = []
        self.report_generator = PerformanceReportGenerator()
        self.regression_detector = RegressionDetector()

    async def run_api_benchmark(self, endpoints: list[str] | None = None) -> list[BenchmarkResult]:
        """বাংলা মন্তব্য: API বেঞ্চমার্ক চালায়"""
        benchmark = APIBenchmark(base_url=self.base_url, duration=self.duration, warmup=self.warmup)
        results = await benchmark.run(endpoints)
        self.all_results.extend(results)
        return results

    async def run_llm_benchmark(self, providers: list[str] | None = None) -> list[BenchmarkResult]:
        """বাংলা মন্তব্য: LLM বেঞ্চমার্ক চালায়"""
        benchmark = LLMBenchmark(providers=providers, duration=self.duration, warmup=self.warmup)
        await benchmark.initialize()
        results = await benchmark.run()
        self.all_results.extend(results)
        return results

    async def run_db_benchmark(self) -> list[BenchmarkResult]:
        """বাংলা মন্তব্য: Database বেঞ্চমার্ক চালায়"""
        benchmark = DatabaseBenchmark(duration=self.duration, warmup=self.warmup)
        await benchmark.initialize()
        results = await benchmark.run()
        self.all_results.extend(results)
        return results

    async def run_load_test(self, users: int, spawn_rate: float, endpoint: str = "/health") -> LoadTestResult:
        """বাংলা মন্তব্য: Load test চালায়"""
        engine = LoadTestEngine()
        return await engine.run(users, spawn_rate, self.duration, endpoint)

    async def run_memory_profile(self, target_func: Callable | None = None) -> list[dict]:
        """বাংলা মন্তব্য: Memory profiling চালায়"""
        profiler = MemoryProfiler()
        profiler.start()

        baseline = profiler.snapshot("baseline")

        if target_func:
            await target_func() if asyncio.iscoroutinefunction(target_func) else target_func()

        after_load = profiler.snapshot("after_load")

        profiler.stop()

        return [baseline, after_load]

    def detect_regressions(self) -> list[dict]:
        """বাংলা মন্তব্য: Regression detection চালায়"""
        regressions = self.regression_detector.detect(self.all_results)

        if regressions:
            print("\n⚠️  REGRESSIONS DETECTED:")
            for reg in regressions:
                print(f"  🔴 [{reg['severity']}] {reg['name']}: {reg['degradation_pct']:.1f}% degradation")
        else:
            print("\n✅ No regressions detected")

        return regressions

    def save_and_report(self, load_results: LoadTestResult | None = None, memory_results: list[dict] | None = None) -> str:
        """বাংলা মন্তব্য: রেজাল্ট সেভ এবং রিপোর্ট জেনারেট করে"""
        self.regression_detector.save_run(self.all_results)
        report_file = self.report_generator.generate(self.all_results, load_results, memory_results)
        return report_file


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """বাংলা মন্তব্য: CLI entry point"""
    parser = argparse.ArgumentParser(
        description="SupremeAI 2.0 — Performance Benchmark Suite\nপারফরম্যান্স বেঞ্চমার্ক ও লোড টেস্ট",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", "-t", default="all",
                        choices=["all", "api", "llm", "db", "load", "memory"],
                        help="Benchmark target")
    parser.add_argument("--duration", "-d", type=int, default=DEFAULT_DURATION,
                        help="Benchmark duration in seconds")
    parser.add_argument("--concurrency", "-c", type=int, default=DEFAULT_CONCURRENCY,
                        help="Number of concurrent requests")
    parser.add_argument("--warmup", "-w", type=int, default=DEFAULT_WARMUP,
                        help="Warmup duration in seconds")
    parser.add_argument("--providers", "-p", default="gemini,deepseek,groq",
                        help="LLM providers to benchmark (comma-separated)")
    parser.add_argument("--endpoints", "-e", default="",
                        help="API endpoints to benchmark (comma-separated)")
    parser.add_argument("--load-test", "-l", action="store_true",
                        help="Run load test")
    parser.add_argument("--users", "-u", type=int, default=100,
                        help="Number of virtual users for load test")
    parser.add_argument("--spawn-rate", "-sr", type=float, default=10.0,
                        help="User spawn rate per second")
    parser.add_argument("--base-url", "-u-url", default=None,
                        help="API base URL to benchmark (defaults to API_BASE_URL or settings.backend_url)")
    parser.add_argument("--memory", "-m", action="store_true",
                        help="Run memory profiling")

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")

    async def run():
        runner = PerformanceBenchmarkRunner(
            duration=args.duration,
            concurrency=args.concurrency,
            warmup=args.warmup,
            base_url=args.base_url,
        )

        load_results = None
        memory_results = None

        if args.target in ("all", "api"):
            endpoints = args.endpoints.split(",") if args.endpoints else None
            await runner.run_api_benchmark(endpoints)

        if args.target in ("all", "llm"):
            providers = args.providers.split(",")
            await runner.run_llm_benchmark(providers)

        if args.target in ("all", "db"):
            await runner.run_db_benchmark()

        if args.load_test or args.target == "load":
            load_results = await runner.run_load_test(args.users, args.spawn_rate)

        if args.memory:
            memory_results = await runner.run_memory_profile()

        runner.detect_regressions()

        report_file = runner.save_and_report(load_results, memory_results)
        print(f"\n📊 Report saved: {report_file}")

    asyncio.run(run())


if __name__ == "__main__":
    main()


