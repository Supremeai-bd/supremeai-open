"""supremeai-skills registry: manifest schemas and descriptors."""

from .manifest_schema import (
    CapabilityDescriptor,
    ManifestError,
    parse_cursor_plugin,
    parse_skill_md,
)
from .progressive_loader import ProgressiveLoader

__all__ = [
    "CapabilityDescriptor",
    "ManifestError",
    "ProgressiveLoader",
    "parse_cursor_plugin",
    "parse_skill_md",
]
