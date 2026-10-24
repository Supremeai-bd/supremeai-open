"""
SupremeAI 2.0 — Inter-Agent Knowledge Persistence Store
======================================================
বাংলা মন্তব্য: অন্যান্য AI থেকে প্রাপ্ত সমস্ত দক্ষতা এবং টিপস ফায়ারবেস/ফায়ারস্টোর ডাটাবেসে সেভ করার ইঞ্জিন।
"""

import datetime
from typing import Any

from core.logging_config import logger
from services.storage.gcp_firestore import GCPFirestoreVerificationQueue


class AgentKnowledgeStore:
    def __init__(self, collection_name: str = "ai_agent_knowledge_base"):
        self.collection_name = collection_name
        self.queue = GCPFirestoreVerificationQueue(collection_name=self.collection_name)

    def save_agent_knowledge(
        self,
        agent_name: str,
        best_skill: str,
        workflow_knowledge: str,
        best_practices: list[str],
        code_snippet_example: str = "",
    ) -> dict[str, Any]:
        """
        সংযুক্ত AI-এর শেখানো সমস্ত নলেজ ফায়ারবেস ডাটাবেসে সেভ করে।
        """
        record = {
            "agent_name": agent_name,
            "best_skill": best_skill,
            "workflow_knowledge": workflow_knowledge,
            "best_practices": best_practices,
            "code_snippet_example": code_snippet_example,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
        }

        # Firestore Database persistence
        if self.queue.mode == "firestore" and self.queue.client:
            try:
                self.queue.client.collection(self.collection_name).add(record)
                logger.info(
                    f"✅ Successfully stored AI agent knowledge for '{agent_name}' in Firestore."
                )
            except Exception as e:
                logger.error(f"Failed to store knowledge in Firestore: {e}")

        # Local fallback SQLite / verification queue
        try:
            self.queue.enqueue(task_id=f"agent_knowledge_{agent_name}", payload=record)
            logger.info(f"✅ Enqueued agent knowledge for '{agent_name}' in local store.")
        except Exception as e:
            logger.error(f"Failed to enqueue knowledge locally: {e}")

        return {"status": "success", "agent_name": agent_name, "best_skill": best_skill}
