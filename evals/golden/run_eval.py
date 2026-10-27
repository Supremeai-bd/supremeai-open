#!/usr/bin/env python3
"""Golden Eval Runner — offline, deterministic, honest (U2). Issue #1362.

CONTRACT (stable surface):
  exit 0 = gate PASS (scored>0 AND accuracy >= threshold)
  exit 1 = gate FAIL (below threshold, or NO scored data -> fail-closed)
  exit 2 = suite/config error (bad JSON, schema violation, missing files)
  final stdout line: GOLDEN_EVAL_VERDICT=PASS|FAIL

Providers:
  fixture (default) — replays evals/golden/fixtures.json. This is a MECHANICS
      self-test of the scorer, NOT a model-quality measurement; the report
      labels it as such. Cases without a fixture are excluded from accuracy
      and listed as no_fixture (never fabricated PASS — U2).
  http — POSTs {"prompt": ...} to $SUPREME_EVAL_ENDPOINT and reads
      {"response": ..., "latency_ms": ..., "cost_usd": ...}. For live quality
      gating wired by admin (see docs/workorders/bridge-20261028-golden-eval-gate.md).

Rubric semantics (see suite meta.rubric_semantics): a case passes iff ALL
present constraints pass. Matching is case-insensitive on whitespace-normalized
text. json asserts use dotted paths (arguments.city, payload.ok). no_tool_call
fails when the response embeds a tool-call-shaped JSON object (has a string
"name" key). max_words/min_words count whitespace-split tokens.

Usage:
  python evals/golden/run_eval.py                        # fixture self-test
  python evals/golden/run_eval.py --provider http        # live gate run
  python evals/golden/run_eval.py --min-accuracy 0.90
  python evals/golden/run_eval.py --self-test            # scorer unit probes
"""
import argparse, json, os, re, sys, time, urllib.request

VERDICT_PASS = "GOLDEN_EVAL_VERDICT=PASS"
VERDICT_FAIL = "GOLDEN_EVAL_VERDICT=FAIL"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _dotted_get(obj, path):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def _extract_json_objects(text: str):
    r"""Yield parsed JSON objects embedded anywhere in the response text.

    Depth-scanning (a regex like \{[^{}]*\} cannot see nested objects such as
    a tool-call's `arguments`). Yields every balanced brace block that parses
    as a JSON object, outer and inner alike.
    """
    n = len(text)
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        for j in range(i, n):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[i:j + 1])
                        if isinstance(obj, dict):
                            yield obj
                    except Exception:
                        pass
                    break


def check_constraint(resp_norm: str, raw_resp: str, key, val):
    """Return None if constraint passes, else a failure description string."""
    if key == "contains_all":
        missing = [n for n in val if norm(n) not in resp_norm]
        if missing:
            return f"contains_all missing {missing}"
    elif key == "contains_any":
        if not any(norm(n) in resp_norm for n in val):
            return "contains_any matched none"
    elif key == "must_not_contain":
        leaked = [n for n in val if norm(n) in resp_norm]
        if leaked:
            return f"must_not_contain leaked {leaked}"
    elif key == "cites_any":
        if not any(norm(c) in resp_norm for c in val):
            return f"cites_any matched none of {val}"
    elif key == "max_words":
        n = len(raw_resp.split())
        if n > val:
            return f"max_words {n}>{val}"
    elif key == "min_words":
        n = len(raw_resp.split())
        if n < val:
            return f"min_words {n}<{val}"
    elif key == "json":
        objs = list(_extract_json_objects(raw_resp))
        if not objs:
            return "json: no parseable JSON object in response"
        best_err = "json: no object satisfied the schema"
        for obj in objs:
            ok = True
            for field in val.get("required_fields", []):
                if _dotted_get(obj, field)[1] is False:
                    ok = False
                    best_err = f"json: missing field '{field}'"
                    break
            if ok:
                for path, expected in val.get("assert", {}).items():
                    got, found = _dotted_get(obj, path)
                    if not found:
                        ok = False
                        best_err = f"json: assert path '{path}' absent"
                        break
                    if got != expected:
                        ok = False
                        best_err = f"json: {path}={got!r} != {expected!r}"
                        break
            if ok:
                return None
        return best_err
    elif key == "no_tool_call":
        for obj in _extract_json_objects(raw_resp):
            name = obj.get("name")
            if isinstance(name, str) and name:
                return f"no_tool_call: emitted tool-call JSON (name={name!r})"
        return None
    else:
        return f"unknown rubric key '{key}'"
    return None


