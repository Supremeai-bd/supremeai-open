"""core/observability/otel_facade.py — Optional OpenTelemetry SDK wrapper (Way 28).

বাংলা: OpenTelemetry SDK-এর পাতলা, optional মোড় — SDK/এক্সপোর্টার না থাকলে
no-op span দেয়; কোর কোডে কোনো হার্ড ডিপেন্ডেন্সি ঢোকায় না (plan Way 28)।

Design:
- `start_span(name, **attrs)` works in BOTH modes:
    * OTel installed + OTEL_EXPORTER_OTLP_ENDPOINT set → real spans on the
      configured tracer provider (TracerProvider is only installed when
      `SUPREMEAI_OTEL=1`, so we never hijack an operator-managed setup).
    * otherwise → a null-span context manager (zero overhead).
- Correlation-id bridge: `install_correlation_bridge()` registers a span
  processor that stamps `supremeai.correlation_id` (from
  gateway.middleware.correlation_id.current_correlation_id) onto every span,
  unifying logs and traces.
- Stdlib when OTel absent; `opentelemetry-*` never enters requirements.txt
  (documented as an optional extra for operators who want tracing).

Local test:
    pytest tests/test_otel_facade.py
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_OTEL_AVAILABLE = False
try:  # optional, operator-chosen
    from opentelemetry import trace as ot_trace  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
        BatchSpanProcessor,
    )
    from opentelemetry.sdk.trace.export import SpanExporter  # type: ignore[import-not-found]

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - OTel not installed
    ot_trace = None  # type: ignore[assignment]

_provider_installed = False


def otel_enabled() -> bool:
    """True only when the SDK is importable AND the operator opted in."""
    return _OTEL_AVAILABLE and _provider_installed and os.getenv("SUPREMEAI_OTEL", "").strip() == "1"


def install_tracing(
    endpoint: str | None = None,
    service_name: str = "supremeai-gateway",
    exporter: Any | None = None,
) -> bool:
    """Install the SDK tracer provider (idempotent). Returns True when active.

    বাংলা: অপারেটর `SUPREMEAI_OTEL=1` দিলে এবং SDK থাকলেই কেবল প্রোভাইডার বসে।
    """
    global _provider_installed
    if not _OTEL_AVAILABLE or _provider_installed:
        return otel_enabled()
    if os.getenv("SUPREMEAI_OTEL", "").strip() != "1":
        return False
    try:
        provider = TracerProvider(resource=None)
        if exporter is not None:
            provider.add_span_processor(BatchSpanProcessor(exporter))
        # endpoint-based OTLP exporter is intentionally NOT auto-configured here:
        # operators pass their own exporter (keeps this module dep-free).
        ot_trace.set_tracer_provider(provider)
        _provider_installed = True
        logger.info("otel_facade: TracerProvider installed (service=%s)", service_name)
    except Exception as exc:
        logger.warning("otel_facade: install failed (%s) — spans stay no-op", exc)
        _provider_installed = False
    return otel_enabled()


def install_correlation_bridge() -> bool:
    """Stamp the current correlation id onto every created span (when OTel active)."""
    if not otel_enabled():
        return False
    try:
        from core.observability.correlation_bridge import CorrelationBridge  # type: ignore

        provider = ot_trace.get_tracer_provider()
        provider.add_span_processor(CorrelationBridge())
        return True
    except Exception as exc:
        logger.warning("otel_facade: correlation bridge unavailable (%s)", exc)
        return False


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Uniform span entry-point: real OTel span when enabled, null-span otherwise.

    বাংলা: OTel বন্ধ থাকলেও কল-সাইট একই থাকে — কোনো if/else ছাড়াই কাজ চলে।
    """
    if otel_enabled():
        tracer = ot_trace.get_tracer("supremeai")
        with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            yield span
    else:
        yield _NullSpan()


class _NullSpan:
    """Drop-in no-op span (record-set methods accepted, everything ignored)."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D102
        return None

    def set_attributes(self, attributes: dict[str, Any]) -> None:  # noqa: D102
        return None

    def record_exception(self, exception: BaseException) -> None:  # noqa: D102
        return None

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:  # noqa: D102
        return None

    def is_recording(self) -> bool:  # noqa: D102
        return False
