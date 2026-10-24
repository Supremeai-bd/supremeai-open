"""Schema registry for database-controlled runtime configuration.

The registry contains only safe defaults and validation metadata. Operational
values remain in ``system_config``; immutable safety bounds stay in code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConfigDefinition:
    key: str
    value_type: type | tuple[type, ...]
    default: Any
    category: str
    description: str
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[Any, ...] = ()
    public: bool = False
    restart_required: bool = False

    def validate(self, value: Any) -> Any:
        if isinstance(value, bool) and self.value_type is int:
            raise ValueError(f"{self.key} must be an integer")
        if not isinstance(value, self.value_type):
            raise ValueError(f"{self.key} must be of type {self.value_type}")
        if self.allowed_values and value not in self.allowed_values:
            raise ValueError(f"{self.key} must be one of {self.allowed_values}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.key} must be >= {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.key} must be <= {self.maximum}")
        return value


REGISTRY: dict[str, ConfigDefinition] = {
    "runtime.max_concurrency": ConfigDefinition(
        "runtime.max_concurrency", int, 5, "runtime", "Maximum concurrent runtime tasks", 1, 100
    ),
    "feature.self_healing": ConfigDefinition(
        "feature.self_healing", bool, False, "feature", "Enable self-healing workflows", public=True
    ),
    "feature.cost_guard": ConfigDefinition(
        "feature.cost_guard", bool, True, "feature", "Enable cost guardrails", public=True
    ),
    "system.maintenance_mode": ConfigDefinition(
        "system.maintenance_mode",
        bool,
        False,
        "system",
        "Put public services into maintenance mode",
        public=True,
    ),
}


def get_definition(key: str) -> ConfigDefinition | None:
    return REGISTRY.get(key)


def validate_value(key: str, value: Any) -> Any:
    definition = get_definition(key)
    if definition is None:
        raise KeyError(f"Unknown configuration key: {key}")
    return definition.validate(value)


def safe_defaults(*, public_only: bool = False) -> dict[str, Any]:
    return {
        key: definition.default
        for key, definition in REGISTRY.items()
        if not public_only or definition.public
    }


def schema(*, public_only: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "key": definition.key,
            "type": definition.value_type.__name__
            if isinstance(definition.value_type, type)
            else "value",
            "category": definition.category,
            "description": definition.description,
            "minimum": definition.minimum,
            "maximum": definition.maximum,
            "allowed_values": list(definition.allowed_values),
            "public": definition.public,
            "restart_required": definition.restart_required,
        }
        for definition in REGISTRY.values()
        if not public_only or definition.public
    ]


__all__ = [
    "ConfigDefinition",
    "REGISTRY",
    "get_definition",
    "safe_defaults",
    "schema",
    "validate_value",
]
