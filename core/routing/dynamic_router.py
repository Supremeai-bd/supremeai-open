#!/usr/bin/env python3
"""SupremeAI dynamic task routing engine — issue #330.

Spec SSOT chain:
  - api-schemas/task-router.schema.json ($defs: ComplexityTier, ModelEndpoint,
    RouteMapping, CostBudgetRules, BudgetRule, RouterDefaults)
  - api-schemas/fixtures/task-router.fixture.json (the routing table this
    engine must pass — issue acceptance criterion #1)
  - api-schemas/provider-registry.schema.json (provider id enum + failover
    semantics the cascade mirrors at model granularity)
  - issue #330: "Failover logic reorders providers dynamically without
    schema change. Zero silent fallback failures (fail-closed / fail-honest)."

The router CONSUMES the declarative routing table — it never mutates the
table or the schema. Dynamic behaviour comes from two honest inputs:
  1. task signals            → complexity tier classification (1..3)
  2. provider health grades  → deterministic chain reorder (no schema change)

Every branch of every decision is recorded in ``decision_path`` — the router
never guesses silently. Budget rules evaluate deterministically in listed
order (schema: "evaluated deterministically in listed order"); the first
matching rule fires. Fail-closed defaults are load-time teeth:
``unclassifiable_task=reject`` and ``unknown_provider=reject`` (both ``const``
in RouterDefaults — any other value fails table validation).

House style (mirrors runner/agent_runner.py and examples/gateway_client.py):
- offline-safe import: module import performs zero file/network I/O
- zero third-party dependencies (AGENT_RULES.md §13); when ``jsonschema`` is
  importable the table is validated authoritatively (Draft 2020-12), else an
  honest frozen mirror of the schema's $defs takes over — one loud degraded
  line on stderr, never a silent downgrade
- honest errors: every violation names the offending field/tier/provider
- no credentials here: the router plans routes, it never touches keys

Contract (বাংলা মন্তব্য — router-চুক্তি):
- ইনপুট: task-router.fixture.json আকৃতির টেবিল (load-time fail-closed যাচাই);
  task signals dict; provider health grades dict; optional telemetry
- শ্রেণিবিন্যাস: estimated_input_tokens (4000/60000 থ্রেশহোল্ড — fixture
  example_signals থেকে) + deterministic tie-breakers; শ্রেণি না বসলে REJECT
  (defaults.unclassifiable_task) — কখনো অনুমান নয়
- চেইন: [primary] + fallback_cascade; health grade (healthy>degraded>
  unavailable) দিয়ে stable reorder — সমান grade হলে ঘোষিত ক্রমই থাকে
  ("first entry is tried first", schema RouteMapping description);
  অজানা provider হলে load-time-এই REJECT (defaults.unknown_provider)
- budget rules: তালিকাভুক্ত ক্রমে, প্রথম মিলটাই চলে — fallback_cascade /
  downgrade_tier / cap_output_tokens / queue_and_retry; কোনো rule না জ্বললে
  সৎ "use_primary"
- fail-honest: চেইনের সব endpoint fail করলে RoutingError সম্পূর্ণ attempt
  ledger সহ — কখনো চুপচাপ None ফেরত নয়
- টেবিল কখনো mutate হয় না — reorder কপিতে চলে (issue: "without schema change")

CLI self-test (offline, hermetic):
    python core/routing/dynamic_router.py --self-test

Route one task (offline demo):
    python core/routing/dynamic_router.py --route '{"estimated_input_tokens": 500}'

Exit codes: 0 = সফল; 1 = রাউটিং/চুক্তি ব্যর্থতা; 2 = usage/টেবিল ত্রুটি
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# Frozen contract constants — kept in lockstep with task-router.schema.json
# ---------------------------------------------------------------------------

ROUTER_CONTRACT_VERSION = "dynamic-router-contract/1"

VALID_PROVIDERS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "gemini",
    "groq",
    "openrouter",
    "mistral",
    "deepseek",
)

GRADES: tuple[str, ...] = ("healthy", "degraded", "unavailable")
GRADE_RANK = {"healthy": 0, "degraded": 1, "unavailable": 2}

TIER_NAMES = ("fast_light", "coding_reasoning", "complex_architecture")

RULE_WHEN: tuple[str, ...] = (
    "context_exceeds_primary",
    "estimated_cost_above_cap",
    "budget_remaining_below_floor",
    "latency_sla_missed",
)
RULE_THEN: tuple[str, ...] = (
    "fallback_cascade",
    "downgrade_tier",
    "cap_output_tokens",
    "queue_and_retry",
)
WHEN_THEN = dict(zip(RULE_WHEN, RULE_THEN))

# Fixture example_signals pin the quantitative thresholds:
#   tier 1 "estimated_input_tokens below 4000"
#   tier 2 "estimated_input_tokens between 4000 and 60000"
#   tier 3 "estimated_input_tokens above 60000"
TOKEN_THRESHOLD_TIER2 = 4000
TOKEN_THRESHOLD_TIER3 = 60000

DEFAULT_TABLE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "api-schemas",
    "fixtures",
    "task-router.fixture.json",
)
DEFAULT_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "api-schemas",
    "task-router.schema.json",
)


# ---------------------------------------------------------------------------
# Errors — honest, field-annotated, fail-closed
# ---------------------------------------------------------------------------


class RouterError(RuntimeError):
    """Base error: names the offending field/tier/provider."""

    def __init__(self, message: str, *, field: str = "") -> None:
        self.field = field
        suffix = f" [field: {field}]" if field else ""
        super().__init__(f"{message}{suffix}")


class TableError(RouterError):
    """The routing table violates task-router.schema.json semantics."""


class RoutingError(RouterError):
    """Routing refused (fail-closed) or the chain exhausted (fail-honest)."""


# ---------------------------------------------------------------------------
# Table loading + fail-closed validation (schema mirror, jsonschema-authoritative)
# ---------------------------------------------------------------------------


def load_routing_table(
    table_path: str | Path = DEFAULT_TABLE_PATH,
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and validate a routing table. Raises TableError on any violation."""
    path = Path(table_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TableError(f"routing table unreadable: {exc}", field=str(path)) from exc
    try:
        table = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TableError(f"routing table is not valid JSON: {exc}", field=str(path)) from exc
    validate_table(table, path=str(path))
    if schema_path is not None:
        _authoritative_validate(table, Path(schema_path), str(path))
    return table


def _authoritative_validate(table: dict[str, Any], schema_path: Path, src: str) -> None:
    """Draft 2020-12 validation when jsonschema exists; loud honest skip otherwise."""
    try:
        import jsonschema  # noqa: PLC0415 — optional, authoritative path only
    except ImportError:
        print(
            "router: jsonschema unavailable — frozen $defs mirror already passed "
            f"({src}); skipping authoritative validation",
            file=sys.stderr,
        )
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TableError(f"schema unreadable: {exc}", field=str(schema_path)) from exc
    validator_cls = getattr(jsonschema, "Draft202012Validator", None)
    if validator_cls is None:
        print(
            "router: jsonschema too old for Draft 2020-12 — frozen mirror verdict stands",
            file=sys.stderr,
        )
        return
    errors = sorted(validator_cls(schema).iter_errors(table), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "<root>"
        raise TableError(f"authoritative validation failed: {first.message}", field=where)


def _require(cond: bool, msg: str, field: str) -> None:
    if not cond:
        raise TableError(msg, field=field)


def validate_table(table: Any, path: str = "<table>") -> None:
    """Frozen mirror of task-router.schema.json $defs — fail-closed."""
    _require(isinstance(table, dict), "table must be a JSON object", path)
    _require(table.get("schema_version") == "1.0", "schema_version must be '1.0'", "schema_version")
    _require(
        isinstance(table.get("router_id"), str) and table["router_id"].strip(),
        "router_id must be a non-empty string",
        "router_id",
    )

    tiers = table.get("complexity_tiers")
    _require(isinstance(tiers, list) and len(tiers) == 3, "complexity_tiers must hold exactly 3 tiers", "complexity_tiers")
    seen: set[int] = set()
    for t in tiers:
        _require(isinstance(t, dict), "each complexity tier must be an object", "complexity_tiers")
        num, name = t.get("tier"), t.get("name")
        _require(num in (1, 2, 3), f"tier ordinal must be 1..3, got {num!r}", "complexity_tiers.tier")
        _require(num not in seen, f"duplicate tier ordinal {num}", "complexity_tiers.tier")
        seen.add(num)
        _require(name == TIER_NAMES[num - 1], f"tier {num} name must be '{TIER_NAMES[num - 1]}' (pinned)", "complexity_tiers.name")
        _require(isinstance(t.get("description"), str) and t["description"].strip(), "tier description required", "complexity_tiers.description")
        sigs = t.get("example_signals")
        _require(
            isinstance(sigs, list) and len(sigs) >= 1 and len(set(sigs)) == len(sigs)
            and all(isinstance(s, str) and s.strip() for s in sigs),
            f"tier {num} example_signals must be unique non-empty strings",
            "complexity_tiers.example_signals",
        )

    rt = table.get("routing_table")
    _require(isinstance(rt, list) and rt, "routing_table must be a non-empty list", "routing_table")
    for mapping in rt:
        _validate_mapping(mapping)

    br = table.get("budget_rules")
    _require(isinstance(br, dict), "budget_rules must be an object", "budget_rules")
    for key, minimum, kind in (
        ("per_task_max_input_tokens", 1024, int),
        ("per_task_max_output_tokens", 256, int),
    ):
        val = br.get(key)
        _require(isinstance(val, int) and not isinstance(val, bool) and val >= minimum, f"{key} must be an integer >= {minimum}", f"budget_rules.{key}")
    for key in ("max_cost_per_task_usd", "budget_floor_usd"):
        val = br.get(key)
        _require(isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0, f"{key} must be a positive number", f"budget_rules.{key}")
    rules = br.get("rules")
    _require(isinstance(rules, list) and rules, "budget_rules.rules must be a non-empty list", "budget_rules.rules")
    for i, rule in enumerate(rules):
        _require(isinstance(rule, dict), f"rule {i} must be an object", f"budget_rules.rules[{i}]")
        when, then = rule.get("when"), rule.get("then")
        _require(when in RULE_WHEN, f"rule {i} 'when' must be one of {RULE_WHEN}, got {when!r}", f"budget_rules.rules[{i}].when")
        _require(then == WHEN_THEN[when], f"rule {i} then='{then}' mismatches schema pin when='{when}' -> then='{WHEN_THEN[when]}'", f"budget_rules.rules[{i}].then")

    defaults = table.get("defaults")
    _require(isinstance(defaults, dict), "defaults must be an object", "defaults")
    _require(defaults.get("unclassifiable_task") == "reject", "defaults.unclassifiable_task must be 'reject' (const)", "defaults.unclassifiable_task")
    _require(defaults.get("unknown_provider") == "reject", "defaults.unknown_provider must be 'reject' (const)", "defaults.unknown_provider")


def _validate_mapping(mapping: Any) -> None:
    _require(isinstance(mapping, dict), "route mapping must be an object", "routing_table")
    tier = mapping.get("tier")
    _require(tier in (1, 2, 3), f"mapping tier must be 1..3, got {tier!r}", "routing_table.tier")
    _validate_endpoint(mapping.get("primary"), f"routing_table[{tier}].primary")
    cascade = mapping.get("fallback_cascade")
    _require(isinstance(cascade, list) and len(cascade) >= 1, f"tier {tier} fallback_cascade needs >= 1 entry (minItems)", f"routing_table[{tier}].fallback_cascade")
    signatures = [json.dumps(e, sort_keys=True) for e in cascade]
    _require(len(set(signatures)) == len(signatures), f"tier {tier} fallback_cascade entries must be unique (uniqueItems)", f"routing_table[{tier}].fallback_cascade")
    for i, endpoint in enumerate(cascade):
        _validate_endpoint(endpoint, f"routing_table[{tier}].fallback_cascade[{i}]")
    # Load-time teeth: defaults.unknown_provider=reject
    for i, endpoint in enumerate([mapping["primary"], *cascade]):
        if endpoint["provider"] not in VALID_PROVIDERS:
            raise TableError(
                f"unknown provider '{endpoint['provider']}' — defaults.unknown_provider=reject",
                field=f"routing_table[{tier}].cascade[{i}].provider",
            )


def _validate_endpoint(endpoint: Any, field: str) -> None:
    _require(isinstance(endpoint, dict), f"{field} must be an object", field)
    provider, model = endpoint.get("provider"), endpoint.get("model")
    _require(provider in VALID_PROVIDERS, f"{field}.provider must be one of {VALID_PROVIDERS}, got {provider!r}", f"{field}.provider")
    _require(isinstance(model, str) and model.strip(), f"{field}.model must be a non-empty string", f"{field}.model")
    ctx = endpoint.get("max_context_tokens")
    if ctx is not None:
        _require(isinstance(ctx, int) and not isinstance(ctx, bool) and ctx > 0, f"{field}.max_context_tokens must be a positive integer", f"{field}.max_context_tokens")
    cost = endpoint.get("cost_per_1k_tokens_usd")
    if cost is not None:
        _require(isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost > 0, f"{field}.cost_per_1k_tokens_usd must be a positive number", f"{field}.cost_per_1k_tokens_usd")


# ---------------------------------------------------------------------------
# Tier classification (deterministic; unclassifiable → reject)
# ---------------------------------------------------------------------------


def classify_task(signals: dict[str, Any]) -> dict[str, Any]:
    """Classify a task onto the 3-tier ladder from deterministic signals.

    Signals (all optional, evaluated in a fixed order):
      - complexity_tier: explicit 1/2/3 pin wins (human or planner override)
      - estimated_input_tokens: fixture thresholds 4000 / 60000
      - task_tag: "P0-critical" or "P1-high" forces at least tier 3
      - files_touched: > 3 files signals multi-subsystem work (tier >= 2)
      - requires_tool_calling / multi_step_reasoning: tier >= 2
    No signal matches → RoutingError (defaults.unclassifiable_task=reject).
    """
    if not isinstance(signals, dict):
        raise RoutingError("task signals must be a dict", field="signals")
    decision_path: list[str] = []

    explicit = signals.get("complexity_tier")
    if explicit is not None:
        if explicit not in (1, 2, 3):
            raise RoutingError(
                f"explicit complexity_tier must be 1/2/3, got {explicit!r}",
                field="signals.complexity_tier",
            )
        decision_path.append(f"explicit pin -> tier {explicit}")
        return _tier_decision(int(explicit), decision_path)

    tokens = signals.get("estimated_input_tokens")
    tier: int | None = None
    if isinstance(tokens, int) and not isinstance(tokens, bool):
        if tokens < TOKEN_THRESHOLD_TIER2:
            tier = 1
            decision_path.append(f"estimated_input_tokens={tokens} < {TOKEN_THRESHOLD_TIER2} -> tier 1")
        elif tokens > TOKEN_THRESHOLD_TIER3:
            tier = 3
            decision_path.append(f"estimated_input_tokens={tokens} > {TOKEN_THRESHOLD_TIER3} -> tier 3")
        else:
            tier = 2
            decision_path.append(f"estimated_input_tokens={tokens} in [{TOKEN_THRESHOLD_TIER2}, {TOKEN_THRESHOLD_TIER3}] -> tier 2")
    else:
        decision_path.append("no estimated_input_tokens signal")

    tag = signals.get("task_tag")
    if isinstance(tag, str) and tag.strip().lower() in ("p0-critical", "p1-high"):
        tier = max(tier or 1, 3)
        decision_path.append(f"task_tag={tag!r} forces tier >= 3")
    files = signals.get("files_touched")
    if isinstance(files, int) and not isinstance(files, bool) and files > 3:
        tier = max(tier or 1, 2)
        decision_path.append(f"files_touched={files} > 3 -> tier >= 2")
    for flag in ("requires_tool_calling", "multi_step_reasoning"):
        if signals.get(flag) is True:
            tier = max(tier or 1, 2)
            decision_path.append(f"{flag}=true -> tier >= 2")

    if tier is None:
        raise RoutingError(
            "task matched no complexity signal — unclassifiable_task=reject "
            "(fail-closed; supply estimated_input_tokens, files_touched, "
            "task_tag, or an explicit complexity_tier)",
            field="signals",
        )
    return _tier_decision(tier, decision_path)


def _tier_decision(tier: int, decision_path: list[str]) -> dict[str, Any]:
    return {
        "tier": tier,
        "tier_name": TIER_NAMES[tier - 1],
        "decision_path": decision_path,
    }


# ---------------------------------------------------------------------------
# Health-driven chain reorder (no schema change) + cost + budget rules
# ---------------------------------------------------------------------------


def _mapping_for(table: dict[str, Any], tier: int) -> dict[str, Any]:
    for mapping in table["routing_table"]:
        if mapping["tier"] == tier:
            return mapping
    raise RoutingError(f"no route mapping for tier {tier}", field="routing_table")


def validate_health(health: dict[str, Any]) -> None:
    """Health grades: provider -> {'grade': healthy|degraded|unavailable}."""
    if not isinstance(health, dict):
        raise RoutingError("health must be a dict of provider -> grade info", field="health")
    for provider, info in health.items():
        if provider not in VALID_PROVIDERS:
            raise RoutingError(
                f"unknown provider '{provider}' in health input — unknown_provider=reject",
                field=f"health.{provider}",
            )
        grade = info.get("grade") if isinstance(info, dict) else info
        if grade not in GRADES:
            raise RoutingError(
                f"grade for '{provider}' must be one of {GRADES}, got {grade!r}",
                field=f"health.{provider}.grade",
            )


def build_chain(table: dict[str, Any], tier: int, health: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ordered model chain for a tier; health grades reorder deterministically.

    Reorder is stable: (grade_rank, declared_index) — equal grades keep the
    declared order, so "first entry is tried first" survives whenever health
    is silent or equal. The input table is never mutated (copy).
    """
    validate_health(health or {})
    mapping = _mapping_for(table, tier)
    declared: list[dict[str, Any]] = [copy.deepcopy(mapping["primary"]), *(copy.deepcopy(e) for e in mapping["fallback_cascade"])]
    for i, endpoint in enumerate(declared):
        endpoint["_declared_index"] = i
    if health:
        for endpoint in declared:
            info = health.get(endpoint["provider"]) or {}
            grade = info.get("grade") if isinstance(info, dict) else info
            endpoint["_grade"] = grade if grade in GRADES else "healthy"
            endpoint["_grade_source"] = "health-input" if grade in GRADES else "default-healthy"
    else:
        for endpoint in declared:
            endpoint["_grade"] = "healthy"
            endpoint["_grade_source"] = "no-health-input"
    ordered = sorted(declared, key=lambda e: (GRADE_RANK[e["_grade"]], e["_declared_index"]))
    chain = [{k: v for k, v in e.items() if not k.startswith("_")} for e in ordered]
    reorder_note = [
        {
            "provider": e["provider"],
            "model": e["model"],
            "grade": e["_grade"],
            "grade_source": e["_grade_source"],
            "declared_index": e["_declared_index"],
        }
        for e in ordered
    ]
    return {"tier": tier, "tier_name": TIER_NAMES[tier - 1], "chain": chain, "reorder": reorder_note}


def estimate_cost_usd(endpoint: dict[str, Any], input_tokens: int, output_tokens: int) -> float | None:
    """Cost from ModelEndpoint.cost_per_1k_tokens_usd; None when unpriced (honest)."""
    cost = endpoint.get("cost_per_1k_tokens_usd")
    if cost is None:
        return None
    return (max(0, input_tokens) + max(0, output_tokens)) / 1000.0 * float(cost)


def evaluate_budget(
    table: dict[str, Any],
    *,
    tier: int,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
    budget_remaining_usd: float | None = None,
    primary_latency_ms: float | None = None,
) -> dict[str, Any]:
    """Evaluate budget_rules deterministically in listed order; first match fires."""
    br = table["budget_rules"]
    primary = _mapping_for(table, tier)["primary"]
    decision_path: list[str] = []
    for i, rule in enumerate(br["rules"]):
        when = rule["when"]
        if when == "context_exceeds_primary":
            ctx = primary.get("max_context_tokens")
            if ctx is not None and estimated_input_tokens > ctx:
                decision_path.append(
                    f"rule[{i}] when=context_exceeds_primary ({estimated_input_tokens} > {ctx}) -> fallback_cascade"
                )
                return _budget_decision("fallback_cascade", i, decision_path)
            decision_path.append(f"rule[{i}] context_exceeds_primary not triggered (primary context {ctx})")
        elif when == "estimated_cost_above_cap":
            est = estimate_cost_usd(primary, estimated_input_tokens, estimated_output_tokens)
            if est is None:
                decision_path.append(f"rule[{i}] estimated_cost_above_cap cannot fire — primary unpriced (honest skip)")
            elif est > float(br["max_cost_per_task_usd"]):
                decision_path.append(
                    f"rule[{i}] when=estimated_cost_above_cap ({est:.6f} > {br['max_cost_per_task_usd']}) -> downgrade_tier"
                )
                return _budget_decision("downgrade_tier", i, decision_path)
            else:
                decision_path.append(f"rule[{i}] estimated_cost_above_cap not triggered (estimate {est:.6f})")
        elif when == "budget_remaining_below_floor":
            if budget_remaining_usd is not None and budget_remaining_usd < float(br["budget_floor_usd"]):
                decision_path.append(
                    f"rule[{i}] when=budget_remaining_below_floor ({budget_remaining_usd} < {br['budget_floor_usd']}) -> cap_output_tokens"
                )
                return _budget_decision("cap_output_tokens", i, decision_path)
            decision_path.append(
                f"rule[{i}] budget_remaining_below_floor not triggered"
                + (f" (remaining {budget_remaining_usd})" if budget_remaining_usd is not None else " — no budget_remaining input (honest skip)")
            )
        elif when == "latency_sla_missed":
            if primary_latency_ms is not None:
                sla = telemetry_sla_ms(table)
                if sla is not None and primary_latency_ms > sla:
                    decision_path.append(
                        f"rule[{i}] when=latency_sla_missed ({primary_latency_ms}ms > {sla}ms) -> queue_and_retry"
                    )
                    return _budget_decision("queue_and_retry", i, decision_path)
                decision_path.append(
                    f"rule[{i}] latency_sla_missed not triggered"
                    + (f" (latency {primary_latency_ms}ms <= sla {sla}ms)" if sla is not None else " — no SLA defined (honest skip)")
                )
            else:
                decision_path.append(f"rule[{i}] latency_sla_missed not triggered — no latency input (honest skip)")
    decision_path.append("no budget rule fired -> use_primary")
    return _budget_decision("use_primary", None, decision_path)


def telemetry_sla_ms(table: dict[str, Any]) -> int | None:
    """Optional SLA knob: table may carry budget_rules.latency_sla_ms (honest None)."""
    val = table["budget_rules"].get("latency_sla_ms")
    if isinstance(val, int) and not isinstance(val, bool) and val > 0:
        return val
    return None


def _budget_decision(action: str, fired: int | None, decision_path: list[str]) -> dict[str, Any]:
    return {"action": action, "fired_rule_index": fired, "decision_path": decision_path}


# ---------------------------------------------------------------------------
# Orchestration + fail-honest chain runner
# ---------------------------------------------------------------------------


def route(
    table: dict[str, Any],
    signals: dict[str, Any],
    *,
    health: dict[str, Any] | None = None,
    budget_remaining_usd: float | None = None,
    primary_latency_ms: float | None = None,
) -> dict[str, Any]:
    """One deterministic routing decision with a full honest audit trail."""
    classification = classify_task(signals)
    tier = classification["tier"]
    tokens = signals.get("estimated_input_tokens") if isinstance(signals.get("estimated_input_tokens"), int) else 0
    out_tokens = signals.get("estimated_output_tokens") if isinstance(signals.get("estimated_output_tokens"), int) else 0
    budget = evaluate_budget(
        table,
        tier=tier,
        estimated_input_tokens=tokens,
        estimated_output_tokens=out_tokens,
        budget_remaining_usd=budget_remaining_usd,
        primary_latency_ms=primary_latency_ms,
    )
    action = budget["action"]
    effective_tier = tier
    if action == "downgrade_tier" and tier > 1:
        effective_tier = tier - 1
        budget["decision_path"].append(f"downgrade_tier: {tier} -> {effective_tier}")
    chain = build_chain(table, effective_tier, health)
    primary_endpoint = chain["chain"][0]
    cost = estimate_cost_usd(primary_endpoint, tokens, out_tokens)
    decision = {
        "router_contract": ROUTER_CONTRACT_VERSION,
        "tier": effective_tier,
        "tier_name": chain["tier_name"],
        "requested_tier": tier,
        "action": action,
        "fired_rule_index": budget["fired_rule_index"],
        "chain": chain["chain"],
        "reorder": chain["reorder"],
        "cost_estimate_usd": cost,
        "output_token_cap": (
            table["budget_rules"]["per_task_max_output_tokens"] if action == "cap_output_tokens" else None
        ),
        "decision_path": classification["decision_path"] + budget["decision_path"],
    }
    if action == "queue_and_retry":
        decision["queued"] = True
    return decision


def run_chain(
    chain: list[dict[str, Any]],
    attempt: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Walk the ordered chain; every fallback transition is recorded (never silent).

    ``attempt(endpoint)`` returns True on success. If every endpoint fails,
    RoutingError carries the complete attempt ledger — fail-honest, never None.
    """
    if not chain:
        raise RoutingError("empty chain — nothing to run", field="chain")
    attempts: list[dict[str, Any]] = []
    for i, endpoint in enumerate(chain):
        transition = "primary" if i == 0 else "fallback_cascade"
        try:
            ok = bool(attempt(endpoint))
        except Exception as exc:  # noqa: BLE001 — attempt failures are evidence too
            ok = False
            attempts.append(
                {
                    "index": i,
                    "transition": transition,
                    "provider": endpoint.get("provider"),
                    "model": endpoint.get("model"),
                    "outcome": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        attempts.append(
            {
                "index": i,
                "transition": transition,
                "provider": endpoint.get("provider"),
                "model": endpoint.get("model"),
                "outcome": "success" if ok else "failed",
            }
        )
        if ok:
            return {"served_by": endpoint, "attempts": attempts, "fallbacks_used": i}
    ledger = "; ".join(
        f"[{a['index']}]{a['provider']}/{a['model']}({a['transition']})->{a['outcome']}" for a in attempts
    )
    raise RoutingError(f"model chain exhausted — every endpoint failed (fail-honest): {ledger}", field="chain")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dynamic task routing engine (issue #330) — consumes the "
        "declarative task-router table; never mutates it."
    )
    parser.add_argument("--table", default=DEFAULT_TABLE_PATH, help="routing table JSON (default: repo fixture)")
    parser.add_argument("--schema", default=None, help="optional authoritative jsonschema validation path")
    parser.add_argument(
        "--route",
        default=None,
        help="JSON object of task signals to route (offline demo; '-' reads stdin)",
    )
    parser.add_argument(
        "--health",
        default=None,
        help="JSON object of provider health grades to apply during --route",
    )
    parser.add_argument("--self-test", action="store_true", help="run the offline hermetic self-test and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        checks = self_test()
        print(f"SELF-TEST OK: {checks} checks passed")
        return 0
    try:
        table = load_routing_table(args.table, schema_path=args.schema)
    except TableError as exc:
        print(f"TABLE ERROR: {exc}", file=sys.stderr)
        return 2
    if args.route is None:
        parser.print_help()
        return 0
    try:
        raw = sys.stdin.read() if args.route == "-" else args.route
        signals = json.loads(raw)
        health = json.loads(args.health) if args.health else None
        decision = route(table, signals, health=health)
    except (json.JSONDecodeError, RoutingError) as exc:
        print(f"ROUTE ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# Self-test (hermetic + real-fixture acceptance)
# ---------------------------------------------------------------------------


def self_test() -> int:
    """Offline self-test. Returns the number of checks performed (≥20)."""
    import tempfile

    checks = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise AssertionError(f"self-test check {checks} failed: {msg}")

    # 1. constants in lockstep with schema pins
    ok(len(VALID_PROVIDERS) == 7, "7 providers (ModelEndpoint enum)")
    ok(GRADES == ("healthy", "degraded", "unavailable"), "3 health grades")
    ok(set(WHEN_THEN) == set(RULE_WHEN), "4 rule triggers pinned")
    ok(
        WHEN_THEN == {
            "context_exceeds_primary": "fallback_cascade",
            "estimated_cost_above_cap": "downgrade_tier",
            "budget_remaining_below_floor": "cap_output_tokens",
            "latency_sla_missed": "queue_and_retry",
        },
        "when->then pairs match schema descriptions",
    )
    ok(TIER_NAMES == ("fast_light", "coding_reasoning", "complex_architecture"), "tier names pinned")

    # 2. real fixture loads + validates (issue acceptance: pass the fixtures)
    table = load_routing_table(DEFAULT_TABLE_PATH)
    ok(table["router_id"] == "federation-task-router", "fixture router_id")
    ok(len(table["routing_table"]) == 3, "3 route mappings in fixture")

    # 3-6. fail-closed table rejections
    def broken(mutate):
        bad = json.loads(json.dumps(table))
        mutate(bad)
        return bad

    for mutate, label in (
        (lambda t: t.update(schema_version="2.0"), "bad schema_version"),
        (lambda t: t["routing_table"][0].update(tier=9), "bad mapping tier"),
        (lambda t: t["routing_table"][0]["fallback_cascade"].clear(), "empty cascade"),
        (lambda t: t["defaults"].update(unknown_provider="fallback"), "defaults const violated"),
        (lambda t: t["budget_rules"].update(rules=[{"when": "made_up", "then": "fallback_cascade"}]), "unknown rule trigger"),
        (lambda t: t["routing_table"][0]["primary"].update(provider="skynet"), "unknown provider rejected at load"),
    ):
        try:
            validate_table(broken(mutate))
            ok(False, f"table rejection: {label}")
        except TableError:
            ok(True, f"table rejection: {label}")

    # 7-9. classification
    ok(classify_task({"estimated_input_tokens": 500})["tier"] == 1, "500 tokens -> tier 1")
    ok(classify_task({"estimated_input_tokens": 20000})["tier"] == 2, "20k tokens -> tier 2")
    ok(classify_task({"estimated_input_tokens": 90000})["tier"] == 3, "90k tokens -> tier 3")
    ok(classify_task({"complexity_tier": 3})["tier"] == 3, "explicit pin wins")
    ok(classify_task({"task_tag": "P1-high", "estimated_input_tokens": 100})["tier"] == 3, "P1-high forces tier 3")
    ok(classify_task({"files_touched": 7})["tier"] == 2, "many files -> tier 2")
    for silent in ({}, {"estimated_input_tokens": "many"}, {"task_tag": "P3"}):
        try:
            classify_task(silent)
            ok(False, "unclassifiable rejected")
        except RoutingError:
            ok(True, "unclassifiable rejected (fail-closed)")

    # 10-12. health-driven reorder WITHOUT schema change (table never mutated)
    snapshot = json.dumps(table, sort_keys=True)
    tier2 = {m["tier"]: m for m in table["routing_table"]}[2]
    ok(tier2["primary"]["provider"] == "anthropic", "tier 2 primary declared anthropic")
    health = {
        "anthropic": {"grade": "unavailable"},
        "deepseek": {"grade": "healthy"},
        "openai": {"grade": "healthy"},
    }
    chain = build_chain(table, 2, health)
    ok(chain["chain"][0]["provider"] == "openai", "healthy openai promoted ahead of declared order (stable: declared index)")
    ok(chain["chain"][-1]["provider"] == "anthropic", "unavailable anthropic demoted to tail")
    ok([e["provider"] for e in chain["chain"]].count("openai") == 1, "no duplicates introduced")
    ok(json.dumps(table, sort_keys=True) == snapshot, "input table untouched by reorder (no schema change)")

    # 13. equal grades keep declared order ("first entry is tried first")
    chain_equal = build_chain(table, 2, {p: {"grade": "healthy"} for p in VALID_PROVIDERS})
    ok(
        [e["provider"] for e in chain_equal["chain"]][0] == "anthropic",
        "equal grades preserve declared order",
    )

    # 14-16. budget rules fire in listed order
    b1 = evaluate_budget(table, tier=3, estimated_input_tokens=500_000, estimated_output_tokens=1000)
    ok(b1["action"] == "fallback_cascade" and b1["fired_rule_index"] == 0, "context rule fires first (500k > 200k)")
    b2 = evaluate_budget(table, tier=3, estimated_input_tokens=1000, estimated_output_tokens=200_000)
    ok(b2["action"] == "downgrade_tier", "cost cap rule fires (opus 0.045 * 201k > $2.5)")
    b3 = evaluate_budget(table, tier=1, estimated_input_tokens=100, estimated_output_tokens=100, budget_remaining_usd=0.05)
    ok(b3["action"] == "cap_output_tokens" and b3["fired_rule_index"] == 2, "budget floor rule fires")
    table_sla = json.loads(json.dumps(table))
    table_sla["budget_rules"]["latency_sla_ms"] = 1200
    b4 = evaluate_budget(table_sla, tier=1, estimated_input_tokens=100, estimated_output_tokens=100, primary_latency_ms=5000.0)
    ok(b4["action"] == "queue_and_retry", "SLA rule fires with telemetry")
    b5 = evaluate_budget(table, tier=1, estimated_input_tokens=100, estimated_output_tokens=100)
    ok(b5["action"] == "use_primary", "no rule fired -> honest use_primary")

    # 17. end-to-end route with full audit trail
    decision = route(
        table,
        {"estimated_input_tokens": 500_000, "estimated_output_tokens": 8000},
        health={"anthropic": {"grade": "degraded"}},
    )
    ok(decision["tier"] == 3 and decision["chain"], "route returns tier 3 chain")
    ok(decision["decision_path"] and any("context_exceeds_primary" in p for p in decision["decision_path"]), "audit trail records rule fire")
    ok(decision["reorder"][0]["grade"] in GRADES, "reorder ledger carries grades")

    # 18. fail-honest exhaustion
    try:
        run_chain(decision["chain"], lambda ep: False)
        ok(False, "chain exhaustion raises")
    except RoutingError as exc:
        ok("fail-honest" in str(exc) and "anthropic" in str(exc), "exhaustion ledger names endpoints")
    served = run_chain(decision["chain"], lambda ep: ep is not decision["chain"][0])
    ok(
        served["served_by"] is decision["chain"][1] and served["fallbacks_used"] == 1,
        "fallback transition recorded (first endpoint failed, second served)",
    )

    # 19. cost honesty: unpriced endpoint -> None (never a silent zero)
    ok(estimate_cost_usd({"provider": "groq", "model": "m"}, 100, 100) is None, "unpriced endpoint -> None")

    # 20. unknown provider in health input rejected
    try:
        build_chain(table, 1, {"skynet": {"grade": "healthy"}})
        ok(False, "unknown health provider rejected")
    except RoutingError:
        ok(True, "unknown health provider rejected")

    with tempfile.TemporaryDirectory() as td:
        # 21. invalid table file on disk -> TableError
        bad_path = Path(td) / "bad.json"
        bad_path.write_text('{"schema_version": "9.9"}', encoding="utf-8")
        try:
            load_routing_table(bad_path)
            ok(False, "bad file rejected")
        except TableError:
            ok(True, "bad table file rejected (fail-closed)")

    return checks


if __name__ == "__main__":
    sys.exit(main())
