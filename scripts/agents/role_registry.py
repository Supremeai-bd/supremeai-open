#!/usr/bin/env python3
"""S10 — Agent Role Registry (issue #497, acceptance criterion 1).

Operational registry that instantiates the deterministic dispatch contracts
from ``role_trigger_matrix.py`` (SSOT — the registry NEVER redefines a
role's trigger or contradicts its weapon allowlist; it only adds
operational, execution-level facts such as tool adapters and read-only
posture).

Issue #497 registers the **Ecosystem Scout (`ecosystem-scout`)** with its
scoped weapons: read-only URL reader, AST parser, repository inspector and
artifact writer. Note the RBAC invariant: `artifact_writer` produces
*report artifacts* (dossiers), not source code — it is deliberately NOT in
`role_trigger_matrix.CODE_WRITE_WEAPONS`, and every read-only role's
registry weapons must remain disjoint from that set.

Fail-closed by contract:

  * unknown role lookups raise ValueError;
  * duplicate registration raises ValueError;
  * a registry record whose weapons violate the SSOT contract (missing a
    dispatch weapon, or leaking a code-write weapon into a read-only role)
    is rejected at registration time.

Pure stdlib. Run: python3 scripts/agents/role_registry.py --self-test
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])

from role_trigger_matrix import (  # noqa: E402
    CODE_WRITE_WEAPONS,
    ROLE_CONTRACTS,
    ROLE_IDS,
    provision_weapons,
)


@dataclass(frozen=True)
class RoleRecord:
    """Operational registration for one dispatch role."""

    role_id: str
    display_name: str
    #: Superset of the SSOT dispatch weapons — operational tool adapters.
    operational_weapons: frozenset[str]
    #: True -> role may not hold any code-write weapon (auditor family).
    read_only: bool
    description: str
    adapters: tuple[str, ...] = field(default_factory=tuple)


class RoleRegistry:
    """Fail-closed registry. Registration validates against the SSOT."""

    def __init__(self) -> None:
        self._roles: dict[str, RoleRecord] = {}

    def register(self, record: RoleRecord) -> None:
        if record.role_id in self._roles:
            raise ValueError(f"role {record.role_id!r} is already registered")
        if record.role_id not in ROLE_CONTRACTS:
            raise ValueError(
                f"role {record.role_id!r} is not a dispatch role; "
                f"add it to role_trigger_matrix.ROLE_CONTRACTS first "
                f"(single source of truth: {sorted(ROLE_IDS)})"
            )
        contract_weapons = provision_weapons(record.role_id)
        missing = contract_weapons - record.operational_weapons
        if missing:
            raise ValueError(
                f"role {record.role_id!r} registry weapons are missing SSOT "
                f"dispatch weapons {sorted(missing)}"
            )
        leaked = record.operational_weapons & CODE_WRITE_WEAPONS
        if record.read_only and leaked:
            raise ValueError(
                f"read-only role {record.role_id!r} leaked code-write "
                f"weapons {sorted(leaked)}"
            )
        if not record.read_only and not leaked:
            # Not fatal, but the registry demands an explicit posture.
            raise ValueError(
                f"role {record.role_id!r} holds code-write weapons "
                f"{sorted(leaked) if leaked else CODE_WRITE_WEAPONS & record.operational_weapons} "
                "and must declare read_only=False explicitly"
            )
        self._roles[record.role_id] = record

    def get(self, role_id: str) -> RoleRecord:
        record = self._roles.get(role_id)
        if record is None:
            raise ValueError(f"unknown role: {role_id!r}")
        return record

    def list_roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._roles))

    def check_read_only(self, role_id: str) -> bool:
        record = self.get(role_id)
        if record.read_only:
            return not (record.operational_weapons & CODE_WRITE_WEAPONS)
        return False


SCOUT_WEAPONS: Final = frozenset({
    # SSOT dispatch weapons (role_trigger_matrix, issue #489 matrix):
    "search_web",
    "read_url_content",
    "gh_issue_create",
    # Operational scoped weapons mandated by issue #497:
    "ast_parser",          # AST slicing for the Gold Pearl (20-100 lines)
    "repo_inspector",      # read-only manifests / contracts / dependency graphs
    "artifact_writer",     # writes EcosystemDossier report artifacts (NOT code)
})


def default_registry() -> RoleRegistry:
    """Registry with the #497 Ecosystem Scout registration."""
    registry = RoleRegistry()
    registry.register(RoleRecord(
        role_id="ecosystem-scout",
        display_name="Ecosystem Scout (ইকোসিস্টেম এজেন্ট)",
        operational_weapons=SCOUT_WEAPONS,
        read_only=True,
        description=(
            "Autonomous external-intelligence scout: 4-phase dissection "
            "(extraction, comparative analysis, risk audit, adoption RFC) "
            "under the Surgical Need-Driven Extraction Doctrine — "
            "never vendor full repositories, extract only the Gold Pearl."
        ),
        adapters=(
            "scout_analyze_repository",   # MCP tool (issue #497 criterion 3)
            "render_dossier_markdown",    # standard artifact export
        ),
    ))
    return registry


def self_test() -> bool:
    registry = default_registry()
    assert registry.list_roles() == ("ecosystem-scout",)
    record = registry.get("ecosystem-scout")
    assert record.read_only is True
    assert registry.check_read_only("ecosystem-scout")
    # SSOT superset holds: every dispatch weapon is registered.
    assert provision_weapons("ecosystem-scout") <= SCOUT_WEAPONS
    # No code-write weapons leak into the read-only role.
    assert not (SCOUT_WEAPONS & CODE_WRITE_WEAPONS)

    # Fail-closed lookups and registrations.
    for broken, exc in (
        (lambda: registry.get("ghost"), ValueError),
        (lambda: registry.register(record), ValueError),          # duplicate
        (lambda: registry.register(RoleRecord(                    # not dispatch role
            role_id="ghost", display_name="g",
            operational_weapons=frozenset({"search_web"}),
            read_only=True, description="x")), ValueError),
        (lambda: registry.register(RoleRecord(                    # missing SSOT weapon
            role_id="ecosystem-scout", display_name="g",
            operational_weapons=frozenset({"search_web"}),
            read_only=True, description="x")), ValueError),
        (lambda: registry.register(RoleRecord(                    # write leak
            role_id="ecosystem-scout", display_name="g",
            operational_weapons=SCOUT_WEAPONS | {"write_to_file"},
            read_only=True, description="x")), ValueError),
        (lambda: registry.register(RoleRecord(                    # undeclared posture
            role_id="ecosystem-scout", display_name="g",
            operational_weapons=SCOUT_WEAPONS | {"pr_create"},
            read_only=True, description="x")), ValueError),
    ):
        try:
            broken()
            raise SystemExit(f"registry gate failed open: {exc}")
        except exc:  # type: ignore[misc]
            pass
    return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF-TEST OK: role_registry")
        return 0
    if args.list:
        registry = default_registry()
        for role in registry.list_roles():
            r = registry.get(role)
            print(f"{role}: {r.display_name} read_only={r.read_only} "
                  f"weapons={sorted(r.operational_weapons)}")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
