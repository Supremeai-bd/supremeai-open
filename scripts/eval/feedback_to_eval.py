#!/usr/bin/env python3
"""scripts/eval/feedback_to_eval.py — Convert user feedback into sanitized candidate eval cases (#1363, AIQ-107).

CONTRACT:
  - Stdlib only, offline, deterministic.
  - Input: JSONL (one feedback record per line) or a JSON array via --input.
  - Only NEGATIVE feedback (rating='down', or a correction/report present) becomes a
    candidate eval case. Thumbs-up is acknowledged but never turned into a regression case.
  - Sanitization: PII (emails, phone numbers, bearer tokens, api keys) redacted;
    conversation ids hashed; long text truncated to --max-chars.
  - Output: JSONL of candidate eval cases to --output (or stdout).
  - Exit 0 on success, 2 on input/schema error.

Feedback record schema (all fields optional except one of rating/correction/report):
  {
    "feedback_id": str,
    "rating": "up" | "down",
    "correction": str | None,        # user-provided corrected answer
    "report": str | None,            # issue report text
    "task_type": str,                # e.g. "ci_fix", "code_review"
    "conversation_id": str,
    "prompt": str,                   # original user prompt (if available)
    "response": str,                 # model response that was rated
    "timestamp": str (ISO-8601)
  }

Candidate eval case schema:
  {
    "case_id": str,                  # "fb-<hash>"
    "source": "user_feedback",
    "feedback_id": str,
    "task_type": str,
    "prompt": str (sanitized),
    "expected": str (sanitized correction or report, may be empty),
    "observed": str (sanitized model response, may be empty),
    "tags": ["negative_feedback", ...],
    "sanitized": true
  }
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Any, Iterable

PII_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE), "Bearer [TOKEN]"),
    (re.compile(r"(?:api[_-]?key|token|secret)\s*[:=]\s*\S+", re.IGNORECASE), "[SECRET]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[API_KEY]"),
]


def sanitize(text: str, max_chars: int = 2000) -> str:
    """Redact PII and truncate. Always returns a str."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    for pat, repl in PII_PATTERNS:
        text = pat.sub(repl, text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    return text


def _hash_id(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:12]


def is_negative(rec: dict[str, Any]) -> bool:
    rating = (rec.get("rating") or "").lower()
    if rating == "down":
        return True
    if rec.get("correction"):
        return True
    if rec.get("report"):
        return True
    return False


def to_case(rec: dict[str, Any], max_chars: int = 2000) -> dict[str, Any] | None:
    if not isinstance(rec, dict):
        return None
    if not is_negative(rec):
        return None
    fid = str(rec.get("feedback_id") or rec.get("id") or "")
    seed = fid or json.dumps(rec, sort_keys=True, default=str)
    case_id = "fb-" + _hash_id(seed)
    tags = ["negative_feedback"]
    if rec.get("rating") == "down":
        tags.append("thumbs_down")
    if rec.get("correction"):
        tags.append("correction")
    if rec.get("report"):
        tags.append("report")
    tt = str(rec.get("task_type") or "default")
    prompt = sanitize(str(rec.get("prompt") or ""), max_chars)
    observed = sanitize(str(rec.get("response") or ""), max_chars)
    expected = sanitize(str(rec.get("correction") or rec.get("report") or ""), max_chars)
    conv = rec.get("conversation_id")
    conv_hash = _hash_id(str(conv)) if conv else ""
    return {
        "case_id": case_id,
        "source": "user_feedback",
        "feedback_id": fid,
        "conversation_id_hash": conv_hash,
        "task_type": tt,
        "prompt": prompt,
        "expected": expected,
        "observed": observed,
        "tags": tags,
        "sanitized": True,
    }


def convert(records: Iterable[Any], max_chars: int = 2000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in records:
        case = to_case(rec, max_chars)
        if case is None:
            continue
        if case["case_id"] in seen:
            continue
        seen.add(case["case_id"])
        out.append(case)
    return out


def _read_input(path: str | None) -> list[Any]:
    if path is None or path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    raw = raw.strip()
    if not raw:
        return []
    # JSON array?
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("top-level JSON must be an array")
        return data
    # JSONL
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Convert user feedback into sanitized candidate eval cases")
    p.add_argument("--input", "-i", default=None, help="Input JSON/JSONL file (default stdin)")
    p.add_argument("--output", "-o", default=None, help="Output JSONL file (default stdout)")
    p.add_argument("--max-chars", type=int, default=2000, help="Max chars per text field")
    p.add_argument("--self-test", action="store_true", help="Run offline unit probes")
    args = p.parse_args(argv)

    if args.self_test:
        return _self_test()

    try:
        records = _read_input(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    cases = convert(records, args.max_chars)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    else:
        for c in cases:
            print(json.dumps(c, ensure_ascii=False))
    return 0


def _self_test() -> int:
    # PII redaction
    assert sanitize("email me at a@b.com or call 555-123-4567") == "email me at [EMAIL] or call [PHONE]"
    assert "[TOKEN]" in sanitize("Bearer abc.def_123")
    # truncation
    long = "x" * 3000
    assert sanitize(long, 10).endswith("...[truncated]")
    # negative detection
    assert is_negative({"rating": "down"})
    assert is_negative({"correction": "fix"})
    assert is_negative({"report": "bug"})
    assert not is_negative({"rating": "up"})
    # conversion + dedup
    recs = [
        {"feedback_id": "1", "rating": "down", "prompt": "p", "response": "r", "task_type": "ci_fix"},
        {"feedback_id": "1", "rating": "down", "prompt": "p", "response": "r", "task_type": "ci_fix"},  # dup
        {"rating": "up", "prompt": "good"},  # skipped
    ]
    cases = convert(recs)
    assert len(cases) == 1
    assert cases[0]["sanitized"] is True
    assert "negative_feedback" in cases[0]["tags"]
    # PII in feedback must be redacted in output
    recs2 = [{"feedback_id": "2", "rating": "down", "prompt": "contact x@y.com", "response": "ok"}]
    c2 = convert(recs2)[0]
    assert "[EMAIL]" in c2["prompt"] and "x@y.com" not in c2["prompt"]
    print("[self-test] feedback_to_eval: all probes passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
