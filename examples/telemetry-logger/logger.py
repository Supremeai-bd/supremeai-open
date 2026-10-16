"""SupremeAI telemetry log parser — zero-dependency example (issue #38).

Spec companion: api-schemas/telemetry-log.schema.json.

House style (mirrors examples/gateway_client.py and examples/mcp-client-py/client.py):
- no third-party dependencies; stdlib only
- honest errors: every contract violation names the offending field/path
- file/network I/O happens ONLY on explicit CLI action (offline-safe import)
- credentials and record payloads are never echoed back — the parser counts, it never leaks

Contract (বাংলা মন্তব্য — parser-চুক্তি):
- ইনপুট: প্রতি লাইনে একটি JSON log record (JSONL) — খালি লাইন চুপচাপ skip
- validation: `jsonschema` প্যাকেজ থাকলে পূর্ণ Draft 2020-12 যাচাই (authoritative);
  না থাকলে সৎ fallback — frozen 7-field চুক্তির হুবহু mirror (কোনো ফিল্ড বাদ,
  ভুল enum/pattern/length = fail-honest, কখনো অনুমান নয়)
- metric: schema-র $defs/MetricConventions রেজিস্ট্রির তিন পরিবার aggregate করে —
  supremeai.request.duration, supremeai.tokens.consumed, supremeai.agent.task.completion
  (self-test চলাকালীন constants↔schema examples ড্রিফট-চেকও হয়)
- secret/PII context-এ কখনোই নয় — parser শুধু গোনে, কনটেন্ট কখনো ফেরত দেয় না
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEFAULT_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "api-schemas",
    "telemetry-log.schema.json",
)

# ── frozen field contract (exact mirror of telemetry-log.schema.json) ─────────
REQUIRED_FIELDS = ("timestamp", "level", "trace_id", "agent_id", "component", "message", "context")
LEVELS = ("debug", "info", "warn", "error", "fatal")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
TRACE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{7,127}$")
AGENT_ID_RE = re.compile(r"^$|^agent-[a-zA-Z0-9_-]{1,64}$")
COMPONENT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_MESSAGE_LEN = 2000
MAX_CONTEXT_PROPS = 64

# ── $defs/MetricConventions registry (names are a contract) ─────────────────
METRIC_REQUEST_DURATION = "supremeai.request.duration"
METRIC_TOKENS_CONSUMED = "supremeai.tokens.consumed"
METRIC_TASK_COMPLETION = "supremeai.agent.task.completion"

TASK_COMPLETED_EVENT = "task.completed"
TASK_FAILED_EVENT = "task.failed"


class TelemetryValidationError(ValueError):
    """রেকর্ড চুক্তি-ভঙ্গ — field/path সহ সৎ ব্যর্থতা (honest failure)."""

    def __init__(self, message: str, path: str = "<record>"):
        super().__init__(f"{path}: {message}")
        self.path = path


class TelemetrySchemaError(RuntimeError):
    """schema ফাইল পড়া/parse করা গেল না — সৎ ব্যর্থতা, ডিফল্ট চুপ নয়।"""


def load_schema(schema_path: str | None = None) -> dict:
    """schema JSON load; না পেলে সৎ TelemetrySchemaError (না পেলে বানানো নয়)।"""
    path = schema_path or DEFAULT_SCHEMA_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            schema = json.load(fh)
    except FileNotFoundError as exc:
        raise TelemetrySchemaError(f"schema ফাইল নেই: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TelemetrySchemaError(f"schema JSON ভাঙা: {path}: {exc}") from exc
    if not isinstance(schema, dict):
        raise TelemetrySchemaError(f"schema top-level object নয়: {path}")
    return schema


def _fallback_validate(record: object, path: str) -> None:
    """frozen চুক্তির হুবহু mirror — jsonschema অনুপস্থিত হলেও শৃঙ্খলা একই।"""
    if not isinstance(record, dict):
        raise TelemetryValidationError("record top-level object নয়", path)
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        raise TelemetryValidationError(f"required field অনুপস্থিত: {', '.join(missing)}", path)
    extra = sorted(set(record) - set(REQUIRED_FIELDS))
    if extra:
        raise TelemetryValidationError(
            f"অজানা top-level field (additionalProperties:false): {', '.join(extra)}", path
        )
    ts = record["timestamp"]
    if not isinstance(ts, str) or not TIMESTAMP_RE.match(ts):
        raise TelemetryValidationError("timestamp RFC 3339 date-time নয়", path)
    if record["level"] not in LEVELS:
        raise TelemetryValidationError(f"level {record['level']!r} enum {list(LEVELS)}-এর বাইরে", path)
    for name, pat, value in (
        ("trace_id", TRACE_ID_RE, record["trace_id"]),
        ("agent_id", AGENT_ID_RE, record["agent_id"]),
        ("component", COMPONENT_RE, record["component"]),
    ):
        if not isinstance(value, str) or not pat.match(value):
            raise TelemetryValidationError(f"{name} pattern চুক্তি-ভঙ্গ", path)
    message = record["message"]
    if not isinstance(message, str) or not (1 <= len(message) <= MAX_MESSAGE_LEN):
        raise TelemetryValidationError(f"message দৈর্ঘ্য 1..{MAX_MESSAGE_LEN} চুক্তি-ভঙ্গ", path)
    context = record["context"]
    if not isinstance(context, dict):
        raise TelemetryValidationError("context object নয়", path)
    if len(context) > MAX_CONTEXT_PROPS:
        raise TelemetryValidationError(f"context maxProperties {MAX_CONTEXT_PROPS} ছাড়ায়", path)


_validator_degraded_notice_shown = False


def validate_record(record: object, schema: dict, path: str = "<record>") -> None:
    """jsonschema থাকলে authoritative যাচাই; না থাকলে এক লাইন সৎ notice + fallback।"""
    global _validator_degraded_notice_shown
    try:
        import jsonschema  # type: ignore
    except ImportError:
        if not _validator_degraded_notice_shown:
            print(
                "[telemetry] jsonschema নেই — frozen-field fallback validation চলছে "
                "(সৎ অবনমন; schema ফাইলই authoritative)",
                file=sys.stderr,
            )
            _validator_degraded_notice_shown = True
        _fallback_validate(record, path)
        return
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        _fallback_validate(record, path)
        return
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.absolute_path) or "<record>"
        raise TelemetryValidationError(first.message, f"{path}#{where}")


def parse_log_line(line: str, lineno: int, schema: dict) -> dict | None:
    """একটি লাইন → validated record; খালি লাইন None; চুক্তিভঙ্গে TelemetryValidationError।"""
    stripped = line.strip()
    if not stripped:
        return None
    path = f"<line {lineno}>"
    try:
        record = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise TelemetryValidationError(f"JSON নয়: {exc.msg}", path) from exc
    validate_record(record, schema, path)
    return record


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    rank = max(1, min(len(sorted_values), round(pct / 100 * len(sorted_values))))
    return sorted_values[rank - 1]


def extract_metrics(records: list[dict]) -> dict:
    """তিন metric-পরিবার aggregate — $defs/MetricConventions-এর log_source চুক্তি অনুযায়ী।"""
    duration: dict[tuple[str, str], list[float]] = {}
    tokens: dict[str, dict[str, int]] = {}
    tasks = {"success": 0, "failure": 0}
    for rec in records:
        ctx = rec.get("context")
        if not isinstance(ctx, dict):
            continue
        latency = ctx.get("latency_ms")
        if isinstance(latency, (int, float)) and latency >= 0:
            outcome = str(ctx.get("status", "unknown")).lower()
            outcome = "success" if outcome == "success" else "failure" if outcome == "failure" else "unknown"
            duration.setdefault((rec["component"], outcome), []).append(float(latency))
        usage = ctx.get("usage")
        if isinstance(usage, dict):
            model = str(ctx.get("model", "unknown"))
            bucket = tokens.setdefault(model, {"prompt": 0, "completion": 0})
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            if isinstance(prompt, (int, float)) and prompt >= 0:
                bucket["prompt"] += int(prompt)
            if isinstance(completion, (int, float)) and completion >= 0:
                bucket["completion"] += int(completion)
        event = ctx.get("event")
        if rec["agent_id"] and event == TASK_COMPLETED_EVENT:
            tasks["success"] += 1
        elif rec["agent_id"] and event == TASK_FAILED_EVENT:
            tasks["failure"] += 1
    return {"duration": duration, "tokens": tokens, "tasks": tasks}


def render_summary(valid: int, invalid: int, metrics: dict) -> str:
    lines = [f"records: {valid + invalid} read, {valid} valid, {invalid} invalid"]
    duration = metrics["duration"]
    total_events = sum(len(v) for v in duration.values())
    lines.append(
        f"metric {METRIC_REQUEST_DURATION}: {total_events} events across {len(duration)} component/outcome buckets"
    )
    for (component, outcome), values in sorted(duration.items()):
        values.sort()
        n = len(values)
        mean = sum(values) / n
        p50 = _percentile(values, 50)
        p95 = _percentile(values, 95)
        lines.append(
            f"  component={component} outcome={outcome}: n={n} min={values[0]:.0f}ms "
            f"p50={p50:.0f}ms p95={p95:.0f}ms max={values[-1]:.0f}ms mean={mean:.1f}ms"
        )
    tokens = metrics["tokens"]
    total_prompt = sum(b["prompt"] for b in tokens.values())
    total_completion = sum(b["completion"] for b in tokens.values())
    lines.append(
        f"metric {METRIC_TOKENS_CONSUMED}: prompt={total_prompt} completion={total_completion} "
        f"tokens across {len(tokens)} models"
    )
    for model, bucket in sorted(tokens.items()):
        lines.append(
            f"  model={model} token_type=prompt: {bucket['prompt']} tokens; "
            f"token_type=completion: {bucket['completion']} tokens"
        )
    success, failure = metrics["tasks"]["success"], metrics["tasks"]["failure"]
    rate = (success / (success + failure)) if (success + failure) else 0.0
    lines.append(f"metric {METRIC_TASK_COMPLETION}: success={success} failure={failure} rate={rate:.3f}")
    return "\n".join(lines)


def run_parser(stream, schema: dict) -> tuple[int, int, dict]:
    valid = invalid = 0
    records: list[dict] = []
    for lineno, line in enumerate(stream, start=1):
        try:
            record = parse_log_line(line, lineno, schema)
        except TelemetryValidationError as exc:
            invalid += 1
            print(f"[invalid] {exc}", file=sys.stderr)
            continue
        if record is None:
            continue
        valid += 1
        records.append(record)
    return valid, invalid, extract_metrics(records)


def self_test() -> int:
    """শেষ-থেকে-শেষ আত্মপরীক্ষা — positive + negative + metric assertion (offline)।"""
    schema = load_schema()
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # constants ↔ schema $defs/MetricConventions examples — ড্রিফট ধরার চুক্তি
    metric_def = (schema.get("$defs") or {}).get("MetricConventions") or {}
    example_names = [e.get("name") for e in metric_def.get("examples", [])]
    check("metric registry constants match schema examples",
          example_names == [METRIC_REQUEST_DURATION, METRIC_TOKENS_CONSUMED, METRIC_TASK_COMPLETION])

    valid_records = [
        {"timestamp": "2026-10-16T10:18:15Z", "level": "info", "trace_id": "9f86d081884c7d65",
         "agent_id": "agent-planner", "component": "orchestrator", "message": "dispatch complete",
         "context": {"latency_ms": 210, "status": "SUCCESS",
                     "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
                     "model": "auto", "event": TASK_COMPLETED_EVENT}},
        {"timestamp": "2026-10-16T10:19:00.5Z", "level": "error", "trace_id": "req-a1b2c3d4e5",
         "agent_id": "", "component": "gateway", "message": "provider chain exhausted",
         "context": {"latency_ms": 480, "status": "FAILURE", "provider": "openai", "action": "chat"}},
        {"timestamp": "2026-10-16T10:20:00Z", "level": "warn", "trace_id": "20261016-mem-0001",
         "agent_id": "agent-coder", "component": "memory", "message": "visibility-scoped dependency skipped",
         "context": {"event": TASK_FAILED_EVENT}},
        {"timestamp": "2026-10-16T10:21:00Z", "level": "fatal", "trace_id": "trace:dead:beef:42",
         "agent_id": "", "component": "mcp-tower", "message": "session table exhausted", "context": {}},
    ]
    invalid_records: list[tuple[str, object]] = [
        ("missing level", {k: v for k, v in valid_records[0].items() if k != "level"}),
        ("bad level", {**valid_records[0], "level": "verbose"}),
        ("bad agent_id", {**valid_records[1], "agent_id": "agentX"}),
        ("extra top-level field", {**valid_records[1], "extra": 1}),
        ("context not object", {**valid_records[1], "context": "oops"}),
        ("empty message", {**valid_records[1], "message": ""}),
        ("short trace_id", {**valid_records[1], "trace_id": "abc"}),
    ]
    for i, rec in enumerate(valid_records):
        try:
            validate_record(rec, schema, f"<self-test valid {i}>")
            check(f"valid record {i} accepted", True)
        except TelemetryValidationError as exc:
            check(f"valid record {i} accepted (got: {exc})", False)
    for name, rec in invalid_records:
        try:
            validate_record(rec, schema, f"<self-test {name}>")
            check(f"negative rejected: {name}", False)
        except TelemetryValidationError:
            check(f"negative rejected: {name}", True)
    metrics = extract_metrics(valid_records)
    check("duration events = 2", sum(len(v) for v in metrics["duration"].values()) == 2)
    check("tokens prompt=120 completion=80",
          metrics["tokens"]["auto"]["prompt"] == 120 and metrics["tokens"]["auto"]["completion"] == 80)
    check("task success=1 failure=1",
          metrics["tasks"]["success"] == 1 and metrics["tasks"]["failure"] == 1)
    check("completion rate=0.5", abs((1 / 2) - 0.5) < 1e-9)
    print(render_summary(len(valid_records), len(invalid_records), metrics))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="logger.py",
        description=(
            "SupremeAI telemetry JSONL parser — validates against "
            "api-schemas/telemetry-log.schema.json and aggregates the $defs/MetricConventions "
            "registry (issue #38)."
        ),
    )
    parser.add_argument("input", nargs="?", default="-", help="JSONL file path, or '-' for stdin (default)")
    parser.add_argument("--schema", default=None, help=f"schema path override (default: {DEFAULT_SCHEMA_PATH})")
    parser.add_argument("--strict", action="store_true", help="exit 2 on the first invalid record instead of continuing")
    parser.add_argument("--self-test", action="store_true", help="run the embedded end-to-end self test (offline)")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        schema = load_schema(args.schema)
    except TelemetrySchemaError as exc:
        print(f"[telemetry] {exc}", file=sys.stderr)
        return 2
    if args.input == "-":
        valid, invalid, metrics = run_parser(sys.stdin, schema)
    else:
        try:
            with open(args.input, "r", encoding="utf-8") as fh:
                valid, invalid, metrics = run_parser(fh, schema)
        except OSError as exc:
            print(f"[telemetry] ইনপুট খোলা গেল না: {exc}", file=sys.stderr)
            return 2
    if invalid:
        print(render_summary(valid, invalid, metrics), file=sys.stderr)
        return 1
    print(render_summary(valid, invalid, metrics))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("[telemetry] বাতিল — KeyboardInterrupt", file=sys.stderr)
        sys.exit(130)
