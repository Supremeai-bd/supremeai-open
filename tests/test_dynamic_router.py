#!/usr/bin/env python3
"""tests/test_dynamic_router.py — test suite for core/routing/dynamic_router.py (issue #330).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_dynamic_router.py -v
  - stdlib:  python3 tests/test_dynamic_router.py   (plain runner, no pytest import)

Every test is offline and deterministic. The suite covers the issue's
acceptance criteria: the dynamic model chain orchestrator passes the shipped
fixture (api-schemas/fixtures/task-router.fixture.json), failover reorders
providers dynamically WITHOUT schema change (the loaded table is never
mutated), and every fallback is fail-closed / fail-honest — zero silent
failures, full audit trails.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FIXTURE = REPO / "api-schemas" / "fixtures" / "task-router.fixture.json"

from core.routing.dynamic_router import (  # noqa: E402
    GRADES,
    ROUTER_CONTRACT_VERSION,
    RULE_WHEN,
    TIER_NAMES,
    VALID_PROVIDERS,
    RoutingError,
    TableError,
    build_chain,
    classify_task,
    estimate_cost_usd,
    evaluate_budget,
    load_routing_table,
    route,
    run_chain,
    validate_table,
)


def table() -> dict:
    return load_routing_table(FIXTURE)


def mapping_for(table: dict, tier: int) -> dict:
    return next(m for m in table["routing_table"] if m["tier"] == tier)


# --- contract constants --------------------------------------------------------


def test_constants_contract():
    assert ROUTER_CONTRACT_VERSION == "dynamic-router-contract/1"
    assert len(VALID_PROVIDERS) == 7
    assert GRADES == ("healthy", "degraded", "unavailable")
    assert len(RULE_WHEN) == 4
    assert TIER_NAMES == ("fast_light", "coding_reasoning", "complex_architecture")


# --- fixture acceptance (the issue's own criterion) ------------------------------


def test_shipped_fixture_loads_and_validates():
    t = table()
    assert t["router_id"] == "federation-task-router"
    assert [m["tier"] for m in t["routing_table"]] == [1, 2, 3]
    validate_table(t)  # idempotent
    for m in t["routing_table"]:
        assert m["primary"]["provider"] in VALID_PROVIDERS
        assert len(m["fallback_cascade"]) >= 1


def test_fixture_tiers_chain_shape():
    t = table()
    for tier in (1, 2, 3):
        m = mapping_for(t, tier)
        chain = build_chain(t, tier)
        assert chain["chain"][0] == m["primary"]  # no health input -> declared order
        assert chain["chain"][1:] == m["fallback_cascade"]


# --- classification ---------------------------------------------------------------


def test_classification_token_thresholds():
    assert classify_task({"estimated_input_tokens": 500})["tier"] == 1
    assert classify_task({"estimated_input_tokens": 3999})["tier"] == 1
    assert classify_task({"estimated_input_tokens": 4000})["tier"] == 2
    assert classify_task({"estimated_input_tokens": 60000})["tier"] == 2
    assert classify_task({"estimated_input_tokens": 60001})["tier"] == 3


def test_classification_overrides_and_reject():
    assert classify_task({"complexity_tier": 3})["tier"] == 3
    assert classify_task({"task_tag": "P0-critical"})["tier"] == 3
    assert classify_task({"files_touched": 9})["tier"] == 2
    assert classify_task({"requires_tool_calling": True})["tier"] == 2
    for silent in ({}, {"estimated_input_tokens": None}, {"task_tag": "P3-low"}):
        try:
            classify_task(silent)
            raise AssertionError("unclassifiable must be rejected")
        except RoutingError as exc:
            assert "reject" in str(exc).lower()


# --- dynamic reorder without schema change ------------------------------------------


def test_health_reorder_promotes_healthy():
    t = table()
    snapshot = json.dumps(t, sort_keys=True)
    health = {"anthropic": {"grade": "unavailable"}, "deepseek": {"grade": "healthy"}}
    chain = build_chain(t, 2, health)
    providers = [e["provider"] for e in chain["chain"]]
    assert providers[-1] == "anthropic"  # unavailable demoted to tail
    assert "deepseek" in providers
    # no schema change, no table mutation — the issue's exact wording
    assert json.dumps(t, sort_keys=True) == snapshot


def test_equal_grades_keep_declared_order():
    t = table()
    health = {p: {"grade": "healthy"} for p in VALID_PROVIDERS}
    chain = build_chain(t, 2, health)
    assert chain["chain"][0] == mapping_for(t, 2)["primary"]


def test_unknown_provider_rejected_everywhere():
    t = table()
    try:
        build_chain(t, 1, {"skynet": {"grade": "healthy"}})
        raise AssertionError("unknown health provider must be rejected")
    except RoutingError:
        pass
    bad = copy.deepcopy(t)
    bad["routing_table"][0]["primary"]["provider"] = "skynet"
    try:
        validate_table(bad)
        raise AssertionError("unknown provider in table must be rejected at load")
    except TableError as exc:
        assert "skynet" in str(exc)


# --- budget rules: deterministic listed order ----------------------------------------


def test_context_rule_fires_first():
    t = table()
    res = evaluate_budget(t, tier=3, estimated_input_tokens=500_000, estimated_output_tokens=1000)
    assert res["action"] == "fallback_cascade"
    assert res["fired_rule_index"] == 0
    assert any("context_exceeds_primary" in p for p in res["decision_path"])


def test_cost_cap_rule_downgrades():
    t = table()
    # opus 0.045/1k * (1000 + 200_000) = $9.045 > $2.5 cap
    res = evaluate_budget(t, tier=3, estimated_input_tokens=1000, estimated_output_tokens=200_000)
    assert res["action"] == "downgrade_tier"
    assert res["fired_rule_index"] == 1


def test_budget_floor_caps_output():
    t = table()
    res = evaluate_budget(t, tier=1, estimated_input_tokens=100, estimated_output_tokens=100, budget_remaining_usd=0.05)
    assert res["action"] == "cap_output_tokens"
    assert res["fired_rule_index"] == 2


def test_sla_rule_with_and_without_telemetry():
    t = table()
    no_telemetry = evaluate_budget(t, tier=1, estimated_input_tokens=100, estimated_output_tokens=100)
    assert no_telemetry["action"] == "use_primary"  # nothing fired, honest
    t_sla = copy.deepcopy(t)
    t_sla["budget_rules"]["latency_sla_ms"] = 1200
    res = evaluate_budget(t_sla, tier=1, estimated_input_tokens=100, estimated_output_tokens=100, primary_latency_ms=5000.0)
    assert res["action"] == "queue_and_retry"
    assert res["fired_rule_index"] == 3


def test_no_rule_fires_is_honest():
    t = table()
    res = evaluate_budget(t, tier=1, estimated_input_tokens=100, estimated_output_tokens=100)
    assert res["action"] == "use_primary"
    assert res["fired_rule_index"] is None
    assert res["decision_path"][-1] == "no budget rule fired -> use_primary"


# --- end-to-end route + fail-honest chain ----------------------------------------------


def test_route_audit_trail_end_to_end():
    t = table()
    decision = route(
        t,
        {"estimated_input_tokens": 500_000, "estimated_output_tokens": 8000},
        health={"anthropic": {"grade": "degraded"}},
    )
    assert decision["tier"] == 3
    assert decision["chain"] and decision["reorder"]
    assert decision["decision_path"] and "context_exceeds_primary" in " ".join(decision["decision_path"])
    assert decision["cost_estimate_usd"] > 0


def test_route_downgrade_tier_action():
    t = table()
    # tier 3 (90k tokens) + huge output -> opus estimate $13.05 > $2.5 cap -> downgrade to tier 2
    decision = route(t, {"estimated_input_tokens": 90_000, "estimated_output_tokens": 200_000})
    assert decision["action"] == "downgrade_tier"
    assert decision["requested_tier"] == 3 and decision["tier"] == 2
    assert any("downgrade_tier" in p for p in decision["decision_path"])


def test_run_chain_fail_honest_exhaustion():
    t = table()
    decision = route(t, {"estimated_input_tokens": 500})
    try:
        run_chain(decision["chain"], lambda ep: False)
        raise AssertionError("exhausted chain must raise")
    except RoutingError as exc:
        assert "fail-honest" in str(exc)
        for endpoint in decision["chain"]:
            assert endpoint["provider"] in str(exc)


def test_run_chain_records_fallback_transition():
    t = table()
    decision = route(t, {"estimated_input_tokens": 500})
    first = decision["chain"][0]
    served = run_chain(decision["chain"], lambda ep: ep is not first)
    assert served["served_by"] == decision["chain"][1]
    assert served["fallbacks_used"] == 1
    assert served["attempts"][0]["outcome"] == "failed"
    assert served["attempts"][1]["outcome"] == "success"


def test_cost_estimates():
    assert estimate_cost_usd({"provider": "groq", "model": "m", "cost_per_1k_tokens_usd": 0.0006}, 1000, 1000) == 0.0012
    assert estimate_cost_usd({"provider": "groq", "model": "m"}, 1000, 1000) is None  # unpriced -> honest None


# --- boot smoke (the issue's own contract, verbatim) ------------------------------------


def test_boot_smoke_real_repo():
    import subprocess

    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import core.routing.dynamic_router"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_self_test_green():
    from core.routing.dynamic_router import self_test

    checks = self_test()
    assert isinstance(checks, int) and checks >= 20


# --- plain stdlib runner (no pytest required) --------------------------------------------


def main() -> int:
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception as exc:  # noqa: BLE001 — plain runner reports everything
            failed += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed (stdlib mode)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
