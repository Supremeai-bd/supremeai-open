#!/usr/bin/env python3
"""MCP Policy Parity Gate (#2429) — TS Tower বনাম Python ইঞ্জিনের drift ধরা।

বাংলা মন্তব্য:
দুই পলিসি ইঞ্জিন (TypeScript টাওয়ার + Python ব্যাকএন্ড) একই canonical
schema থেকে generated — এই gate প্রমাণ করে যে তারা **runtime-এ** সত্যিই
একই decision দেয়। তিন স্তরের যাচাই:

  ১. Snapshot sync: schema → generated ফাইল মিলে আছে? (generator --check)
  ২. Schema hash: উভয় embedded snapshot একই schema hash বহন করে?
  ৩. Runtime parity: সব (provider, action) combo-তে দুই ইঞ্জিনের
     risk + decision অভিন্ন?

Usage:
    python3 scripts/ci/check_mcp_policy_parity.py [--json report.json]

Exit codes: 0 = parity OK · 1 = drift detected · 2 = harness failure
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATOR = REPO_ROOT / "scripts" / "ci" / "generate_mcp_policy.py"
TOWER_DIR = REPO_ROOT / "infrastructure" / "mcp-control-plane"
TOWER_DUMP = TOWER_DIR / "policy_parity_dump.ts"
BACKEND_ROOT = REPO_ROOT / "backend"


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)
    return result.returncode, result.stdout + result.stderr


def _ts_dump() -> dict:
    """টাওয়ারের parity harness চালিয়ে JSON ফলাফল সংগ্রহ।"""
    code, output = _run(["npx", "tsx", str(TOWER_DUMP.relative_to(TOWER_DIR))], TOWER_DIR)
    if code != 0:
        print(f"❌ TS parity harness failed (exit {code}):", file=sys.stderr)
        print(output[-1500:], file=sys.stderr)
        raise SystemExit(2)
    return json.loads(output)


def _python_dump(ts_cases: list[dict]) -> dict:
    """Python ইঞ্জিনে একই combo সেট evaluate করা (একই ক্রম ও কী-সহ)।"""
    backend_root_repr = repr(str(BACKEND_ROOT))
    harness = f"""
import json, sys
sys.path.insert(0, {backend_root_repr})
from core.mcp_policy import get_policy_engine

cases = json.loads(sys.stdin.read())
engine = get_policy_engine()
results = []
for case in cases:
    risk = engine.risk_engine.evaluate(case["provider"], case["action"])
    decision = engine.decide(risk)
    entry = {{"provider": case["provider"], "action": case["action"]}}
    if "tool" in case:
        entry["tool"] = case["tool"]
    entry["risk"] = risk
    entry["decision"] = decision
    results.append(entry)
print(json.dumps({{"engine": "python", "results": results}}))
"""
    payload = json.dumps([{k: v for k, v in c.items() if k in ("provider", "action", "tool")} for c in ts_cases])
    result = subprocess.run(
        [sys.executable, "-c", harness],
        input=payload, capture_output=True, text=True, timeout=120,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print(f"❌ Python parity harness failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr[-1500:], file=sys.stderr)
        raise SystemExit(2)
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP policy parity gate (#2429)")
    parser.add_argument("--json", type=Path, help="structured JSON রিপোর্ট ফাইলে লিখুন")
    args = parser.parse_args()

    findings: list[str] = []

    # ── ধাপ ১: snapshot sync (schema → generated ফাইল) ──
    code, output = _run([sys.executable, str(GENERATOR), "--check"], REPO_ROOT)
    if code != 0:
        findings.append("snapshot-drift: " + " ".join(output.splitlines()))
    else:
        print("✅ ধাপ ১/৩ — snapshot sync: " + output.strip())

    # ── ধাপ ২: উভয় snapshot-এর schema hash অভিন্ন ──
    ts_report = _ts_dump()
    py_harness = (
        f"import sys; sys.path.insert(0, {repr(str(BACKEND_ROOT))}); "
        "from core.mcp_policy_schema_generated import SCHEMA_HASH as h, SCHEMA_VERSION as v; "
        "print(h, v)"
    )
    result = subprocess.run([sys.executable, "-c", py_harness], capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        print("❌ Python schema snapshot import failed:", result.stderr[-500:], file=sys.stderr)
        return 2
    py_hash, py_version = result.stdout.split()
    if ts_report.get("schemaHash") != py_hash:
        findings.append(
            f"schema-hash-mismatch: TS={ts_report.get('schemaHash')} Python={py_hash}"
        )
    else:
        print(f"✅ ধাপ ২/৩ — schema hash অভিন্ন: {py_hash} (v{py_version})")

    # ── ধাপ ৩: runtime parity (সব combo-তে একই risk + decision) ──
    py_report = _python_dump(ts_report["results"])
    py_by_key = {
        (r["provider"], r["action"], r.get("tool")): r for r in py_report["results"]
    }
    mismatches: list[dict] = []
    for ts_case in ts_report["results"]:
        key = (ts_case["provider"], ts_case["action"], ts_case.get("tool"))
        py_case = py_by_key.get(key)
        if py_case is None:
            mismatches.append({"case": key, "error": "Python পাশে case অনুপস্থিত"})
            continue
        if ts_case["risk"] != py_case["risk"] or ts_case["decision"] != py_case["decision"]:
            mismatches.append({
                "case": key,
                "ts": {"risk": ts_case["risk"], "decision": ts_case["decision"]},
                "python": {"risk": py_case["risk"], "decision": py_case["decision"]},
            })
    if mismatches:
        findings.append(f"runtime-parity: {len(mismatches)} mismatched case")
    else:
        print(f"✅ ধাপ ৩/৩ — runtime parity: {ts_report['caseCount']} combo-তে দুই ইঞ্জিন অভিন্ন")

    report = {
        "gate": "mcp-policy-parity",
        "issue": 2429,
        "schema_hash": py_hash,
        "schema_version": py_version,
        "case_count": ts_report.get("caseCount"),
        "findings": findings,
        "mismatches": mismatches,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"📄 রিপোর্ট: {args.json}")

    if findings:
        print("\n❌ MCP policy parity FAIL:")
        for finding in findings:
            print(f"   - {finding}")
        for mismatch in mismatches[:10]:
            print(f"   · {mismatch['case']}: TS={mismatch.get('ts')} Python={mismatch.get('python')}")
        return 1
    print("✅ MCP policy parity PASS — দুই ইঞ্জিনের মধ্যে drift শূন্য")
    return 0


if __name__ == "__main__":
    sys.exit(main())
