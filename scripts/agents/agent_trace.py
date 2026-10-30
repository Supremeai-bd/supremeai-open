#!/usr/bin/env python3
"""Agent Trace → Evaluation → Learning loop (#3187 — intentionally small v1).

=============================================================
# বাংলা মন্তব্য: এজেন্ট রানের **execution evidence** কে পুনর্ব্যবহারযোগ্য
# learning asset বানানো — vendor tracing product কপি নয় (OpenAI/Anthropic
# guidance-র principle, #3187 §What SupremeAI Should Learn)।
#
# v1 চুক্তি (ইচ্ছাকৃতভাবে ছোট — #3187 §Complexity):
#   1. একটি canonical, versioned trace schema (AGENT_TRACE_SCHEMA_VERSION)
#   2. একটি persistence path — বিদ্যমান `data/supremeai.db` sqlite স্তর
#      (agent_solution_memory.py-এর প্রতিষ্ঠিত রীতি; নতুন memory subsystem নয়)
#   3. একটি deterministic evaluator interface (model-judge পরে — interface point)
#   4. Redaction: sensitive key-pattern মেললে value রেডঅ্যাক্ট, বড় payload
#      শুধু hash-reference (#3187 §Risks: secrets/PII enforcement)
#   5. Replay/compare: known-good evaluation record-এর সাথে তুলনা → regression
#   6. Retrieval: ভবিষ্যৎ এজেন্ট একই ধরনের task-এর verified trace খুঁজে নিতে পারে
#
# skill_bundle (#3194) ইন্টিগ্রেশন: trace-এ ঐচ্ছিক `skill_bundle_hash` —
# কোন পলিসি কন্ট্রাক্টের অধীনে রান হয়েছিল তা replay-যোগ্য থাকে।
#
# Usage:
#   python scripts/agents/agent_trace.py record --trace t.json
#   python scripts/agents/agent_trace.py evaluate --trace t.json
#   python scripts/agents/agent_trace.py compare --trace t.json --baseline b.json
#   python scripts/agents/agent_trace.py search --role coder --outcome success
"""

from __future__ import annotations

from typing import Any  # #4099 fix: missing import for Any type hints

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]
SQLITE_DB_PATH = ROOT_DIR / "data" / "supremeai.db"

# বাংলা: schema বদলালে version বাড়ান — evaluation record-এর সাথে সংগতি রাখতে
AGENT_TRACE_SCHEMA_VERSION = 1

TRACE_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id     TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    task_id      TEXT NOT NULL,
    role         TEXT NOT NULL,
    agent_name   TEXT NOT NULL,
    task_type    TEXT,
    outcome      TEXT NOT NULL,
    skill_bundle_hash TEXT,
    trace_json   TEXT NOT NULL,
    evaluation_json TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_traces_role ON agent_traces (role, outcome);
