"""core/evaluation/swe_benchmark/runner.py — Frozen SWE benchmark runner (Way 15).

বাংলা: self-evolution/agent-breeding-এর জন্য frozen held-out SWE বেঞ্চমার্ক গেট।
ফ্রোজেন কেসগুলোর SHA-256 manifest-এর সাথে মিল না হলে রান ব্যর্থ (fail-closed) —
কেউ সাইলেন্টলি কেস বদলে "উন্নতি" দেখাতে পারে না।

Plan contract (Way 15):
- frozen test corpus (seed set now, extensible via manifest discipline)
- accuracy / precision / recall / specificity / F1 reporting
- CI gate: fail if any metric regresses vs the pinned baseline
- SHA-256 pinned cases (corpus.json carries case_sha256; runner verifies)

This module is stdlib-only and side-effect-free: it EVALUATES a detector
function against the corpus; it does not run agents or touch the network.

A "case" is:
    {
      "id": "swe-001",
      "category": "injection|planning|regression|tooluse",
      "input": "<task/prompt text>",
      "expect_defect": true|false,       # is this input a defect/benign?
      "expect_match": ["rule-id", ...]   # optional: exact rule ids expected
    }

The detector contract (injected by the caller / gate):
    detector(text: str) -> DetectionResult | bool | dict
      - truthy / {"is_injection": true} / DetectionResult(is_injection=True)
        means "defect detected".
      - Optional ".matched" / ["matched"] / {"matched": [...]} rule ids are
        used for expect_match verification when present.

Local test:
    pytest tests/test_swe_benchmark.py
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CORPUS_PATH = Path(__file__).resolve().parent / "corpus.json"


# --------------------------------------------------------------------- corpus
def load_corpus(path: Path = CORPUS_PATH) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Load (cases, sha_index). Raises ValueError on any manifest mismatch."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("corpus.json: 'cases' must be a non-empty list")
    sha_index: dict[str, str] = {}
    for case in cases:
        cid = case.get("id")
        if not cid:
            raise ValueError("corpus.json: every case needs an 'id'")
        # Hash the case WITHOUT the self-referential case_sha256 field.
        digest_payload = {k: v for k, v in case.items() if k != "case_sha256"}
        digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        declared = case.get("case_sha256")
        if declared and declared != digest:
            raise ValueError(
                f"corpus.json: case {cid} SHA-256 mismatch — corpus tampered or stale"
            )
        sha_index[cid] = digest
    return cases, sha_index


def corpus_fingerprint(cases: list[dict[str, Any]]) -> str:
    """Single SHA-256 over the id-sorted corpus (the 'frozen' stamp)."""
    h = hashlib.sha256()
    for case in sorted(cases, key=lambda c: str(c.get("id", ""))):
        h.update(str(case.get("id", "")).encode("utf-8"))
        h.update(b"\x00")
    h.update(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


# ------------------------------------------------------------------- metrics
@dataclass(slots=True)
class BenchmarkReport:
    """Confusion-matrix metrics over the corpus (plan Way 15 contract)."""

    total: int
    detected: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    match_violations: list[str] = field(default_factory=list)
    corpus_fingerprint: str = ""

    @property
    def accuracy(self) -> float:
        return (self.true_positive + self.true_negative) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        d = self.true_positive + self.false_positive
        return self.true_positive / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.true_positive + self.false_negative
        return self.true_positive / d if d else 0.0

    @property
    def specificity(self) -> float:
        d = self.true_negative + self.false_positive
        return self.true_negative / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "detected": self.detected,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "accuracy": round(self.accuracy, 6),
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "specificity": round(self.specificity, 6),
            "f1": round(self.f1, 6),
            "match_violations": self.match_violations,
            "corpus_fingerprint": self.corpus_fingerprint,
        }


def _detector_says_defect(result: Any) -> bool:
    """Normalise detector output to a boolean 'defect detected' signal."""
    if isinstance(result, bool):
        return result
    if result is None:
        return False
    if isinstance(result, dict):
        return bool(result.get("is_injection") or result.get("is_defect") or result.get("detected"))
    attr = getattr(result, "is_injection", None)
    if attr is not None:
        return bool(attr)
    return bool(getattr(result, "is_defect", False) or bool(result))


def _detector_matched(result: Any) -> list[str]:
    if isinstance(result, dict):
        m = result.get("matched")
    else:
        m = getattr(result, "matched", None)
    if isinstance(m, str):
        return [m]
    if isinstance(m, (list, tuple, set)):
        return [str(x) for x in m]
    return []


def run_benchmark(
    detector: Callable[[str], Any],
    cases: list[dict[str, Any]] | None = None,
) -> BenchmarkReport:
    """Evaluate *detector* over the frozen corpus → confusion-matrix report."""
    if cases is None:
        cases, _ = load_corpus()
    tp = fp = tn = fn = 0
    detected = 0
    violations: list[str] = []
    for case in cases:
        text = case.get("input", "")
        got = _detector_says_defect(detector(text))
        expect_defect = bool(case.get("expect_defect"))
        if got:
            detected += 1
        if expect_defect and got:
            tp += 1
        elif expect_defect and not got:
            fn += 1
        elif not expect_defect and got:
            fp += 1
        else:
            tn += 1
        expected_rules = case.get("expect_match")
        if expect_defect and got and expected_rules:
            got_rules = set(_detector_matched(detector(text)))
            for rule in expected_rules:
                if rule not in got_rules:
                    violations.append(f"{case.get('id')}: missing rule {rule}")
    return BenchmarkReport(
        total=len(cases),
        detected=detected,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        match_violations=violations,
        corpus_fingerprint=corpus_fingerprint(cases),
    )
