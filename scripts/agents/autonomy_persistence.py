"""Autonomy-Layer persistence reference: router_patterns + task_permissions.

Zero-dependency reference implementation of Phase 2 Workstream 2 (issue #328,
backing private-monorepo #106): the durable models that back model-routing
decisions (``router_patterns``) and least-privilege task scoping
(``task_permissions``), proving conformance against the landed Layer 1
contracts:

- ``api-schemas/task-router.schema.json``  (RouteMapping / ModelEndpoint /
  ComplexityTier; routing_table pins exactly one route per tier 1..3)
- ``api-schemas/permissions.schema.json``  (PermissionScope: kebab-case
  scope ids, resource path families, closed action vocabulary, min role
  tier, MFA barrier)

Design invariants
-----------------
1. **Fail-closed wholesale loads.`` Documents are validated in full BEFORE
   any row is written; a rejected load leaves the previous state byte-ident
   ical (single transaction, rolled back on the first invalid record).
2. **Hand-rolled validators mirror the SSOT enums/patterns exactly**, and
   the test battery syncs those constants against the schema files them
   selves, so a schema change fails CI until this module catches up.
3. **Zero dependencies**: stdlib ``sqlite3`` only. Reads are snapshotable;
   writes are deterministic under an injected clock.
4. **Honest scope**: budget rules, provider health and defaults are ROUTER
   RUNTIME concerns (see the dynamic router reference) and intentionally
   out of persistence scope here; only routing decisions and permission
   scopes are durable.

CLI: run ``python scripts/agents/autonomy_persistence.py`` with no arguments
for the embedded offline self-test (temp database, full roundtrip).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# Contract pins (synced against api-schemas/*.json by the test battery)
# ---------------------------------------------------------------------------

ROUTER_CONTRACT = "api-schemas/task-router.schema.json"
PERMISSIONS_CONTRACT = "api-schemas/permissions.schema.json"

PROVIDERS = frozenset({
    "openai", "anthropic", "gemini", "groq", "openrouter", "mistral", "deepseek",
})
ACTIONS = frozenset({
    "read", "execute", "write", "approve", "deploy", "rotate_secrets", "override",
})

SCOPE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
RESOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}(/\*|/[a-z0-9-]+)?$")
MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,99}$")

MIN_CONTEXT_TOKENS = 1024
MIN_ROLE_TIER, MAX_ROLE_TIER = 1, 4
MIN_ROUTE_TIER, MAX_ROUTE_TIER = 1, 3

MAX_TEXT_FIELD = 512
MAX_CASCADE = 16
MAX_SCOPES = 256

# ---------------------------------------------------------------------------
# Error taxonomy — fail-closed, honest
# ---------------------------------------------------------------------------


class PersistenceError(Exception):
    code = "PERSISTENCE_ERROR"
    retryable = False

    def __init__(self, detail: str, *, retryable: Optional[bool] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if retryable is not None:
            self.retryable = retryable


class StoreUnavailableError(PersistenceError):
    """The store cannot be opened or the schema cannot be bootstrapped."""

    code = "STORE_UNAVAILABLE"
    retryable = True


class ReadOnlyError(PersistenceError):
    """A write was attempted on a read-only store."""

    code = "READ_ONLY"


class NotFoundError(PersistenceError):
    """No row for the requested key."""

    code = "NOT_FOUND"


class ValidationError(PersistenceError):
    """A record or document failed its contract check (nothing was written)."""

    code = "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Records (frozen, JSON-safe)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelEndpoint:
    provider: str
    model: str
    max_context_tokens: Optional[int] = None
    cost_per_1k_tokens_usd: Optional[float] = None

    def to_json(self) -> str:
        payload: Dict[str, Any] = {"provider": self.provider, "model": self.model}
        if self.max_context_tokens is not None:
            payload["max_context_tokens"] = self.max_context_tokens
        if self.cost_per_1k_tokens_usd is not None:
            payload["cost_per_1k_tokens_usd"] = self.cost_per_1k_tokens_usd
        return json.dumps(payload, sort_keys=True)

    @classmethod
    def from_json(cls, raw: Any) -> "ModelEndpoint":
        payload = json.loads(raw) if isinstance(raw, str) else raw
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class RouterPatternRow:
    """One durable routing decision: the route for one complexity tier."""

    tier: int
    tier_name: str
    tier_description: str
    primary: ModelEndpoint
    fallback_cascade: tuple  # tuple[ModelEndpoint, ...] (ordered)
    updated_at: float


@dataclass(frozen=True, slots=True)
class TaskPermissionRow:
    """One durable least-privilege scope grant."""

    scope_id: str
    resource: str
    actions: tuple  # tuple[str, ...] (closed vocabulary, insertion order kept)
    min_role_tier: int
    requires_mfa: bool
    updated_at: float


# ---------------------------------------------------------------------------
# Validators — mirror the SSOT contracts exactly (fail-closed, poka-yoke)
# ---------------------------------------------------------------------------


def _check_text(value: Any, name: str, *, pattern: Optional[re.Pattern] = None,
                max_len: int = MAX_TEXT_FIELD) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string, got {type(value).__name__}")
    if not value:
        raise ValidationError(f"{name} must be non-empty")
    if len(value) > max_len:
        raise ValidationError(f"{name} exceeds {max_len} characters")
    if pattern is not None and not pattern.match(value):
        raise ValidationError(f"{name} violates its contract pattern: {value!r}")
    return value


def validate_model_endpoint(raw: Any, *, where: str) -> ModelEndpoint:
    if not isinstance(raw, Mapping):
        raise ValidationError(f"{where}: endpoint must be an object")
    unknown = set(raw) - {"provider", "model", "max_context_tokens", "cost_per_1k_tokens_usd"}
    if unknown:
        raise ValidationError(f"{where}: unknown endpoint keys {sorted(unknown)}")
    provider = _check_text(raw.get("provider"), f"{where}.provider")
    if provider not in PROVIDERS:
        raise ValidationError(f"{where}.provider {provider!r} is not a registered provider")
    model = _check_text(raw.get("model"), f"{where}.model", pattern=MODEL_PATTERN)
    max_ctx = raw.get("max_context_tokens")
    if max_ctx is not None:
        if isinstance(max_ctx, bool) or not isinstance(max_ctx, int) or max_ctx < MIN_CONTEXT_TOKENS:
            raise ValidationError(f"{where}.max_context_tokens must be an integer >= {MIN_CONTEXT_TOKENS}")
    cost = raw.get("cost_per_1k_tokens_usd")
    if cost is not None:
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ValidationError(f"{where}.cost_per_1k_tokens_usd must be a number >= 0")
    return ModelEndpoint(
        provider=provider, model=model,
        max_context_tokens=max_ctx, cost_per_1k_tokens_usd=cost,
    )


def validate_fallback_cascade(raw: Any, *, where: str) -> tuple:
    if not isinstance(raw, list):
        raise ValidationError(f"{where}: fallback_cascade must be an array")
    if not (1 <= len(raw) <= MAX_CASCADE):
        raise ValidationError(f"{where}: fallback_cascade must hold 1..{MAX_CASCADE} endpoints")
    endpoints = tuple(
        validate_model_endpoint(item, where=f"{where}[{i}]") for i, item in enumerate(raw)
    )
    labels = [e.to_json() for e in endpoints]
    if len(set(labels)) != len(labels):
        raise ValidationError(f"{where}: fallback_cascade entries must be unique")
    return endpoints


def validate_route_mapping(raw: Any, *, where: str) -> tuple:
    """Validate one RouteMapping; returns (tier, primary, cascade)."""
    if not isinstance(raw, Mapping):
        raise ValidationError(f"{where}: route mapping must be an object")
    unknown = set(raw) - {"tier", "primary", "fallback_cascade"}
    if unknown:
        raise ValidationError(f"{where}: unknown route keys {sorted(unknown)}")
    tier = raw.get("tier")
    if isinstance(tier, bool) or not isinstance(tier, int) or not (MIN_ROUTE_TIER <= tier <= MAX_ROUTE_TIER):
        raise ValidationError(f"{where}.tier must be an integer in [{MIN_ROUTE_TIER}, {MAX_ROUTE_TIER}]")
    if "primary" not in raw:
        raise ValidationError(f"{where}: primary endpoint is required")
    primary = validate_model_endpoint(raw["primary"], where=f"{where}.primary")
    cascade = validate_fallback_cascade(raw.get("fallback_cascade"), where=where)
    return tier, primary, cascade


def validate_permission_scope(raw: Any, *, where: str) -> TaskPermissionRowFields:
    """Validate one PermissionScope; returns the plain field tuple."""
    if not isinstance(raw, Mapping):
        raise ValidationError(f"{where}: permission scope must be an object")
    unknown = set(raw) - {"scope_id", "resource", "actions", "min_role_tier", "requires_mfa"}
    if unknown:
        raise ValidationError(f"{where}: unknown scope keys {sorted(unknown)}")
    scope_id = _check_text(raw.get("scope_id"), f"{where}.scope_id", pattern=SCOPE_ID_PATTERN)
    resource = _check_text(raw.get("resource"), f"{where}.resource", pattern=RESOURCE_PATTERN)
    actions = raw.get("actions")
    if not isinstance(actions, list) or not (1 <= len(actions) <= len(ACTIONS)):
        raise ValidationError(f"{where}.actions must be a non-empty array")
    for i, action in enumerate(actions):
        if action not in ACTIONS:
            raise ValidationError(f"{where}.actions[{i}] {action!r} is outside the closed vocabulary")
    if len(set(actions)) != len(actions):
        raise ValidationError(f"{where}.actions entries must be unique")
    min_tier = raw.get("min_role_tier")
    if isinstance(min_tier, bool) or not isinstance(min_tier, int) or not (MIN_ROLE_TIER <= min_tier <= MAX_ROLE_TIER):
        raise ValidationError(f"{where}.min_role_tier must be an integer in [{MIN_ROLE_TIER}, {MAX_ROLE_TIER}]")
    requires_mfa = raw.get("requires_mfa")
    if not isinstance(requires_mfa, bool):
        raise ValidationError(f"{where}.requires_mfa must be a boolean")
    return scope_id, resource, tuple(actions), min_tier, requires_mfa


# alias for readability of validate_permission_scope's return contract
TaskPermissionRowFields = tuple


def validate_router_document(doc: Mapping[str, Any]) -> Dict[int, tuple]:
    """Validate a full router document; returns {tier: (name, desc, primary, cascade)}.

    Enforces the routing_table pin: exactly one route per tier 1..3, and a
    matching ComplexityTier declaration for each routed tier.
    """
    if not isinstance(doc, Mapping):
        raise ValidationError("router document must be an object")
    unknown = set(doc) - {"schema_version", "router_id", "complexity_tiers",
                          "routing_table", "budget_rules", "defaults"}
    if unknown:
        raise ValidationError(f"router document: unknown top-level keys {sorted(unknown)}")
    _check_text(doc.get("schema_version"), "schema_version", max_len=16)
    if not re.match(r"^\d+\.\d+$", str(doc.get("schema_version"))):
        raise ValidationError("schema_version must be semantic 'major.minor' (e.g. 1.0)")
    _check_text(doc.get("router_id"), "router_id")
    tiers_raw = doc.get("complexity_tiers")
    if not isinstance(tiers_raw, list) or len(tiers_raw) != 3:
        raise ValidationError("complexity_tiers must hold exactly three tier declarations")
    tier_meta: Dict[int, tuple] = {}
    for i, item in enumerate(tiers_raw):
        if not isinstance(item, Mapping):
            raise ValidationError(f"complexity_tiers[{i}] must be an object")
        unknown = set(item) - {"tier", "name", "description", "example_signals"}
        if unknown:
            raise ValidationError(f"complexity_tiers[{i}]: unknown keys {sorted(unknown)}")
        tier = item.get("tier")
        if isinstance(tier, bool) or not isinstance(tier, int) or not (MIN_ROUTE_TIER <= tier <= MAX_ROUTE_TIER):
            raise ValidationError(f"complexity_tiers[{i}].tier must be an integer in [{MIN_ROUTE_TIER}, {MAX_ROUTE_TIER}]")
        if tier in tier_meta:
            raise ValidationError(f"complexity_tiers: duplicate tier {tier}")
        name = _check_text(item.get("name"), f"complexity_tiers[{i}].name")
        desc = _check_text(item.get("description"), f"complexity_tiers[{i}].description")
        signals = item.get("example_signals")
        if not isinstance(signals, list) or not signals or len(signals) > 16:
            raise ValidationError(f"complexity_tiers[{i}].example_signals must be a non-empty array (max 16)")
        for s in signals:
            _check_text(s, f"complexity_tiers[{i}].example_signals entry")
        tier_meta[tier] = (name, desc)

    table_raw = doc.get("routing_table")
    if not isinstance(table_raw, list) or len(table_raw) != 3:
        raise ValidationError("routing_table must hold exactly three route mappings")
    routes: Dict[int, tuple] = {}
    for i, item in enumerate(table_raw):
        tier, primary, cascade = validate_route_mapping(item, where=f"routing_table[{i}]")
        if tier in routes:
            raise ValidationError(f"routing_table: duplicate route for tier {tier}")
        if tier not in tier_meta:
            raise ValidationError(f"routing_table: route for tier {tier} has no complexity_tiers declaration")
        routes[tier] = (tier_meta[tier][0], tier_meta[tier][1], primary, cascade)
    if set(routes) != {1, 2, 3}:
        raise ValidationError("routing_table must cover exactly tiers 1, 2 and 3")
    if "budget_rules" in doc and not isinstance(doc["budget_rules"], list):
        raise ValidationError("budget_rules must be an array when present")
    if "defaults" in doc and not isinstance(doc["defaults"], Mapping):
        raise ValidationError("defaults must be an object when present")
    return routes


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS persistence_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS router_patterns (
    tier                 INTEGER PRIMARY KEY,
    tier_name            TEXT NOT NULL,
    tier_description     TEXT NOT NULL,
    primary_endpoint     TEXT NOT NULL,   -- ModelEndpoint JSON
    fallback_cascade     TEXT NOT NULL,   -- JSON array of ModelEndpoint
    updated_at           REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS task_permissions (
    scope_id             TEXT PRIMARY KEY,
    resource             TEXT NOT NULL,
    actions              TEXT NOT NULL,   -- JSON array (closed vocabulary)
    min_role_tier        INTEGER NOT NULL,
    requires_mfa         INTEGER NOT NULL,  -- 0/1 boolean
    updated_at           REAL NOT NULL
);
"""