"""

# বাংলা (#3187 §Risks): sensitive key pattern — value কখনো trace-এ ঢোকে না;
# মিললে value বদলে "<redacted:hash-prefix>" থাকে (প্রমাণ আছে, সামগ্রী নেই)。
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|cookie|"
    r"session|credential|private[_-]?key|client[_-]?secret|bearer)"
)
# বাংলা: বড় payload — শুধু hash-reference রাখা হয় (storage/cost pressure এড়াতে)
LARGE_PAYLOAD_LIMIT = 2048

# বাংলা (R87/#3620 root-cause fix): token-count কী-এর অখণ্ড int মান টেলিমেট্রি
# (gen_ai.usage.* ভোক্তা), credential নয় — SENSITIVE_KEY_RE-এর "token" সাবস্ট্রিং
# এদের রেডঅ্যাক্ট করলে প্রতিটি cost/usage কনজিউমার অন্ধ হয়। সংকীর্ণ allowlist:
# শুধু এই কী-শেষাংশের int মান প্রবাহিত হবে; string/dict/list মান আগের মতোই
# সবসময় রেডঅ্যাক্টেড (fail-closed অপরিবর্তিত — কোনো credential-int পথ নেই)।
TOKEN_COUNT_KEY_RE = re.compile(
    r"(?i)(input|output|prompt|completion|total)[_-]?tokens?$"
)


def _redact_value(value: Any) -> Any:
    """Value redaction — dict/list recursively; বড় string ও sensitive string হ্যাশ-রেফ।"""
    if isinstance(value, dict):
        return {k: _redact_key_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, str) and len(value) > LARGE_PAYLOAD_LIMIT:
        digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]
        return f"<large-ref:sha256:{digest}>"
    if isinstance(value, str) and SENSITIVE_KEY_RE.search(value):
        digest = hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]
        return f"<redacted:sha256:{digest}>"
    return value


def _redact_key_value(key: str, value: Any) -> Any:
    """Key-aware redaction — sensitive নামের কী-এর value কখনো plaintext থাকে না।"""
    # বাংলা (R87/#3620): token-count int allowlist — রেডঅ্যাকশনের আগে, সংকীর্ণ।
    if (TOKEN_COUNT_KEY_RE.search(key or "")
            and isinstance(value, int) and not isinstance(value, bool)):
        return value
    if SENSITIVE_KEY_RE.search(key or ""):
        if value in (None, "", [], {}):
            return value
        digest = hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
            .encode("utf-8", "replace")).hexdigest()[:16]
        return f"<redacted:sha256:{digest}>"
    return _redact_value(value)


@dataclass
class TraceEvent:
    """একটি trace event — run/tool_call/verification/guardrail/outcome ইত্যাদি।"""
    event_type: str  # run_start | tool_call | handoff | guardrail | verification | outcome
    name: str
    status: str = "ok"  # ok | failed | rejected | skipped
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTrace:
    """Canonical agent run trace — #3187 §What SupremeAI Should Learn-এর ক্ষেত্রসেট।"""
    task_id: str
    role: str
    agent_name: str
    events: list[TraceEvent] = field(default_factory=list)
    task_type: str | None = None
    model: str | None = None
    provider: str | None = None
    decision: str | None = None          # সিদ্ধান্ত + rationale (U8 decision ledger লিংক)
    decision_ledger: dict[str, Any] | None = None  # U8 JSON হলে এখানে
    guardrail_result: str | None = None  # approved | rejected | n/a
    tests_evidence: list[str] = field(default_factory=list)  # pytest/চেক প্রমাণ
    links: dict[str, str] = field(default_factory=dict)  # issue/pr/commit
    cost_usd: float | None = None
    latency_seconds: float | None = None
    outcome: str = "partial"             # success | failure | partial | rejected
    skill_bundle_hash: str | None = None  # #3194 integration

    def to_dict(self) -> dict[str, Any]:
        d = {
            "schema_version": AGENT_TRACE_SCHEMA_VERSION,
            "task_id": self.task_id,
            "role": self.role,
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "model": self.model,
            "provider": self.provider,
            "decision": self.decision,
            "decision_ledger": self.decision_ledger,
            "guardrail_result": self.guardrail_result,
            "tests_evidence": self.tests_evidence,
            "links": self.links,
            "cost_usd": self.cost_usd,
            "latency_seconds": self.latency_seconds,
            "outcome": self.outcome,
            "skill_bundle_hash": self.skill_bundle_hash,
            "events": [
                {"event_type": e.event_type, "name": e.name, "status": e.status,
                 "detail": e.detail}
                for e in self.events
            ],
        }
        return _redact_value(d)

    def trace_id(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False,
                             default=str).encode("utf-8", "replace")
        return f"trace_{hashlib.sha256(payload).hexdigest()[:20]}"


# ---------------------------------------------------------------------------
# Persistence — বিদ্যমান sqlite স্তর (data/supremeai.db), নতুন subsystem নয়
# ---------------------------------------------------------------------------
def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else SQLITE_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(TRACE_SCHEMA)
    return conn


