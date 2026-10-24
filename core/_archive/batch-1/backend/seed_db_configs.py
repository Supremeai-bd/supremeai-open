import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from core.config_cache import DEFAULT_CONFIGS
from core.logging_config import logger
from database.session import AsyncSessionLocal
from models.system_config import SystemConfig
from utils.branding import MODEL_DISPLAY, PROVIDER_DISPLAY


async def seed():
    configs_to_seed = {
        # Agent / LLM Parameters
        "LLM_MAX_TOKENS": 2048,
        "LLM_TEMPERATURE": 0.7,
        # Rate Limiting
        "rate_limit_tiers": {"Anonymous": 10, "Auth": 60, "Premium": 300, "Admin": 1000},
        "endpoint_overrides": {"/api/chat/stream": 30, "/api/ai/generate": 20},
        # Resilience & Budgets
        "RETRY_BUDGET_MAX_TOKENS": 20,
        "RETRY_BUDGET_REFILL_RATE_PER_SEC": 1.0,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_timeout_sec": 60,
        "health_monitor_interval_sec": 30,
        # Branding
        "model_branding_map": {
            "provider_display": PROVIDER_DISPLAY,
            "model_display": MODEL_DISPLAY,
        },
    }

    # Merge with DEFAULT_CONFIGS
    for k, v in DEFAULT_CONFIGS.items():
        if k not in configs_to_seed:
            configs_to_seed[k] = v

    try:
        async with AsyncSessionLocal() as session:
            for key, value in configs_to_seed.items():
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if not existing:
                    logger.info(f"Inserting new config: {key}")
                    new_config = SystemConfig(
                        key=key, value=value, description=f"Seeded config for {key}"
                    )
                    session.add(new_config)
                else:
                    logger.info(f"Config {key} already exists. Skipping.")

            await session.commit()
            logger.info("✅ Database successfully seeded with default configurations!")
    except Exception as e:
        logger.error(f"❌ Failed to seed database: {e}")


if __name__ == "__main__":
    asyncio.run(seed())
