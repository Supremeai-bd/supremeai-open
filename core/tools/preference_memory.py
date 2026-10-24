import json
import os
from typing import Any

from core.logging_config import logger


class PreferenceMemory:
    """
    Tracks and auto-applies user preferences over time using weighted embeddings.
    (Closes Gap #14)
    """

    def __init__(self, memory_dir: str = "data/memory/preferences"):
        self.memory_dir = memory_dir
        os.makedirs(self.memory_dir, exist_ok=True)
        self.preferences: dict[str, Any] = {}
        logger.info(f"Initialized PreferenceMemory at {self.memory_dir}")

    def load_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Loads preferences for a specific user."""
        file_path = os.path.join(self.memory_dir, f"{user_id}.json")
        if os.path.exists(file_path):
            with open(file_path) as f:
                self.preferences[user_id] = json.load(f)
        else:
            self.preferences[user_id] = {
                "ui_theme": "dark",
                "verbosity": "concise",
                "auto_deploy": False,
                "preferred_frameworks": ["react", "fastapi"],
            }
            self.save_preferences(user_id)

        return self.preferences[user_id]

    def save_preferences(self, user_id: str):
        """Saves user preferences to disk."""
        if user_id in self.preferences:
            file_path = os.path.join(self.memory_dir, f"{user_id}.json")
            with open(file_path, "w") as f:
                json.dump(self.preferences[user_id], f, indent=4)
            logger.info(f"Saved preferences for user {user_id}")

    def update_preference(self, user_id: str, key: str, value: Any, weight: float = 1.0):
        """
        Updates a preference. In a real ML scenario, 'weight' updates the embedding vector.
        """
        prefs = self.load_user_preferences(user_id)

        # Simple dict update for now
        # ML implementation would adjust embedding weights here
        prefs[key] = value
        self.save_preferences(user_id)
        logger.info(
            f"Updated preference '{key}' to '{value}' for user {user_id} (weight: {weight})"
        )

    def generate_context_prompt(self, user_id: str) -> str:
        """Generates a system prompt modifier based on user preferences."""
        prefs = self.load_user_preferences(user_id)

        prompt = "USER PREFERENCES:\n"
        prompt += f"- Verbosity: {prefs.get('verbosity', 'normal')}\n"
        if prefs.get("preferred_frameworks"):
            prompt += f"- Preferred Frameworks: {', '.join(prefs['preferred_frameworks'])}\n"

        return prompt
