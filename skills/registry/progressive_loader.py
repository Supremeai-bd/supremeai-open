"""Three-stage progressive disclosure loader.

Stage 1 (boot):  discover() — walk roots, read frontmatter/manifests only.
Stage 2 (index): summaries() — cheap metadata payloads for agent context.
Stage 3 (dispatch): load() — read full instructions for exactly one skill.
"""

from __future__ import annotations

import json
from pathlib import Path

from .manifest_schema import (
    CapabilityDescriptor,
    ManifestError,
    parse_cursor_plugin,
    parse_skill_md,
)

SKILL_MD = "SKILL.md"
CURSOR_MANIFEST = "plugin.json"


class ProgressiveLoader:
    """Filesystem-backed capability registry with context-diet semantics."""

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(root) for root in roots]
        self._index: dict[str, CapabilityDescriptor] = {}
        self._bodies: dict[str, str] = {}

    def discover(self) -> dict[str, CapabilityDescriptor]:
        """Stage 1: index every skill under the roots (metadata only)."""
        self._index = {}
        self._bodies = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for skill_md in sorted(root.rglob(SKILL_MD)):
                descriptor, body = parse_skill_md(
                    skill_md.read_text(encoding="utf-8"), source_path=str(skill_md)
                )
                self._adopt(descriptor, body)
            for plugin_json in sorted(root.rglob(CURSOR_MANIFEST)):
                if plugin_json.parent.name != ".cursor-plugin":
                    continue
                descriptor, notes = parse_cursor_plugin(
                    plugin_json.read_text(encoding="utf-8"),
                    source_path=str(plugin_json),
                )
                self._adopt(descriptor, notes)
        return dict(self._index)

    def _adopt(self, descriptor: CapabilityDescriptor, body: str) -> None:
        if descriptor.name in self._index:
            raise ManifestError(f"duplicate capability name: {descriptor.name}")
        self._index[descriptor.name] = descriptor
        self._bodies[descriptor.name] = body

    def summaries(self) -> list[dict[str, object]]:
        """Stage 2: lightweight summaries; safe for boot-time context."""
        return [descriptor.summary() for descriptor in self._index.values()]

    def load(self, name: str) -> dict[str, object]:
        """Stage 3: full instructions + entry for exactly one capability."""
        if name not in self._index:
            raise KeyError(f"capability not indexed: {name}")
        descriptor = self._index[name]
        return {
            "descriptor": descriptor.summary(),
            "entry": descriptor.entry,
            "instructions": self._bodies[name],
        }

    def match(self, task_text: str) -> CapabilityDescriptor | None:
        """Resolve a dispatched task to a capability via trigger keywords."""
        lowered = task_text.lower()
        best: CapabilityDescriptor | None = None
        best_score = 0
        for descriptor in self._index.values():
            score = sum(
                1 for trigger in descriptor.triggers if trigger.lower() in lowered
            )
            if score > best_score:
                best, best_score = descriptor, score
        return best

    @staticmethod
    def read_index(path: Path) -> dict[str, dict[str, str]]:
        """Validate and return registry/index.json content (git sources)."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        skills = raw.get("skills", {})
        if not isinstance(skills, dict):
            raise ManifestError("index.json skills must be an object")
        for name, spec in skills.items():
            if not isinstance(spec, dict) or "git" not in spec:
                raise ManifestError(f"index entry {name!r} missing git source")
        return skills
