"""Circuit Breaker — Resilience pattern for preventing cascading failures.

বাংলা: সার্কিট ব্রেকার — ক্যাসকেডিং ফেইলিওর প্রতিরোধের জন্য রেজিলিয়েন্স প্যাটার্ন।

Tracks failure/success counts and opens the circuit when threshold exceeded.
After cooldown, transitions to half-open state for recovery testing.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from core.logging_config import logger

from ..config import settings  # Fixed import path - using relative import

T = TypeVar("T")


class CircuitBreakerState(StrEnum):
    """Circuit breaker states.

    Issue #684 (H-05): this enum is the CANONICAL breaker-state vocabulary.
    Other breaker implementations historically spelled the same states as
    "open"/"closed"/"half_open" (core.circuit_breaker.CircuitState — whose
    lowercase values are persisted to Redis and exposed via API payloads),
    "HALF-OPEN" with a hyphen (predictive breaker), or raw string literals
    (auto-healer, redis client, chaos worker). Do NOT introduce new state
    literals: reuse these members, and route any externally-produced state
    string through normalize_circuit_state() before comparing.
    """

    CLOSED = "CLOSED"  # Normal operation — requests pass through
    OPEN = "OPEN"  # Failing — requests are rejected immediately
    HALF_OPEN = "HALF_OPEN"  # Testing — limited requests allowed


def normalize_circuit_state(value: Any) -> CircuitBreakerState:
    """Normalize any externally-produced breaker-state representation to the canonical enum.

    Issue #684 (H-05): breaker state strings reached the codebase in several
    casings/spellings ("open", "OPEN", "half-open", "HALF_OPEN", ...). Old
    serialized values (Redis ``circuit_breaker:<name>:state`` keys written by
    RedisCircuitBreaker, cached API payloads) must keep comparing correctly,
    so readers normalize instead of producers rewriting history. Case- and
    separator-insensitive; unknown values fall back to CLOSED with a warning
    (this helper is for status reporting/comparison, not a request gate).
    """
    if isinstance(value, CircuitBreakerState):
        return value
    text = str(value or "").strip().upper().replace("-", "_")
    try:
        return CircuitBreakerState(text)
    except ValueError:
        logger.warning(
            f"Unknown circuit breaker state {value!r}; normalizing to {CircuitBreakerState.CLOSED.value}"
        )
        return CircuitBreakerState.CLOSED


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit breaker is OPEN and a request is rejected.

    বাংলা: সার্কিট ব্রেকার OPEN থাকলে রিকোয়েস্ট রিজেক্ট হলে এই এক্সেপশন রেইজ হয়।
    RuntimeError থেকে inherit করা হয়েছে যাতে contextlib.suppress(RuntimeError) দিয়ে
    suppress করা যায় এবং pytest.raises(RuntimeError) দিয়ে catch করা যায়।
    """

    def __init__(self, name: str, state: CircuitBreakerState) -> None:
        self.name = name
        self.state = state
        super().__init__(f"Circuit breaker '{name}' is {state.value}. Request rejected.")


