"""
Refactored constants using DynamicConfigProxy
"""

from core.config_proxy import DynamicConfigProxy


async def get_default_code_smell_thresholds(proxy: DynamicConfigProxy) -> dict:
    return await proxy.get("DEFAULT_CODE_SMELL_THRESHOLDS")


async def get_common_strings_to_ignore(proxy: DynamicConfigProxy) -> list:
    return await proxy.get("COMMON_STRINGS_TO_IGNORE")


# Centralized Constants for Magic Number Elimination
class TimeoutConfig:
    """System-wide standardized timeouts in seconds."""

    REDIS_TIMEOUT: int = 5
    DB_QUERY_TIMEOUT: int = 30
    HTTP_CLIENT_TIMEOUT: int = 15
    LLM_RESPONSE_TIMEOUT: int = 120
    CIRCUIT_BREAKER_COOLDOWN: int = 60


class RateLimitConfig:
    """System-wide rate limit defaults."""

    FREE_TIER_RPM: int = 60
    PRO_TIER_RPM: int = 600
    ENTERPRISE_TIER_RPM: int = 6000
    DEFAULT_BURST_ALLOWANCE: int = 10
