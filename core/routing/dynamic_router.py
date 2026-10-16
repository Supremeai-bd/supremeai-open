#!/usr/bin/env python3
"""Dynamic Task Routing Engine — deterministic chain orchestration (issue #330).

Reference implementation of the landed SSOT contract:
  - api-schemas/task-router.schema.json          (routing table, budget rules, defaults)
  - api-schemas/fixtures/task-router.fixture.json (canonical tier/route configuration)

Zero-dependency (stdlib only). The router NEVER talks to a provider network:
transport is injected via ``attempt_fn`` — the engine only decides the ORDER
of providers and records every decision honestly.

Core contracts (issue #330 acceptance criteria):

1. Fixture-faithful orchestration — the canonical fixture IS a valid router
   configuration; ``DynamicRouter`` validates it fail-closed (tier↔name pins,
   closed provider enum, budget rule vocabulary, defaults) and resolves a
   chain for every tier.
2. Failover reorders providers dynamically WITHOUT schema change — measured
   provider health (``healthy > degraded > down``) re-ranks the primary +
   fallback cascade at plan time; the payload shape is untouched.
3. Zero silent fallback failures — every skip/transition is recorded in the
   plan/attempt ledger; exhausting a chain raises ``RoutingExhaustedError``
   carrying the FULL ledger (fail-honest). Unknown providers and
   unclassifiable tasks follow the config ``defaults`` ("reject") — never a
   silent guess.

Self-test (offline, no network):

    python3 core/routing/dynamic_router.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROUTER_VERSION = "dynamic-router/1"
SCHEMA_VERSION = "1.0"

# Closed vocabularies (schema-pinned; drift here is a bug).
PROVIDERS = frozenset({
    "openai", "anthropic", "gemini", "groq", "openrouter", "mistral", "deepseek",
})
TIER_NAMES = {1: "fast_light", 2: "coding_reasoning", 3: "complex_architecture"}
HEALTH_RANK = {"healthy": 0, "degraded": 1, "down": 2}  # lower rank = preferred

BUDGET_TRIGGERS = frozenset({
    "context_exceeds_primary", "estimated_cost_above_cap",
    "budget_remaining_below_floor", "latency_sla_missed",
})
BUDGET_ACTIONS = frozenset({
    "fallback_cascade", "downgrade_tier", "cap_output_tokens", "queue_and_retry",
})

# Classification bounds — canonical fixture example_signals (deterministic).
TIER1_TOKEN_CEILING = 4000       # "below 4000" -> fast_light
TIER3_TOKEN_FLOOR = 60000        # "above 60000" -> complex_architecture
ESCALATING_PRIORITIES = frozenset({"P0", "P0-critical", "P1-high"})


class ConfigError(ValueError):
    """Router configuration rejected (fail-closed)."""


class ClassificationError(ValueError):
    """Task unclassifiable and config defaults say reject — fail-honest."""


class UnknownProviderError(KeyError):
    """Health/feed references a provider outside the closed enum or the table."""


class RoutingExhaustedError(RuntimeError):
    """Every endpoint in the ordered chain failed — carries the full ledger."""


# --- configuration ---------------------------------------------------------------


def load_fixture(path: Path | None = None) -> dict[str, Any]:
    """Load the canonical fixture as a router configuration."""
    p = path or (Path(__file__).resolve().parents[2] / "api-schemas" / "fixtures" / "task-router.fixture.json")
    return json.loads(p.read_text(encoding="utf-8"))


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed config validation (schema semantics, stdlib-only)."""
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ConfigError(f"schema_version must be {SCHEMA_VERSION!r} (got {config.get('schema_version')!r})")
    if not isinstance(config.get("router_id"), str) or not config["router_id"]:
        raise ConfigError("router_id must be a non-empty string")

    tiers_seen: dict[int, dict[str, Any]] = {}
    for tier_node in config.get("complexity_tiers", []):
        tier = tier_node.get("tier")
        if tier not in TIER_NAMES or tier_node.get("name") != TIER_NAMES[tier]:
            raise ConfigError(f"tier/name pin violated: {tier!r} -> {tier_node.get('name')!r}")
        if not tier_node.get("example_signals"):
            raise ConfigError(f"tier {tier} needs example_signals (schema minItems 1)")
        tiers_seen[tier] = tier_node
    if set(tiers_seen) != set(TIER_NAMES):
        raise ConfigError(f"expected tiers {{1,2,3}}, saw {sorted(tiers_seen)}")

    routes: dict[int, dict[str, Any]] = {}
    for route in config.get("routing_table", []):
        tier = route.get("tier")
        if tier in routes:
            raise ConfigError(f"duplicate routing_table entry for tier {tier}")
        primary = route.get("primary") or {}
        if primary.get("provider") not in PROVIDERS:
            raise ConfigError(f"tier {tier} primary provider invalid: {primary.get('provider')!r}")
        cascade = route.get("fallback_cascade") or []
        if not cascade:
            raise ConfigError(f"tier {tier} fallback_cascade needs >= 1 entry (schema minItems 1)")
        for endpoint in [primary, *cascade]:
            if endpoint.get("provider") not in PROVIDERS:
                raise ConfigError(
                    f"tier {tier} endpoint provider invalid: {endpoint.get('provider')!r}"
                )
        routes[tier] = {"primary": primary, "fallback_cascade": list(cascade)}
    if set(routes) != set(TIER_NAMES):
        raise ConfigError(f"routing_table must cover tiers 1..3, saw {sorted(routes)}")

    rules = config.get("budget_rules") or {}
    for rule in rules.get("rules", []):
        if rule.get("when") not in BUDGET_TRIGGERS or rule.get("then") not in BUDGET_ACTIONS:
            raise ConfigError(f"budget rule outside closed vocabulary: {rule}")
    for key in ("per_task_max_input_tokens", "per_task_max_output_tokens", "max_cost_per_task_usd"):
        if not isinstance(rules.get(key), (int, float)) or rules[key] <= 0:
            raise ConfigError(f"budget_rules.{key} must be a positive number")

    defaults = config.get("defaults") or {}
    if defaults.get("unclassifiable_task") != "reject" or defaults.get("unknown_provider") != "reject":
        raise ConfigError(
            "v1 defaults are pinned to reject/reject (fail-closed posture) — "
            f"got {defaults!r}"
        )
    return {"tiers": tiers_seen, "routes": routes, "budget": rules, "defaults": defaults}