class CircuitBreaker:
    """Circuit breaker for a specific operation or service.

    বাংলা: নির্দিষ্ট অপারেশন বা সার্ভিসের জন্য সার্কিট ব্রেকার।

    Attributes:
        name: Identifier for this breaker (e.g., service name).
        failure_threshold: Number of consecutive failures to open the circuit.
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN.
        state: Current circuit state.
        failure_count: Current consecutive failure count.
        success_count: Current consecutive success count (for half-open recovery).
        last_failure_time: Timestamp of the last failure.
        last_success_time: Timestamp of the last success.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int | None = None,
        recovery_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        self.name = name
        # Issue #895: আগে `failure_threshold or settings.circuit_breaker_failure_threshold`
        # ব্যবহার হতো — কিন্তু `0` falsy চেকে পড়ে যায়, ফলে test যখন `recovery_timeout=0`
        # (instant recovery) দেয়, সেটা silently default 60s দিয়ে replace হয়ে যেত।
        # Explicit `None` চেক করে সেই regression ঠেকানো হলো।
        self.failure_threshold = (
            failure_threshold
            if failure_threshold is not None
            else settings.circuit_breaker_failure_threshold
        )
        self.recovery_timeout = float(
            recovery_timeout
            if recovery_timeout is not None
            else settings.circuit_breaker_cooldown_period
        )

        self.state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_failure_time: float | None = None
        self.last_success_time: float | None = None
        self.opened_at: float | None = None
        self._recovery_in_progress: bool = False
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        with self._lock:
            return f"CircuitBreaker(name='{self.name}', state={self.state.value}, failures={self.failure_count}, successes={self.success_count})"

    @property
    def is_open(self) -> bool:
        """Check if the circuit is currently open.

        বাংলা: সার্কিট বর্তমানে OPEN কিনা চেক করে।
        """
        with self._lock:
            return self.state == CircuitBreakerState.OPEN

    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery.

        বাংলা: রিকভারি চেষ্টা করার জন্য যথেষ্ট সময় পেরিয়েছে কিনা চেক করে।
        opened_at ব্যবহার করা হয় যাতে টেস্টে সহজে ম্যানিপুলেট করা যায়।
        """
        if self.opened_at is None:
            return True
        return (time.monotonic() - self.opened_at) >= self.recovery_timeout

    def allow_request(self) -> bool:
        """Check if a request should be allowed to proceed."""
        with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True

            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_recovery():
                    logger.info(
                        f"Circuit breaker '{self.name}' transitioning to HALF_OPEN for recovery test"
                    )
                    self.state = CircuitBreakerState.HALF_OPEN
                    self._recovery_in_progress = True
                    return True
                return False

            if self.state == CircuitBreakerState.HALF_OPEN:
                if not self._recovery_in_progress:
                    self._recovery_in_progress = True
                    return True
                return False

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Allow CircuitBreaker instance to be used as a decorator.

        বাংলা: CircuitBreaker ইন্সট্যান্সকে ডেকোরেটর হিসেবে ব্যবহার করতে দেয়।
        """
        import functools
        import inspect

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await self.acall(func, *args, **kwargs)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return self.call(func, *args, **kwargs)

            return sync_wrapper

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a function with circuit breaker protection (sync or async).

        Implements FAIL-CLOSED strategy: raises CircuitBreakerOpenError when
        the circuit is OPEN and not ready for recovery, preventing execution
        of the underlying function.

        বাংলা: সার্কিট ব্রেকার প্রোটেকশন সহ ফাংশন এক্সিকিউট করে।
        যদি func একটি async function হয়, তাহলে acall() coroutine return করা হয়
        যাতে caller নিজে await বা asyncio.run() করতে পারে।
        এটি নিশ্চিত করে যে async function এর failure সঠিকভাবে ট্র্যাক হবে।

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN and not ready for recovery.
        """
        import inspect

        # বাংলা মন্তব্য: async function detect করে acall() coroutine return করা হচ্ছে।
        # এটা করলে caller asyncio.run() বা await দিয়ে সঠিকভাবে execute করতে পারবে।
        # nested asyncio.run() এড়াতে এখানে আমরা asyncio.run() করি না।
        if inspect.iscoroutinefunction(func):
            return self.acall(func, *args, **kwargs)  # type: ignore[return-value]

        kwargs.pop("_correlation_id", None)

        # Check if request is allowed before executing
        if not self.allow_request():
            err = CircuitBreakerOpenError(self.name, self.state)
            logger.error(
                f"Circuit breaker '{self.name}' rejected request - state: {self.state.value}"
            )
            raise err

        try:
            result = func(*args, **kwargs)
            self.mark_success()
            return result
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning(f"Circuit breaker '{self.name}' caught recoverable error: {exc}")
            self.mark_failure()
            raise
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            logger.opt(exception=True).error(
                f"Circuit breaker '{self.name}' caught unexpected error type={type(exc).__name__}"
            )
            self.mark_failure()
            raise

    async def call_async(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Async alias of :meth:`acall`.

        বাংলা: `acall`-এর পাবলিক async alias। অনেক caller/test `call_async` নামের API
        contract ধরে রেখেছে (যেমন ``backend/tests/core/test_circuit_breaker.py``), তাই
        `acall`-এর implementation এক রেখে এই alias দেওয়া হয়েছে — নতুন behavior নয়,
        শুধু naming compatibility।
        """
        return await self.acall(func, *args, **kwargs)

    async def acall(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Execute an async function with circuit breaker protection.

        Implements FAIL-CLOSED strategy: raises CircuitBreakerOpenError when
        the circuit is OPEN and not ready for recovery, preventing execution
        of the underlying function.

        বাংলা: সার্কিট ব্রেকার প্রোটেকশন সহ অ্যাসিঙ্ক্রোনাস ফাংশন এক্সিকিউট করে।

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN and not ready for recovery.
        """
        kwargs.pop("_correlation_id", None)

        # Check if request is allowed before executing
        if not self.allow_request():
            err = CircuitBreakerOpenError(self.name, self.state)
            logger.error(
                f"Circuit breaker '{self.name}' rejected request - state: {self.state.value}"
            )
            raise err

        try:
            result = await func(*args, **kwargs)
            self.mark_success()
            return result
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning(f"Circuit breaker '{self.name}' caught recoverable error: {exc}")
            self.mark_failure()
            raise
        except CircuitBreakerOpenError:
            raise
        except Exception as exc:
            logger.opt(exception=True).error(
                f"Circuit breaker '{self.name}' caught unexpected error type={type(exc).__name__}"
            )
            self.mark_failure()
            raise

    def mark_success(self) -> None:
        """Record a successful call and potentially close the circuit.

        বাংলা: সফল কল রেকর্ড করে এবং সম্ভবত সার্কিট বন্ধ করে।
        """
        with self._lock:
            self.success_count += 1
            self.failure_count = 0  # Reset failure count on success
            self.last_success_time = time.monotonic()

            if self.state == CircuitBreakerState.HALF_OPEN:
                # After a successful test in HALF_OPEN, close the circuit
                logger.info(f"Circuit breaker '{self.name}' closing after successful recovery test")
                self.state = CircuitBreakerState.CLOSED
                self._recovery_in_progress = False
            elif self.state == CircuitBreakerState.CLOSED:
                logger.debug(
                    f"Circuit breaker '{self.name}' recorded success (total: {self.success_count})"
                )

    def mark_failure(self) -> None:
        """Record a failed call and potentially open the circuit.

        Implements FAIL-CLOSED strategy: when failure threshold is exceeded,
        the circuit is opened to prevent further damage.

        বাংলা: ব্যর্থ কল রেকর্ড করে এবং সম্ভবত সার্কিট খুলে।
        """
        with self._lock:
            self.failure_count += 1
            self.success_count = 0  # Reset success count on failure
            self.last_failure_time = time.monotonic()

            if self.state == CircuitBreakerState.HALF_OPEN:
                # Recovery test failed, reopen the circuit
                logger.warning(
                    f"Circuit breaker '{self.name}' reopening after failed recovery test"
                )
                self._open_circuit()
            elif (
                self.state == CircuitBreakerState.CLOSED
                and self.failure_count >= self.failure_threshold
            ):
                # Threshold exceeded, open the circuit
                logger.warning(
                    f"Circuit breaker '{self.name}' opening after {self.failure_count} consecutive failures"
                )
                self._open_circuit()
            elif self.state == CircuitBreakerState.CLOSED:
                logger.debug(
                    f"Circuit breaker '{self.name}' recorded failure ({self.failure_count}/{self.failure_threshold})"
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state.

        বাংলা: ম্যানুয়ালি সার্কিট ব্রেকারকে CLOSED স্টেটে রিসেট করে।
        """
        with self._lock:
            logger.info(f"Circuit breaker '{self.name}' manually reset")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.last_success_time = None
            # বাংলা মন্তব্য: রিসেটে opened_at ক্লিয়ার করা হচ্ছে
            self.opened_at = None
            self._recovery_in_progress = False

    def _open_circuit(self) -> None:
        """Open the circuit and record the time.

        Implements FAIL-CLOSED strategy: opens the circuit to prevent further
        requests from passing through when the service is unstable.

        বাংলা: সার্কিট খুলে দেয় এবং সময় রেকর্ড করে।
        """
        self.state = CircuitBreakerState.OPEN
        self.opened_at = time.monotonic()
        self._recovery_in_progress = False
        logger.info(f"Circuit breaker '{self.name}' is now OPEN - requests will be rejected")

    def force_close(self) -> None:
        """Force the circuit to close (use with caution in emergency situations).

        বাংলা: জোর করে সার্কিট বন্ধ করে দেয় (জরুরি অবস্থায় সাবধানে ব্যবহার করুন)।
        """
        with self._lock:
            logger.warning(f"Circuit breaker '{self.name}' force closed by operator")
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.opened_at = None
            self._recovery_in_progress = False

    def force_open(self) -> None:
        """Force the circuit to open (use for maintenance or emergency shutdown).

        Implements FAIL-CLOSED strategy: can be used to manually open the circuit
        when a service needs to be taken offline safely.

        বাংলা: জোর করে সার্কিট খুলে দেয় (রক্ষণাবেক্ষণ বা জরুরি বন্ধের জন্য ব্যবহার করুন)।
        """
        with self._lock:
            logger.warning(f"Circuit breaker '{self.name}' force opened by operator")
            self._open_circuit()

    def get_state_info(self) -> dict[str, Any]:
        """Get detailed information about the circuit breaker state.

        বাংলা: সার্কিট ব্রেকারের বর্তমান অবস্থা সম্পর্কে বিস্তারিত তথ্য দেয়।
        """
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self.last_failure_time,
                "last_success_time": self.last_success_time,
                "opened_at": self.opened_at,
                "is_recovery_in_progress": self._recovery_in_progress,
                # ROOT-CAUSE FIX (issue #1070): do NOT call self.is_open here —
                # it re-acquires self._lock (non-reentrant threading.Lock) while
                # get_state_info() already holds it -> guaranteed self-deadlock
                # for ANY caller iterating breakers (e.g. /llm-gateway/health)
                # once at least one breaker exists. Read self.state directly.
                "is_open": self.state == CircuitBreakerState.OPEN,
            }

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics for monitoring.

        বাংলা: মনিটরিংয়ের জন্য বর্তমান মেট্রিক্স রিটার্ন করে।
        """
        with self._lock:
            state_val = 0
            if self.state == CircuitBreakerState.OPEN:
                state_val = 2
            elif self.state == CircuitBreakerState.HALF_OPEN:
                state_val = 1

            return {
                f'circuit_breaker_state{{name="{self.name}"}}': state_val,
                f'circuit_breaker_failures_total{{name="{self.name}"}}': self.failure_count,
                f'circuit_breaker_successes_total{{name="{self.name}"}}': self.success_count,
            }


# =============================================================================
# Async circuit-breaker family (consolidated from core/circuit_breaker.py)
#
# Issue #2250: the legacy `core.circuit_breaker` module is retired so every
# breaker caller shares ONE import path. The classes below are a verbatim
# behavior-preserving port of the legacy v3.0 async state machine + the
# Redis-backed compatibility API:
#   - `AsyncCircuitBreaker` (legacy class name `CircuitBreaker`): async
#     `protect()` context manager, asyncio.Lock, consecutive-failure threshold,
#     success-threshold HALF_OPEN recovery, `CircuitStats` counters.
#   - `RedisCircuitBreaker`: `should_attempt_external()` / `record_success()` /
#     `record_failure()` surface used by the chat path, with central Redis
#     state and in-memory fallback.
#   - `CIRCUITS` / `get_circuit()` / `sync_from_db()`: shared registry and
#     DB-driven threshold sync (ConfigService `circuit_breaker_configs`).
# The lowercase `CircuitState` spelling below is PERSISTED to Redis
# (`circuit_breaker:<name>:state`) and exposed in API payloads — do NOT
# re-case it; normalize via `normalize_circuit_state()` when comparing
# against `CircuitBreakerState` (issue #684, H-05). Full semantic unification
# of the sync/async pair is tracked under issue #688.
# =============================================================================


class CircuitState(StrEnum):
    """Async-family breaker states (lowercase, Redis-persisted family).

    Issue #684 (H-05): the canonical breaker-state enum is
    ``CircuitBreakerState`` above (uppercase values). These lowercase values
    are PERSISTED to Redis (``circuit_breaker:<name>:state``, written by
    RedisCircuitBreaker) and exposed in API payloads, so the spelling must
    NOT change — backward compatibility with already-serialized state.
    Cross-family comparisons must normalize via ``normalize_circuit_state()``.
    """

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject immediately
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitStats:
    """Statistics for an async-family circuit breaker."""

    total_requests: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_rejections: int = 0  # Rejected while OPEN
    current_state: CircuitState = CircuitState.CLOSED
    last_failure_time: float = 0
    last_success_time: float = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class CircuitBreakerError(Exception):
    """Raised when the async-family breaker is OPEN and a request is rejected."""

    def __init__(self, name: str, state: CircuitState, recovery_in: float):
        self.name = name
        self.state = state
        self.recovery_in = recovery_in
        super().__init__(
            f"Circuit '{name}' is OPEN. "
            f"Recovery in ~{recovery_in:.0f}s. "
            f"Requests are being rejected."
        )


class AsyncCircuitBreaker:
    """
    Async circuit breaker (legacy v3.0 state machine, ported verbatim).

    Prevents cascading failures by temporarily stopping calls to
    failing services and automatically testing for recovery.

    Usage:
        cb = AsyncCircuitBreaker(name="gemini_api", failure_threshold=5)
        async with cb.protect():
            result = await call_external_api()
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Identifier for this circuit (for logging/metrics)
            failure_threshold: Consecutive failures before opening
            success_threshold: Successes in HALF_OPEN before closing
            recovery_timeout: Seconds before trying HALF_OPEN
            half_open_max_calls: Max concurrent test requests in HALF_OPEN
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        self._stats = CircuitStats()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def stats(self) -> CircuitStats:
        return self._stats

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try HALF_OPEN."""
        if self._state != CircuitState.OPEN:
            return False
        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.recovery_timeout

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self._stats.total_successes += 1
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._half_open_calls = 0
            else:  # CLOSED
                self._failure_count = 0
                self._consecutive_failures = 0

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._stats.total_failures += 1
            self._stats.last_failure_time = time.time()
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                # Failure in HALF_OPEN → back to OPEN
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()
                self._half_open_calls = 0
            elif self._failure_count >= self.failure_threshold:
                # Threshold reached → OPEN
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()

    @asynccontextmanager
    async def protect(self):
        """
        Context manager that wraps a call with circuit breaker protection.

        Raises:
            CircuitBreakerError: If circuit is OPEN
        """
        self._stats.total_requests += 1

        async with self._lock:
            # Check if we should try reset
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0

            self._stats.current_state = self._state

            if self._state == CircuitState.OPEN:
                self._stats.total_rejections += 1
                recovery_in = self.recovery_timeout - (time.time() - self._last_failure_time)
                raise CircuitBreakerError(self.name, self._state, recovery_in)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._stats.total_rejections += 1
                    raise CircuitBreakerError(self.name, self._state, 0)
                self._half_open_calls += 1

        try:
            yield
            await self._on_success()
        except Exception:
            await self._on_failure()
            raise

    def get_recovery_time(self) -> float:
        """Get seconds until circuit may attempt recovery."""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    def reset(self) -> None:
        """Manually reset circuit to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0


# Pre-configured circuits for common services
CIRCUITS: dict[str, AsyncCircuitBreaker] = {
    "gemini_api": AsyncCircuitBreaker("gemini_api", failure_threshold=5, recovery_timeout=30),
    "groq_api": AsyncCircuitBreaker("groq_api", failure_threshold=5, recovery_timeout=30),
    "openrouter_api": AsyncCircuitBreaker(
        "openrouter_api", failure_threshold=5, recovery_timeout=30
    ),
    "database": AsyncCircuitBreaker("database", failure_threshold=3, recovery_timeout=15),
    "external_http": AsyncCircuitBreaker("external_http", failure_threshold=5, recovery_timeout=20),
}


async def sync_from_db(db: Any) -> None:
    """Sync circuit breaker thresholds from the database configuration."""
    # Lazy import: keeps the resilience package import-graph free of the
    # services layer at module load (behavior identical to the legacy
    # module-level import — sync_from_db() is the only consumer).
    from services.config_service import ConfigService

    global CIRCUITS
    try:
        # We serialize the default dict to a dict of config kwargs for fallback
        default_configs = {
            name: {
                "failure_threshold": cb.failure_threshold,
                "recovery_timeout": cb.recovery_timeout,
            }
            for name, cb in CIRCUITS.items()
        }

        configs = await ConfigService.get_config(db, "circuit_breaker_configs", default_configs)

        if configs:
            for name, cfg in configs.items():
                if name in CIRCUITS:
                    CIRCUITS[name].failure_threshold = cfg.get(
                        "failure_threshold", CIRCUITS[name].failure_threshold
                    )
                    CIRCUITS[name].recovery_timeout = float(
                        cfg.get("recovery_timeout", CIRCUITS[name].recovery_timeout)
                    )
                else:
                    CIRCUITS[name] = AsyncCircuitBreaker(
                        name=name,
                        failure_threshold=cfg.get("failure_threshold", 5),
                        recovery_timeout=float(cfg.get("recovery_timeout", 30.0)),
                    )
            logger.info(f"✅ Synced {len(configs)} circuit_breaker_configs from DB.")
    except Exception as e:
        logger.error(f"❌ Failed to sync circuit_breaker_configs from DB: {e}")


def get_circuit(name: str) -> AsyncCircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in CIRCUITS:
        CIRCUITS[name] = AsyncCircuitBreaker(name)
    return CIRCUITS[name]


class RedisCircuitBreaker(AsyncCircuitBreaker):
    """
    Circuit breaker with a Redis-backed compatibility API.

    Provides the should_attempt_external() / record_success() / record_failure()
    surface used by call sites written against the original Redis-based circuit
    breaker (see core/cache/redis_manager.py), while delegating actual
    open/closed/half-open bookkeeping to the async state machine above. State
    is tracked centrally in Redis when available (shared across workers), and
    falls back to local in-memory state if Redis is unreachable.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        super().__init__(
            name=name, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout
        )
        self.prefix = f"circuit_breaker:{name}"

    async def _get_redis_client(self):
        try:
            from core.cache.redis_manager import redis_manager

            return await redis_manager.get_client_async()
        except Exception as e:
            logger.debug(f"RedisCircuitBreaker: Redis unavailable ({e}), using in-memory state")
            return None

    async def record_success(self) -> None:
        await self._on_success()
        client = await self._get_redis_client()
        if not client:
            return
        try:
            await client.set(f"{self.prefix}:state", self._state.value)
            await client.set(f"{self.prefix}:failures", self._failure_count)
        except Exception as e:
            logger.error(f"RedisCircuitBreaker record_success sync failed: {e}")

    async def record_failure(self) -> None:
        await self._on_failure()
        client = await self._get_redis_client()
        if not client:
            return
        try:
            await client.set(f"{self.prefix}:state", self._state.value)
            await client.set(f"{self.prefix}:failures", self._failure_count)
            if self._state == CircuitState.OPEN:
                await client.set(f"{self.prefix}:opened_at", self._last_failure_time)
        except Exception as e:
            logger.error(f"RedisCircuitBreaker record_failure sync failed: {e}")

    async def should_attempt_external(self) -> bool:
        """Return True if a call should be attempted (mirrors protect()'s gate logic)."""
        async with self._lock:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0

            if self._state == CircuitState.OPEN:
                return False
            if self._state == CircuitState.HALF_OPEN:
                return self._half_open_calls < self.half_open_max_calls
            return True
