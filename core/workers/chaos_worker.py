# backend/workers/chaos_worker.py
"""Autonomous Self-Testing & Chaos Auditor with Circuit Breaker and Error Bus."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.resilience.circuit_breaker import CircuitBreakerState
from utils.firestore_helpers import get_firestore_db

try:
    from tools.code.fuzz_sandbox import generate_fuzz_payloads, run_sandbox_ast_check
except ImportError:  # pragma: no cover
    generate_fuzz_payloads = None
    run_sandbox_ast_check = None

SERVER_ERROR_THRESHOLD = 500


@dataclass
class AuditResult:
    """Structured result model for Nightly Chaos Audits."""

    passed: bool
    test_count: int
    failure_count: int
    duration_seconds: float
    failures: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "test_count": self.test_count,
            "failure_count": self.failure_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "failures": self.failures,
            "timestamp": self.timestamp,
        }


class CircuitBreaker:
    """Stateful circuit breaker protecting deployment gates from transient lockouts."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 300) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        # Issue #684 (H-05): canonical breaker-state enum instead of raw literals.
        self.state = CircuitBreakerState.CLOSED
        self.cooldown_until: float | None = None

    def is_available(self) -> bool:
        if self.state == CircuitBreakerState.OPEN:
            if self.cooldown_until and time.time() < self.cooldown_until:
                return False
            self.state = CircuitBreakerState.HALF_OPEN
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.cooldown_until = time.time() + self.cooldown_seconds


class NightlyChaosAuditor:
    """Autonomous Self-Testing & Healing Auditor guarded by Circuit Breaker."""

    def __init__(self) -> None:
        self.db = get_firestore_db()
        self.gate_ref = self.db.collection("deploy_gate").document("status") if self.db else None
        self.target_url = os.getenv("STAGING_REPLICA_URL", "").rstrip("/")
        if not self.target_url:
            logger.warning("Chaos auditor disabled: STAGING_REPLICA_URL is not configured")
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=300)
        self.stats = {"total_audits": 0, "passed": 0, "failed": 0}

    @with_error_bus("chaos_audit_run")
    async def execute_audit_sequence(self) -> bool:
        if not self.target_url:
            return False
        start_time = time.perf_counter()
        self.stats["total_audits"] += 1

        if not self.circuit_breaker.is_available():
            logger.warning("Chaos audit skipped: circuit breaker is open.")
            return False

        failures: list[str] = []
        tests_run = 0

        try:
            # 🧪 টেস্ট ১: স্যান্ডবক্স ইন্টিগ্রিটি চেক
            if generate_fuzz_payloads and run_sandbox_ast_check:
                payloads = generate_fuzz_payloads()
                for code, _ in payloads[:20]:
                    tests_run += 1
                    with contextlib.suppress(Exception):
                        if run_sandbox_ast_check(code):
                            failures.append("Sandbox AST bypass detected during fuzzing")
                            logger.critical(
                                "🚨 [SECURITY BREACH] Sandbox bypass detected during autonomous fuzzing!"
                            )
            else:
                # বাংলা মন্তব্য: fuzz_sandbox টুলিং আনঅভেইলেবল (ImportError) মানে এই
                # security-critical চেক আসলে চলেইনি — silently skip করে gate UNLOCKED
                # করা fail-open আচরণ। এর বদলে fail-closed: audit-কে failure হিসেবে গণ্য করা।
                tests_run += 1
                failures.append(
                    "fuzz_sandbox tooling unavailable — sandbox integrity check could not run"
                )
                logger.error(
                    "🚨 [FAIL-CLOSED] fuzz_sandbox unavailable — treating chaos audit as failed, not skipping."
                )

            # 🧪 টেস্ট ২: রানটাইম স্ট্রেস চেক
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"Idempotency-Key": f"auto-chaos-{datetime.now(UTC).timestamp()}"}
                tasks = [
                    client.post(
                        f"{self.target_url}/api/task/execute",
                        json={"message": "Ping"},
                        headers=headers,
                    )
                    for _ in range(5)
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                for res in responses:
                    tests_run += 1
                    if (
                        isinstance(res, Exception)
                        or getattr(res, "status_code", 0) >= SERVER_ERROR_THRESHOLD
                    ):
                        failures.append(f"HTTP Server Error: {res}")
                        logger.error(f"💥 Runtime Connection Failure or Server Error: {res}")

            time.perf_counter() - start_time
            passed = len(failures) == 0

            if passed:
                self.circuit_breaker.record_success()
                self.stats["passed"] += 1
                logger.info("🏆 Autonomous Chaos Audit PASSED perfectly. Deploy gate is UNLOCKED.")
                if self.gate_ref:
                    await asyncio.to_thread(
                        self.gate_ref.set,
                        {
                            "status": "UNLOCKED",
                            "reason": "All self-testing gates green.",
                            "updated_at": datetime.now(UTC),
                        },
                    )
                return True
            else:
                self.circuit_breaker.record_failure()
                self.stats["failed"] += 1
                logger.critical(
                    f"💣 Chaos Audit FAILED with {len(failures)} anomalies. LOCKING deployment gates!"
                )
                if self.gate_ref:
                    await asyncio.to_thread(
                        self.gate_ref.set,
                        {
                            "status": "LOCKED",
                            "reason": f"Audit failed: {len(failures)} anomalies.",
                            "updated_at": datetime.now(UTC),
                        },
                    )
                return False

        except Exception as global_err:
            self.circuit_breaker.record_failure()
            self.stats["failed"] += 1
            logger.critical(
                f"⚠️ Auditor crashed internally: {global_err!s}. Circuit state: {self.circuit_breaker.state}"
            )
            if self.gate_ref:
                await asyncio.to_thread(
                    self.gate_ref.set,
                    {
                        "status": "LOCKED",
                        "reason": f"Auditor crash: {global_err!s}",
                        "updated_at": datetime.now(UTC),
                    },
                )
            return False