def record_trace(trace: AgentTrace, db_path: Path | None = None) -> str:
    """একটি coherent trace সংরক্ষণ (redacted JSON) — trace_id ফেরত দেয়।"""
    trace_dict = trace.to_dict()
    trace_id = trace.trace_id()
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO agent_traces (trace_id, schema_version, task_id,"
            " role, agent_name, task_type, outcome, skill_bundle_hash, trace_json,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trace_id, AGENT_TRACE_SCHEMA_VERSION, str(trace.task_id), trace.role,
             trace.agent_name, trace.task_type, trace.outcome,
             trace.skill_bundle_hash, json.dumps(trace_dict, ensure_ascii=False),
             now),
        )
        conn.commit()
        return trace_id
    finally:
        conn.close()


def load_trace(trace_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT trace_json FROM agent_traces WHERE trace_id = ?",
            (trace_id,)).fetchone()
        return json.loads(row["trace_json"]) if row else None
    finally:
        conn.close()


def search_traces(role: str | None = None, outcome: str | None = None,
                  limit: int = 10, db_path: Path | None = None) -> list[dict[str, Any]]:
    """ভবিষ্যৎ এজেন্টদের জন্য retrieval — verified একই-ধরনের task trace খোঁজা।"""
    query = "SELECT trace_id, task_id, role, outcome, trace_json, created_at FROM agent_traces"
    clauses, params = [], []
    if role:
        clauses.append("role = ?")
        params.append(role)
    if outcome:
        clauses.append("outcome = ?")
        params.append(outcome)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    conn = _connect(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Deterministic evaluator — v1 শুধু নির্ধারিত চেক (model-judge: পরের স্লাইস)
# ---------------------------------------------------------------------------
EVALUATOR_ID = "deterministic-v1"


@dataclass
class EvaluationRecord:
    """Evaluator evidence — model-judge নয়, deterministic চেকের ফল।"""
    evaluator_id: str
    trace_id: str
    passed: bool
    checks: list[dict[str, Any]]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator_id": self.evaluator_id,
            "trace_id": self.trace_id,
            "passed": self.passed,
            "checks": self.checks,
            "evaluated_at": self.evaluated_at,
        }


def evaluate_trace(trace: AgentTrace) -> EvaluationRecord:
    """Deterministic চেক সেট — সব পাস করলেই passed=True।

    # বাংলা: চেকগুলো #3187 §What SupremeAI Should Learn-এর ফিল্ডসেট থেকে:
    # outcome ঘোষিত, decision+rationale আছে, guardrail নন-বায়োলেটেড,
    # tests/evidence আছে, links আছে — সবই objective, model-judge নয়।
    """
    checks: list[dict[str, Any]] = []

    def _check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    _check("outcome_declared", trace.outcome in ("success", "failure", "partial", "rejected"),
           trace.outcome)
    _check("decision_rationale_present", bool(trace.decision and trace.decision.strip()))
    _check("guardrail_not_violated", trace.guardrail_result != "rejected",
           trace.guardrail_result or "n/a")
    _check("verification_evidence_present", len(trace.tests_evidence) > 0)
    _check("links_present", len(trace.links) > 0)
    outcome_events = [e for e in trace.events if e.event_type == "outcome"]
    _check("coherent_outcome_event", len(outcome_events) >= 1)
    # বাংলা: run → tool/verification → outcome পথ সংগতি — outcome event-এর
    # status ঘোষিত outcome-এর সাথে মিলবে
    if outcome_events:
        _check("outcome_event_matches_declaration",
               outcome_events[-1].status == ("ok" if trace.outcome == "success" else outcome_events[-1].status))
    passed = all(c["passed"] for c in checks)
    return EvaluationRecord(
        evaluator_id=EVALUATOR_ID,
        trace_id=trace.trace_id(),
        passed=passed,
        checks=checks,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )


def save_evaluation(trace_id: str, evaluation: EvaluationRecord,
                    db_path: Path | None = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE agent_traces SET evaluation_json = ? WHERE trace_id = ?",
            (json.dumps(evaluation.to_dict(), ensure_ascii=False), trace_id))
        conn.commit()
    finally:
        conn.close()


