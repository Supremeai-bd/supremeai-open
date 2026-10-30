"""Dual manifest schema: SKILL.md frontmatter + cursor plugin.json.

Normalizes both ecosystem formats into one CapabilityDescriptor so the
registry, loader, and CLI treat every capability identically.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
NAME_RE = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")


class ManifestError(ValueError):
    """Raised when a manifest violates the schema contract."""


@dataclass
class CapabilityDescriptor:
    """Normalized capability metadata (stage-1/2 payload: no body).

    Extended contract fields (proposal section 6) are optional with safe
    defaults so legacy manifests keep parsing. They describe governance,
    preconditions, stop conditions, idempotency guidance, evidence and
    memory policy, and ownership without changing the core identity.
    """

    name: str
    version: str
    description: str
    triggers: list[str] = field(default_factory=list)
    entry: str | None = None
    source_format: str = "skill-md"  # or "cursor-plugin"
    source_path: str | None = None
    permission_level: str = "read"  # read | write | deploy | restart | secret
    preconditions: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    idempotency: str = ""
    evidence_requirements: list[str] = field(default_factory=list)
    memory_policy: str = "read"  # none | read | write
    owner: str = ""
    verification_required: bool = True

    def validate(self) -> None:
        if not NAME_RE.match(self.name):
            raise ManifestError(f"invalid skill name: {self.name!r}")
        if not self.version:
            raise ManifestError(f"skill {self.name}: missing version")
        if not self.description:
            raise ManifestError(f"skill {self.name}: missing description")
        if self.permission_level not in {
            "read",
            "write",
            "deploy",
            "restart",
            "secret",
        }:
            raise ManifestError(
                f"skill {self.name}: invalid permission_level {self.permission_level!r}"
            )
        if self.memory_policy not in {"none", "read", "write"}:
            raise ManifestError(
                f"skill {self.name}: invalid memory_policy {self.memory_policy!r}"
            )

    def summary(self) -> dict[str, Any]:
        """Lightweight boot-index payload (progressive disclosure, stage 1)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "triggers": list(self.triggers),
            "source_format": self.source_format,
            "permission_level": self.permission_level,
            "owner": self.owner,
            "verification_required": self.verification_required,
        }


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [item.strip().strip("'\"") for item in inner.split(",")]
        return [value]
    return []


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Minimal YAML frontmatter reader: scalars, inline lists, comments."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ManifestError("SKILL.md must open with a --- frontmatter block")
    data: dict[str, Any] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if ":" not in line:
            raise ManifestError(f"malformed frontmatter line: {raw_line!r}")
        key, _, rest = line.partition(":")
        data[key.strip()] = _parse_scalar(rest)
    return data


def parse_skill_md(text: str, source_path: str | None = None) -> tuple:
    """Return (descriptor, instructions_body) from SKILL.md content."""
    data = parse_frontmatter(text)
    match = FRONTMATTER_RE.match(text)
    body = text[match.end() :].strip()
    for required in ("name", "version", "description"):
        if required not in data:
            raise ManifestError(f"SKILL.md frontmatter missing {required!r}")
    descriptor = CapabilityDescriptor(
        name=str(data["name"]),
        version=str(data["version"]),
        description=str(data["description"]),
        triggers=[str(t) for t in data.get("triggers", [])]
        if isinstance(data.get("triggers"), list)
        else [],
        entry=str(data["entry"]) if data.get("entry") else None,
        source_format="skill-md",
        source_path=source_path,
        permission_level=str(data.get("permission_level", "read")),
        preconditions=_as_list(data.get("preconditions", [])),
        stop_conditions=_as_list(data.get("stop_conditions", [])),
        idempotency=str(data.get("idempotency", "")),
        evidence_requirements=_as_list(data.get("evidence_requirements", [])),
        memory_policy=str(data.get("memory_policy", "read")),
        owner=str(data.get("owner", "")),
        verification_required=_as_bool(data.get("verification_required", True)),
    )
    descriptor.validate()
    return descriptor, body


def parse_cursor_plugin(json_text: str, source_path: str | None = None) -> tuple:
    """Normalize a cursor/plugins plugin.json into (descriptor, notes)."""
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"plugin.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("plugin.json root must be an object")
    for required in ("name", "description"):
        if required not in data:
            raise ManifestError(f"plugin.json missing {required!r}")
    commands = data.get("commands")
    triggers: list[str] = []
    if isinstance(commands, dict):
        triggers = [str(key) for key in commands]
    elif isinstance(commands, list):
        triggers = [
            str(item.get("name"))
            for item in commands
            if isinstance(item, dict) and item.get("name")
        ]
    descriptor = CapabilityDescriptor(
        name=str(data["name"]).lower().replace("_", "-"),
        version=str(data.get("version", "0.0.0")),
        description=str(data["description"]),
        triggers=triggers,
        entry=str(data.get("entry")) if data.get("entry") else None,
        source_format="cursor-plugin",
        source_path=source_path,
        permission_level=str(data.get("permission_level", "read")),
        preconditions=_as_list(data.get("preconditions", [])),
        stop_conditions=_as_list(data.get("stop_conditions", [])),
        idempotency=str(data.get("idempotency", "")),
        evidence_requirements=_as_list(data.get("evidence_requirements", [])),
        memory_policy=str(data.get("memory_policy", "read")),
        owner=str(data.get("owner", "")),
        verification_required=_as_bool(data.get("verification_required", True)),
    )
    descriptor.validate()
    notes = str(data.get("instructions", "")).strip()
    return descriptor, notes
