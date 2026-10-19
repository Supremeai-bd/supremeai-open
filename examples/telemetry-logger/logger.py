"""SupremeAI telemetry — zero-dependency structured JSON logger (issue #38).

Standard: api-schemas/telemetry-log.schema.json (OpenTelemetry-aligned).

House style (mirrors examples/gateway_client.py):
- no third-party dependencies; stdlib only
- honest output: one JSON object per line (JSONL) — streams, greps, ships
- network I/O: none, ever (local emission only; shipping is another layer's job)
- secrets never enter messages or context (constitutional log hygiene)

Canonical metric catalog (enum-pinned in the schema):
- supremeai.request.latency            (histogram, ms)
- supremeai.tokens.consumed            (counter, count)
- supremeai.agent.task.completion_rate (gauge, ratio)

Usage:
    from logger import TelemetryLogger, metric_latency
    log = TelemetryLogger(service_name="mcp-tower", component="gate")
    log.info("gate merged PR", context={"pr": 315, "issue": 36})
    log.metric(metric_latency(42.5, attributes={"provider": "anthropic"}))

CLI self-test (offline):
    python logger.py --self-test
"""

from __future__ import annotations

import io
import json
import sys
import time
import uuid

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "FATAL")
# OTel severity_number default mapping per level (schema documents this).
LEVEL_SEVERITY_NUMBER = {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17, "FATAL": 21}

CANONICAL_METRICS = {
    "supremeai.request.latency": ("histogram", "ms"),
    "supremeai.tokens.consumed": ("counter", "count"),
    "supremeai.agent.task.completion_rate": ("gauge", "ratio"),
}


class TelemetryError(RuntimeError):
    """Logger misuse — fail loudly rather than emitting a non-conforming record."""


def _rfc3339_now() -> str:
    """RFC 3339 UTC timestamp with milliseconds and Z suffix."""
    secs, millis = divmod(int(time.time() * 1000), 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(secs)) + f".{millis:03d}Z"


def _new_trace_id() -> str:
    """W3C Trace Context trace id: 32 lowercase hex (uuid4 hex is exactly that)."""
    return uuid.uuid4().hex


def metric_latency(value_ms: float, attributes: dict | None = None) -> dict:
    return _metric("supremeai.request.latency", value_ms, attributes)


def metric_tokens(value: int, attributes: dict | None = None) -> dict:
    return _metric("supremeai.tokens.consumed", value, attributes)


def metric_completion_rate(value: float, attributes: dict | None = None) -> dict:
    return _metric("supremeai.agent.task.completion_rate", value, attributes)


def _metric(name: str, value: float, attributes: dict | None) -> dict:
    if name not in CANONICAL_METRICS:
        raise TelemetryError(
            f"metric '{name}' is not in the canonical catalog {sorted(CANONICAL_METRICS)} — "
            "extend the schema enum first, dashboards must not drift"
        )
    instrument, unit = CANONICAL_METRICS[name]
    return {
        "metric": name,
        "value": value,
        "unit": unit,
        "instrument": instrument,
        "attributes": attributes or {},
    }


class TelemetryLogger:
    """Emits schema-conforming JSONL records to stdout or a file object."""

    def __init__(
        self,
        service_name: str,
        component: str,
        agent_id: str | None = None,
        sink=None,
        trace_id: str | None = None,
    ):
        self.service_name = service_name
        self.component = component
        self.agent_id = agent_id
        self.sink = sink or sys.stdout
        self.trace_id = trace_id or _new_trace_id()

    def _emit(
        self,
        level: str,
        message: str,
        context: dict | None,
        metrics: list | None = None,
    ) -> dict:
        if level not in LEVELS:
            raise TelemetryError(f"level '{level}' not in {LEVELS}")
        if not message:
            raise TelemetryError("message must be non-empty (honest logging)")
        record: dict = {
            "timestamp": _rfc3339_now(),
            "level": level,
            "trace_id": self.trace_id,
            "service_name": self.service_name,
            "component": self.component,
            "message": message,
            "context": context or {},
        }
        if self.agent_id:
            record["agent_id"] = self.agent_id
        record["severity_number"] = LEVEL_SEVERITY_NUMBER[level]
        if metrics:
            record["metrics"] = metrics
        self.sink.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def debug(self, message: str, context: dict | None = None) -> dict:
        return self._emit("DEBUG", message, context)

    def info(self, message: str, context: dict | None = None) -> dict:
        return self._emit("INFO", message, context)

    def warn(self, message: str, context: dict | None = None) -> dict:
        return self._emit("WARN", message, context)

    def error(self, message: str, context: dict | None = None) -> dict:
        return self._emit("ERROR", message, context)

    def fatal(self, message: str, context: dict | None = None) -> dict:
        return self._emit("FATAL", message, context)

    def metric(self, *samples: dict) -> dict:
        """Emit an INFO record carrying one or more canonical metric samples."""
        for s in samples:
            if s.get("metric") not in CANONICAL_METRICS:
                raise TelemetryError(f"non-canonical metric sample: {s}")
        return self._emit("INFO", "metric sample", {}, metrics=list(samples))


def _self_test() -> int:
    """Offline round-trip: emit records, re-parse, assert contract shape."""
    checks: list = []

    buf = io.StringIO()
    log = TelemetryLogger(
        "mcp-tower",
        "gate",
        agent_id="agent-1",
        sink=buf,
        trace_id="0af7651916cd43dd8448eb211c80319c",
    )
    r1 = log.info("gate merged PR", context={"pr": 315, "issue": 36})
    log.metric(metric_latency(42.5, {"provider": "anthropic"}), metric_tokens(1337))
    try:
        log._emit("LOUD", "bad level", {})
        checks.append(("bad level rejected", False))
    except TelemetryError:
        checks.append(("bad level rejected", True))
    try:
        _metric("custom rogue.metric", 1, None)
        checks.append(("non-canonical metric rejected", False))
    except TelemetryError:
        checks.append(("non-canonical metric rejected", True))

    records = [json.loads(line) for line in buf.getvalue().splitlines()]
    checks.append(("records parse as JSONL", len(records) == 2))
    required = {"timestamp", "level", "trace_id", "component", "message", "context"}
    checks.append(("required fields present", all(required <= set(r) for r in records)))
    checks.append(
        (
            "trace_id is 32 hex",
            all(
                len(r["trace_id"]) == 32
                and all(c in "0123456789abcdef" for c in r["trace_id"])
                for r in records
            ),
        )
    )
    checks.append(("level vocabulary", all(r["level"] in LEVELS for r in records)))
    checks.append(
        (
            "metric catalog pinned",
            records[1]["metrics"][0]["metric"] == "supremeai.request.latency"
            and records[1]["metrics"][0]["unit"] == "ms",
        )
    )
    checks.append(("correlation fields", r1["context"].get("issue") == 36))

    ok = True
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'} | {name}")
        ok &= passed
    print(f"Self-test: {sum(1 for _, p in checks if p)}/{len(checks)} checks passed")
    return 0 if ok else 1


def main(argv: list) -> int:
    if argv and argv[0] == "--self-test":
        return _self_test()
    print(__doc__.strip())
    print("\nUsage: logger.py --self-test")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
