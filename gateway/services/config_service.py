import asyncio
import json
import weakref

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.logging_config import logger
from models.system_config import SystemConfig
from services.config_registry import get_definition, safe_defaults, validate_value


class ConfigService:
    """Resilient L1-L4 configuration service.

    L1 is Redis, L2 is PostgreSQL, L3 is the process-local last-known-good
    snapshot, and L4 is the immutable registry default.
    """

    CACHE_PREFIX = "sys_config:"
    DEFAULT_TTL = 300
    _last_known_good: dict[str, object] = {}

    # A SQLAlchemy AsyncSession cannot execute overlapping operations. Several
    # startup/config-sync paths can legitimately ask for different keys using
    # the same session, so protect only the DB section per session rather than
    # serializing Redis lookups or all sessions globally.
    _db_locks: "weakref.WeakKeyDictionary[AsyncSession, asyncio.Lock]" = weakref.WeakKeyDictionary()

    @classmethod
    def _get_db_lock(cls, db: AsyncSession) -> asyncio.Lock:
        lock = cls._db_locks.get(db)
        if lock is None:
            lock = asyncio.Lock()
            cls._db_locks[db] = lock
        return lock

    @classmethod
    async def get_config(cls, db: AsyncSession, key: str, default: any = None) -> any:
        """Read a config value through the L1-L4 fallback chain."""
        definition = get_definition(key)
        fallback = default if default is not None else (definition.default if definition else None)
        cache_key = f"{cls.CACHE_PREFIX}{key}"
        redis = None

        try:
            from core.optimization.optimized_redis_client import get_redis_client

            redis = await get_redis_client()
            if redis:
                cached_val = await redis.execute_with_retry("get", cache_key)
                if cached_val is not None:
                    try:
                        value = json.loads(cached_val)
                    except json.JSONDecodeError:
                        value = cached_val
                    try:
                        value = validate_value(key, value) if definition else value
                    except (KeyError, ValueError):
                        value = None
                    if value is not None:
                        cls._last_known_good[key] = value
                        return value
        except Exception as e:
            logger.warning(f"Redis cache error when getting config {key}: {e}")

        if db is None:
            return cls._last_known_good.get(key, fallback)

        try:
            async with cls._get_db_lock(db):
                result = await db.execute(
                    select(SystemConfig).where(SystemConfig.key == key, SystemConfig.is_active)
                )
                config = result.scalars().first()
                val = config.value if config is not None else fallback
                if definition and config is not None:
                    val = validate_value(key, val)
            cls._last_known_good[key] = val
            if redis and config is not None:
                try:
                    await redis.execute_with_retry(
                        "setex",
                        cache_key,
                        cls.DEFAULT_TTL,
                        json.dumps(val) if not isinstance(val, str) else val,
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache config {key} in Redis: {e}")
            return val
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid config value for {key}: {e}")
            return cls._last_known_good.get(key, fallback)
        except Exception as e:
            logger.error(f"DB error fetching config {key}: {e}")
            return cls._last_known_good.get(key, fallback)

    @classmethod
    def get_config_sync(cls, db: Session, key: str, default: any = None) -> any:
        """Synchronous version for when async is not available, bypasses Redis caching for simplicity."""
        if db is None:
            return default

        try:
            config = (
                db.query(SystemConfig)
                .filter(SystemConfig.key == key, SystemConfig.is_active)
                .first()
            )
            if config is not None:
                return config.value
            return default
        except Exception as e:
            logger.error(f"DB error fetching config sync {key}: {e}")
            return default
