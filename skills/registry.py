import json
import os
from typing import Any

from loguru import logger


class SkillRegistry:
    """
    স্কিল রেজিস্ট্রি — Supabase DB-কে single-source-of-truth হিসেবে ব্যবহার করে।
    লোকাল JSON ফাইল শুধুমাত্র ENV=local (dev-mode) এ fallback হিসেবে রাখা হয়েছে।
    Serverless পরিবেশে (Cloud Run, Vercel) লোকাল ফাইল প্রতিটি cold-start-এ রিসেট হবে,
    তাই সেখানে DB-ই একমাত্র নির্ভরযোগ্য স্টোরেজ।
    """

    def __init__(self, registry_path: str | None = None):
        if registry_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.registry_path = os.path.join(base_dir, "data", "skills_registry.json")
        else:
            self.registry_path = registry_path

        self.skills = self._load_registry()

    def _load_registry(self) -> dict[str, Any]:
        # Environment check: local JSON fallback শুধুমাত্র dev-mode-এ
        # Serverless (Cloud Run/Vercel) পরিবেশে এটা কাজ করবে না — ফলে DB-ই মাস্টার
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning(
                    f"Could not load skills registry from {self.registry_path}: {exc}"
                )

        default_registry = {"skills": {}}

        # লোকাল JSON fallback শুধুমাত্র dev-mode (ENV=local) এ তৈরি করা হবে
        env = os.getenv("ENV", "local")
        if env == "local":
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            try:
                with open(self.registry_path, "w", encoding="utf-8") as f:
                    json.dump(default_registry, f, indent=4)
            except Exception as exc:
                logger.warning(
                    f"Could not write default skills registry to {self.registry_path}: {exc}"
                )

        return default_registry

    def register_skill(
        self,
        name: str,
        version: str,
        description: str,
        entry_point: str,
        dependencies: list[str] | None = None,
        uss: dict[str, Any] | None = None,
    ) -> bool:
        """
        একটি স্কিল নিবন্ধন করে।
        dependencies-এর জন্য None-safe ডিফল্ট ব্যবহৃত হচ্ছে (mutable default arg bug ফিক্স)।
        """
        # Fix: mutable default argument bug — None-safe initialization
        if dependencies is None:
            dependencies = []

        if uss:
            from skills.schema import UniversalSkillSchema

            try:
                UniversalSkillSchema(**uss)
            except Exception as e:
                logger.error(f"USS validation failed for skill '{name}': {e}")
                return False

        # Attempt to store in Supabase DB first (single-source-of-truth)
        # P0 (Task 9-c2): a FAILED DB write is now LOUD (ERROR log) and makes
        # register_skill return False — the caller can tell persistence failed.
        db_persisted = False
        try:
            from database.supabase_client import db

            if db.client:
                upsert_result = db.upsert_db_skill(
                    {
                        "name": name,
                        "version": version,
                        "description": description,
                        "category": uss.get("category", "general")
                        if uss
                        else "general",
                        "parameters_schema": uss.get("parameters", {}) if uss else {},
                        "metadata": uss or {},
                    }
                )
                if upsert_result is None:
                    # P0 (Task 9-c2): upsert_db_skill degrades to None on failure —
                    # treat it as the persistence failure it is.
                    logger.error(
                        f"Failed to register skill '{name}' to Supabase: upsert returned no data."
                    )
                    return False
                db_persisted = True
        except Exception as e:
            logger.error(f"Failed to register skill '{name}' to Supabase: {e}")
            return False

        # Store in local registry fallback — শুধুমাত্র dev-mode-এ
        self.skills["skills"][name] = {
            "name": name,
            "version": version,
            "description": description,
            "entry_point": entry_point,
            "dependencies": dependencies,
            "uss": uss,
        }
        env = os.getenv("ENV", "local")
        if env == "local":
            try:
                with open(self.registry_path, "w", encoding="utf-8") as f:
                    json.dump(self.skills, f, indent=4)
                return True
            except Exception as exc:
                logger.error(
                    f"Could not write skill '{name}' to local registry: {exc}"
                )
                return db_persisted
        else:
            # Serverless পরিবেশে — শুধুমাত্র DB-তে স্টোর করাই যথেষ্ট।
            # P0 (Task 9-c2): the DB is the ONLY store here, so report honestly
            # whether the skill actually reached the database.
            if db_persisted:
                logger.debug(
                    f"Skill '{name}' registered to Supabase (local file skipped in {env} mode)"
                )
            else:
                logger.error(
                    f"Skill '{name}' NOT persisted: no Supabase client available in {env} mode "
                    "(no local registry fallback outside ENV=local)."
                )
            return db_persisted

    def get_skill(self, name: str) -> dict[str, Any] | None:
        # Attempt to retrieve from Supabase DB first
        try:
            from database.supabase_client import db

            if db.client:
                skill_data = db.get_db_skill(name)
                if skill_data:
                    return {
                        "name": skill_data.get("name"),
                        "version": skill_data.get("version"),
                        "description": skill_data.get("description"),
                        "entry_point": f"skills.dynamic.{name}",
                        "dependencies": [],
                        "uss": skill_data.get("metadata"),
                    }
        except Exception as e:
            logger.debug(f"Failed to fetch skill '{name}' from Supabase: {e}")

        # Local fallback — শুধুমাত্র dev-mode-এ
        return self.skills["skills"].get(name)