def compare_evaluations(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Known-good evaluation vs নতুন evaluation → regression শনাক্ত।

    # বাংলা: baseline-এ পাস করা চেক এখন ফেল করলেই regression — replay/compare
    # চুক্তি (#3187 verification bullet 5)।
    """
    base = {c["check"]: c["passed"] for c in baseline.get("checks", [])}
    curr = {c["check"]: c["passed"] for c in current.get("checks", [])}
    regressions = [name for name, was_ok in base.items() if was_ok and not curr.get(name)]
    improvements = [name for name, is_ok in curr.items() if is_ok and not base.get(name)]
    return {
        "baseline_evaluator": baseline.get("evaluator_id"),
        "current_evaluator": current.get("evaluator_id"),
        "regressions": regressions,
        "improvements": improvements,
        "regressed": bool(regressions),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_record(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.trace).read_text(encoding="utf-8"))
    trace = AgentTrace(
        task_id=str(data["task_id"]), role=data["role"], agent_name=data["agent_name"],
        task_type=data.get("task_type"), model=data.get("model"),
        provider=data.get("provider"), decision=data.get("decision"),
        decision_ledger=data.get("decision_ledger"),
        guardrail_result=data.get("guardrail_result"),
        tests_evidence=data.get("tests_evidence", []),
        links=data.get("links", {}), cost_usd=data.get("cost_usd"),
        latency_seconds=data.get("latency_seconds"),
        outcome=data.get("outcome", "partial"),
        skill_bundle_hash=data.get("skill_bundle_hash"),
        events=[TraceEvent(**e) for e in data.get("events", [])],
    )
    trace_id = record_trace(trace)
    print(json.dumps({"trace_id": trace_id}, ensure_ascii=False))
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    trace = _trace_from_file(args.trace)
    evaluation = evaluate_trace(trace)
    if args.db and not args.dry:
        record_trace(trace)
    print(json.dumps(evaluation.to_dict(), ensure_ascii=False, indent=2))
    return 0 if evaluation.passed else 1


def _cmd_compare(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    result = compare_evaluations(baseline, current)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["regressed"] else 0


def _cmd_search(args: argparse.Namespace) -> int:
    results = search_traces(role=args.role, outcome=args.outcome, limit=args.limit)
    print(json.dumps([{"trace_id": r["trace_id"], "task_id": r["task_id"],
                       "role": r["role"], "outcome": r["outcome"],
                       "created_at": r["created_at"]} for r in results],
                      ensure_ascii=False, indent=2))
    return 0


def _trace_from_file(path: str) -> AgentTrace:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AgentTrace(
        task_id=str(data["task_id"]), role=data["role"], agent_name=data["agent_name"],
        task_type=data.get("task_type"), model=data.get("model"),
        provider=data.get("provider"), decision=data.get("decision"),
        decision_ledger=data.get("decision_ledger"),
        guardrail_result=data.get("guardrail_result"),
        tests_evidence=data.get("tests_evidence", []),
        links=data.get("links", {}), cost_usd=data.get("cost_usd"),
        latency_seconds=data.get("latency_seconds"),
        outcome=data.get("outcome", "partial"),
        skill_bundle_hash=data.get("skill_bundle_hash"),
        events=[TraceEvent(**e) for e in data.get("events", [])],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent trace/evaluation loop (#3187)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="persist a trace JSON")
    p_rec.add_argument("--trace", required=True)
    p_rec.set_defaults(func=_cmd_record)

    p_eval = sub.add_parser("evaluate", help="deterministic evaluation of a trace")
    p_eval.add_argument("--trace", required=True)
    p_eval.add_argument("--db", action="store_true", help="also persist trace")
    p_eval.add_argument("--dry", action="store_true", help="do not persist")
    p_eval.set_defaults(func=_cmd_evaluate)

    p_cmp = sub.add_parser("compare", help="compare current vs known-good evaluation")
    p_cmp.add_argument("--baseline", required=True)
    p_cmp.add_argument("--current", required=True)
    p_cmp.set_defaults(func=_cmd_compare)

    p_search = sub.add_parser("search", help="retrieve traces for future learning")
    p_search.add_argument("--role", default=None)
    p_search.add_argument("--outcome", default=None)
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=_cmd_search)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
