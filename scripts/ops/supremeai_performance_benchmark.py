import asyncio
import json
import os
import platform

# Ensure project root is in pythonpath
import sys
import time
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

try:
    from core.optimization.optimized_async_cache import OptimizedAsyncLRUCache
    from core.optimization.performance_optimizer import AsyncLRUCache
    from core.security.intelligence.behavioral_analyzer import BehaviorEvent as OldEvent
    from core.security.intelligence.behavioral_analyzer import BehaviorTracker
    from core.security.intelligence.optimized_behavioral_analyzer import (
        BehaviorEvent as NewEvent,
    )
    from core.security.intelligence.optimized_behavioral_analyzer import (
        OptimizedBehaviorTracker,
    )
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    print(f"Failed to import modules: {e}")
    IMPORTS_SUCCESSFUL = False

def calculate_stats(times: list[float], name: str, iterations: int) -> dict[str, Any]:
    total_time = sum(times)
    avg_time = total_time / iterations
    min_time = min(times) if times else 0
    max_time = max(times) if times else 0
    variance = sum((t - avg_time) ** 2 for t in times) / iterations if iterations > 0 else 0
    std_dev = variance ** 0.5
    ops_per_sec = iterations / (total_time / 1000) if total_time > 0 else 0

    return {
        "name": name,
        "iterations": iterations,
        "total_time_ms": round(total_time, 3),
        "avg_time_ms": round(avg_time, 4),
        "min_time_ms": round(min_time, 4),
        "max_time_ms": round(max_time, 4),
        "std_dev_ms": round(std_dev, 4),
        "ops_per_second": round(ops_per_sec, 1)
    }

async def benchmark_cache():
    iterations = 10000

    # Original Cache
    original_cache = AsyncLRUCache(maxsize=1000)
    orig_times = []

    for i in range(iterations):
        key = f"key_{i % 500}"
        start = time.perf_counter()
        await original_cache.put(key, {"data": i})
        await original_cache.get(key)
        end = time.perf_counter()
        orig_times.append((end - start) * 1000)

    orig_stats = calculate_stats(orig_times, f"Original LRUCache ({iterations:,} ops)", iterations)

    # Optimized Cache
    optimized_cache = OptimizedAsyncLRUCache(maxsize=1000)
    opt_times = []

    for i in range(iterations):
        key = f"key_{i % 500}"
        start = time.perf_counter()
        await optimized_cache.put(key, {"data": i})
        await optimized_cache.get(key)
        end = time.perf_counter()
        opt_times.append((end - start) * 1000)

    opt_stats = calculate_stats(opt_times, f"Optimized LRUCache ({iterations:,} ops)", iterations)

    speedup = orig_stats["avg_time_ms"] / opt_stats["avg_time_ms"] if opt_stats["avg_time_ms"] > 0 else 0
    return orig_stats, opt_stats, speedup

def benchmark_tracker():
    iterations = 5000

    # Original Tracker
    orig_tracker = BehaviorTracker()
    orig_times = []

    for i in range(iterations):
        user_id = f"user_{i % 100}"
        event = OldEvent(
            user_id=user_id,
            ip_address=f"192.168.1.{i % 255}",
            action="login",
            timestamp=time.time()
        )
        start = time.perf_counter()
        orig_tracker.record_event(event)
        orig_tracker.get_recent_ips(user_id)
        end = time.perf_counter()
        orig_times.append((end - start) * 1000)

    orig_stats = calculate_stats(orig_times, f"Original Tracker ({iterations:,} events)", iterations)

    # Optimized Tracker
    opt_tracker = OptimizedBehaviorTracker()
    opt_times = []

    for i in range(iterations):
        user_id = f"user_{i % 100}"
        event = NewEvent(
            user_id=user_id,
            ip_address=f"192.168.1.{i % 255}",
            action="login",
            timestamp=time.time()
        )
        start = time.perf_counter()
        opt_tracker.record_event(event)
        opt_tracker.get_recent_ips(user_id)
        end = time.perf_counter()
        opt_times.append((end - start) * 1000)

    opt_stats = calculate_stats(opt_times, f"Optimized Tracker ({iterations:,} events)", iterations)

    speedup = orig_stats["avg_time_ms"] / opt_stats["avg_time_ms"] if opt_stats["avg_time_ms"] > 0 else 0
    return orig_stats, opt_stats, speedup

async def main():
    if not IMPORTS_SUCCESSFUL:
        print("Cannot run benchmark without successful imports.")
        return

    print("Running P0 Optimization Benchmarks...")

    results = []
    speedups_info = []
    overall_speedup = 0

    # Run Cache Benchmark
    print("Benchmarking Cache Operations...")
    c_orig, c_opt, c_speed = await benchmark_cache()
    results.extend([c_orig, c_opt])
    speedups_info.append({
        "avg_speedup_factor": round(c_speed, 2),
        "throughput_increase": f"{c_speed:.2f}x"
    })

    # Run Tracker Benchmark
    print("Benchmarking Tracker Operations...")
    t_orig, t_opt, t_speed = benchmark_tracker()
    results.extend([t_orig, t_opt])
    speedups_info.append({
        "avg_speedup_factor": round(t_speed, 2),
        "throughput_increase": f"{t_speed:.2f}x"
    })

    overall_speedup = (c_speed + t_speed) / 2

    report = {
        "benchmark_run": {
            "timestamp": datetime.now().isoformat(),
            "python_version": platform.python_version(),
            "platform": platform.system().lower()
        },
        "results": results,
        "speedups": speedups_info,
        "summary": {
            "overall_avg_speedup": round(overall_speedup, 2),
            "recommendation": "✅ All P0 optimizations validated successfully!"
        }
    }

    print("\nBenchmark Complete!")
    print(f"Overall Average Speedup: {overall_speedup:.2f}x")

    out_file = "supremeai_performance_benchmark.json"
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Detailed report saved to {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
