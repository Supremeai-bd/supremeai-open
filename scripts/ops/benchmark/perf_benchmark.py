#!/usr/bin/env python3
"""
Performance Benchmark for SupremeAI 2.0
Measures API latency, throughput, and resource usage.
"""

import argparse
import statistics
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx required: pip install httpx")
    sys.exit(1)


def benchmark_endpoint(base_url: str, path: str, num_requests: int = 50):
    url = f"{base_url}{path}"
    latencies = []
    success = 0
    failures = 0

    with httpx.Client(timeout=30.0) as client:
        for i in range(num_requests):
            start = time.perf_counter()
            try:
                resp = client.get(url)
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
                if resp.status_code < 400:
                    success += 1
                else:
                    failures += 1
            except Exception as exc:
                failures += 1
                print(f"Request {i+1} failed: {exc}")

    if not latencies:
        print(f"No successful requests to {path}")
        return

    print(f"\n=== Benchmark: {path} ===")
    print(f"Requests: {num_requests} | Success: {success} | Failures: {failures}")
    print(f"Min:    {min(latencies)*1000:.1f} ms")
    print(f"Median: {statistics.median(latencies)*1000:.1f} ms")
    print(f"P95:    {sorted(latencies)[int(len(latencies)*0.95)]*1000:.1f} ms")
    print(f"Max:    {max(latencies)*1000:.1f} ms")
    print(f"RPS:    {num_requests / sum(latencies):.1f}")


def main():
    parser = argparse.ArgumentParser(description="SupremeAI Performance Benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base API URL")  # is_local()
    parser.add_argument("--requests", type=int, default=50, help="Number of requests per endpoint")
    parser.add_argument("--endpoints", nargs="+", default=[
        "/health",
        "/api/v1/metrics",
        "/api/v1/repos?limit=10",
    ])
    args = parser.parse_args()

    print(f"Benchmarking {args.url} with {args.requests} requests per endpoint...")
    for ep in args.endpoints:
        benchmark_endpoint(args.url, ep, args.requests)


if __name__ == "__main__":
    main()
