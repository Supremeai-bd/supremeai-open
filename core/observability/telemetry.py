import os
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from core.logging_config import logger

_tracer: Tracer | None = None
_provider: TracerProvider | None = None
_httpx_instrumented = False


def setup_tracing(service_name: str = "supremeai", otlp_endpoint: str | None = None) -> None:
    global _tracer, _provider, _httpx_instrumented
    if _tracer is not None:
        return

    endpoint = otlp_endpoint or os.getenv("OTLP_ENDPOINT", "")
    provider = TracerProvider()
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"✅ OTLP tracing exporter initialized for endpoint: {endpoint}")
        except ImportError as exc:
            logger.warning(f"OTLP exporter not available: {exc}")
            if os.getenv("ENV", "").lower() == "production":
                logger.critical(
                    "🔥 PRODUCTION: OTLP endpoint configured but exporter not installed! "
                    "Tracing is disabled. Install opentelemetry-exporter-otlp-proto-grpc."
                )
    else:
        logger.info("ℹ️ No OTLP endpoint configured — tracing runs in no-op mode.")
    otel_trace.set_tracer_provider(provider)
    _provider = provider
    _tracer = otel_trace.get_tracer(service_name)

    # Enable automatic tracing for outgoing HTTPX calls (end-to-end W3C propagation)
    if not _httpx_instrumented:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
            _httpx_instrumented = True
            logger.info("HTTPX OpenTelemetry instrumentor enabled.")
        except ImportError:
            logger.warning("opentelemetry-instrumentation-httpx not installed.")


def get_tracer() -> Tracer | None:
    """Return the current tracer. Always call this after setup_tracing(), never import at module level."""
    return _tracer


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None, kind: str = "internal"):
    tracer = get_tracer()
    if tracer is None:
        yield _NoOpSpan()
        return
    span_kind = {
        "internal": otel_trace.SpanKind.INTERNAL,
        "server": otel_trace.SpanKind.SERVER,
        "client": otel_trace.SpanKind.CLIENT,
        "producer": otel_trace.SpanKind.PRODUCER,
        "consumer": otel_trace.SpanKind.CONSUMER,
    }.get(kind, otel_trace.SpanKind.INTERNAL)
    with tracer.start_as_current_span(name, kind=span_kind) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        try:
            yield _RealSpan(span)
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


class _NoOpSpan:
    def set_attribute(self, *args, **kwargs):
        pass

    def record_exception(self, *args, **kwargs):
        pass


class _RealSpan:
    def __init__(self, span: Span):
        self._span = span

    def set_attribute(self, key: str, value: Any):
        self._span.set_attribute(key, value)

    def record_exception(self, exc: BaseException):
        self._span.record_exception(exc)
