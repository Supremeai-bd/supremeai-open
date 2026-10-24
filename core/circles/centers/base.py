"""CircleCenter base class — the local coordinator of every FCC circle.

Per the Federated Capability Circle Architecture, each circle center owns
its domain locally and NEVER calls another center or module directly:

    ── local concerns (owned by the center) ──────────────────────────
    registry      local capability registry (name → spec + handler)
    permissions   local permission check before any execution
    retries       local retry policy with bounded attempts/backoff
    health        local health snapshot (counters, latency, last error)
    caching       local TTL cache for idempotent reads (opt-in per spec)
    events        local EventEnvelope emission attached to every result
    adapters      local adapter selection hook for domain modules

Cross-cutting concerns (identity, tenant, global policy, approval,
correlation, execution lifecycle, audit, cross-circle fan-out) belong to
the Global Governance Core — NOT here. Centers must not import each
other; this is enforced by tests/test_fcc_boundaries.py.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from core.circles.contracts import (
    CapabilityRef,
    CapabilityRequest,
    CircleName,
    EventEnvelope,
    ExecutionStatus,
    RiskLevel,
)
from core.circles.envelopes import ExecutionEnvelope, ExecutionError, ResultEnvelope

CenterHandler = Callable[[CapabilityRequest], Awaitable[Any] | Any]


class RetryPolicy(BaseModel):
    """Local retry policy applied to handler exceptions (not policy denials)."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=2, ge=1, le=5)
    backoff_ms: int = Field(default=25, ge=0, le=5_000)


