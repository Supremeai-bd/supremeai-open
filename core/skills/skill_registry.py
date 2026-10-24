"""Skill Registry for SupremeAI 2.0.

বাংলা: স্কিল ম্যানিফেস্ট লোড, রেজিস্ট্রেশন এবং ডাইনামিক ডিসকভারি ইঞ্জিন।
"""

import json
from pathlib import Path
from typing import Any

from core.logging_config import logger

SKILLS_DIR = Path(__file__).parent
MANIFESTS_DIR = SKILLS_DIR / "manifests"


class SkillRegistry:
    """Dynamic Registry for loading and managing skill manifests."""

    def __init__(self, manifests_path: Path = MANIFESTS_DIR):
        self.manifests_path = manifests_path
        self._skills: dict[str, dict[str, Any]] = {}

    def discover_skills(self) -> dict[str, dict[str, Any]]:
        """Discover all valid skill manifests in the manifests directory.

        বাংলা: সব বৈধ স্কিল ম্যানিফেস্ট স্ক্যান ও লোড করে।
        """
        self._skills.clear()
        if not self.manifests_path.exists():
            logger.warning(f"Manifests directory does not exist: {self.manifests_path}")
            return self._skills

        for manifest_file in self.manifests_path.glob("*.json"):
            try:
                with open(manifest_file, encoding="utf-8") as f:
                    data = json.load(f)
                    skill_id = data.get("id") or manifest_file.stem
                    self._skills[skill_id] = {
                        "id": skill_id,
                        "name": data.get("name", skill_id),
                        "version": data.get("version", "1.0.0"),
                        "description": data.get("description", ""),
                        "dependencies": data.get("dependencies", []),
                        "system_packages": data.get("system_packages", []),
                        "entrypoint": data.get("entrypoint", f"{skill_id}.py"),
                        "manifest_path": str(manifest_file),
                    }
            except Exception as exc:
                logger.error(f"Failed to load manifest {manifest_file}: {exc}")

        return self._skills

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Get skill metadata by ID."""
        if not self._skills:
            self.discover_skills()
        return self._skills.get(skill_id)

    def list_skills(self) -> list[dict[str, Any]]:
        """List all discovered skills."""
        if not self._skills:
            self.discover_skills()
        return list(self._skills.values())


skill_registry = SkillRegistry()
