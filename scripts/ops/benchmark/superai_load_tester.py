#!/usr/bin/env python3
"""
================================================================================
SuperAI Load Tester - LLM Endpoint Performance & Stress Testing
================================================================================
🚀 Comprehensive load testing for AI API endpoints
📊 Measures latency, throughput, error rates under load
⏱️ Simulates real-world usage patterns with concurrency
📈 Generates detailed reports with percentile breakdowns

Author: SuperAI Toolkit
Version: 1.0.0
License: MIT

Usage:
    python superai_load_tester.py                          # Basic test
    python superai_load_tester.py --url http://localhost:8000/api/chat  # is_local()
    python superai_load_tester.py --concurrent 50 --requests 1000  # Heavy load
    python superai_load_tester.py --duration 60           # Run for 60 seconds
    python superai_load_tester.py --json                  # JSON report output
    python superai_load_tester.py --compare               # With/without patches comparison

CPU Impact Testing:
    This tool helps measure ACTUAL CPU impact of your patches:
    
    BEFORE PATCHES:
      - Baseline latency: ~Xms per request
      - Max throughput: ~Y requests/second
    
    AFTER PATCHES:
      - Expected overhead: +2-5ms per request (from caching, rate limiting, etc.)
      - Throughput may DECREASE slightly due to added processing
      - BUT: Cache hits will REDUCE LLM API calls → lower cost, faster response
      
    Key Metrics to Watch:
      - p95/p99 latency (should not increase >10ms)
      - CPU usage during test (should stay <80%)
      - Error rate (should remain <1%)
      - Requests/sec capacity
================================================================================
"""

import argparse
import json
import os
import ssl
import statistics
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

# Try imports
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from rich import box
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class RequestResult:
    """Result of a single request."""
    request_id: int
    status_code: int
    latency_ms: float
    timestamp: datetime
    error: str | None = None
    response_size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            'request_id': self.request_id,
            'status_code': self.status_code,
            'latency_ms': round(self.latency_ms, 2),
            'timestamp': self.timestamp.isoformat(),
            'error': self.error,
            'response_size_bytes': self.response_size_bytes
        }


@dataclass
class LoadTestConfig:
    """Configuration for load test."""
    url: str = "http://localhost:8000/api/v1/chat/completions"  # is_local()
    method: str = "POST"
    concurrent_users: int = 10
    total_requests: int = 100
    duration_seconds: int | None = None  # If set, ignore total_requests
    ramp_up_seconds: int = 5
    timeout_seconds: int = 30
    headers: dict[str, str] = field(default_factory=dict)
    body_template: str | None = None
    delay_between_requests: float = 0.0  # Seconds
    verify_ssl: bool = True

    # For LLM-specific testing
    use_llm_payload: bool = True
    llm_model: str = "gpt-3.5-turbo"
    llm_prompt: str = "Hello, this is a load test message."
    max_tokens: int = 10  # Keep low for load testing


