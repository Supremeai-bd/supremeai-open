"""Ecosystem citizen manifests and architecture graph validation.

বাংলা: প্রতিটি module নিজস্ব identity, inputs/outputs, capabilities এবং
boundary ঘোষণা করে। এই registry কোনো নতুন database নয়; CI/runtime validation-এর
জন্য immutable in-memory contract এবং graph snapshot তৈরি করে।
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CitizenManifest:
    module_id: str
    version: str
    domain: str
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.module_id or "." not in self.module_id:
            errors.append("module_id must be namespaced")
        if not self.version:
            errors.append("version is required")
        if not self.domain:
            errors.append("domain is required")
        if not self.provides and not self.emits:
            errors.append("citizen must provide a capability or emit an event")
        return errors


@dataclass(frozen=True)
class GraphSnapshot:
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str, str], ...]
    violations: tuple[str, ...] = ()


class CitizenRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, CitizenManifest] = {}

    def register(self, manifest: CitizenManifest) -> CitizenManifest:
        errors = manifest.validate()
        if errors:
            raise ValueError("; ".join(errors))
        existing = self._manifests.get(manifest.module_id)
        if existing is not None and existing.version != manifest.version:
            raise ValueError(f"manifest_version_conflict:{manifest.module_id}")
        self._manifests[manifest.module_id] = manifest
        return manifest

    def snapshot(self) -> GraphSnapshot:
        edges: list[tuple[str, str, str]] = []
        violations: list[str] = []
        for manifest in self._manifests.values():
            for required in manifest.requires:
                providers = [
                    m.module_id for m in self._manifests.values() if required in m.provides
                ]
                if not providers:
                    violations.append(f"missing_provider:{manifest.module_id}:{required}")
                edges.extend((provider, manifest.module_id, "requires") for provider in providers)
            for consumed in manifest.consumes:
                producers = [m.module_id for m in self._manifests.values() if consumed in m.emits]
                edges.extend((producer, manifest.module_id, "consumes") for producer in producers)
        return GraphSnapshot(
            nodes=tuple(sorted(self._manifests)),
            edges=tuple(sorted(set(edges))),
            violations=tuple(sorted(set(violations))),
        )

    def validate_boundaries(self, forbidden_pairs: set[tuple[str, str]]) -> list[str]:
        """Detect direct cross-domain imports that must go through the Hub."""
        violations: list[str] = []
        for source, target in forbidden_pairs:
            source_manifest = self._manifests.get(source)
            target_manifest = self._manifests.get(target)
            if (
                source_manifest
                and target_manifest
                and source_manifest.domain != target_manifest.domain
            ):
                violations.append(f"direct_cross_domain:{source}->{target}")
        return sorted(violations)


__all__ = ["CitizenManifest", "CitizenRegistry", "GraphSnapshot"]
