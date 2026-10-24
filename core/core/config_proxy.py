"""This module provides the `DynamicConfigProxy` class, which is central to
managing tenant-specific runtime configuration settings within the SupremeAI
ecosystem. It facilitates the dynamic retrieval and caching of configuration
parameters from a database, ensuring that each tenant can operate with its own
customized settings. The proxy implements a time-based caching mechanism to
optimize database access and includes robust error handling and fallback
defaults, making it a critical component for supporting multi-tenancy and
adaptable AI agent behavior.

Key Components:
- `DynamicConfigProxy`: Manages tenant-specific dynamic configuration, including caching, database retrieval, and fallback defaults.
- `get()`: Retrieves a configuration value for the current tenant, refreshing the internal cache if its Time-To-Live (TTL) has expired.
- `_refresh_cache()`: Asynchronously fetches the latest configuration settings for the tenant from the database and updates the internal cache.

Dependencies:
- `asyncio`: For handling asynchronous database operations.
- `datetime`: For managing cache expiry times.
- `timedelta`: For defining the cache Time-To-Live (TTL).
- `typing`: For type hinting.
- `loguru`: For structured logging of errors and information."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from core.logging_config import logger
from core.utils.time_utils import utc_now


class DynamicConfigProxy:
    def __init__(self, tenant_id: str, db: Any):
        self._tenant_id = tenant_id
        self._db = db
        self._cache = {}
        self._expiry = datetime.min.replace(tzinfo=UTC)

    async def get(self, key: str, default: Any = None) -> Any:
        # TTL চেক (১ মিনিট)
        if utc_now() > self._expiry:
            await self._refresh_cache()

        return self._cache.get(key, default)

    async def _refresh_cache(self):
        try:
            doc_ref = self._db.collection(f"tenants/{self._tenant_id}/config/runtime").document(
                "settings"
            )

            # handle both sync and async get() based on the db client
            if asyncio.iscoroutinefunction(doc_ref.get):
                snapshot = await doc_ref.get()
            else:
                snapshot = doc_ref.get()

            if snapshot.exists:
                self._cache = snapshot.to_dict()
                self._expiry = utc_now() + timedelta(minutes=1)
            else:
                # Source defaults from centralized config_cache instead of hardcoded dummy data
                from core.config_cache import config_cache

                self._cache = {
                    "DEFAULT_CODE_SMELL_THRESHOLDS": config_cache.get(
                        "DEFAULT_CODE_SMELL_THRESHOLDS",
                        default={
                            "complexity": 10,
                            "lines": 75,
                            "args": 5,
                            "class_methods": 15,
                        },
                    ),
                    "COMMON_STRINGS_TO_IGNORE": config_cache.get(
                        "COMMON_STRINGS_TO_IGNORE",
                        default=[
                            "",
                            "utf-8",
                            "rb",
                            "wb",
                            "r",
                            "w",
                            "a",
                            "x",
                            "b",
                            "t",
                            "+",
                        ],
                    ),
                }
                self._expiry = utc_now() + timedelta(minutes=1)
        except Exception as e:
            logger.error(f"Failed to refresh config from DB: {e}")
            raise RuntimeError(f"Failed to refresh config from DB: {e}") from e