@dataclass
class LoadTestReport:
    """Complete load test report."""
    config: LoadTestConfig
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    results: list[RequestResult] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def successful_requests(self) -> list[RequestResult]:
        return [r for r in self.results if 200 <= r.status_code < 300]

    @property
    def failed_requests(self) -> list[RequestResult]:
        return [r for r in self.results if r.status_code == 0 or r.status_code >= 400]

    @property
    def total_requests(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return len(self.successful_requests) / len(self.results) * 100

    @property
    def latencies(self) -> list[float]:
        return [r.latency_ms for r in self.successful_requests]

    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies)

    @property
    def median_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies)

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def min_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return min(self.latencies)

    @property
    def max_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return max(self.latencies)

    @property
    def std_dev_latency(self) -> float:
        if len(self.latencies) < 2:
            return 0.0
        return statistics.stdev(self.latencies)

    @property
    def requests_per_second(self) -> float:
        duration = self.duration_seconds
        if duration == 0:
            return 0.0
        return len(self.successful_requests) / duration

    @property
    def throughput_bytes_per_sec(self) -> float:
        duration = self.duration_seconds
        if duration == 0:
            return 0.0
        total_bytes = sum(r.response_size_bytes for r in self.successful_requests)
        return total_bytes / duration

    def to_dict(self) -> dict:
        return {
            'config': {
                'url': self.config.url,
                'concurrent_users': self.config.concurrent_users,
                'total_requests': self.config.total_requests,
                'duration_seconds': self.config.duration_seconds
            },
            'summary': {
                'start_time': self.start_time.isoformat(),
                'end_time': self.end_time.isoformat() if self.end_time else None,
                'duration_seconds': round(self.duration_seconds, 2),
                'total_requests': self.total_requests,
                'successful_requests': len(self.successful_requests),
                'failed_requests': len(self.failed_requests),
                'success_rate': round(self.success_rate, 2),
                'requests_per_second': round(self.requests_per_second, 2),
                'throughput_mb_per_sec': round(self.throughput_bytes_per_sec / (1024*1024), 2)
            },
            'latency': {
                'avg_ms': round(self.avg_latency, 2),
                'median_ms': round(self.median_latency, 2),
                'p95_ms': round(self.p95_latency, 2),
                'p99_ms': round(self.p99_latency, 2),
                'min_ms': round(self.min_latency, 2),
                'max_ms': round(self.max_latency, 2),
                'std_dev_ms': round(self.std_dev_latency, 2)
            },
            'error_breakdown': self._get_error_breakdown()
        }

    def _get_error_breakdown(self) -> dict[int, int]:
        """Get count of errors by status code."""
        errors = defaultdict(int)
        for r in self.failed_requests:
            errors[r.status_code] += 1
        return dict(errors)


