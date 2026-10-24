import os
import uuid
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class ModelTrainer:
    def __init__(self, provider: str = "auto"):
        self.provider = "auto"
        if provider in ("runpod", "modal", "docker"):
            self.provider = provider
        elif getattr(settings, "runpod_api_key", None):
            self.provider = "runpod"
        elif getattr(settings, "modal_token_id", None) and getattr(
            settings, "modal_token_secret", None
        ):
            self.provider = "modal"
        else:
            self.provider = "local"
        logger.info(f"Initialized ModelTrainer with provider {self.provider}")

    async def trigger_lora_finetune(
        self, dataset_path: str, base_model: str = "llama3-8b"
    ) -> dict[str, Any]:
        # Issue #440 fix: the old code silently WROTE A FAKE 1-row dataset
        # ("hello"→"world") when the path was missing and then trained on it —
        # fabricated data → fabricated model.  Missing dataset is a loud error.
        if not os.path.exists(dataset_path):
            raise FileNotFoundError(
                f"Dataset not found: {dataset_path} — refusing to fabricate one "
                "(issue #440). Provide a real JSONL dataset."
            )

        logger.info(
            f"Triggering {base_model} LoRA fine-tune on {self.provider} using {dataset_path}"
        )
        job_id = f"ft-job-{uuid.uuid4().hex[:8]}"

        if self.provider == "runpod":
            api_key = getattr(settings, "runpod_api_key", None)
            endpoint_id = getattr(settings, "runpod_endpoint_id", "unsloth-training")
            if not api_key:
                raise RuntimeError("RUNPOD_API_KEY required for RunPod training.")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "input": {
                    "job_id": job_id,
                    "dataset_path": dataset_path,
                    "base_model": base_model,
                    "hyperparameters": {
                        "learning_rate": 2e-4,
                        "epochs": 3,
                        "batch_size": 2,
                    },
                }
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://api.runpod.ai/v2/{endpoint_id}/run",
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                if resp.status_code not in (200, 201):
                    raise RuntimeError(f"RunPod execution failed: {resp.text}")
                data = resp.json()
                job_id = data.get("id", job_id)
                logger.info(f"RunPod training job queued: {job_id}")

        elif self.provider == "modal":
            modal_url = getattr(settings, "modal_finetune_webhook_url", None)
            if not modal_url:
                modal_url = "https://supremeai--finetune-trigger.modal.run"

            # বাংলা মন্তব্য: MyPy no-redef এড়াতে modal_payload নামে নতুন variable ব্যবহার করা হলো
            modal_payload: dict[str, str] = {
                "job_id": job_id,
                "dataset_path": dataset_path,
                "base_model": base_model,
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(modal_url, json=modal_payload, timeout=30.0)
                if resp.status_code not in (200, 201):
                    raise RuntimeError(f"Modal execution failed: {resp.text}")
                logger.info(f"Modal training job queued: {job_id}")
        else:
            # Issue #440 fix: "local" previously logged a "simulation" line and
            # returned success — nothing ran.  Honest not_implemented now.
            return {
                "status": "not_implemented",
                "job_id": job_id,
                "base_model": base_model,
                "provider": self.provider,
                "dataset": dataset_path,
                "message": (
                    "Local training is not implemented (512MB container, heavy "
                    "deps excluded by policy). Configure RUNPOD_API_KEY or MODAL "
                    "credentials, or offload to the Kaggle pipeline."
                ),
            }

        return {
            "status": "success",
            "job_id": job_id,
            "base_model": base_model,
            "provider": self.provider,
            "dataset": dataset_path,
            "message": f"Training initiated on {self.provider}.",
        }

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        logger.info(f"Checking training job status: {job_id}")
        if self.provider == "runpod":
            api_key = getattr(settings, "runpod_api_key", None)
            endpoint_id = getattr(settings, "runpod_endpoint_id", "unsloth-training")
            if api_key:
                headers = {"Authorization": f"Bearer {api_key}"}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}",
                        headers=headers,
                        timeout=15.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "IN_QUEUE").lower()
                        if status == "completed":
                            output = data.get("output", {}) or {}
                            # Issue #440 fix: report ONLY real fields from the
                            # provider — the old code fell back to a hardcoded
                            # loss=0.12 and an unverified checkpoint path.
                            result: dict[str, Any] = {
                                "status": "completed",
                                "job_id": job_id,
                            }
                            if output.get("loss") is not None:
                                result["loss"] = output["loss"]
                            if output.get("checkpoint_path") or output.get("checkpoint"):
                                result["checkpoint_path"] = output.get(
                                    "checkpoint_path"
                                ) or output.get("checkpoint")
                            if output.get("epochs_trained") is not None:
                                result["epochs_trained"] = output["epochs_trained"]
                            return result
                        return {"status": status, "job_id": job_id, "raw_status": data}

                # বাংলা মন্তব্য: non-200 response — fabricated "completed" এর বদলে honest "unknown" (Patch 23 fix)
                logger.warning(f"RunPod status check for {job_id} returned HTTP {resp.status_code}")
                return {
                    "status": "unknown",
                    "job_id": job_id,
                    "message": "Could not verify job status",
                }

        if self.provider == "local":
            # বাংলা মন্তব্য: local training কখনো বাস্তবে চালানো হয়নি (simulation-only) —
            # তাই "completed"/loss fabricate করা হচ্ছে না।
            return {
                "status": "not_implemented",
                "job_id": job_id,
                "message": "Local training is simulated only — no real checkpoint was produced. Configure RUNPOD_API_KEY or MODAL credentials for real training.",
            }

        return {
            "status": "unknown",
            "job_id": job_id,
            "message": "Unable to verify job status for this provider",
        }

    async def learn_from_execution_failure(
        self, fingerprint: str, trace_stack: str, fix_applied: str
    ) -> bool:
        """PERSIST the failure-to-fix pattern in the experience store so
        self-healing can actually retrieve it later (issue #440 fix: the old
        implementation logged a "learned" line and returned True while storing
        NOTHING)."""
        try:
            from adaptive_engine.experience_db import Experience, ExperienceDatabase

            db = ExperienceDatabase()
            exp = Experience(
                request=f"execution-failure:{fingerprint}",
                context={
                    "fingerprint": fingerprint,
                    "trace": (trace_stack or "")[:2000],
                    "kind": "self_heal_fix_pattern",
                },
                action_taken=(fix_applied or "")[:1000],
                result="success",
            )
            stored_id = db.record_experience(exp)
            if not stored_id:
                logger.warning(
                    "ModelTrainer: fix pattern for %s NOT persisted (store unavailable)",
                    fingerprint[:8],
                )
                return False
            logger.info(
                "ModelTrainer: fix pattern for fingerprint %s persisted (id=%s)",
                fingerprint[:8],
                stored_id,
            )
            return True
        except Exception as exc:
            logger.error(f"ModelTrainer learn_from_execution_failure failed: {exc}")
            return False

    async def retrieve_similar_fix(self, current_trace: str) -> list[str]:
        """Retrieve persisted fix patterns similar to the current error trace
        from the experience store (issue #440 fix: the old implementation
        always returned [] - the store was never queried)."""
        try:
            from adaptive_engine.experience_db import ExperienceDatabase

            if not (current_trace or "").strip():
                return []
            db = ExperienceDatabase()
            hits = db.find_similar(query=current_trace[:500], limit=3, threshold=0.55)
            fixes = [
                str(h.get("response") or h.get("text") or "").strip()
                for h in hits
                if isinstance(h, dict)
            ]
            return [f for f in fixes if f]
        except Exception as exc:
            logger.warning(f"ModelTrainer retrieve_similar_fix failed (honest empty): {exc}")
            return []
