"""Canonical configuration registry — single authoritative import point.

Issue #124 (Phase-3, SupremeAI Final Roadmap): unify configuration metadata
behind one import surface. বাংলা: একসময় CONFIG_SCHEMA / ENV_REGISTRY /
CONFIG_SPECS তিন জায়গায় ছিল — #1260 (Wave 3.4) CONFIG_SPECS-কে SSOT বানিয়ে
CONFIG_SCHEMA-কে derived view বানায় এবং .env.example অটো-জেনারেশন লাগায়।
এই মডিউল সেই SSOT-এর **facade**: কনজিউমাররা এখন থেকে এক জায়গা থেকেই সব
configuration metadata পাবে, আর ভেতরের ফাইল-লেআউট বদলালে শুধু এখানে ধরতে হবে।

Path note (deviation from the issue text, validated live): the issue declared
``core/config/registry.py``, but ``backend/core/config.py`` (the ``Settings``
pydantic module) already owns the ``core.config`` namespace — a ``config/``
package there would shadow it and break every ``from core.config import
settings`` import (boot-smoke-verified failure). Per the sibling naming
convention (config_classification / config_validator / config_control_plane),
the facade lives at ``core/config_registry.py``.

Contract (machine-checked by ``tests/test_config_registry.py``):

* **No duplication** — every symbol re-exports the SSOT object by identity,
  never a copy. If a future edit copies data into this module, the identity
  tests fail loudly.
* **Secrets coverage** — ``secret_specs()`` / ``is_secret_key()`` /
  ``secrets_registry_gaps()`` let CI and ``scripts/ci/generate_env_example.py``
  keep ``secrets_registry.yaml`` in sync with the SSOT's secret class.

Related docs: ``backend/core/config_classification.py`` (SSOT data),
``backend/core/config_validator.py`` (derived schema view),
``backend/core/config.py`` (Settings — separate concern, do not merge),
``scripts/ci/generate_env_example.py`` (template + secrets-registry generator).
"""

from __future__ import annotations

from core.config_classification import (
    ALIAS_TO_CANONICAL,
    BY_NAME,
    CONFIG_SPECS,
    ConfigClass,
    ConfigSource,
    ConfigSpec,
    all_config_names,
    canonical_name,
    get_config_spec,
)
from core.config_validator import CONFIG_SCHEMA, VarDefinition

__all__ = [
    "ALIAS_TO_CANONICAL",
    "BY_NAME",
    "CONFIG_SCHEMA",
    "CONFIG_SPECS",
    "ConfigClass",
    "ConfigSource",
    "ConfigSpec",
    "VarDefinition",
    "all_config_names",
    "canonical_name",
    "get_config_spec",
    "is_secret_key",
    "secret_specs",
    "secrets_registry_gaps",
]


def secret_specs() -> tuple[ConfigSpec, ...]:
    """Return every SSOT spec whose class marks it a secret, in declaration order.

    বাংলা: SSOT-তে যত secret-শ্রেণির key আছে সব কটা, ঘোষণা-ক্রমে।
    """
    return tuple(spec for spec in CONFIG_SPECS if spec.is_secret)


def is_secret_key(name: str) -> bool:
    """Resolve ``name`` (canonical or alias) and report whether it is a secret."""
    spec = get_config_spec(name)
    return bool(spec is not None and spec.is_secret)


def secrets_registry_gaps(registry_names: set[str]) -> tuple[str, ...]:
    """Return secret-class SSOT names absent from a secrets-registry name set.

    বাংলা: secrets_registry.yaml-এ যে secret key-গুলো এখনো নেই শুধু সেগুলোর
    নাম — gap শূন্য মানে registry SSOT-কে পুরোপুরি কভার করছে।
    """
    return tuple(spec.name for spec in secret_specs() if spec.name not in registry_names)
