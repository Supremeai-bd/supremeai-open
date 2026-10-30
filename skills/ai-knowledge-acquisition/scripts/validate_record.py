#!/usr/bin/env python3
"""Validate knowledge records and assign a trust tier. Standard library only.

Usage:
    python validate_record.py record.json [more.json ...]
    python validate_record.py records.jsonl
Prints one JSON result per record and exits 1 if any record is invalid.
"""

import json
import re
import sys

KINDS = {"fact", "opinion", "hypothesis", "recommendation", "lesson"}
METHODS = {"copy_paste", "api", "mcp", "agent", "human", "own_analysis"}
EVID_TYPES = {
    "primary_source",
    "test_result",
    "documentation",
    "data",
    "reasoning_only",
    "other_ai_claim",
}
QUALITY = {"strong", "moderate", "weak"}
STATUS = {"unverified", "corroborated", "verified", "disputed", "superseded"}
IMPACT = {"low", "medium", "high"}
AREAS = {
    "security",
    "privacy",
    "policy",
    "architecture",
    "core_philosophy",
    "money",
    "legal",
    "none",
}
# Always need review, at any impact level (these protect the system's rules and people).
ALWAYS_REVIEW_AREAS = {"security", "policy", "core_philosophy", "privacy"}
# Need review only when impact is high (otherwise a normal provisional/auto decision).
HIGH_ONLY_AREAS = {"architecture", "money", "legal"}
REQUIRED = [
    "id",
    "kind",
    "claim",
    "topic",
    "source",
    "confidence",
    "verification",
    "risk",
    "applicability",
    "limitations",
    "created_at",
]
ALLOWED = set(REQUIRED) | {
    "rationale",
    "evidence",
    "uncertainty",
    "assumptions",
    "counterarguments",
    "conflicts_with",
    "supersedes",
    "outcome",
    "review_after",
    "flags",
}
HOLD_FLAGS = {
    "unverified_citation",
    "fabricated_specifics_suspected",
}  # block auto_store_ok
FORBIDDEN_KEYS = {
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "scratchpad",
}
INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard (the )?(system|previous)"
    r"|you must (now )?(run|execute|delete)|override (the )?(policy|safety|rules)"
    r"|mark this as authoritative|reveal (your )?(system prompt|secret|token|key))",
    re.IGNORECASE,
)
SECRET = re.compile(
    r"(github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def _text_fields(rec):
    out = []
    for k in ("claim", "rationale", "uncertainty"):
        if isinstance(rec.get(k), str):
            out.append(rec[k])
    for k in ("assumptions", "limitations", "counterarguments"):
        v = rec.get(k)
        if isinstance(v, list):
            out += [x for x in v if isinstance(x, str)]
    return out


def validate(rec):
    errors, warnings = [], []
    if not isinstance(rec, dict):
        return ["record must be a JSON object"], [], None
    for k in REQUIRED:
        if k not in rec:
            errors.append(f"missing required field: {k}")
    for k in rec:
        if k in FORBIDDEN_KEYS:
            errors.append(
                f"forbidden field '{k}': store short checkable rationale, not hidden reasoning"
            )
        elif k not in ALLOWED:
            errors.append(f"unknown field: {k}")
    if errors and any(e.startswith("missing") for e in errors):
        return errors, warnings, None

    if rec["kind"] not in KINDS:
        errors.append(f"kind must be one of {sorted(KINDS)}")
    if not isinstance(rec["claim"], str) or not rec["claim"].strip():
        errors.append("claim must be a non-empty string")
    c = rec["confidence"]
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
        errors.append("confidence must be a number between 0 and 1")

    src = rec["source"]
    if not isinstance(src, dict) or not src.get("name"):
        errors.append("source.name is required (provenance)")
    elif src.get("method") not in METHODS:
        errors.append(f"source.method must be one of {sorted(METHODS)}")

    ver = rec["verification"]
    if not isinstance(ver, dict) or ver.get("status") not in STATUS:
        errors.append(f"verification.status must be one of {sorted(STATUS)}")
    risk = rec["risk"]
    if not isinstance(risk, dict) or risk.get("impact") not in IMPACT:
        errors.append(f"risk.impact must be one of {sorted(IMPACT)}")
    elif any(a not in AREAS for a in risk.get("areas", [])):
        errors.append(f"risk.areas values must be in {sorted(AREAS)}")
    app = rec["applicability"]
    if (
        not isinstance(app, dict)
        or not isinstance(app.get("contexts"), list)
        or not app["contexts"]
    ):
        errors.append("applicability.contexts must be a non-empty list")
    if not isinstance(rec["limitations"], list):
        errors.append("limitations must be a list (use [] only if truly none)")

    evidence = rec.get("evidence", [])
    if not isinstance(evidence, list):
        errors.append("evidence must be a list")
        evidence = []
    for i, e in enumerate(evidence):
        if (
            not isinstance(e, dict)
            or e.get("type") not in EVID_TYPES
            or e.get("quality") not in QUALITY
        ):
            errors.append(f"evidence[{i}] needs valid type and quality")

    for t in _text_fields(rec):
        if SECRET.search(t):
            errors.append("possible secret/credential in text: redact before storing")
            break

    if rec["kind"] == "lesson":
        o = rec.get("outcome")
        if not o or not o.get("actual"):
            warnings.append(
                "lesson without outcome.actual: store as hypothesis until an outcome is known"
            )
        elif o.get("root_cause") and not o.get("root_cause_supported"):
            warnings.append(
                "root_cause stated but not marked supported: treat as hypothesis"
            )
    if rec["kind"] in {"fact", "lesson"} and not evidence:
        warnings.append("no evidence listed for a fact/lesson")
    if not app.get("not_applicable") if isinstance(app, dict) else False:
        warnings.append(
            "applicability.not_applicable is empty: say where this does NOT apply"
        )

    if errors:
        return errors, warnings, None
    tier, reasons = triage(rec, evidence, warnings)
    return errors, warnings, {"tier": tier, "reasons": reasons}


def triage(rec, evidence, warnings):
    reasons = []
    risk = rec["risk"]
    areas = set(risk.get("areas", []))
    if risk["impact"] == "high":
        reasons.append("high impact")
    always = areas & ALWAYS_REVIEW_AREAS
    if always:
        reasons.append("protected area: " + ", ".join(sorted(always)))
    flags = rec.get("flags") or []
    if "injection_suspected" in flags:
        reasons.append(
            "flagged injection_suspected: source content contained instructions aimed at the assistant"
        )
    if any(INJECTION.search(t) for t in _text_fields(rec)):
        reasons.append("instruction-like text found (possible prompt injection)")
    if reasons:
        return "needs_review", reasons

    held = sorted(set(flags) & HOLD_FLAGS)
    if held:
        reasons.append("flags block auto-store: " + ", ".join(held))

    if rec["kind"] in {"opinion", "hypothesis"}:
        reasons.append(f"kind={rec['kind']} is never auto-stored")
    if rec["verification"]["status"] in {"disputed", "unverified"}:
        reasons.append(f"verification.status={rec['verification']['status']}")
    if rec.get("conflicts_with"):
        reasons.append("open conflict with: " + ", ".join(rec["conflicts_with"]))
    if rec["confidence"] < 0.8:
        reasons.append("confidence below 0.8")
    strong = [
        e
        for e in evidence
        if e["quality"] == "strong" and e["type"] != "other_ai_claim"
    ]
    indep = [
        e for e in evidence if e.get("independent") and e["type"] != "other_ai_claim"
    ]
    if not strong and len(indep) < 2:
        reasons.append(
            "no strong non-AI evidence and fewer than 2 independent confirmations"
        )
    if risk["impact"] == "medium":
        reasons.append("medium impact")
    if any("lesson without outcome" in w for w in warnings):
        reasons.append("no recorded outcome")
    if reasons:
        return "provisional", reasons
    return "auto_store_ok", ["low impact, well supported, corroborated, no conflict"]


def load(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".jsonl"):
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    bad = False
    for path in argv[1:]:
        try:
            records = load(path)
        except (OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {"file": path, "valid": False, "errors": [str(exc)]},
                    ensure_ascii=False,
                )
            )
            bad = True
            continue
        for rec in records:
            errors, warnings, result = validate(rec)
            out = {
                "file": path,
                "id": rec.get("id") if isinstance(rec, dict) else None,
                "valid": not errors,
                "errors": errors,
                "warnings": warnings,
            }
            if result:
                out.update(result)
            print(json.dumps(out, ensure_ascii=False))
            bad = bad or bool(errors)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