# --- classification (deterministic) ----------------------------------------------


def classify(
    estimated_input_tokens: int,
    subsystems_touched: int = 1,
    priority_tag: str | None = None,
    defaults: dict[str, Any] | None = None,
) -> int:
    """Tier from the fixture's example signals (deterministic, no ML).

    Tier 3: >60000 tokens, or spans >1 subsystem, or escalating priority tag.
    Tier 1: <4000 tokens AND single-subsystem AND no escalation tag.
    Otherwise tier 2. Negative/absent size = unclassifiable -> reject (default).
    """
    if not isinstance(estimated_input_tokens, int) or isinstance(estimated_input_tokens, bool) \
            or estimated_input_tokens < 0:
        action = (defaults or {}).get("unclassifiable_task", "reject")
        if action == "reject":
            raise ClassificationError(
                f"estimated_input_tokens {estimated_input_tokens!r} is unclassifiable — "
                "defaults.unclassifiable_task=reject (fail-honest, no tier guessed)"
            )
        raise ClassificationError(f"unsupported unclassifiable_task action: {action!r}")
    if estimated_input_tokens > TIER3_TOKEN_FLOOR or subsystems_touched > 1 \
            or (priority_tag or "") in ESCALATING_PRIORITIES:
        return 3
    if estimated_input_tokens < TIER1_TOKEN_CEILING and subsystems_touched <= 1 \
            and (priority_tag or "") not in ESCALATING_PRIORITIES:
        return 1
    return 2