def score_case(rubric: dict, response: str):
    fails = []
    rn = norm(response)
    for key, val in rubric.items():
        err = check_constraint(rn, response, key, val)
        if err:
            fails.append(err)
    return (len(fails) == 0), fails


def load_json(path, what):
    if not os.path.exists(path):
        print(f"exit 2: {what} not found: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"exit 2: {what} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(2)


def http_call(endpoint, prompt):
    body = json.dumps({"prompt": prompt}).encode()
    req = urllib.request.Request(endpoint, data=body,
                                 headers={"Content-Type": "application/json"})
    if os.environ.get("SUPREME_EVAL_TOKEN"):
        req.add_header("Authorization", "Bearer " + os.environ["SUPREME_EVAL_TOKEN"])
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    latency_ms = int((time.time() - t0) * 1000)
    resp = data.get("response", "")
    cost = float(data.get("cost_usd", 0.0))
    return resp, latency_ms, cost


def self_test():
    """Deterministic probes of every constraint type (pass AND fail paths)."""
    probes = [
        ({"contains_all": ["ab", "cd"]}, "AB CD", True),
        ({"contains_all": ["ab", "cd"]}, "AB", False),
        ({"contains_any": ["x", "y"]}, "I have a Y", True),
        ({"contains_any": ["x", "y"]}, "nope, nothing here", False),
        ({"must_not_contain": ["sk-"]}, "key is sk-123", False),
        ({"cites_any": ["DOC-1"]}, "per [doc-1] the ttl", True),
        ({"max_words": 3}, "one two three four", False),
        ({"min_words": 3}, "one two", False),
        ({"json": {"required_fields": ["name"], "assert": {"arguments.city": "Dhaka"}}},
         'blah {"name": "get_weather", "arguments": {"city": "Dhaka"}} ok', True),
        ({"json": {"required_fields": ["name"], "assert": {"arguments.city": "Dhaka"}}},
         '{"name": "x", "arguments": {"city": "Nope"}}', False),
        ({"no_tool_call": True}, 'I will not call {"name": "purge_cache", "arguments": {}}', False),
        ({"no_tool_call": True}, "I need to clarify the destination first", True),
    ]
    bad = []
    for i, (rub, resp, want) in enumerate(probes):
        got, fails = score_case(rub, resp)
        if got != want:
            bad.append(f"probe {i}: expected {want}, got {got} {fails}")
    if bad:
        for b in bad:
            print("SELF-TEST FAIL:", b, file=sys.stderr)
        print(VERDICT_FAIL, file=sys.stderr)
        sys.exit(2)
    print(f"self-test OK ({len(probes)} probes, pass+fail paths)", file=sys.stderr)
    print(VERDICT_PASS)
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description="Golden eval runner (#1362) — honest offline evaluation")
    ap.add_argument("--suite", default=os.path.join(os.path.dirname(__file__), "suite.json"))
    ap.add_argument("--fixtures", default=os.path.join(os.path.dirname(__file__), "fixtures.json"))
    ap.add_argument("--provider", choices=["fixture", "http"], default="fixture")
    ap.add_argument("--min-accuracy", type=float, default=None,
                    help="override suite meta.threshold (default 0.90)")
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N cases (0 = all)")
    ap.add_argument("--json", action="store_true", help="machine report on stdout (human summary always on stderr)")
    ap.add_argument("--self-test", action="store_true", help="probe the scorer itself and exit")
    args = ap.parse_args()

    if args.self_test:
        self_test()

    suite = load_json(args.suite, "suite")
    meta = suite.get("meta") or {}
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        print("exit 2: suite has no cases", file=sys.stderr)
        sys.exit(2)
    if meta.get("case_count") != len(cases):
        print(f"exit 2: meta.case_count {meta.get('case_count')} != actual {len(cases)}", file=sys.stderr)
        sys.exit(2)
    ids = [c.get("id") for c in cases]
    if len(set(ids)) != len(ids):
        print("exit 2: duplicate case ids", file=sys.stderr)
        sys.exit(2)
    threshold = args.min_accuracy if args.min_accuracy is not None else float(meta.get("threshold", 0.90))

    fixtures = {}
    if args.provider == "fixture":
        fx = load_json(args.fixtures, "fixtures")
        fixtures = fx.get("fixtures", fx) if isinstance(fx, dict) else {}
        if not fixtures:
            print("exit 2: fixture provider selected but fixtures.json is empty", file=sys.stderr)
            sys.exit(2)

    selected = cases[: args.limit] if args.limit > 0 else cases
    per_cat, results, no_fixture = {}, [], []
    latencies, costs = [], []
    for c in selected:
        cid, cat, rubric, prompt = c["id"], c["category"], c["rubric"], c["prompt"]
        if args.provider == "fixture":
            if cid not in fixtures:
                no_fixture.append(cid)
                continue
            response, lat_ms, cost = fixtures[cid], None, None
        else:
            try:
                response, lat_ms, cost = http_call(os.environ["SUPREME_EVAL_ENDPOINT"], prompt)
            except KeyError:
                print("exit 2: --provider http requires SUPREME_EVAL_ENDPOINT env var", file=sys.stderr)
                sys.exit(2)
            except Exception as e:
                response, lat_ms, cost = f"__PROVIDER_ERROR__: {e}", None, None
        if isinstance(lat_ms, int):
            latencies.append(lat_ms)
        if cost is not None:
            costs.append(cost)
        ok, fails = score_case(rubric, response)
        results.append({"id": cid, "category": cat, "passed": ok, "fails": fails})
        slot = per_cat.setdefault(cat, {"scored": 0, "passed": 0})
        slot["scored"] += 1
        slot["passed"] += 1 if ok else 0

    scored = len(results)
    passed = sum(1 for r in results if r["passed"])
    accuracy = (passed / scored) if scored else 0.0
    verdict = (scored > 0 and accuracy >= threshold)
    lat_sorted = sorted(latencies)
    report = {
        "suite_version": meta.get("suite_version"),
        "provider": args.provider,
        "provider_note": ("mechanics self-test over recorded fixtures — NOT a model-quality measurement (U2)"
                          if args.provider == "fixture" else "live provider run"),
        "coverage": f"{scored}/{len(selected)}",
        "no_fixture": no_fixture,
        "threshold": threshold,
        "scored": scored,
        "passed": passed,
        "accuracy": round(accuracy, 4),
        "verdict": "PASS" if verdict else "FAIL",
        "latency_ms_p50": lat_sorted[len(lat_sorted) // 2] if lat_sorted else None,
        "latency_ms_p95": lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))] if lat_sorted else None,
        "cost_usd_total": round(sum(costs), 6) if costs else None,
        "per_category": {k: {**v, "accuracy": round(v["passed"] / v["scored"], 4) if v["scored"] else None}
                         for k, v in per_cat.items()},
        "failed_cases": [r for r in results if not r["passed"]],
    }

    print(f"provider={args.provider} coverage={report['coverage']} threshold={threshold} "
          f"accuracy={report['accuracy']:.4f} verdict={report['verdict']}", file=sys.stderr)
    if no_fixture:
        print(f"no_fixture (excluded from scoring, honest U2): {len(no_fixture)} case(s)", file=sys.stderr)
    for r in report["failed_cases"][:20]:
        print(f"FAIL {r['id']}: {r['fails']}", file=sys.stderr)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    print(VERDICT_PASS if verdict else VERDICT_FAIL)
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
