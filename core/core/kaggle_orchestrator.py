"""
Kaggle Orchestrator - Heavy Compute Offloading System
Distributes ML/AI tasks across 6 Kaggle accounts (180 hrs/week total).

Issue #439 (Round 16): the pipeline was dead end-to-end — no dispatcher ran,
the pushed kernel body was a placeholder that fabricated success, and the
callback was both unreachable (auth middleware) and forgeable.  This module
now provides: a REAL executable kernel per task type (LoRA fine-tune / ETL /
batch inference) that reports REAL results, a per-job callback token, honest
queue lifecycle (dequeue on dispatch, retry exhaustion fails loudly), and the
hook the worker dispatcher loop consumes.
"""

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
import redis.asyncio as redis

from core.config import settings
from core.logging_config import logger


class KaggleTaskType(Enum):
    """Types of tasks that can be offloaded to Kaggle."""

    EMBEDDING_GENERATION = "embedding_generation"  # Generate vector embeddings
    MODEL_FINE_TUNING = "model_fine_tuning"  # Fine-tune LLMs
    BATCH_INFERENCE = "batch_inference"  # Bulk LLM calls
    DATA_PROCESSING = "data_processing"  # ETL jobs
    IMAGE_GENERATION = "image_generation"  # AI image creation
    TRAINING_RUN = "training_run"  # Model training
    EVALUATION = "evaluation"  # Model evaluation


class KaggleAccountStatus(Enum):
    """Status of each Kaggle account's quota."""

    AVAILABLE = "available"
    IN_USE = "in_use"
    EXHAUSTED = "exhausted"
    COOLING_DOWN = "cooling_down"


@dataclass
class KaggleAccount:
    """Represents one Kaggle account with its quota tracking."""

    account_id: str
    username: str
    api_key: str
    max_hours: float = 30.0
    used_hours: float = 0.0
    status: KaggleAccountStatus = KaggleAccountStatus.AVAILABLE
    current_task: str | None = None
    last_used: datetime | None = None

    @property
    def remaining_hours(self) -> float:
        return max(0.0, self.max_hours - self.used_hours)

    def can_accept_task(self, estimated_hours: float) -> bool:
        return (
            self.status == KaggleAccountStatus.AVAILABLE and self.remaining_hours >= estimated_hours
        )


@dataclass
class KaggleJob:
    """A job to be executed on Kaggle."""

    job_id: str
    task_type: KaggleTaskType
    payload: dict[str, Any]
    priority: int = 5  # 1-10, 10 is highest
    estimated_hours: float = 2.0
    status: str = "queued"
    created_at: datetime = field(default_factory=datetime.utcnow)
    assigned_account: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3


