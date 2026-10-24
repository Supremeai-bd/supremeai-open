"""Configuration Control Plane facade.

The canonical vocabulary remains ``config_classification``. This module adds
orchestration/health semantics without creating a second source of truth.
Secret values are never returned; only presence and metadata are exposed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .config_classification import (
    ALIAS_TO_CANONICAL,
    BY_NAME,
    ConfigClass,
    ConfigSource,
    canonical_name,
)


@dataclass(frozen=True)
class ConfigHealth:
    name: str
    canonical_name: str
    present: bool
    secret: bool
    required: bool
    scopes: tuple[str, ...]
    sources: tuple[str, ...]
    status: str


def _present(name: str) -> bool:
    # Presence only: never expose or log the value.
    return bool(os.getenv(name))


def health_snapshot() -> list[ConfigHealth]:
    result: list[ConfigHealth] = []
    for name, spec in sorted(BY_NAME.items()):
        present = _present(name) or any(_present(alias) for alias in spec.aliases)
        required = ConfigClass.REQUIRED in spec.classes
        conditional = ConfigClass.CONDITIONAL in spec.classes
        if present:
            status = "configured"
        elif required:
            status = "missing-required"
        elif conditional:
            status = "conditional-unset"
        else:
            status = "unset"
        result.append(
            ConfigHealth(
                name=name,
                canonical_name=canonical_name(name),
                present=present,
                secret=ConfigClass.SECRET in spec.classes,
                required=required,
                scopes=tuple(sorted(spec.scopes)),
                sources=tuple(sorted(s.value for s in spec.sources)),
                status=status,
            )
        )
    return result


def health_summary() -> dict[str, int]:
    items = health_snapshot()
    return {
        "total": len(items),
        "configured": sum(x.present for x in items),
        "missing_required": sum(x.status == "missing-required" for x in items),
        "secrets": sum(x.secret for x in items),
    }


def canonical_contract() -> dict[str, object]:
    """Metadata contract consumed by future CI/Admin/adapter integrations."""
    return {
        "version": 1,
        "canonical_keys": sorted(BY_NAME),
        "aliases": dict(sorted(ALIAS_TO_CANONICAL.items())),
        "health": health_summary(),
        "provenance": {
            "env": "runtime presence only",
            "vault": "external verification adapter",
            "deploy": "external verification adapter",
        },
    }