# --- chain resolution (health-aware reorder, no schema change) -------------------


@dataclass
class RoutePlan:
    tier: int
    tier_name: str
    ordered_chain: list[dict[str, Any]]
    ledger: list[dict[str, Any]] = field(default_factory=list)
    output_cap: int | None = None
    queued: bool = False
    plan_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "tier": self.tier,
            "tier_name": self.tier_name,
            "ordered_chain": self.ordered_chain,
            "ledger": self.ledger,
            "output_cap": self.output_cap,
            "queued": self.queued,
        }


def _endpoint_key(endpoint: dict[str, Any]) -> str:
    return f"{endpoint.get('provider')}:{endpoint.get('model')}"


def validate_health(health: dict[str, str] | None) -> None:
    """Fail-honest health validation: enum + state vocabulary, fleet-wide.

    Entries for providers outside the current tier's table are legitimate
    (the feed covers the whole fleet) — they simply never enter this tier's
    chain. Out-of-enum providers or unknown states are anomalies and REJECT.
    """
    for provider, state in (health or {}).items():
        if provider not in PROVIDERS:
            raise UnknownProviderError(
                f"health references provider {provider!r} outside the closed enum — "
                "defaults.unknown_provider=reject"
            )
        if state not in HEALTH_RANK:
            raise UnknownProviderError(
                f"health state {state!r} for {provider!r} outside "
                f"{sorted(HEALTH_RANK)} — refusing to guess"
            )