KERNEL_TEMPLATE = r'''#!/usr/bin/env python3
# SupremeAI Auto-Generated Kaggle Kernel (issue #439 REAL runtime)
# Job ID: __JOB_ID__
# Task Type: __TASK_TYPE__
import json
import sys
import traceback
import urllib.request
from datetime import datetime

JOB_ID = "__JOB_ID__"
CALLBACK_URL = "__CALLBACK_URL__"
CALLBACK_TOKEN = "__CALLBACK_TOKEN__"  # placeholder template
JOB_PAYLOAD = json.loads(r"""__PAYLOAD_JSON__""")


def callback(status, result=None, error=None):
    payload = {
        "job_id": JOB_ID,
        "status": status,
        "result": result or {},
        "error": error,
        "completed_at": datetime.utcnow().isoformat(),
        "kaggle_metadata": {"kernel_output": "/kaggle/working/output.json"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        CALLBACK_URL,
        data=data,
        headers={"Content-Type": "application/json", "X-Callback-Token": CALLBACK_TOKEN},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            print("callback sent:", response.read().decode()[:200])
    except Exception as exc:
        print("callback failed:", exc)


def _download_dataset(url, dest):
    if url.startswith("kaggle://"):
        import subprocess

        subprocess.run(
            ["kaggle", "datasets", "download", "-p", dest, url.split("kaggle://", 1)[1]],
            check=True,
        )
        return dest
    urllib.request.urlretrieve(url, dest)
    return dest


def run_model_training():
    """Real LoRA fine-tune (transformers + peft + datasets)."""
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "transformers", "peft", "datasets"],
        check=False,
    )
    from datasets import load_dataset
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    base_model = JOB_PAYLOAD.get("base_model", "hf-internal-testing/tiny-random-gpt2")
    hp = JOB_PAYLOAD.get("hyperparameters", {}) or {}
    epochs = int(hp.get("epochs", 1))
    lr = float(hp.get("learning_rate", 2e-4))
    batch_size = int(hp.get("batch_size", 2))
    text_field = JOB_PAYLOAD.get("text_field", "text")

    ds_url = JOB_PAYLOAD.get("dataset_url")
    ds_name = JOB_PAYLOAD.get("dataset_name")
    if ds_url:
        _download_dataset(ds_url, "/kaggle/working/dataset.jsonl")
        ds = load_dataset("json", data_files="/kaggle/working/dataset.jsonl", split="train")
    elif ds_name:
        ds = load_dataset(ds_name, split="train")
    else:
        raise ValueError("payload needs dataset_url or dataset_name")

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model)
    model = get_peft_model(
        model,
        LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, task_type="CAUSAL_LM"),
    )

    def _tok(examples):
        return tokenizer(examples[text_field], truncation=True, max_length=512)

    ds = ds.map(_tok, batched=True, remove_columns=ds.column_names)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir="/kaggle/working",
            num_train_epochs=epochs,
            learning_rate=lr,
            per_device_train_batch_size=batch_size,
            logging_steps=10,
            report_to=[],
        ),
        train_dataset=ds,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )
    train_result = trainer.train()
    trainer.save_model("/kaggle/working/adapter")

    callback(
        "success",
        result={
            "task": "model_training",
            "base_model": base_model,
            "loss": train_result.metrics.get("train_loss"),
            "epochs_trained": epochs,
            "train_runtime_s": train_result.metrics.get("train_runtime"),
            "checkpoint_path": "/kaggle/working/adapter",
        },
    )


def run_data_processing():
    """Real ETL/profile over a dataset URL."""
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pandas"], check=False)
    import pandas as pd

    ds_url = JOB_PAYLOAD.get("dataset_url")
    if not ds_url:
        raise ValueError("payload needs dataset_url")
    local = _download_dataset(ds_url, "/kaggle/working/input_data")
    if str(local).endswith(".jsonl"):
        frame = pd.read_json(local, lines=True)
    else:
        frame = pd.read_csv(local)
    profile = {
        "rows": int(len(frame)),
        "columns": list(frame.columns)[:50],
        "dtypes": {c: str(t) for c, t in list(frame.dtypes.items())[:50]},
        "null_counts": {c: int(frame[c].isna().sum()) for c in frame.columns[:50]},
    }
    frame.head(1000).to_csv("/kaggle/working/processed.csv", index=False)
    callback("success", result={"task": "data_processing", "profile": profile})


def run_batch_inference():
    """Real batch generation with a HF model."""
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "transformers"], check=False)
    from transformers import pipeline

    prompts = JOB_PAYLOAD.get("prompts") or []
    if not prompts:
        raise ValueError("payload needs prompts[]")
    base_model = JOB_PAYLOAD.get("base_model", "gpt2")
    pipe = pipeline("text-generation", model=base_model)
    outputs = [pipe(p, max_new_tokens=128)[0]["generated_text"] for p in prompts]
    callback("success", result={"task": "batch_inference", "outputs": outputs})


TASK_HANDLERS = {
    "model_fine_tuning": run_model_training,
    "training_run": run_model_training,
    "data_processing": run_data_processing,
    "batch_inference": run_batch_inference,
}


def main():
    try:
        handler = TASK_HANDLERS.get(JOB_PAYLOAD.get("task_type") or "__TASK_TYPE__")
        if handler is None:
            callback(
                "failed",
                error=(
                    "task_type not supported on the Kaggle runtime yet - honest "
                    "failure (issue #439): supported = "
                    + ", ".join(sorted(TASK_HANDLERS))
                ),
            )
            return
        handler()
    except Exception as exc:
        callback("failed", error=traceback.format_exc())


if __name__ == "__main__":
    main()
'''


