"""Offline tests for the #328-WS2 autonomy persistence reference.

Proves the store is a faithful, fail-closed implementation of the landed
Layer 1 contracts, including an SSOT sync battery that reads the schema files
themselves and asserts the hand-rolled validators still mirror them.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

import importlib.util

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "scripts" / "agents" / "autonomy_persistence.py"

_spec = importlib.util.spec_from_file_location("autonomy_persistence_under_test", MODULE_PATH)
ap = importlib.util.module_from_spec(_spec)
import sys
sys.modules.setdefault("autonomy_persistence_under_test", ap)
_spec.loader.exec_module(ap)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def router_doc(**overrides) -> dict:
    doc = {
        "schema_version": "1.0",
        "router_id": "federation-router",
        "complexity_tiers": [
            {"tier": 1, "name": "trivial", "description": "single-step lookups",
             "example_signals": ["one tool call"]},
            {"tier": 2, "name": "standard", "description": "multi-step tasks",
             "example_signals": ["3-8 steps"]},
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
             "fallback_cascade": [{"provider": "gemini", "model": "gemini-2.0-flash"}]},
        ],
        "budget_rules": [],
        "defaults": {},
    }
    for key, value in overrides.items():
        if value is _DELETE:
            doc.pop(key, None)
        else:
            doc[key] = value
    return doc


_DELETE = object()


def scopes() -> list:
    return [
        {"scope_id": "mcp-tools-read", "resource": "mcp-tools", "actions": ["read"],
         "min_role_tier": 1, "requires_mfa": False},
        {"scope_id": "tenant-admin", "resource": "tenants/*",
         "actions": ["read", "write", "approve"], "min_role_tier": 3, "requires_mfa": True},
        {"scope_id": "secret-rotation", "resource": "secrets/prod",
         "actions": ["rotate_secrets"], "min_role_tier": 4, "requires_mfa": True},
    ]


@pytest.fixture()
def store(tmp_path):
    s = ap.AutonomyPersistence(tmp_path / "store.sqlite3", clock=lambda: 42.0)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# SSOT sync — validators must mirror the schema files exactly
# ---------------------------------------------------------------------------


def test_ssot_provider_enum_matches_schema():
    schema = json.loads((REPO / "api-schemas" / "task-router.schema.json").read_text())
    enum = schema["$defs"]["ModelEndpoint"]["properties"]["provider"]["enum"]
    assert set(enum) == set(ap.PROVIDERS)


def test_ssot_action_vocabulary_matches_schema():
    schema = json.loads((REPO / "api-schemas" / "permissions.schema.json").read_text())
    enum = schema["$defs"]["PermissionScope"]["properties"]["actions"]["items"]["enum"]
    assert set(enum) == set(ap.ACTIONS)


def test_ssot_patterns_match_schema():
    perm = json.loads((REPO / "api-schemas" / "permissions.schema.json").read_text())
    props = perm["$defs"]["PermissionScope"]["properties"]
    assert props["scope_id"]["pattern"] == ap.SCOPE_ID_PATTERN.pattern
    assert props["resource"]["pattern"] == ap.RESOURCE_PATTERN.pattern
    router = json.loads((REPO / "api-schemas" / "task-router.schema.json").read_text())
    me = router["$defs"]["ModelEndpoint"]["properties"]
    assert me["model"]["pattern"] == ap.MODEL_PATTERN.pattern
    assert me["max_context_tokens"]["minimum"] == ap.MIN_CONTEXT_TOKENS


def test_ssot_tier_bounds_match_schema():
    router = json.loads((REPO / "api-schemas" / "task-router.schema.json").read_text())
    tier_prop = router["$defs"]["RouteMapping"]["properties"]["tier"]
    assert (tier_prop["minimum"], tier_prop["maximum"]) == (ap.MIN_ROUTE_TIER, ap.MAX_ROUTE_TIER)
    perm = json.loads((REPO / "api-schemas" / "permissions.schema.json").read_text())
    mrt = perm["$defs"]["PermissionScope"]["properties"]["min_role_tier"]
    assert (mrt["minimum"], mrt["maximum"]) == (ap.MIN_ROLE_TIER, ap.MAX_ROLE_TIER)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_bootstrap_writes_contract_meta(store):
    assert store.meta("contract:router") == "api-schemas/task-router.schema.json"
    assert store.meta("contract:permissions") == "api-schemas/permissions.schema.json"
    assert store.meta("schema_version") == "autonomy-persistence/1"


def test_router_document_roundtrip(store):
    assert store.load_router_document(router_doc()) == 3
    route = store.route_for_tier(2)
    assert route.tier_name == "standard"
    assert route.primary == ap.ModelEndpoint(provider="anthropic", model="claude-sonnet-4-5")
    assert route.fallback_cascade[0].model == "gpt-4o"
    assert route.updated_at == 42.0


def test_scope_roundtrip_preserves_action_order(store):
    store.load_permission_scopes(scopes())
    row = store.scope("tenant-admin")
    assert row.actions == ("read", "write", "approve")
    assert row.min_role_tier == 3 and row.requires_mfa is True


def test_snapshot_is_json_safe(store):
    store.load_router_document(router_doc())
    store.load_permission_scopes(scopes())
    snap = store.snapshot()
    assert json.loads(json.dumps(snap)) == snap
    assert len(snap["routes"]) == 3 and len(snap["scopes"]) == 3


def test_upsert_overwrites_and_bumps_timestamp(store):
    store.load_router_document(router_doc())
    assert store.route_for_tier(1).primary.model == "llama-3.1-8b-instant"
    doc = router_doc()
    doc["routing_table"][0]["primary"] = {"provider": "groq", "model": "llama-3.3-70b"}
    store2_clock = {"t": 100.0}
    store._clock = lambda: store2_clock["t"]  # deterministic advance
    store.load_router_document(doc)
    assert store.route_for_tier(1).primary.model == "llama-3.3-70b"
    assert store.route_for_tier(1).updated_at == 100.0


def test_reopen_read_only_sees_committed_rows(store, tmp_path):
    store.load_router_document(router_doc())
    store.close()
    ro = ap.AutonomyPersistence(tmp_path / "store.sqlite3", read_only=True)
    try:
        assert ro.route_for_tier(3).tier_name == "complex"
    finally:
        ro.close()


# ---------------------------------------------------------------------------
# Fail-closed rejections (nothing may be written)
# ---------------------------------------------------------------------------


def test_atomicity_invalid_route_leaves_previous_state(store):
    store.load_router_document(router_doc())
    bad = router_doc()
    bad["routing_table"][1]["fallback_cascade"] = []
    with pytest.raises(ap.ValidationError):
        store.load_router_document(bad)
    assert store.route_for_tier(2).primary.model == "claude-sonnet-4-5"


def test_atomicity_invalid_scope_leaves_previous_state(store):
    store.load_permission_scopes(scopes())
    bad = scopes() + [{"scope_id": "Bad_Upper", "resource": "mcp-tools",
                       "actions": ["read"], "min_role_tier": 1, "requires_mfa": False}]
    with pytest.raises(ap.ValidationError):
        store.load_permission_scopes(bad)
    assert store.scope("mcp-tools-read").resource == "mcp-tools"
    with pytest.raises(ap.NotFoundError):
        store.scope("Bad_Upper")


@pytest.mark.parametrize("mutate,fragment", [
    (lambda d: d.update(unexpected=1), "unknown top-level"),
    (lambda d: d.update(schema_version="one"), "schema_version"),
    (lambda d: d["routing_table"].__setitem__(0, {**d["routing_table"][0], "tier": 9}), "tier"),
    (lambda d: d["routing_table"].__setitem__(1, {**d["routing_table"][1], "extra": 1}), "unknown route keys"),
    (lambda d: d["routing_table"][2].update(primary={"provider": "skynet", "model": "x"}), "registered provider"),
    (lambda d: d["routing_table"][2].update(fallback_cascade=[{"provider": "groq", "model": "a"},
                                                              {"provider": "groq", "model": "a"}]), "unique"),
    (lambda d: d["complexity_tiers"].pop(), "exactly three"),
    (lambda d: d["routing_table"].pop(), "exactly three route"),
])
def test_router_document_rejections(mutate, fragment, store):
    doc = router_doc()
    mutate(doc)
    with pytest.raises(ap.ValidationError, match=fragment):
        store.load_router_document(doc)
    assert store.all_routes() == []


@pytest.mark.parametrize("mutate,fragment", [
    (lambda s: s[0].update(scope_id="Uppercase"), "pattern"),
    (lambda s: s[0].update(scope_id="ab"), "pattern"),
    (lambda s: s[0].update(resource="Not-Valid"), "pattern"),
    (lambda s: s[0].update(actions=[]), "non-empty"),
    (lambda s: s[0].update(actions=["read", "read"]), "unique"),
    (lambda s: s[0].update(actions=["teleport"]), "closed vocabulary"),
    (lambda s: s[0].update(min_role_tier=0), "min_role_tier"),
    (lambda s: s[0].update(min_role_tier=5), "min_role_tier"),
    (lambda s: s[0].update(requires_mfa="yes"), "boolean"),
    (lambda s: s[0].update(extra_key=1), "unknown scope keys"),
])
def test_scope_rejections(mutate, fragment, store):
    rows = scopes()
    mutate(rows)
    with pytest.raises(ap.ValidationError, match=fragment):
        store.load_permission_scopes(rows)
    assert store.all_scopes() == []


def test_duplicate_scope_ids_rejected(store):
    rows = scopes()
    rows.append(dict(rows[0]))
    with pytest.raises(ap.ValidationError, match="duplicate scope_id"):
        store.load_permission_scopes(rows)


def test_empty_scope_list_rejected(store):
    with pytest.raises(ap.ValidationError):
        store.load_permission_scopes([])


# ---------------------------------------------------------------------------
# Store lifecycle errors
# ---------------------------------------------------------------------------


def test_directory_path_is_store_unavailable(tmp_path):
    with pytest.raises(ap.StoreUnavailableError):
        ap.AutonomyPersistence(tmp_path)


def test_read_only_missing_file_is_store_unavailable(tmp_path):
    with pytest.raises(ap.StoreUnavailableError):
        ap.AutonomyPersistence(tmp_path / "missing.sqlite3", read_only=True)


def test_read_only_write_refused(tmp_path):
    path = tmp_path / "s.sqlite3"
    with ap.AutonomyPersistence(path) as w:
        w.load_permission_scopes(scopes())
    ro = ap.AutonomyPersistence(path, read_only=True)
    try:
        with pytest.raises(ap.ReadOnlyError):
            ro.load_permission_scopes(scopes())
    finally:
        ro.close()


def test_corrupt_database_is_store_unavailable(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(ap.StoreUnavailableError):
        ap.AutonomyPersistence(path)


# ---------------------------------------------------------------------------
# Embedded self-test CLI
# ---------------------------------------------------------------------------


def test_self_test_passes():
    assert ap.self_test() == 0