def resolve_chain(
    tier: int,
    routes: dict[int, dict[str, Any]],
    health: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Order primary + cascade by measured health (acceptance criterion 2).

    Returns (ordered_chain, ledger). Healthy primary keeps its seat; a
    degraded primary sinks below healthy cascade entries; down/absent-from-
    table endpoints are excluded WITH a ledger record (never silent). Order
    inside equal health ranks is the schema order (deterministic tie-break).
    """
    route = routes[tier]
    candidates: list[tuple[int, int, dict[str, Any], str]] = []  # (rank, orig_idx, endpoint, role)
    ledger: list[dict[str, Any]] = []
    idx = 0
    for role, endpoint in [("primary", route["primary"]),
                           *[(f"cascade[{i}]", e) for i, e in enumerate(route["fallback_cascade"])]]:
        provider = endpoint["provider"]
        state = (health or {}).get(provider, "healthy")
        if state == "down":
            ledger.append({
                "event": "excluded", "provider": provider, "role": role,
                "reason": f"health={state}", "endpoint": _endpoint_key(endpoint),
            })
            idx += 1
            continue
        rank = HEALTH_RANK[state]
        if role == "primary" and rank > 0:
            ledger.append({
                "event": "reordered", "provider": provider, "role": role,
                "reason": f"primary health={state} sinks below healthy cascade",
                "endpoint": _endpoint_key(endpoint),
            })
        candidates.append((rank, idx, endpoint, role))
        idx += 1
    candidates.sort(key=lambda c: (c[0], c[1]))  # health rank, then schema order
    ordered = [c[2] for c in candidates]
    if not ordered:
        ledger.append({"event": "chain_empty", "reason": "every endpoint excluded by health"})
    return ordered, ledger


# --- budget rules + planning ------------------------------------------------------


def _estimated_cost_usd(endpoint: dict[str, Any], input_tokens: int, output_tokens: int) -> float:
    cost = endpoint.get("cost_per_1k_tokens_usd", 0.0)
    return ((input_tokens + output_tokens) / 1000.0) * cost


def plan_task(
    router_config: dict[str, Any],
    estimated_input_tokens: int,
    estimated_output_tokens: int = 1024,
    subsystems_touched: int = 1,
    priority_tag: str | None = None,
    health: dict[str, str] | None = None,
    budget_remaining_usd: float | None = None,
) -> RoutePlan:
    """Deterministic RoutePlan: classify -> budget rules -> health-ordered chain.

    The ledger records every budget trigger and reorder (zero silent decisions).
    """
    parsed = validate_config(router_config)
    tier = classify(estimated_input_tokens, subsystems_touched, priority_tag,
                    parsed["defaults"])
    budget = parsed["budget"]
    ledger: list[dict[str, Any]] = []
    output_cap: int | None = None
    queued = False

    # Budget rules (closed vocabulary, deterministic evaluation order).
    if estimated_output_tokens > budget["per_task_max_output_tokens"]:
        ledger.append({"event": "budget_rule", "when": "per_task_max_output_tokens",
                       "detail": f"capping {estimated_output_tokens} -> {budget['per_task_max_output_tokens']}"})
        output_cap = budget["per_task_max_output_tokens"]
    if budget_remaining_usd is not None and budget_remaining_usd < budget.get("budget_floor_usd", 0.0):
        cap = budget["per_task_max_output_tokens"]
        ledger.append({"event": "budget_rule", "when": "budget_remaining_below_floor",
                       "then": "cap_output_tokens", "detail": f"remaining ${budget_remaining_usd}"})
        output_cap = min(output_cap or cap, cap)
    if estimated_input_tokens > budget["per_task_max_input_tokens"]:
        # budget rule: context exceeds the per-task ceiling -> fail-honest
        ledger.append({"event": "budget_rule", "when": "per_task_max_input_tokens",
                       "detail": f"{estimated_input_tokens} > {budget['per_task_max_input_tokens']}"})
        raise ClassificationError(
            f"task exceeds per_task_max_input_tokens ({estimated_input_tokens} > "
            f"{budget['per_task_max_input_tokens']}) — refuse rather than silently truncate"
        )

    validate_health(health)
    chain, chain_ledger = resolve_chain(tier, parsed["routes"], health)
    ledger.extend(chain_ledger)

    # context_exceeds_primary -> cascade (recorded; the reorder already reflects it)
    primary = parsed["routes"][tier]["primary"]
    primary_ctx = primary.get("max_context_tokens")
    if primary_ctx is not None and estimated_input_tokens > primary_ctx:
        ledger.append({"event": "budget_rule", "when": "context_exceeds_primary",
                       "then": "fallback_cascade",
                       "detail": f"est {estimated_input_tokens} > primary ctx {primary_ctx}"})
        # promote first cascade endpoint with a large-enough context to the front
        promoted = False
        for i, endpoint in enumerate(chain[1:], start=1):
            ctx = endpoint.get("max_context_tokens")
            if ctx is not None and estimated_input_tokens <= ctx and not promoted:
                ledger.append({"event": "promoted", "provider": endpoint["provider"],
                               "endpoint": _endpoint_key(endpoint),
                               "reason": "context headroom for oversized task"})
                chain.insert(0, chain.pop(i))
                promoted = True
                break
        if not promoted:
            ledger.append({"event": "no_context_headroom",
                           "reason": "no cascade endpoint admits the task size"})

    # estimated_cost_above_cap -> downgrade_tier (honest floor at tier 1)
    head = chain[0] if chain else primary
    cost = _estimated_cost_usd(head, estimated_input_tokens,
                               min(estimated_output_tokens, output_cap or estimated_output_tokens))
    if cost > budget["max_cost_per_task_usd"]:
        ledger.append({"event": "budget_rule", "when": "estimated_cost_above_cap",
                       "then": "downgrade_tier", "detail": f"est ${cost:.4f}"})
        if tier > 1:
            tier -= 1
            ledger.append({"event": "downgraded", "to_tier": tier, "tier_name": TIER_NAMES[tier]})
            chain, chain_ledger = resolve_chain(tier, parsed["routes"], health)
            ledger.extend(chain_ledger)
        else:
            ledger.append({"event": "downgrade_floor",
                           "reason": "tier 1 is the floor — honest refusal required"})

    seed = json.dumps({"t": tier, "in": estimated_input_tokens, "out": estimated_output_tokens,
                       "chain": [_endpoint_key(e) for e in chain]}, sort_keys=True)
    plan = RoutePlan(
        tier=tier,
        tier_name=TIER_NAMES[tier],
        ordered_chain=chain,
        ledger=ledger,
        output_cap=output_cap,
        queued=queued,
        plan_id="plan-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12],
    )
    return plan


# --- execution (transport injected; full attempt ledger) ---------------------------


@dataclass
class RouteResult:
    plan_id: str
    attempts: list[dict[str, Any]]
    served_by: str

    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "attempts": self.attempts, "served_by": self.served_by}


def execute(
    plan: RoutePlan,
    attempt_fn: Callable[[dict[str, Any]], tuple[bool, str]],
) -> RouteResult:
    """Walk the ordered chain; every transition is ledgered; exhaustion is loud.

    ``attempt_fn(endpoint) -> (ok, detail)`` is the injected transport probe.
    """
    attempts: list[dict[str, Any]] = []
    for position, endpoint in enumerate(plan.ordered_chain):
        try:
            ok, detail = attempt_fn(endpoint)
        except Exception as exc:  # noqa: BLE001 — transport crash == failed attempt
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        attempts.append({
            "position": position,
            "provider": endpoint["provider"],
            "endpoint": _endpoint_key(endpoint),
            "outcome": "success" if ok else "failed",
            "detail": detail,
        })
        if ok:
            return RouteResult(plan_id=plan.plan_id, attempts=attempts,
                               served_by=_endpoint_key(endpoint))
    raise RoutingExhaustedError(
        "every endpoint in the chain failed — no silent fallback to nowhere: "
        + json.dumps(attempts, indent=1)
    )


# --- offline self-test ------------------------------------------------------------


def _self_test() -> int:
    failures: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"  PASS | {name}")
        except AssertionError as exc:
            failures.append(f"{name}: {exc}")
            print(f"  FAIL | {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  ERROR | {name}: {type(exc).__name__}: {exc}")

    config = load_fixture()

    # R1 — fixture loads and passes fail-closed validation (acceptance 1).
    def r1() -> None:
        parsed = validate_config(config)
        assert set(parsed["routes"]) == {1, 2, 3}
        assert parsed["defaults"] == {"unclassifiable_task": "reject", "unknown_provider": "reject"}
        for bad in (
            {**config, "schema_version": "9.9"},
            {**config, "routing_table": config["routing_table"][:2]},
            {**config, "defaults": {"unclassifiable_task": "guess", "unknown_provider": "reject"}},
            {**config, "budget_rules": {**config["budget_rules"],
                                        "rules": [{"when": "made_up", "then": "fallback_cascade"}]}},
        ):
            try:
                validate_config(bad)
                raise AssertionError(f"config accepted: {json.dumps(bad)[:60]}")
            except ConfigError:
                pass

    # R2 — deterministic classification bounds (fixture example_signals).
    def r2() -> None:
        assert classify(3999) == 1
        assert classify(4000) == 2
        assert classify(60001) == 3
        assert classify(1000, subsystems_touched=3) == 3
        assert classify(1000, priority_tag="P1-high") == 3
        for bad in (-1, None, "5000"):
            try:
                classify(bad)  # type: ignore[arg-type]
                raise AssertionError(f"classify accepted {bad!r}")
            except ClassificationError:
                pass

    # R3 — health reorder without schema change (acceptance 2).
    def r3() -> None:
        parsed = validate_config(config)
        chain, ledger = resolve_chain(1, parsed["routes"], {"groq": "degraded"})
        assert chain[0]["provider"] != "groq", "degraded primary must sink"
        assert any(e["event"] == "reordered" for e in ledger)
        chain2, _ = resolve_chain(1, parsed["routes"], {"groq": "down"})
        assert all(e["provider"] != "groq" for e in chain2)
        # out-of-enum fleet entries are anomalies: plan_task rejects (fail-honest)
        try:
            plan_task(config, 20000, health={"not-a-provider": "healthy"})
            raise AssertionError("unknown provider accepted")
        except UnknownProviderError:
            pass
        try:
            plan_task(config, 20000, health={"groq": "on-fire"})
            raise AssertionError("unknown health state accepted")
        except UnknownProviderError:
            pass

    # R4 — zero silent fallback: failover ledger + exhaustion carries everything.
    def r4() -> None:
        plan = plan_task(config, estimated_input_tokens=20000)  # tier 2 chain
        providers = [e["provider"] for e in plan.ordered_chain]
        assert providers == ["anthropic", "openai", "deepseek"], providers
        calls: list[str] = []

        def flaky(endpoint):
            calls.append(endpoint["provider"])
            return (len(calls) >= 3, "simulated 429" if len(calls) < 3 else "ok")

        result = execute(plan, flaky)
        assert result.served_by and len(result.attempts) == 3
        assert [a["outcome"] for a in result.attempts] == ["failed", "failed", "success"]
        assert "simulated 429" in result.attempts[0]["detail"], "no silent transitions"

        def always_down(endpoint):
            return (False, "provider unreachable")

        try:
            execute(plan, always_down)
            raise AssertionError("exhaustion must raise")
        except RoutingExhaustedError as exc:
            for provider in providers:
                assert provider in str(exc), \
                    f"exhaustion ledger missing {provider} (must carry FULL ledger)"

    # R5 — budget rules: context promotion (custom config; the canonical
    # fixture's primary ctx 128k exceeds its 120k per-task ceiling, so the
    # promotion path needs a config where primary ctx < ceiling), floor cap,
    # honest over-ceiling refusal.
    def r5() -> None:
        small_primary = json.loads(json.dumps(config))
        small_primary["routing_table"][0]["primary"]["max_context_tokens"] = 3000
        plan = plan_task(small_primary, estimated_input_tokens=3500)
        head_ctx = plan.ordered_chain[0].get("max_context_tokens") or 0
        assert head_ctx >= 3500, "chain head must admit the oversized task"
        assert any(e["event"] == "promoted" for e in plan.ledger)

        capped = plan_task(config, estimated_input_tokens=5000,
                           estimated_output_tokens=99999)
        assert capped.output_cap is not None and capped.output_cap > 0

        floored = plan_task(config, estimated_input_tokens=5000, budget_remaining_usd=0.01)
        assert floored.output_cap is not None
        assert any(e["when"] == "budget_remaining_below_floor" for e in floored.ledger)

        try:
            plan_task(config, estimated_input_tokens=500000)
            raise AssertionError("over-ceiling task must refuse")
        except ClassificationError:
            pass

    # R6 — determinism: identical inputs -> byte-identical plans.
    def r6() -> None:
        p1 = plan_task(config, 20000, health={"groq": "degraded"})
        p2 = plan_task(config, 20000, health={"groq": "degraded"})
        assert json.dumps(p1.to_dict(), sort_keys=True) == json.dumps(p2.to_dict(), sort_keys=True)
        assert p1.plan_id.startswith("plan-")

    for name, fn in (
        ("R1 fixture-faithful config validation", r1),
        ("R2 deterministic classification bounds", r2),
        ("R3 health reorder, no schema change", r3),
        ("R4 zero-silent failover + loud exhaustion", r4),
        ("R5 budget rules (promotion/cap/refusal)", r5),
        ("R6 plan determinism", r6),
    ):
        check(name, fn)

    print(f"{6 - len(failures)}/6 self-test groups passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dynamic Task Routing Engine (#330)")
    parser.add_argument("--self-test", action="store_true",
                        help="run the offline scenario harness and exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
