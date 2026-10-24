import json
import os
from pathlib import Path
from typing import Any

import redis.asyncio as redis
import yaml  # type: ignore

from core.logging_config import logger

# Import the unified memory interface
from core.unified_memory import unified_memory

from .tools import (
    check_env_secrets_sync,
    check_infrastructure_drift,
    check_redis_connection,
)


class SyncGuardAgent:
    def __init__(self, llm_client=None):
        """
        Initialize the SyncGuard Agent with its config and LLM client.
        """
        self.llm_client = llm_client
        self.config = self._load_config()
        self.name = self.config.get("name", "SyncGuard")

    def _load_config(self) -> dict:
        config_path = Path(__file__).parent / "config.yaml"
        with open(config_path, encoding="utf-8") as file:
            return yaml.safe_load(file)

    async def run_full_audit(self) -> dict[str, Any]:
        """
        Executes the full synchronization audit across the 10-Crore-Floor architecture.
        """
        logger.info(f"🚀 [{self.name}] Initiating System Audit...")
        audit_report = {"status": "SYNC_OK", "issues": [], "timestamp": self._get_timestamp()}

        # 1. Check Infrastructure Blueprint Sync
        infra_status = await check_infrastructure_drift("github.com/paykaribazaronline/supremeai")
        if infra_status["status"] != "matched":
            audit_report["status"] = "SYNC_FAILED"
            audit_report["issues"].append("Infrastructure Blueprint Drift Detected.")

        # 2. Check Environment Variables (Core infra + Dynamic AI provider pool check)
        required_env_keys = ["REDIS_URL", "SUPABASE_URL"]
        env_status = await check_env_secrets_sync(required_env_keys)
        if env_status["status"] != "synced":
            audit_report["status"] = "SYNC_FAILED"
            audit_report["issues"].append(f"Missing Env Secrets: {env_status['missing']}")

        # Verify whether at least one AI provider is configured (informational, not fatal)
        ai_provider_candidates = [
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "OPENROUTER_API_KEY",
            "GROQ_API_KEY",
            "MISTRAL_API_KEY",
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
            "HF_API_KEY",
            "BYNARA_API_KEY",
        ]
        has_ai_key = any(bool(os.getenv(k)) for k in ai_provider_candidates)
        if not has_ai_key:
            audit_report["issues"].append(
                "AI Providers: 0 keys configured (System operating in zero-key resilient mode)."
            )

        # 3. Check Message Broker (Upstash Redis)
        redis_alive = await check_redis_connection(os.getenv("REDIS_URL", "dummy_url"))
        if not redis_alive:
            audit_report["status"] = "SYNC_FAILED"
            audit_report["issues"].append("Redis Message Broker is unreachable.")

        # Final Decision
        if audit_report["status"] == "SYNC_FAILED":
            logger.error(f"❌ [{self.name}] AUDIT FAILED. System is out of sync!")
            logger.error(f"Details: {audit_report['issues']}")
            # Broadcast the alert to other agents via Redis Pub/Sub
            try:
                redis_url = os.getenv("REDIS_URL")
                if redis_url:
                    redis_client = redis.from_url(redis_url)
                    await redis_client.publish(
                        "supremeai:alerts:syncguard", json.dumps(audit_report)
                    )
                    await redis_client.aclose()
                    logger.info(f"📡 [{self.name}] Broadcasted SYNC_FAILED alert to Swarm.")
            except Exception as e:
                logger.warning(f"⚠️ [{self.name}] Failed to broadcast alert: {e}")
        else:
            logger.info(
                f"✅ [{self.name}] AUDIT PASSED. System is 100% synchronized and ready for scaling."
            )

        # Store the audit report in long-term memory
        # PLAN-004: write-time distillation — the dense summary + structured
        # facts replace the raw 200-char truncation; on any distiller failure
        # the call falls back to the legacy path internally (memory never lost).
        success = await unified_memory.store_long_term_memory_distilled(
            session_id=f"syncguard_audit_{audit_report['timestamp']}",  # Unique ID for this audit
            agent_type="SyncGuard",
            task_type="System_Audit",
            content=json.dumps(audit_report, indent=2),  # Store the full report
            metadata={"status": audit_report["status"]},
        )
        if success:
            logger.info(f"💾 [{self.name}] Audit report saved to Eternal Brain.")
        else:
            logger.warning(f"⚠️ [{self.name}] Failed to save audit report to Eternal Brain.")

        return audit_report

    def _get_timestamp(self):
        from datetime import datetime

        return datetime.now().strftime("%Y%m%d_%H%M%S")