class KaggleOrchestrator:
    """
    Main orchestrator for managing Kaggle job distribution.
    Implements round-robin with quota-aware scheduling.
    """

    REDIS_KEY_PREFIX = "kaggle:"
    JOB_QUEUE_KEY = f"{REDIS_KEY_PREFIX}jobs:queue"
    JOB_STATUS_KEY = f"{REDIS_KEY_PREFIX}job:{{job_id}}"
    ACCOUNT_STATUS_KEY = f"{REDIS_KEY_PREFIX}account:{{account_id}}"
    CALLBACK_URL = f"{settings.auto_backend_url.rstrip('/')}/api/v1/kaggle/callback"

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            # Initialize with accounts from settings
            accounts = []
            keys = settings.kaggle_api_keys
            for i, key in enumerate(keys):
                # Simple extraction: normally Kaggle tokens are username:key
                username = f"supremeai_worker_{i + 1}"
                api_key = key
                if ":" in key:
                    username, api_key = key.split(":", 1)

                accounts.append(
                    KaggleAccount(account_id=f"worker_{i + 1}", username=username, api_key=api_key)
                )
            cls._instance = cls(settings.redis_url, accounts)
        return cls._instance

    def __init__(self, redis_url: str, accounts: list[KaggleAccount]):
        if not redis_url:
            logger.warning("KaggleOrchestrator initialized without Redis URL. Queue will not work.")
            self.redis_client = None
        else:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)

        self.accounts = {acc.account_id: acc for acc in accounts}
        timeout_val = float(os.getenv("KAGGLE_TASK_TIMEOUT", "300.0"))
        self.http_client = httpx.AsyncClient(timeout=timeout_val)

    async def submit_job(
        self,
        task_type: KaggleTaskType,
        payload: dict[str, Any],
        priority: int = 5,
        estimated_hours: float = 2.0,
    ) -> str:
        if not self.redis_client:
            raise RuntimeError("Redis not configured for KaggleOrchestrator")

        job_id = f"job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(json.dumps(payload).encode()).hexdigest()[:8]}"

        job = KaggleJob(
            job_id=job_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            estimated_hours=estimated_hours,
        )

        job_key = self.JOB_STATUS_KEY.format(job_id=job_id)
        # Issue #439: per-job callback token.  The kernel sends it as
        # X-Callback-Token; the callback route rejects any request without it
        # (previously the callback was BOTH unreachable via auth middleware AND
        # forgeable-by-anyone once public).
        callback_token = secrets.token_hex(16)
        await self.redis_client.hset(
            job_key,
            mapping={
                "job_id": job.job_id,
                "task_type": job.task_type.value,
                "payload": json.dumps(job.payload),
                "priority": str(job.priority),
                "estimated_hours": str(job.estimated_hours),
                "status": job.status,
                "created_at": job.created_at.isoformat(),
                "retry_count": str(job.retry_count),
                "callback_token": callback_token,
            },
        )

        await self.redis_client.expire(job_key, 86400)
        await self.redis_client.zadd(self.JOB_QUEUE_KEY, {job_id: -priority})

        logger.info(f"📤 Job submitted: {job_id} ({task_type.value}, priority={priority})")
        return job_id

    async def get_callback_token(self, job_id: str) -> str | None:
        if not self.redis_client:
            return None
        return await self.redis_client.hget(
            self.JOB_STATUS_KEY.format(job_id=job_id), "callback_token"
        )

    async def get_next_job(self) -> KaggleJob | None:
        if not self.redis_client:
            return None

        results = await self.redis_client.zrange(self.JOB_QUEUE_KEY, 0, 0, withscores=True)
        if not results:
            return None

        job_id = results[0][0]
        job_key = self.JOB_STATUS_KEY.format(job_id=job_id)
        job_data = await self.redis_client.hgetall(job_key)

        if not job_data:
            await self.redis_client.zrem(self.JOB_QUEUE_KEY, job_id)
            return None

        return KaggleJob(
            job_id=job_data.get("job_id", job_id),
            task_type=KaggleTaskType(job_data.get("task_type", "data_processing")),
            payload=json.loads(job_data.get("payload", "{}")),
            priority=int(job_data.get("priority", "5")),
            estimated_hours=float(job_data.get("estimated_hours", "2.0")),
            status=job_data.get("status", "unknown"),
            created_at=datetime.fromisoformat(
                job_data.get("created_at", datetime.utcnow().isoformat())
            ),
            retry_count=int(job_data.get("retry_count", "0")),
        )

    async def select_account_for_job(self, job: KaggleJob) -> KaggleAccount | None:
        available_accounts = [
            acc for acc in self.accounts.values() if acc.can_accept_task(job.estimated_hours)
        ]

        if not available_accounts:
            logger.warning(
                f"⚠️ No account available for job {job.job_id} (needs {job.estimated_hours}h)"
            )
            return None

        available_accounts.sort(key=lambda x: x.remaining_hours, reverse=True)
        return available_accounts[0]

    async def dispatch_job_to_kaggle(self, job: KaggleJob, account: KaggleAccount) -> bool:
        if not self.redis_client:
            return False

        try:
            kernel_payload = {
                "id": f"supremeai-{job.job_id}",
                "title": f"SupremeAI: {job.task_type.value} [{job.job_id}]",
                "code": self._generate_kernel_code(
                    job, await self.get_callback_token(job.job_id) or ""
                ),
                "dataset_sources": [],
                "kernel_sources": [],
                "kernel_type": "script",
                "is_private": True,
                # GPU only for training tasks — ETL/inference run fine on CPU
                # and GPU quota is the scarce resource across the 6 accounts.
                "enable_gpu": job.task_type
                in (KaggleTaskType.MODEL_FINE_TUNING, KaggleTaskType.TRAINING_RUN),
                "enable_internet": True,
                "category_ids": [],
                "language": "python",
            }

            response = await self.http_client.post(
                "https://www.kaggle.com/api/v1/kernels/push",
                json=kernel_payload,
                headers={"Kaggle-Username": account.username, "Kaggle-Key": account.api_key},
            )

            if response.status_code in (200, 201):
                job_key = self.JOB_STATUS_KEY.format(job_id=job.job_id)
                await self.redis_client.hset(
                    job_key, mapping={"status": "running", "assigned_account": account.account_id}
                )
                # Issue #439: remove from the pending queue — get_next_job()
                # only PEEKS, so without this the dispatcher re-pushed the same
                # running job forever.
                await self.redis_client.zrem(self.JOB_QUEUE_KEY, job.job_id)

                account.status = KaggleAccountStatus.IN_USE
                account.current_task = job.job_id
                account.last_used = datetime.utcnow()

                logger.info(f"🚀 Job {job.job_id} dispatched to Kaggle account {account.username}")
                return True
            else:
                logger.error(f"❌ Failed to dispatch job: {response.text}")
                await self._record_dispatch_failure(job)
                return False

        except Exception as e:
            logger.error(f"❌ Error dispatching job: {e}")
            await self._record_dispatch_failure(job)
            return False

    async def _record_dispatch_failure(self, job: KaggleJob) -> None:
        """Track retries honestly: exhausting max_retries fails the job loudly."""
        if not self.redis_client:
            return
        job_key = self.JOB_STATUS_KEY.format(job_id=job.job_id)
        retries = int(await self.redis_client.hget(job_key, "retry_count") or "0") + 1
        if retries >= job.max_retries:
            await self.redis_client.hset(
                job_key,
                mapping={"status": "failed", "error": f"dispatch failed {retries} times"},
            )
            await self.redis_client.zrem(self.JOB_QUEUE_KEY, job.job_id)
            logger.error(f"❌ Job {job.job_id} failed after {retries} dispatch attempts")
        else:
            await self.redis_client.hset(job_key, mapping={"retry_count": str(retries)})

    def _generate_kernel_code(self, job: KaggleJob, callback_token: str = "") -> str:
        """Real, executable kernel bodies per task type (issue #439).

        The pushed kernel downloads its payload dataset, performs REAL compute
        (LoRA fine-tune / ETL / batch inference), and reports REAL results via
        the token-authenticated callback.  Unsupported task types fail
        honestly — no placeholder, no fabricated success.
        """
        code = KERNEL_TEMPLATE
        code = code.replace("__JOB_ID__", job.job_id)
        code = code.replace("__TASK_TYPE__", job.task_type.value)
        code = code.replace("__CALLBACK_URL__", self.CALLBACK_URL)
        code = code.replace("__CALLBACK_TOKEN__", callback_token)
        code = code.replace("__PAYLOAD_JSON__", json.dumps(job.payload))
        return code

    async def get_queue_stats(self) -> dict[str, Any]:
        queue_length = 0
        if self.redis_client:
            queue_length = await self.redis_client.zcard(self.JOB_QUEUE_KEY)

        account_stats = {}
        for acc_id, acc in self.accounts.items():
            account_stats[acc.username] = {
                "remaining_hours": acc.remaining_hours,
                "status": acc.status.value,
                "current_task": acc.current_task,
            }

        return {
            "queue_length": queue_length,
            "accounts": account_stats,
            "total_weekly_gpu_hours": sum(acc.max_hours for acc in self.accounts.values()),
            "total_remaining_hours": sum(acc.remaining_hours for acc in self.accounts.values()),
            "active_nodes": len(self.accounts),
        }
