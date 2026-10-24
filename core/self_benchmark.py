# backend/core/self_benchmark.py
"""SupremeAI Self-Benchmarking Engine.

Comprehensive testing framework for self-evaluation and limit detection:
- Performance benchmarking (speed, throughput, latency)
- Accuracy testing across all domains
- Stress testing (find breaking points)
- Resource utilization analysis
- Weakness identification
- Baseline comparison
- Score calculation and grading
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from core.logging_config import logger

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class BenchmarkCategory(StrEnum):
    PERFORMANCE = "performance"
    ACCURACY = "accuracy"
    STRESS = "stress"
    MEMORY = "memory"
    CONCURRENCY = "concurrency"
    DOMAIN_SPECIFIC = "domain_specific"
    RELIABILITY = "reliability"


class DifficultyLevel(int, Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3
    EXTREME = 4
    IMPOSSIBLE = 5


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    test_name: str
    category: BenchmarkCategory
    score: float  # 0.0 to 1.0
    value: float  # Actual measured value
    unit: str
    passed: bool
    threshold: float  # Target threshold
    duration_ms: int
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None


@dataclass
class LimitDetection:
    """Detected system limit."""

    metric_name: str
    current_value: float
    max_sustainable: float
    breaking_point: float
    unit: str
    confidence: float  # How confident we are in this limit
    recommendations: list[str] = field(default_factory=list)


@dataclass
class WeaknessReport:
    """Identified weakness area."""

    area: str
    severity: str  # 'critical', 'major', 'minor'
    current_score: float
    target_score: float
    impact_description: str
    suggested_improvements: list[str]
    priority: int  # 1 = highest priority


@dataclass
class FullBenchmarkReport:
    """Complete benchmark report."""

    report_id: str
    timestamp: datetime
    duration_seconds: float
    overall_score: float  # Weighted average of all categories
    grade: str  # 'A+', 'A', 'B+', etc.
    results: list[BenchmarkResult]
    limits_detected: list[LimitDetection]
    weaknesses: list[WeaknessReport]
    improvements_needed: bool
    optimization_plan: dict[str, Any]
    summary: dict[str, Any]


class SelfBenchmarkEngine:
    """Comprehensive self-benchmarking engine."""

    def __init__(self, ai_system: Any = None, config: dict[str, Any] | None = None) -> None:
        self.ai_system = ai_system
        self.config: dict[str, Any] = config or {}

        # Benchmark settings
        self.test_duration_per_query_ms = self.config.get("test_duration_ms", 5000)
        self.concurrent_test_count = self.config.get("concurrent_tests", 10)
        self.stress_test_multiplier = self.config.get("stress_multiplier", 10)
        self.memory_test_max_mb = self.config.get("memory_test_max_mb", 1024)
        # বাংলা: pass^k reliability gate — ROADMAP Sprint 4 ও promotion-gate
        # প্রয়োজনে (HUMAN_BEHAVIOR §16)। pass@k বলে “k চেষ্টার অন্তত একটা সফল”;
        # pass^k বলে “k চেষ্টার *সবগুলোই* সফল” — এটাই আসল reliability মানদণ্ড।
        self.reliability_k = int(self.config.get("reliability_k", 3))
        self.reliability_samples = int(self.config.get("reliability_samples", 5))
        self.reliability_threshold = float(self.config.get("reliability_threshold", 0.7))

        # Scoring thresholds
        self.thresholds: dict[str, dict[str, float]] = {
            "response_time_ms": {"excellent": 200, "good": 500, "acceptable": 1000, "poor": 2000},
            "accuracy": {"excellent": 0.95, "good": 0.85, "acceptable": 0.70, "poor": 0.50},
            "concurrent_requests": {"excellent": 100, "good": 50, "acceptable": 20, "poor": 10},
            "memory_usage_mb": {"excellent": 256, "good": 512, "acceptable": 1024, "poor": 2048},
            "error_rate": {"excellent": 0.01, "good": 0.05, "acceptable": 0.10, "poor": 0.20},
        }

        # Test queries for different domains
        self.test_queries = self._generate_test_queries()

        # History tracking
        self.benchmark_history: list[FullBenchmarkReport] = []
        self.baseline_scores: dict[str, float] = {}

        # Statistics
        self.stats: dict[str, Any] = {
            "total_benchmarks_run": 0,
            "improvements_triggered": 0,
            "avg_score_improvement": 0.0,
        }

    async def run_full_benchmark(
        self, categories: list[BenchmarkCategory] | None = None
    ) -> FullBenchmarkReport:
        """Run complete benchmark suite."""
        start_time = time.time()
        report_id = f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if categories is None:
            categories = list(BenchmarkCategory)

        all_results: list[BenchmarkResult] = []

        for category in categories:
            if category == BenchmarkCategory.PERFORMANCE:
                results = await self._benchmark_performance()
            elif category == BenchmarkCategory.ACCURACY:
                results = await self._benchmark_accuracy()
            elif category == BenchmarkCategory.STRESS:
                results = await self._benchmark_stress()
            elif category == BenchmarkCategory.MEMORY:
                results = await self._benchmark_memory()
            elif category == BenchmarkCategory.CONCURRENCY:
                results = await self._benchmark_concurrency()
            elif category == BenchmarkCategory.DOMAIN_SPECIFIC:
                results = await self._benchmark_domain_specific()
            elif category == BenchmarkCategory.RELIABILITY:
                results = await self._benchmark_reliability()
            else:
                results = []

            all_results.extend(results)

        # Detect limits and weaknesses
        limits_detected = await self._detect_limits(all_results)
        weaknesses = await self._identify_weaknesses(all_results)
        overall_score = self._calculate_overall_score(all_results)
        grade = self._score_to_grade(overall_score)

        improvements_needed = any(w.severity in ["critical", "major"] for w in weaknesses)
        optimization_plan = (
            self._generate_optimization_plan(weaknesses, limits_detected)
            if improvements_needed
            else {}
        )
        duration = time.time() - start_time

        report = FullBenchmarkReport(
            report_id=report_id,
            timestamp=datetime.now(),
            duration_seconds=round(duration, 2),
            overall_score=round(overall_score, 4),
            grade=grade,
            results=all_results,
            limits_detected=limits_detected,
            weaknesses=weaknesses,
            improvements_needed=improvements_needed,
            optimization_plan=optimization_plan,
            summary=self._generate_summary(all_results, overall_score, grade, weaknesses),
        )

        self.benchmark_history.append(report)
        self.stats["total_benchmarks_run"] += 1
        return report

    async def _benchmark_performance(self) -> list[BenchmarkResult]:
        """Benchmark response times and throughput."""
        results: list[BenchmarkResult] = []
        if not self.ai_system:
            # FIX(honest-empty): no system to measure -> no fabricated numbers.
            # The old fallback reported a hardcoded 150ms/0.8 result for a
            # benchmark that never ran.
            return []

        times: list[float] = []
        for _ in range(5):
            query = random.choice(self.test_queries["general"])
            start = time.perf_counter()
            try:
                await asyncio.wait_for(
                    self.ai_system.process(query),
                    timeout=self.test_duration_per_query_ms / 1000.0,
                )
                elapsed = (time.perf_counter() - start) * 1000.0
                times.append(elapsed)
            except Exception:
                times.append(float(self.test_duration_per_query_ms))

        avg_time = statistics.mean(times) if times else 200.0
        thresholds = self.thresholds["response_time_ms"]
        score = (
            1.0
            if avg_time <= thresholds["excellent"]
            else max(0.5, 1.0 - (avg_time / thresholds["poor"]))
        )

        results.append(
            BenchmarkResult(
                test_name="avg_response_time",
                category=BenchmarkCategory.PERFORMANCE,
                score=round(score, 2),
                value=round(avg_time, 2),
                unit="ms",
                passed=avg_time <= thresholds["acceptable"],
                threshold=thresholds["acceptable"],
                duration_ms=int(sum(times)),
            )
        )
        return results

    async def _benchmark_accuracy(self) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []
        if not self.ai_system:
            return []

        for domain in ["development", "business", "ux_design"]:
            queries = self.test_queries.get(domain, [])
            correct_count = 0
            for q in queries[:2]:
                try:
                    res = await self.ai_system.process(q)
                    if getattr(res, "success", False):
                        correct_count += 1
                except Exception as e:
                    logger.debug(f"Benchmark query evaluation error: {e}")

            accuracy = correct_count / max(len(queries[:2]), 1)
            results.append(
                BenchmarkResult(
                    test_name=f"accuracy_{domain}",
                    category=BenchmarkCategory.ACCURACY,
                    score=round(accuracy, 2),
                    value=round(accuracy, 2),
                    unit="ratio",
                    passed=accuracy >= 0.5,
                    threshold=0.7,
                    duration_ms=0,
                )
            )
        return results

    async def _safe_process(self, query: str) -> bool:
        """Run one probe through the real system; True only on a successful call."""
        try:
            res = await asyncio.wait_for(
                self.ai_system.process(query),
                timeout=self.test_duration_per_query_ms / 1000.0,
            )
            return bool(getattr(res, "success", True))
        except Exception as exc:
            logger.debug(f"Benchmark probe failed: {exc}")
            return False

    async def _benchmark_stress(self) -> list[BenchmarkResult]:
        """Concurrent load burst — measured against the real system.

        Fires concurrent_test_count * stress_test_multiplier simultaneous
        requests and scores by the real success ratio. The old version
        reported a hardcoded 0.9/50-requests result without running
        anything.
        """
        if not self.ai_system:
            return []

        target = max(1, self.concurrent_test_count * self.stress_test_multiplier)
        start = time.perf_counter()
        outcomes = await asyncio.gather(
            *(self._safe_process(f"stress probe {i}") for i in range(target))
        )
        wall_ms = int((time.perf_counter() - start) * 1000)
        succeeded = sum(1 for ok in outcomes if ok)
        ratio = succeeded / target
        # Pass = the system handled (almost) the whole burst it was given.
        return [
            BenchmarkResult(
                test_name="max_concurrent_requests",
                category=BenchmarkCategory.STRESS,
                score=round(ratio, 2),
                value=float(succeeded),
                unit="requests",
                passed=ratio >= 0.9,
                threshold=float(target),
                duration_ms=wall_ms,
            )
        ]

    async def _benchmark_memory(self) -> list[BenchmarkResult]:
        results: list[BenchmarkResult] = []
        memory_mb = 128.0
        if HAS_PSUTIL:
            try:
                proc = psutil.Process(os.getpid())
                memory_mb = proc.memory_info().rss / (1024 * 1024)
            except Exception as e:
                logger.debug(f"psutil memory read error: {e}")

        results.append(
            BenchmarkResult(
                test_name="memory_usage",
                category=BenchmarkCategory.MEMORY,
                score=0.95 if memory_mb < 512 else 0.7,
                value=round(memory_mb, 2),
                unit="MB",
                passed=memory_mb < 1024,
                threshold=1024.0,
                duration_ms=0,
            )
        )
        return results

    async def _benchmark_concurrency(self) -> list[BenchmarkResult]:
        """Sustained throughput — real req/s measured over a 2s window.

        The old version reported a hardcoded 0.85/25 req/s without
        executing any request.
        """
        if not self.ai_system:
            return []

        window_seconds = 2.0
        batch = max(1, self.concurrent_test_count)
        completed = 0
        start = time.perf_counter()
        while (time.perf_counter() - start) < window_seconds:
            outcomes = await asyncio.gather(
                *(self._safe_process(f"concurrency probe {completed + i}") for i in range(batch))
            )
            completed += sum(1 for ok in outcomes if ok)
        wall = time.perf_counter() - start
        rps = completed / wall if wall > 0 else 0.0
        threshold = float(self.thresholds["concurrent_requests"]["acceptable"])
        # 5x the acceptable rate counts as a perfect score.
        score = min(1.0, rps / (threshold * 5)) if threshold > 0 else 0.0
        return [
            BenchmarkResult(
                test_name="sustained_concurrency_10",
                category=BenchmarkCategory.CONCURRENCY,
                score=round(score, 2),
                value=round(rps, 2),
                unit="req/s",
                passed=rps >= threshold,
                threshold=threshold,
                duration_ms=int(wall * 1000),
            )
        ]

    async def _benchmark_domain_specific(self) -> list[BenchmarkResult]:
        """Domain probes — real success ratio of domain queries.

        The old version reported a hardcoded 0.95 score and 120ms value
        without executing anything.
        """
        if not self.ai_system:
            return []

        results: list[BenchmarkResult] = []
        for domain in ["development", "business", "ux_design"]:
            queries = self.test_queries.get(domain, [])[:2]
            if not queries:
                continue
            latencies: list[float] = []
            successes = 0
            for q in queries:
                probe_start = time.perf_counter()
                ok = await self._safe_process(q)
                latencies.append((time.perf_counter() - probe_start) * 1000.0)
                if ok:
                    successes += 1
            ratio = successes / len(queries)
            avg_ms = statistics.mean(latencies)
            results.append(
                BenchmarkResult(
                    test_name=f"domain_{domain}",
                    category=BenchmarkCategory.DOMAIN_SPECIFIC,
                    score=round(ratio, 2),
                    value=round(avg_ms, 2),
                    unit="ms",
                    passed=ratio >= 0.5,
                    threshold=0.6,
                    duration_ms=int(sum(latencies)),
                )
            )
        return results

    @staticmethod
    def _pass_hat_k_estimator(successes: int, n: int, k: int) -> float:
        """Unbiased pass^k estimate: C(successes, k) / C(n, k).

        বাংলা: n-টা independent রানের মধ্যে s-টা সফল হলে, k-টা রাণের একটি
        random সেটে *সব* সফল হওয়ার সম্ভাবনার unbiased estimator হলো
        C(s, k) / C(n, k) (Brown et al., 2024-এ pass@k-এর মতোই)। n < k হলে 0.0।
        """
        if n < k:
            return 0.0
        if successes < k:
            return 0.0
        if successes > n:
            successes = n
        return math.comb(successes, k) / math.comb(n, k)

    async def _benchmark_reliability(self) -> list[BenchmarkResult]:
        """pass^k reliability gate across repeated independent attempts.

        বাংলা: একই task k বার চালিয়ে *সব* চেষ্টা সফল কি না মাপা হয় —
        এটাই SupremeAI-র "Deliver honestly" প্রতিশ্রুতির সংখ্যাগত রূপ।
        Success convention হিসেবে _benchmark_accuracy-র মতোই response.success ব্যবহৃত হয়।
        """
        results: list[BenchmarkResult] = []
        if not self.ai_system:
            return []

        k = max(1, self.reliability_k)
        n = max(k, self.reliability_samples)
        task_set = self.test_queries["general"] + self.test_queries["development"]

        per_task_estimates: list[float] = []
        started = time.perf_counter()
        for task in task_set:
            successes = 0
            for _attempt in range(n):
                try:
                    res = await asyncio.wait_for(
                        self.ai_system.process(task),
                        timeout=self.test_duration_per_query_ms / 1000.0,
                    )
                    if getattr(res, "success", False):
                        successes += 1
                except Exception as e:
                    logger.debug(f"reliability attempt failed for '{task[:40]}...': {e}")
            estimate = self._pass_hat_k_estimator(successes, n, k)
            per_task_estimates.append(estimate)

        duration_ms = int((time.perf_counter() - started) * 1000)
        if not per_task_estimates:
            return results

        aggregate = statistics.mean(per_task_estimates)
        results.append(
            BenchmarkResult(
                test_name=f"pass_hat_k_reliability_k{k}",
                category=BenchmarkCategory.RELIABILITY,
                score=round(aggregate, 4),
                value=round(aggregate, 4),
                unit="ratio",
                passed=aggregate >= self.reliability_threshold,
                threshold=self.reliability_threshold,
                duration_ms=duration_ms,
                details={
                    "k": k,
                    "samples_per_task": n,
                    "tasks": len(task_set),
                    "estimator": "C(s,k)/C(n,k)",
                },
            )
        )
        return results

    async def _detect_limits(self, results: list[BenchmarkResult]) -> list[LimitDetection]:
        limits: list[LimitDetection] = []
        for r in results:
            if not r.passed or r.score < 0.6:
                limits.append(
                    LimitDetection(
                        metric_name=r.test_name,
                        current_value=r.value,
                        max_sustainable=r.threshold * 0.9,
                        breaking_point=r.threshold,
                        unit=r.unit,
                        confidence=round(1.0 - r.score, 2),
                        recommendations=[f"Optimize {r.test_name}"],
                    )
                )
        return limits

    async def _identify_weaknesses(self, results: list[BenchmarkResult]) -> list[WeaknessReport]:
        weaknesses: list[WeaknessReport] = []
        for r in results:
            if r.score < 0.7:
                weaknesses.append(
                    WeaknessReport(
                        area=r.category.value,
                        severity="major" if r.score < 0.5 else "minor",
                        current_score=r.score,
                        target_score=0.85,
                        impact_description=f"Low score on {r.test_name}",
                        suggested_improvements=[f"Tune {r.test_name}"],
                        priority=1 if r.score < 0.5 else 2,
                    )
                )
        return weaknesses

    def _calculate_overall_score(self, results: list[BenchmarkResult]) -> float:
        if not results:
            return 0.0
        return statistics.mean([r.score for r in results])

    def _score_to_grade(self, score: float) -> str:
        if score >= 0.95:
            return "A+"
        if score >= 0.90:
            return "A"
        if score >= 0.85:
            return "B+"
        if score >= 0.80:
            return "B"
        if score >= 0.75:
            return "C+"
        if score >= 0.70:
            return "C"
        if score >= 0.60:
            return "D"
        return "F"

    def _generate_optimization_plan(
        self, weaknesses: list[WeaknessReport], limits: list[LimitDetection]
    ) -> dict[str, Any]:
        return {
            "priority_actions": [w.area for w in weaknesses],
            "parameter_adjustments": {limit.metric_name: limit.max_sustainable for limit in limits},
            "estimated_improvement": 0.15,
        }

    def _generate_summary(
        self,
        results: list[BenchmarkResult],
        overall_score: float,
        grade: str,
        weaknesses: list[WeaknessReport],
    ) -> dict[str, Any]:
        passed = sum(1 for r in results if r.passed)
        total = len(results)
        return {
            "grade": grade,
            "overall_score": round(overall_score, 4),
            "tests_passed": passed,
            "tests_total": total,
            "pass_rate": round(passed / total, 2) if total > 0 else 0.0,
            "weakness_count": len(weaknesses),
            "critical_issues": sum(1 for w in weaknesses if w.severity == "critical"),
        }

    def _generate_test_queries(self) -> dict[str, list[str]]:
        return {
            "general": [
                "What is 2+2?",
                "Explain photosynthesis simply",
                "What is the capital of France?",
            ],
            "development": [
                "Debug this Python code: def divide(a,b): return a/b",
                "Write a function to reverse a string",
            ],
            "business": [
                "Analyze our Q3 revenue growth",
                "Calculate ROI for marketing campaign",
            ],
            "ux_design": [
                "Design a modern login page using React",
                "Create accessible navigation menu",
            ],
        }

    def get_improvement_trend(self) -> dict[str, Any]:
        if len(self.benchmark_history) < 2:
            return {"trend": "insufficient_data", "improvement": 0.0}
        recent = self.benchmark_history[-1].overall_score
        first = self.benchmark_history[0].overall_score
        diff = recent - first
        return {
            "trend": "improving" if diff > 0.02 else ("declining" if diff < -0.02 else "stable"),
            "improvement": round(diff, 4),
            "benchmarks_compared": len(self.benchmark_history),
        }
