#!/usr/bin/env python3
"""tests/test_dynamic_router.py — suite for core/routing/dynamic_router.py (issue #330).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_dynamic_router.py -v
  - stdlib:  python3 tests/test_dynamic_router.py   (plain runner, no pytest import)

Every test is offline and deterministic. Coverage mirrors the issue #330
acceptance criteria: fixture-faithful chain orchestration (the canonical
api-schemas/fixtures/task-router.fixture.json validates against the REAL
task-router.schema.json via the repo's stdlib validator), health-driven
failover reordering without schema change, and zero-silent fallback semantics
(full ledgers, loud exhaustion, reject defaults).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE_DIR = REPO / "core"
SCRIPTS_DIR = REPO / "scripts"
for p in (str(CORE_DIR), str(CORE_DIR / "routing"), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dynamic_router import (  # noqa: E402
    PROVIDERS,
    ROUTER_VERSION,
    ClassificationError,
    ConfigError,
    RoutePlan,
    RoutingExhaustedError,
    UnknownProviderError,
    classify,
    execute,
    load_fixture,
    plan_task,
    validate_config,
    validate_health,
)

CONFIG = load_fixture()


# --- fixture + config validation (acceptance criterion 1) ------------------------

def test_canonical_fixture_is_schema_valid():
    """The fixture itself must validate against the REAL repo schema."""
    from validate_schemas import SchemaValidator

    schema = json.loads((REPO / "api-schemas" / "task-router.schema.json").read_text(encoding="utf-8"))
    errs = SchemaValidator(schema).validate(CONFIG)
    assert errs == [], f"canonical fixture violates its own schema: {errs[:3]}"


def test_fixture_config_passes_validation():
    parsed = validate_config(CONFIG)
    assert set(parsed["routes"]) == {1, 2, 3}
    assert parsed["defaults"] == {"unclassifiable_task": "reject", "unknown_provider": "reject"}
    assert parsed["budget"]["max_cost_per_task_usd"] == 2.5


def test_config_validation_fail_closed():
    bad_cases = [
        {**CONFIG, "schema_version": "9.9"},
        {**CONFIG, "router_id": ""},
        {**CONFIG, "complexity_tiers": CONFIG["complexity_tiers"][:2]},
        {**CONFIG, "complexity_tiers": [{**CONFIG["complexity_tiers"][0], "name": "wrong"}]},
        {**CONFIG, "routing_table": CONFIG["routing_table"] + [CONFIG["routing_table"][0]]},
        {**CONFIG, "defaults": {"unclassifiable_task": "guess", "unknown_provider": "reject"}},
        {**CONFIG, "budget_rules": {**CONFIG["budget_rules"],
                                    "rules": [{"when": "moon_is_up", "then": "fallback_cascade"}]}},
        {**CONFIG, "budget_rules": {**CONFIG["budget_rules"], "max_cost_per_task_usd": -1}},
        {**CONFIG, "routing_table": [
            {**CONFIG["routing_table"][0], "fallback_cascade": []},
            *CONFIG["routing_table"][1:],
        ]},
    ]
    for bad in bad_cases:
        try:
            validate_config(bad)
            raise AssertionError(f"config accepted: {json.dumps(bad)[:70]}")
        except ConfigError:
            pass


# --- deterministic classification --------------------------------------------------

def test_classification_bounds_deterministic():
    assert classify(3999) == 1
    assert classify(4000) == 2
    assert classify(60000) == 2
    assert classify(60001) == 3
    assert classify(1000, subsystems_touched=3) == 3
    assert classify(1000, priority_tag="P1-high") == 3
    assert classify(1000, priority_tag="P2") == 1  # non-escalating tag keeps light tier


def test_unclassifiable_rejects_fail_honest():
    for bad in (-1, None, "5000", 3.5, True):
        try:
            classify(bad)  # type: ignore[arg-type]
            raise AssertionError(f"classify accepted {bad!r}")
        except ClassificationError:
            pass


# --- health reorder (acceptance criterion 2, no schema change) ---------------------

def test_degraded_primary_sinks_below_healthy_cascade():
    chain, ledger = _resolve(1, {"groq": "degraded"})
    assert chain[0]["provider"] != "groq"
    assert any(e["event"] == "reordered" for e in ledger)
    # degraded primary still present, just later
    assert "groq" in [e["provider"] for e in chain]


def test_down_provider_excluded_with_ledger():
    chain, ledger = _resolve(1, {"groq": "down"})
    assert "groq" not in [e["provider"] for e in chain]
    assert any(e["event"] == "excluded" and e["provider"] == "groq" for e in ledger)


def test_no_health_table_order_preserved():
    chain, ledger = _resolve(2, None)
    assert [e["provider"] for e in chain] == ["anthropic", "openai", "deepseek"]
    assert ledger == [] or not any(e["event"] in ("reordered", "excluded") for e in ledger)


def test_health_fleet_wide_fail_honest():
    validate_health({"anthropic": "degraded"})  # cross-tier entry is legitimate
    for bad_health in ({"not-a-provider": "healthy"}, {"groq": "on-fire"}):
        try:
            plan_task(CONFIG, 20000, health=bad_health)
            raise AssertionError(f"health accepted: {bad_health}")
        except UnknownProviderError:
            pass


# --- zero-silent failover (acceptance criterion 3) ----------------------------------

def _resolve(tier, health):
    parsed = validate_config(CONFIG)
    from dynamic_router import resolve_chain
    return resolve_chain(tier, parsed["routes"], health)


def test_failover_ledger_records_every_transition():
    plan = plan_task(CONFIG, 20000)
    calls = []

    def flaky(endpoint):
        calls.append(endpoint["provider"])
        return (len(calls) >= 3, "simulated 429" if len(calls) < 3 else "ok")

    result = execute(plan, flaky)
    assert result.served_by.endswith("deepseek") or len(result.attempts) == 3
    outcomes = [a["outcome"] for a in result.attempts]
    assert outcomes == ["failed", "failed", "success"]
    assert result.attempts[0]["detail"] == "simulated 429"


def test_exhaustion_is_loud_with_full_ledger():
    plan = plan_task(CONFIG, 20000)
    providers = [e["provider"] for e in plan.ordered_chain]
    try:
        execute(plan, lambda endpoint: (False, "provider unreachable"))
        raise AssertionError("exhaustion must raise")
    except RoutingExhaustedError as exc:
        for provider in providers:
            assert provider in str(exc), f"ledger missing {provider}"


def test_context_promotion_and_over_ceiling_refusal():
    small_primary = copy.deepcopy(CONFIG)
    small_primary["routing_table"][0]["primary"]["max_context_tokens"] = 3000
    plan = plan_task(small_primary, 3500)
    assert (plan.ordered_chain[0].get("max_context_tokens") or 0) >= 3500
    assert any(e["event"] == "promoted" for e in plan.ledger)
    # canonical fixture: over-ceiling refuses instead of silently truncating
    try:
        plan_task(CONFIG, 500000)
        raise AssertionError("over-ceiling task accepted")
    except ClassificationError:
        pass


def test_budget_floor_caps_and_ledgers():
    plan = plan_task(CONFIG, 5000, budget_remaining_usd=0.01)
    assert plan.output_cap is not None
    assert any(e.get("when") == "budget_remaining_below_floor" for e in plan.ledger)


def test_output_cap_from_budget():
    plan = plan_task(CONFIG, 5000, estimated_output_tokens=99999)
    assert plan.output_cap == CONFIG["budget_rules"]["per_task_max_output_tokens"]
    assert any("per_task_max_output_tokens" in e.get("when", "") for e in plan.ledger)


# --- determinism ----------------------------------------------------------------------

def test_plans_deterministic():
    p1 = plan_task(CONFIG, 20000, health={"groq": "degraded"})
    p2 = plan_task(CONFIG, 20000, health={"groq": "degraded"})
    assert json.dumps(p1.to_dict(), sort_keys=True) == json.dumps(p2.to_dict(), sort_keys=True)
    assert p1.plan_id.startswith("plan-") and len(p1.plan_id) == 17


def test_provider_enum_closed():
    assert PROVIDERS == frozenset({
        "openai", "anthropic", "gemini", "groq", "openrouter", "mistral", "deepseek",
    })


def test_router_version_tag():
    assert ROUTER_VERSION == "dynamic-router/1"


# --- stdlib plain runner ---------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest failure reporting
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