_META_CONTRACTS = {
    "contract:router": ROUTER_CONTRACT,
    "contract:permissions": PERMISSIONS_CONTRACT,
    "schema_version": "autonomy-persistence/1",
}


class AutonomyPersistence:
    """SQLite-backed store for routing decisions and task permission scopes."""

    def __init__(self, path: str | Path, *, clock: Optional[Callable[[], float]] = None,
                 read_only: bool = False) -> None:
        self._clock = clock or time.time
        self._read_only = bool(read_only)
        target = Path(path)
        if target.is_dir():
            raise StoreUnavailableError(f"store path is a directory: {target}")
        try:
            if self._read_only:
                if not target.exists():
                    raise StoreUnavailableError(f"read-only store does not exist: {target}")
                self._conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(str(target))
                self._conn.executescript(_SCHEMA_SQL)
                for key, value in _META_CONTRACTS.items():
                    self._conn.execute(
                        "INSERT INTO persistence_meta(key, value) VALUES(?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, value),
                    )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise StoreUnavailableError(f"cannot open store {target}: {exc}") from exc

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "AutonomyPersistence":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def _require_writable(self) -> None:
        if self._read_only:
            raise ReadOnlyError("store opened read-only; writes are refused")

    def _write_tx(self) -> sqlite3.Cursor:
        self._require_writable()
        return self._conn.cursor()

    # -- router_patterns ----------------------------------------------------

    def load_router_document(self, doc: Mapping[str, Any]) -> int:
        """Wholesale fail-closed load of a task-router document (3 routes)."""
        routes = validate_router_document(doc)  # raises before any write
        now = self._clock()
        cur = self._write_tx()
        try:
            for tier, (name, desc, primary, cascade) in sorted(routes.items()):
                cur.execute(
                    "INSERT INTO router_patterns(tier, tier_name, tier_description, "
                    "primary_endpoint, fallback_cascade, updated_at) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(tier) DO UPDATE SET tier_name=excluded.tier_name, "
                    "tier_description=excluded.tier_description, "
                    "primary_endpoint=excluded.primary_endpoint, "
                    "fallback_cascade=excluded.fallback_cascade, "
                    "updated_at=excluded.updated_at",
                    (tier, name, desc, primary.to_json(),
                     json.dumps([json.loads(e.to_json()) for e in cascade]), now),
                )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise StoreUnavailableError(f"router load failed atomically: {exc}") from exc
        return len(routes)

    def route_for_tier(self, tier: int) -> RouterPatternRow:
        row = self._conn.execute(
            "SELECT tier, tier_name, tier_description, primary_endpoint, "
            "fallback_cascade, updated_at FROM router_patterns WHERE tier = ?",
            (tier,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no route persisted for tier {tier}")
        return RouterPatternRow(
            tier=row[0], tier_name=row[1], tier_description=row[2],
            primary=ModelEndpoint.from_json(row[3]),
            fallback_cascade=tuple(ModelEndpoint.from_json(e) for e in json.loads(row[4])),
            updated_at=row[5],
        )

    def all_routes(self) -> List[RouterPatternRow]:
        return [self.route_for_tier(t) for t in range(MIN_ROUTE_TIER, MAX_ROUTE_TIER + 1)
                if self._tier_exists(t)]

    def _tier_exists(self, tier: int) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM router_patterns WHERE tier = ?", (tier,)
        ).fetchone() is not None

    # -- task_permissions ---------------------------------------------------

    def load_permission_scopes(self, scopes: Sequence[Mapping[str, Any]]) -> int:
        """Wholesale fail-closed load of permission scopes (unique ids)."""
        if not isinstance(scopes, list) or not (1 <= len(scopes) <= MAX_SCOPES):
            raise ValidationError(f"scopes must be an array of 1..{MAX_SCOPES} objects")
        fields: List[tuple] = []
        seen: set = set()
        for i, raw in enumerate(scopes):
            parsed = validate_permission_scope(raw, where=f"scopes[{i}]")
            if parsed[0] in seen:
                raise ValidationError(f"scopes[{i}]: duplicate scope_id {parsed[0]!r}")
            seen.add(parsed[0])
            fields.append(parsed)
        now = self._clock()
        cur = self._write_tx()
        try:
            for scope_id, resource, actions, min_tier, mfa in fields:
                cur.execute(
                    "INSERT INTO task_permissions(scope_id, resource, actions, "
                    "min_role_tier, requires_mfa, updated_at) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(scope_id) DO UPDATE SET resource=excluded.resource, "
                    "actions=excluded.actions, min_role_tier=excluded.min_role_tier, "
                    "requires_mfa=excluded.requires_mfa, updated_at=excluded.updated_at",
                    (scope_id, resource, json.dumps(list(actions)), min_tier,
                     int(mfa), now),
                )
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise StoreUnavailableError(f"scope load failed atomically: {exc}") from exc
        return len(fields)

    def scope(self, scope_id: str) -> TaskPermissionRow:
        row = self._conn.execute(
            "SELECT scope_id, resource, actions, min_role_tier, requires_mfa, "
            "updated_at FROM task_permissions WHERE scope_id = ?",
            (scope_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no permission scope persisted for {scope_id!r}")
        return TaskPermissionRow(
            scope_id=row[0], resource=row[1], actions=tuple(json.loads(row[2])),
            min_role_tier=row[3], requires_mfa=bool(row[4]), updated_at=row[5],
        )

    def all_scopes(self) -> List[TaskPermissionRow]:
        rows = self._conn.execute(
            "SELECT scope_id FROM task_permissions ORDER BY scope_id"
        ).fetchall()
        return [self.scope(r[0]) for r in rows]

    # -- meta / snapshot ----------------------------------------------------

    def meta(self, key: str) -> str:
        row = self._conn.execute(
            "SELECT value FROM persistence_meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no meta key {key!r}")
        return row[0]

    def snapshot(self) -> Dict[str, Any]:
        """JSON-safe full read (both tables + meta) for audits and tests."""
        return {
            "routes": [
                {
                    "tier": r.tier, "tier_name": r.tier_name,
                    "tier_description": r.tier_description,
                    "primary": json.loads(r.primary.to_json()),
                    "fallback_cascade": [json.loads(e.to_json()) for e in r.fallback_cascade],
                    "updated_at": r.updated_at,
                }
                for r in self.all_routes()
            ],
            "scopes": [
                {
                    "scope_id": s.scope_id, "resource": s.resource,
                    "actions": list(s.actions), "min_role_tier": s.min_role_tier,
                    "requires_mfa": s.requires_mfa, "updated_at": s.updated_at,
                }
                for s in self.all_scopes()
            ],
            "meta": {k: self.meta(k) for k in sorted(_META_CONTRACTS)},
        }


# ---------------------------------------------------------------------------
# Embedded offline self-test (boot smoke without pytest)
# ---------------------------------------------------------------------------

_MINIMAL_ROUTER_DOC = {
    "schema_version": "1.0",
    "router_id": "self-test-router",
    "complexity_tiers": [
        {"tier": 1, "name": "trivial", "description": "single-step lookups",
         "example_signals": ["one tool call", "no state"]},
        {"tier": 2, "name": "standard", "description": "multi-step tasks",
         "example_signals": ["3-8 steps", "some state"]},
        {"tier": 3, "name": "complex", "description": "long-horizon orchestration",
         "example_signals": ["multi-repo", "verification loop"]},
    ],
    "routing_table": [
        {"tier": 1,
         "primary": {"provider": "groq", "model": "llama-3.1-8b-instant"},
         "fallback_cascade": [{"provider": "openai", "model": "gpt-4o-mini"}]},
        {"tier": 2,
         "primary": {"provider": "anthropic", "model": "claude-sonnet-4-5"},
         "fallback_cascade": [{"provider": "openai", "model": "gpt-4o"}]},
        {"tier": 3,
         "primary": {"provider": "openai", "model": "gpt-4o"},
         "fallback_cascade": [
             {"provider": "anthropic", "model": "claude-sonnet-4-5"},
             {"provider": "gemini", "model": "gemini-2.0-flash"},
         ]},
    ],
    "budget_rules": [],
    "defaults": {},
}

_MINIMAL_SCOPES = [
    {"scope_id": "mcp-tools-read", "resource": "mcp-tools", "actions": ["read"],
     "min_role_tier": 1, "requires_mfa": False},
    {"scope_id": "tenant-admin", "resource": "tenants/*",
     "actions": ["read", "write", "approve"], "min_role_tier": 3, "requires_mfa": True},
    {"scope_id": "secret-rotation", "resource": "secrets/prod",
     "actions": ["rotate_secrets"], "min_role_tier": 4, "requires_mfa": True},
]


def self_test() -> int:
    """Full offline roundtrip on a temp database; prints PASS or raises."""
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "selftest.sqlite3"
        with AutonomyPersistence(store_path, clock=lambda: 1234.5) as store:
            assert store.load_router_document(_MINIMAL_ROUTER_DOC) == 3
            assert store.load_permission_scopes(_MINIMAL_SCOPES) == 3
            route = store.route_for_tier(3)
            assert route.primary.model == "gpt-4o"
            assert len(route.fallback_cascade) == 2
            assert route.fallback_cascade[0].provider == "anthropic"
            scope = store.scope("secret-rotation")
            assert scope.actions == ("rotate_secrets",) and scope.requires_mfa is True
            assert store.meta("contract:router") == ROUTER_CONTRACT
            snap = store.snapshot()
            assert len(snap["routes"]) == 3 and len(snap["scopes"]) == 3
            # atomicity: a rejected load must leave the previous state intact
            bad = json.loads(json.dumps(_MINIMAL_ROUTER_DOC))
            bad["routing_table"][1]["tier"] = 9
            try:
                store.load_router_document(bad)
                raise AssertionError("invalid tier must be rejected")
            except ValidationError:
                pass
            assert store.route_for_tier(2).primary.model == "claude-sonnet-4-5"
        # read-only reopen sees the same rows
        with AutonomyPersistence(store_path, read_only=True) as ro:
            assert ro.route_for_tier(1).tier_name == "trivial"
            try:
                ro.load_router_document(_MINIMAL_ROUTER_DOC)
                raise AssertionError("read-only write must be refused")
            except ReadOnlyError:
                pass
    print("SELF-TEST PASS — router_patterns + task_permissions roundtrip verified.")
    return 0


if __name__ == "__main__":
    sys.exit(self_test())
