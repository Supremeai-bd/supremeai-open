import datetime
import json
import os
from typing import Any

from core.logging_config import logger


class RLHFPipeline:
    def __init__(self, storage_dir: str = "data/rlhf"):
        self.preference_logs: list[dict[str, Any]] = []
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        logger.info("Initialized RLHFPipeline")
        self._load_existing_preferences()

    def _load_existing_preferences(self):
        path = os.path.join(self.storage_dir, "preferences.jsonl")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            self.preference_logs.append(json.loads(line))
                logger.info(f"Loaded {len(self.preference_logs)} existing local preference records")
            except Exception as e:
                logger.error(f"Failed to load existing preferences: {e}")

        # Firestore sync if available
        try:
            from services.storage.gcp_firestore import GCPFirestoreVerificationQueue

            queue = GCPFirestoreVerificationQueue(collection_name="ai_rlhf_preferences")
            if queue.mode == "firestore" and queue.client:
                docs = queue.client.collection("ai_rlhf_preferences").limit(100).stream()
                fs_count = 0
                for doc in docs:
                    data = doc.to_dict()
                    if data and "prompt" in data:
                        self.preference_logs.append(data)
                        fs_count += 1
                logger.info(
                    f"Synced {fs_count} preference records from Firestore 'ai_rlhf_preferences'"
                )
        except Exception as err:
            logger.debug(f"Firestore sync skipped or not configured: {err}")

    def record_preference(
        self, prompt: str, chosen_response: str, rejected_response: str
    ) -> dict[str, Any]:
        logger.debug("Recording RLHF preference data point.")
        record = {
            "prompt": prompt,
            "chosen": chosen_response,
            "rejected": rejected_response,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
            # বাংলা: provenance ছাড়া training record পরে audit/trace করা যায় না
            # (HUMAN_BEHAVIOR §15 Phase 3; Constitution: Reversible Evolution)
            "dataset_version": datetime.datetime.now(datetime.UTC).strftime("%Y%m%d"),
            "source": "runtime_feedback",
        }
        self.preference_logs.append(record)
        path = os.path.join(self.storage_dir, "preferences.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        # Save automatically to Firestore database for continuous cross-platform persistence
        try:
            from services.storage.gcp_firestore import GCPFirestoreVerificationQueue

            queue = GCPFirestoreVerificationQueue(collection_name="ai_rlhf_preferences")
            if queue.mode == "firestore" and queue.client:
                queue.client.collection("ai_rlhf_preferences").add(record)
                logger.info("Successfully persisted preference record to Firestore database.")
        except Exception as err:
            logger.debug(f"Firestore auto-save skipped: {err}")

        return {"status": "success", "recorded": len(self.preference_logs)}

    async def export_dpo_dataset(self, output_path: str | None = None) -> dict[str, Any]:
        if not self.preference_logs:
            logger.warning("No preference data to export.")
            return {"status": "error", "error": "No preference data to export."}
        output_path = output_path or os.path.join(self.storage_dir, "dpo_dataset.jsonl")
        logger.info(f"Exporting {len(self.preference_logs)} DPO records to {output_path}")
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for log in self.preference_logs:
                    f.write(json.dumps(log) + "\n")
            return {
                "status": "success",
                "exported": len(self.preference_logs),
                "output_path": output_path,
            }
        except Exception as exc:
            logger.error(f"DPO export failed: {exc}")
            return {"status": "error", "error": str(exc)}

    async def trigger_dpo_training(self, base_model: str = "gpt2") -> dict[str, Any]:
        """
        Triggers HuggingFace TRL DPOTrainer either locally if trl is installed,
        or delegates to ModelTrainer (RunPod/Modal).

        বাংলা: Constitution লঙ্ঘন ছিল — (1) ডেটা না থাকলে ভুয়া preference record
        ("Hello"/"Chosen response") ইনজেক্ট করা হতো, (2) TRL পাওয়া গেলে কোনো
        training না করেই "simulation success" রিটার্ন করা হতো (Verification
        Before Trust ভঙ্গ)। এখন দুটোই বন্ধ — ডেটা না থাকলে স্পষ্ট error,
        লোকাল wiring না থাকলে সৎ not_implemented, নয়তো আসল ModelTrainer path।
        """
        dataset_path = os.path.join(self.storage_dir, "preferences.jsonl")
        if not os.path.exists(dataset_path) or len(self.preference_logs) == 0:
            logger.error(
                "DPO training refused: no preference data available. "
                "Refusing to train on fabricated records (Constitution: Verification Before Trust)."
            )
            return {
                "status": "error",
                "error": "No preference data available; collect real feedback before training.",
            }

        logger.info(f"Triggering DPO training on {base_model} using {dataset_path}")

        try:
            # Attempt to check if TRL and dependencies are available
            import importlib.util

            if (
                importlib.util.find_spec("trl") is not None
                and importlib.util.find_spec("torch") is not None
                and importlib.util.find_spec("transformers") is not None
            ):
                # বাংলা: লোকাল DPOTrainer wiring এখনো implemented নয় — আগে এখানে
                # training না করেই success ফেরত দেওয়া হতো। এখন সৎভাবে স্বীকার করি
                # এবং caller সত্যিকারের remote path বেছে নিতে পারে।
                logger.warning(
                    "trl is installed but local DPOTrainer wiring is not implemented; "
                    "not fabricating a simulated success."
                )
                return {
                    "status": "not_implemented",
                    "method": "local_trl",
                    "message": (
                        "Local TRL DPOTrainer wiring is not implemented yet; "
                        "use ModelTrainer delegation for real training."
                    ),
                }
            else:
                raise ImportError("trl or dependencies missing")
        except ImportError:
            # Fallback to model trainer (RunPod/Modal Serverless)
            logger.warning("trl library not found locally. Delegating DPO job to ModelTrainer.")
            from tools.learning.model_trainer import ModelTrainer

            trainer = ModelTrainer()
            res = await trainer.trigger_lora_finetune(dataset_path, base_model)
            # Issue #440 fix: the delegation previously rewrapped EVERY result
            # as "success" — propagating the local-simulation fake.  Propagate
            # the honest status instead.
            if res.get("status") != "success":
                return {
                    "status": res.get("status", "error"),
                    "method": "model_trainer_delegation",
                    "message": res.get("message", "ModelTrainer could not start the DPO/LoRA job"),
                }
            return {
                "status": "success",
                "method": "model_trainer_delegation",
                "job_id": res.get("job_id"),
                "provider": res.get("provider"),
            }