class LocalCapability(BaseModel):
    """A capability registered in ONE circle's local registry."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    approval_required: bool = False
    timeout_ms: int = Field(default=30_000, ge=1, le=300_000)
    cache_ttl_ms: int = Field(default=0, ge=0, le=3_600_000)

    def to_ref(self, circle: CircleName) -> CapabilityRef:
        return CapabilityRef(
            name=self.name,
            owner_circle=circle,
            risk_level=self.risk_level,
            approval_required=self.approval_required,
            timeout_ms=self.timeout_ms,
        )


class CenterHealth(BaseModel):
    """Local health snapshot exposed at center level."""

    model_config = ConfigDict(extra="forbid")

    circle: CircleName
    display_name: str
    owner: str
    status: str = "unknown"
    capabilities: tuple[str, ...] = ()
    total_executions: int = 0
    failed_executions: int = 0
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_execution_at: float | None = None
    avg_latency_ms: float | None = None


class CircleCenter:
    """Base class for every circle center. Subclasses wire domain adapters."""

    circle: ClassVar[CircleName]
    display_name: ClassVar[str] = "Circle"
    owner: ClassVar[str] = "unassigned"

    _CACHE_MAX_ENTRIES = 128
    _LATENCY_WINDOW = 64

    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self._capabilities: dict[str, LocalCapability] = {}
        self._handlers: dict[str, CenterHandler] = {}
        self._retry_policy = retry_policy or RetryPolicy()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._total = 0
        self._failed = 0
        self._last_error: tuple[str, str | None] | None = None
        self._last_execution_at: float | None = None
        self._latencies: deque[float] = deque(maxlen=self._LATENCY_WINDOW)

    # ── local registry ────────────────────────────────────────────────
    def register(self, spec: LocalCapability, handler: CenterHandler) -> None:
        if spec.name in self._capabilities:
            raise ValueError(
                f"Capability already registered in {self.circle.value} circle: {spec.name}"
            )
        self._capabilities[spec.name] = spec
        self._handlers[spec.name] = handler

    def describe(self, capability: str) -> LocalCapability | None:
        return self._capabilities.get(capability)

    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))

    def capability_specs(self) -> tuple[LocalCapability, ...]:
        return tuple(self._capabilities[name] for name in sorted(self._capabilities))

    # ── local permission hook (override for center-local rules) ──────
    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        """Return a denial reason, or None when locally permitted."""
        return None

    # ── local adapter selection hook (override) ──────────────────────
    def resolve_adapter(self, envelope: ExecutionEnvelope) -> Any | None:
        """Select the local domain adapter for this execution."""
        return None

    # ── execution lifecycle (template method) ────────────────────────
    async def handle(self, envelope: ExecutionEnvelope) -> ResultEnvelope:
        started = time.perf_counter()
        spec = self._capabilities.get(envelope.capability)
        if spec is None:
            return self._result(
                envelope,
                ExecutionStatus.UNAVAILABLE,
                error_code="capability_not_registered",
                error_message=f"{envelope.capability} is not registered in the "
                f"{envelope.circle.value} circle",
            )

        if not envelope.actor_id.strip() or not envelope.tenant_id.strip():
            return self._result(
                envelope,
                ExecutionStatus.REJECTED,
                error_code="execution_context_incomplete",
                error_message="actor_id and tenant_id are required",
            )

        denial = self.local_permission(envelope)
        if denial is not None:
            return self._result(
                envelope,
                ExecutionStatus.REJECTED,
                error_code="local_permission_denied",
                error_message=denial,
            )

        if spec.approval_required:
            return self._result(
                envelope,
                ExecutionStatus.APPROVAL_REQUIRED,
                error_code="human_approval_required",
                error_message="This capability must be approved before execution",
            )

        cache_key = self._cache_key(envelope) if spec.cache_ttl_ms > 0 else None
        if cache_key is not None:
            cached = self._cache_get(cache_key)
            if cached is not None:
                event = self._event(envelope, ExecutionStatus.SUCCEEDED, cached=True)
                self._record(started, failed=False)
                return ResultEnvelope(
                    execution_id=envelope.execution_id,
                    status=ExecutionStatus.SUCCEEDED,
                    circle=self.circle,
                    data=cached,
                    events=(event,),
                )

        data: Any = None
        error_code: str | None = None
        error_message: str | None = None
        attempts = self._retry_policy.max_attempts
        for attempt in range(1, attempts + 1):
            try:
                data = await self._invoke(envelope, spec)
                error_code = error_message = None
                break
            except TimeoutError:
                error_code, error_message = (
                    "deadline_exceeded",
                    (f"{envelope.capability} exceeded {spec.timeout_ms}ms"),
                )
                break  # deadlines are never retried
            except Exception as exc:  # noqa: BLE001 — center-level failure isolation
                error_code, error_message = "circle_handler_failed", str(exc)
                if attempt < attempts:
                    await asyncio.sleep(self._retry_policy.backoff_ms / 1000.0)

        status = ExecutionStatus.SUCCEEDED if error_code is None else ExecutionStatus.FAILED
        if status is ExecutionStatus.SUCCEEDED and cache_key is not None:
            self._cache_put(cache_key, data, ttl_ms=spec.cache_ttl_ms)

        event = self._event(envelope, status)
        self._record(started, failed=status is ExecutionStatus.FAILED)
        if status is ExecutionStatus.FAILED:
            self._last_error = (error_code or "circle_handler_failed", error_message)

        result = ResultEnvelope(
            execution_id=envelope.execution_id,
            status=status,
            circle=self.circle,
            data=data,
            events=(event,),
        )
        if error_code:
            result.error = ExecutionError(code=error_code, message=error_message)
        return result

    async def _invoke(self, envelope: ExecutionEnvelope, spec: LocalCapability) -> Any:
        """Adapter-selected invocation with per-attempt local deadline."""
        self.resolve_adapter(envelope)  # adapter selection is a center concern
        request = envelope.to_capability_request(spec.to_ref(self.circle))
        handler = self._handlers[spec.name]
        timeout_s = spec.timeout_ms / 1000.0
        if inspect.iscoroutinefunction(handler):
            value = handler(request)
            if hasattr(value, "__await__"):
                return await asyncio.wait_for(value, timeout_s)
            return value
        # Sync handlers run in a worker thread so the event loop never
        # blocks and the local deadline stays enforceable.
        return await asyncio.wait_for(asyncio.to_thread(handler, request), timeout_s)

    # ── local events ─────────────────────────────────────────────────
    def _event(
        self,
        envelope: ExecutionEnvelope,
        status: ExecutionStatus,
        *,
        cached: bool = False,
    ) -> EventEnvelope:
        payload: dict[str, Any] = {"capability": envelope.capability}
        if cached:
            payload["cache"] = "hit"
        return EventEnvelope(
            event_type=f"execution.{status.value}",
            execution_id=envelope.execution_id,
            correlation_id=envelope.correlation_id,
            actor_id=envelope.actor_id,
            tenant_id=envelope.tenant_id,
            circle=self.circle,
            payload=payload,
        )

    # ── local health ─────────────────────────────────────────────────
    def health(self) -> CenterHealth:
        if not self._capabilities:
            status = "unavailable"
        elif self._total >= 5 and self._failed / self._total > 0.5:
            status = "degraded"
        else:
            status = "healthy"
        avg = round(sum(self._latencies) / len(self._latencies), 3) if self._latencies else None
        return CenterHealth(
            circle=self.circle,
            display_name=self.display_name,
            owner=self.owner,
            status=status,
            capabilities=self.capabilities(),
            total_executions=self._total,
            failed_executions=self._failed,
            last_error_code=self._last_error[0] if self._last_error else None,
            last_error_message=self._last_error[1] if self._last_error else None,
            last_execution_at=self._last_execution_at,
            avg_latency_ms=avg,
        )

    # ── internals ────────────────────────────────────────────────────
    def _result(
        self,
        envelope: ExecutionEnvelope,
        status: ExecutionStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ResultEnvelope:
        self._record(time.perf_counter(), failed=False)
        result = ResultEnvelope(
            execution_id=envelope.execution_id,
            status=status,
            circle=self.circle,
            events=(self._event(envelope, status),),
        )
        if error_code:
            result.error = ExecutionError(code=error_code, message=error_message)
        return result

    def _record(self, started: float, *, failed: bool) -> None:
        self._total += 1
        if failed:
            self._failed += 1
        self._latencies.append((time.perf_counter() - started) * 1000.0)
        self._last_execution_at = time.time()

    def _cache_key(self, envelope: ExecutionEnvelope) -> str:
        try:
            canonical = json.dumps(envelope.payload, sort_keys=True, default=str)
        except (TypeError, ValueError):
            canonical = repr(envelope.payload)
        return f"{envelope.tenant_id}|{envelope.capability}|{canonical}"

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, data = entry
        if expires_at < time.monotonic():
            self._cache.pop(key, None)
            return None
        return data

    def _cache_put(self, key: str, data: Any, *, ttl_ms: int = 0) -> None:
        if len(self._cache) >= self._CACHE_MAX_ENTRIES:
            oldest = next(iter(self._cache))
            self._cache.pop(oldest, None)
        self._cache[key] = (time.monotonic() + ttl_ms / 1000.0, data)


__all__ = [
    "CenterHandler",
    "CenterHealth",
    "CircleCenter",
    "LocalCapability",
    "RetryPolicy",
]
