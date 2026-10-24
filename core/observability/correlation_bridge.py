"""core/observability/correlation_bridge.py — OTel span processor bridging correlation ids (Way 28).

বাংলা: প্রতিটি span-এ `supremeai.correlation_id` অ্যাট্রিবিউট বসিয়ে দেয় —
লগ আর ট্রেস এক correlation id-তে জোড়া লাগে।

This module is only imported lazily by otel_facade when the OTel SDK is active,
so `opentelemetry` imports here are guaranteed safe at runtime.
"""

from __future__ import annotations

from typing import Any

from gateway.middleware.correlation_id import current_correlation_id


class CorrelationBridge:
    """ReadableProcessingSpanProcessor-compatible bridge (on_start stamping)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # accept SDK signature variants
        super().__init__(*args, **kwargs)

    def on_start(self, span: Any, parent_context: Any = None) -> None:  # noqa: D102
        try:
            cid = current_correlation_id()
            if cid:
                span.set_attribute("supremeai.correlation_id", cid)
        except Exception:  # never break tracing for a missing id
            pass

    def on_end(self, span: Any) -> None:  # noqa: D102
        return None

    def shutdown(self) -> None:  # noqa: D102
        return None

    def force_flush(self, timeout_millis: int | None = None) -> bool:  # noqa: D102
        return True