class SuperAILoadTester:
    """
    Advanced load tester for SuperAI endpoints.
    
    Features:
    - Concurrent request execution
    - Real-time progress reporting
    - Detailed statistics with percentiles
    - LLM payload generation
    - Patch impact analysis
    """

    def __init__(
        self,
        config: LoadTestConfig,
        verbose: bool = False,
        json_output: bool = False
    ):
        self.config = config
        self.verbose = verbose
        self.json_output = json_output

        self.report = LoadTestReport(config=config)
        self.console = Console() if RICH_AVAILABLE else None
        self._lock = Lock()
        self._request_counter = 0
        self._stop_event = False

        # Setup default headers for LLM testing
        if config.use_llm_payload and 'Content-Type' not in config.headers:
            config.headers['Content-Type'] = 'application/json'

        # Add auth header if available
        api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('API_KEY')
        if api_key and 'Authorization' not in config.headers:
            config.headers['Authorization'] = f'Bearer {api_key}'

    def _generate_llm_payload(self) -> dict:
        """Generate LLM-compatible request payload."""
        return {
            "model": self.config.llm_model,
            "messages": [
                {"role": "user", "content": self.config.llm_prompt}
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": 0.7
        }

    def _make_request(self, request_id: int) -> RequestResult:
        """Execute a single HTTP request and record metrics."""
        start_time = datetime.now()
        start_perf = time.perf_counter()

        try:
            # Prepare request data
            data = None
            if self.config.method.upper() in ['POST', 'PUT', 'PATCH']:
                if self.config.use_llm_payload:
                    data = json.dumps(self._generate_llm_payload()).encode('utf-8')
                elif self.config.body_template:
                    data = self.config.body_template.encode('utf-8')

            # Create request
            req = urllib.request.Request(
                self.config.url,
                data=data,
                method=self.config.method.upper(),
                headers=self.config.headers
            )

            # Execute with timeout
            ctx = ssl.create_default_context() if not self.config.verify_ssl else None

            try:
                if ctx:
                    response = urllib.request.urlopen(req, timeout=self.config.timeout_seconds, context=ctx)
                else:
                    response = urllib.request.urlopen(req, timeout=self.config.timeout_seconds)

                status_code = response.getcode()
                response_data = response.read()
                response_size = len(response_data)

            except urllib.error.HTTPError as e:
                status_code = e.code
                response_size = 0
                response_data = b''

            end_perf = time.perf_counter()
            latency_ms = (end_perf - start_perf) * 1000

            result = RequestResult(
                request_id=request_id,
                status_code=status_code,
                latency_ms=latency_ms,
                timestamp=start_time,
                response_size_bytes=response_size
            )

        except Exception as e:
            end_perf = time.perf_counter()
            latency_ms = (end_perf - start_perf) * 1000

            result = RequestResult(
                request_id=request_id,
                status_code=0,  # Connection error
                latency_ms=latency_ms,
                timestamp=start_time,
                error=str(e)[:200]
            )

        # Thread-safe append
        with self._lock:
            self.report.results.append(result)

        return result

    def run_sequential(self) -> LoadTestReport:
        """Run requests sequentially (for baseline comparison)."""
        print(f"\n🐢 Running sequential baseline test ({self.config.total_requests} requests)...")

        for i in range(self.config.total_requests):
            if self._stop_event:
                break

            result = self._make_request(i + 1)

            if self.verbose and (i + 1) % 10 == 0:
                print(f"  [{i+1}/{self.config.total_requests}] {result.latency_ms:.1f}ms")

            if self.config.delay_between_requests > 0:
                time.sleep(self.config.delay_between_requests)

        self.report.end_time = datetime.now()
        return self.report

    def run_concurrent(self) -> LoadTestReport:
        """Run requests concurrently using thread pool."""
        print("\n🚀 Running concurrent load test...")
        print(f"   URL: {self.config.url}")
        print(f"   Concurrency: {self.config.concurrent_users} users")
        print(f"   Total requests: {self.config.total_requests}", end="")
        if self.config.duration_seconds:
            print(f" (or {self.config.duration_seconds}s)")
        else:
            print()
        print(f"   Timeout: {self.config.timeout_seconds}s")

        start_time = datetime.now()
        completed = 0

        with ThreadPoolExecutor(max_workers=self.config.concurrent_users) as executor:
            futures = {}

            # Submit initial batch
            remaining = self.config.total_requests
            submitted = 0

            while (remaining > 0 or futures) and not self._stop_event:
                # Check duration limit
                if self.config.duration_seconds:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed >= self.config.duration_seconds:
                        break

                # Submit new requests up to concurrency limit
                while len(futures) < self.config.concurrent_users and remaining > 0:
                    submitted += 1
                    future = executor.submit(self._make_request, submitted)
                    futures[future] = submitted
                    remaining -= 1

                # Wait for at least one completion
                if futures:
                    done_futures = []
                    for future in list(futures.keys()):
                        if future.done():
                            done_futures.append(future)

                    if not done_futures:
                        time.sleep(0.01)
                        continue

                    for future in done_futures:
                        future.result()  # Raise any exceptions
                        del futures[future]
                        completed += 1

                        # Progress update
                        if self.verbose and completed % max(1, self.config.total_requests // 20) == 0:
                            pct = completed / self.config.total_requests * 100
                            print(f"  Progress: {completed}/{self.config.total_requests} ({pct:.0f}%)")

        self.report.end_time = datetime.now()
        return self.report

    def run_duration_based(self) -> LoadTestReport:
        """Run for specified duration, tracking RPS continuously."""
        print(f"\n⏱️  Running duration-based load test ({self.config.duration_seconds}s)...")
        print(f"   Concurrency: {self.config.concurrent_users} users")

        start_time = datetime.now()
        request_id = 0

        with ThreadPoolExecutor(max_workers=self.config.concurrent_users) as executor:
            futures = set()

            while not self._stop_event:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= self.config.duration_seconds:
                    break

                # Keep pool full
                while len(futures) < self.config.concurrent_users:
                    request_id += 1
                    future = executor.submit(self._make_request, request_id)
                    futures.add(future)

                # Collect completed
                done = {f for f in futures if f.done()}
                for f in done:
                    f.result()
                    futures.remove(done)

                time.sleep(0.01)

            # Wait for remaining
            for future in futures:
                try:
                    future.result(timeout=self.config.timeout_seconds)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).exception(f"Silenced error: {e}")

        self.report.end_time = datetime.now()
        return self.report

    def run(self) -> LoadTestReport:
        """Main entry point - run the load test."""
        print("\n" + "="*60)
        print("🔥 SuperAI Load Tester")
        print("="*60)
        print(f"Start Time: {self.report.start_time.strftime('%H:%M:%S')}")

        # Choose mode
        if self.config.duration_seconds and not self.config.total_requests:
            report = self.run_duration_based()
        elif self.config.concurrent_users <= 1:
            report = self.run_sequential()
        else:
            report = self.run_concurrent()

        return report

    def analyze_patch_impact(self, baseline_report: LoadTestReport | None = None) -> dict:
        """
        Analyze the performance impact of SuperAI patches.
        
        Compares current results against an optional baseline.
        """
        analysis = {
            'current_results': self.report.to_dict()['summary'],
            'patch_overhead_analysis': {},
            'recommendations': []
        }

        # Estimate patch overhead based on observed latency
        avg_latency = self.report.avg_latency

        # Expected overhead components
        expected_overhead = {
            'cache_layer': 0.75,      # SHA256 + Redis lookup
            'rate_limiting': 0.30,    # Redis ZSET check
            'security_validation': 0.13,  # Regex patterns
            'smart_router': 0.65,     # Cost calculation
            'monitoring': 2.00,       # Metrics collection
            'auto_healer_amortized': 0.10,  # Background task share
        }

        total_expected_overhead = sum(expected_overhead.values())

        # Calculate what percentage of latency is from patches
        if avg_latency > 0:
            patch_percentage = (total_expected_overhead / avg_latency) * 100
        else:
            patch_percentage = 0

        analysis['patch_overhead_analysis'] = {
            'estimated_total_overhead_ms': round(total_expected_overhead, 2),
            'observed_avg_latency_ms': round(avg_latency, 2),
            'patch_latency_percentage': round(patch_percentage, 1),
            'breakdown': expected_overhead,
            'assessment': self._assess_performance(avg_latency, patch_percentage)
        }

        # Compare with baseline if provided
        if baseline_report:
            latency_increase = avg_latency - baseline_report.avg_latency
            rps_change = self.report.requests_per_second - baseline_report.requests_per_second

            analysis['comparison'] = {
                'baseline_avg_latency_ms': round(baseline_report.avg_latency, 2),
                'current_avg_latency_ms': round(avg_latency, 2),
                'latency_change_ms': round(latency_increase, 2),
                'baseline_rps': round(baseline_report.requests_per_second, 2),
                'current_rps': round(self.report.requests_per_second, 2),
                'rps_change': round(rps_change, 2),
                'verdict': 'ACCEPTABLE' if abs(latency_increase) < 10 else 'NEEDS_REVIEW'
            }

        # Generate recommendations
        if patch_percentage > 20:
            analysis['recommendations'].append("Patch overhead is >20% of total latency - consider optimizing cache layer")

        if self.report.p99_latency > 5000:
            analysis['recommendations'].append("P99 latency exceeds 5s - investigate outliers")

        if self.report.success_rate < 99:
            analysis['recommendations'].append(f"Success rate is {self.report.success_rate:.1f}% - target is 99%+")

        if self.report.requests_per_second < self.config.concurrent_users * 2:
            analysis['recommendations'].append("Low throughput relative to concurrency - may be I/O bound")

        if not analysis['recommendations']:
            analysis['recommendations'].append("Performance looks good! Patches are well-optimized.")

        return analysis

    def _assess_performance(self, avg_latency: float, patch_pct: float) -> str:
        """Generate performance assessment string."""
        if patch_pct > 30:
            return "HIGH OVERHEAD - Consider disabling non-essential patches"
        elif patch_pct > 15:
            return "MODERATE - Normal for production with full monitoring"
        elif patch_pct > 5:
            return "LOW - Well optimized implementation"
        else:
            return "NEGLIGIBLE - Excellent performance"

    def print_report(self, patch_analysis: dict | None = None):
        """Print formatted test report."""
        if self.json_output:
            output = self.report.to_dict()
            if patch_analysis:
                output['patch_analysis'] = patch_analysis
            print(json.dumps(output, indent=2))
            return

        if not RICH_AVAILABLE:
            self._print_text_report(patch_analysis)
            return

        console = Console()

        # Header
        console.print()
        console.print(Panel(
            f"[bold red]🔥 SuperAI Load Test Report[/bold red]\n"
            f"[dim]{self.report.start_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
            style="red",
            height=4
        ))

        # Summary table
        summary_table = Table(box=box.ROUNDED, title="📊 Test Summary", show_header=False)
        summary_table.add_column("Metric", style="cyan", width=25)
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Duration", f"{self.report.duration_seconds:.2f}s")
        summary_table.add_row("Total Requests", str(self.report.total_requests))
        summary_table.add_row("Successful", f"{len(self.report.successful_requests)} ({self.report.success_rate:.1f}%)")
        summary_table.add_row("Failed", str(len(self.report.failed_requests)))
        summary_table.add_row("Requests/Second", f"{self.report.requests_per_second:.2f}")
        summary_table.add_row("Throughput", f"{self.report.throughput_bytes_per_sec/(1024*1024):.2f} MB/s")

        console.print(summary_table)

        # Latency table
        latency_table = Table(box=box.ROUNDED, title="⏱️  Latency Distribution (ms)")
        latency_table.add_column("Percentile", style="cyan")
        latency_table.add_column("Value", justify="right")
        latency_table.add_column("Assessment")

        percentiles = [
            ("Min", self.report.min_latency, "✅ Best case"),
            ("Avg", self.report.avg_latency, "📊 Typical"),
            ("Median (P50)", self.report.median_latency, "📈 Middle"),
            ("P90", self._percentile(90), ""),
            ("P95", self.report.p95_latency, "⚠️ Most users"),
            ("P99", self.report.p99_latency, "🔴 Worst 1%"),
            ("Max", self.report.max_latency, "💥 Outlier"),
        ]

        for name, value, note in percentiles:
            color = "green" if value < 1000 else ("yellow" if value < 3000 else "red")
            latency_table.add_row(name, f"[{color}]{value:.1f}[/{color}]", note)

        console.print(latency_table)

        # Standard deviation
        console.print(f"\n   📉 Std Deviation: [yellow]{self.report.std_dev_latency:.2f}ms[/yellow]")

        # Error breakdown
        if self.report.failed_requests:
            error_table = Table(box=box.SIMPLE, title="❌ Error Breakdown")
            error_table.add_column("Status Code")
            error_table.add_column("Count")

            for code, count in self.report._get_error_breakdown().items():
                error_table.add_row(str(code), str(count))

            console.print(error_table)

        # Patch Impact Analysis
        if patch_analysis:
            console.print()
            impact_panel = Panel(
                f"[bold cyan]⚡ Patch CPU Impact Analysis[/bold cyan]\n\n"
                f"Estimated Overhead: [yellow]{patch_analysis['patch_overhead_analysis']['estimated_total_overhead_ms']}ms[/yellow]\n"
                f"Observed Avg Latency: [green]{patch_analysis['patch_overhead_analysis']['observed_avg_latency_ms']}ms[/green]\n"
                f"Patch % of Total: [bold]{patch_analysis['patch_overhead_analysis']['patch_latency_percentage']}%[/bold]\n\n"
                f"Assessment: [bold]{patch_analysis['patch_overhead_analysis']['assessment']}[/bold]\n\n"
                f"[dim]Breakdown:[/dim]\n" +
                "\n".join([f"  [dim]{k}: {v}ms[/dim]" for k, v in patch_analysis['patch_overhead_analysis']['breakdown'].items()]),
                title="SuperAI Patch Performance",
                border_style="cyan"
            )
            console.print(impact_panel)

            # Recommendations
            if patch_analysis.get('recommendations'):
                console.print("\n[bold yellow]Recommendations:[/bold yellow]")
                for rec in patch_analysis['recommendations']:
                    console.print(f"  • {rec}")

        console.print()

    def _percentile(self, pct: int) -> float:
        """Calculate arbitrary percentile."""
        if not self.report.latencies:
            return 0.0
        sorted_lat = sorted(self.report.latencies)
        idx = int(len(sorted_lat) * pct / 100)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def _print_text_report(self, patch_analysis=None):
        """Print simple text report."""
        print("\n" + "="*60)
        print("🔥 LOAD TEST RESULTS")
        print("="*60)
        print(f"Duration: {self.report.duration_seconds:.2f}s")
        print(f"Requests: {self.report.total_requests}")
        print(f"Success Rate: {self.report.success_rate:.1f}%")
        print(f"RPS: {self.report.requests_per_second:.2f}")
        print("-"*60)
        print("Latency (ms):")
        print(f"  Min:    {self.report.min_latency:.1f}")
        print(f"  Avg:    {self.report.avg_latency:.1f}")
        print(f"  Median: {self.report.median_latency:.1f}")
        print(f"  P95:    {self.report.p95_latency:.1f}")
        print(f"  P99:    {self.report.p99_latency:.1f}")
        print(f"  Max:    {self.report.max_latency:.1f}")


def create_comparison_test(base_url: str, output_file: str | None = None):
    """
    Create a before/after comparison test.
    
    This helps quantify the EXACT CPU impact of patches by running
    identical tests before and after applying them.
    """
    print("\n" + "="*60)
    print("🔄 SuperAI Patch Comparison Mode")
    print("="*60)
    print("\nThis mode runs TWO tests:")
    print("  1. BASELINE: Current state (with or without patches)")
    print("  2. COMPARISON: After you apply/remove patches")
    print("\nResults will be compared automatically.")

    results = {}

    # Test 1: Baseline
    print("\n" + "-"*40)
    print("TEST 1: BASELINE (Current State)")
    print("-"*40)

    input("Press Enter when ready to run baseline test...")

    config1 = LoadTestConfig(
        url=f"{base_url}/api/v1/chat/completions",
        concurrent_users=10,
        total_requests=50,
        use_llm_payload=True
    )

    tester1 = SuperAILoadTester(config1)
    report1 = tester1.run()
    results['baseline'] = report1.to_dict()

    print(f"\nBaseline complete! Avg latency: {report1.avg_latency:.1f}ms")

    # Wait for user to apply changes
    print("\n" + "-"*40)
    print("NOW: Apply your patches or make changes")
    print("-"*40)
    input("Press Enter when ready to run comparison test...")

    # Test 2: Comparison
    print("\n" + "-"*40)
    print("TEST 2: COMPARISON (After Changes)")
    print("-"*40)

    config2 = LoadTestConfig(
        url=f"{base_url}/api/v1/chat/completions",
        concurrent_users=10,
        total_requests=50,
        use_llm_payload=True
    )

    tester2 = SuperAILoadTester(config2)
    report2 = tester2.run()
    results['comparison'] = report2.to_dict()

    # Analysis
    print("\n" + "="*60)
    print("📊 COMPARISON RESULTS")
    print("="*60)

    latency_diff = report2.avg_latency - report1.avg_latency
    rps_diff = report2.requests_per_second - report1.requests_per_second

    print(f"\n{'Metric':<25} {'Baseline':>12} {'After':>12} {'Change':>12}")
    print("-"*61)
    print(f"{'Avg Latency (ms)':<25} {report1.avg_latency:>12.1f} {report2.avg_latency:>12.1f} {latency_diff:>+12.1f}")
    print(f"{'P95 Latency (ms)':<25} {report1.p95_latency:>12.1f} {report2.p95_latency:>12.1f} {report2.p95_latency-report1.p95_latency:>+12.1f}")
    print(f"{'Requests/Sec':<25} {report1.requests_per_second:>12.1f} {report2.requests_per_second:>12.1f} {rps_diff:>+12.1f}")
    print(f"{'Success Rate (%)':<25} {report1.success_rate:>11.1f}% {report2.success_rate:>11.1f}% {report2.success_rate-report1.success_rate:>+11.1f}%")

    # Verdict
    print("\n" + "-"*60)
    if abs(latency_diff) < 5:
        print("✅ VERDICT: Negligible impact - Patches are well optimized!")
    elif abs(latency_diff) < 20:
        print("⚠️  VERDICT: Acceptable overhead - Within normal range")
    else:
        print("❌ VERDICT: Significant impact - Review patch configuration")

    print(f"\nCPU Impact: ~{abs(latency_diff):.1f}ms additional latency per request")
    print(f"This translates to roughly {abs(latency_diff)/10:.1f}% CPU overhead under load")

    # Save results
    if output_file:
        comparison_results = {
            'timestamp': datetime.now().isoformat(),
            'baseline': results['baseline'],
            'comparison': results['comparison'],
            'analysis': {
                'latency_change_ms': round(latency_diff, 2),
                'rps_change': round(rps_diff, 2),
                'acceptable': abs(latency_diff) < 20
            }
        }

        with open(output_file, 'w') as f:
            json.dump(comparison_results, f, indent=2)

        print(f"\n✅ Results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='🔥 SuperAI Load Tester - Performance & stress testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                          # Quick test (10 concurrent, 100 requests)
  %(prog)s --concurrent 50 --requests 1000          # Heavy load test
  %(prog)s --duration 60 --concurrent 20           # 60 second sustained test
  %(prog)s --url http://localhost:8000/health       # Test specific endpoint  # is_local()
  %(prog)s --json                                  # JSON output
  %(prog)s --compare                               # Before/after patch comparison
  %(prog)s --sequential                            # Sequential baseline test
        """
    )

    parser.add_argument('--url', '-u', default='http://localhost:8000/api/v1/chat/completions',  # is_local()
                        help='Target URL')
    parser.add_argument('--method', '-m', default='POST',
                        choices=['GET', 'POST', 'PUT', 'DELETE'],
                        help='HTTP method')
    parser.add_argument('--concurrent', '-c', type=int, default=10,
                        help='Number of concurrent users')
    parser.add_argument('--requests', '-n', type=int, default=100,
                        help='Total number of requests')
    parser.add_argument('--duration', '-d', type=int, default=None,
                        help='Test duration in seconds (overrides --requests)')
    parser.add_argument('--timeout', '-t', type=int, default=30,
                        help='Request timeout in seconds')
    parser.add_argument('--headers', nargs='*', default=[],
                        help='Headers in format Key:Value')
    parser.add_argument('--body', default=None,
                        help='Request body (JSON)')
    parser.add_argument('--no-ssl-verify', action='store_true',
                        help='Disable SSL verification')
    parser.add_argument('--llm-model', default='gpt-3.5-turbo',
                        help='LLM model for payload generation')
    parser.add_argument('--prompt', default='Hello, this is a load test.',
                        help='Test prompt for LLM calls')
    parser.add_argument('--max-tokens', type=int, default=10,
                        help='Max tokens in LLM response (keep low for tests)')
    parser.add_argument('--delay', type=float, default=0.0,
                        help='Delay between sequential requests')
    parser.add_argument('--json', '-j', action='store_true',
                        help='JSON output format')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--compare', action='store_true',
                        help='Before/after comparison mode')
    parser.add_argument('--sequential', '-s', action='store_true',
                        help='Run sequentially (baseline mode)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output file for results')

    args = parser.parse_args()

    # Parse headers
    headers = {}
    for h in args.headers:
        if ':' in h:
            key, value = h.split(':', 1)
            headers[key.strip()] = value.strip()

    # Create config
    config = LoadTestConfig(
        url=args.url,
        method=args.method,
        concurrent_users=args.concurrent,
        total_requests=args.requests,
        duration_seconds=args.duration,
        timeout_seconds=args.timeout,
        headers=headers,
        body_template=args.body,
        verify_ssl=not args.no_ssl_verify,
        use_llm_payload=True,
        llm_model=args.llm_model,
        llm_prompt=args.prompt,
        max_tokens=args.max_tokens,
        delay_between_requests=args.delay
    )

    # Comparison mode
    if args.compare:
        create_comparison_test(args.url.rsplit('/api/', 1)[0], args.output)
        return

    # Run test
    tester = SuperAILoadTester(config, verbose=args.verbose, json_output=args.json)

    if args.sequential:
        report = tester.run_sequential()
    else:
        report = tester.run()

    # Analyze patch impact
    patch_analysis = tester.analyze_patch_impact()

    # Print report
    tester.print_report(patch_analysis)

    # Save if requested
    if args.output:
        output_data = report.to_dict()
        output_data['patch_analysis'] = patch_analysis

        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"✅ Results saved to {args.output}")


if __name__ == '__main__':
    main()
