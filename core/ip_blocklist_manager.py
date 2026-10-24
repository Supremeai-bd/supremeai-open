from core.logging_config import logger


class IPBlocklistManager:
    """
    Dynamic IP Blocklist Manager.
    Dynamically blocks and releases malicious IPs in Upstash Redis.
    """

    def __init__(self) -> None:
        self.cooldown_seconds = 1800  # Default 30 minutes block

    def is_ip_blocked(self, ip_address: str) -> bool:
        from core import services

        if (
            hasattr(services, "redis_queue")
            and services.redis_queue
            and services.redis_queue.configured
        ):
            redis_key = f"blocklist:ip:{ip_address}"
            try:
                val = services.redis_queue.get(redis_key)
                if val is not None:
                    return val != "ok"
            except Exception as e:
                logger.error(f"Redis connection failed during is_ip_blocked: {e}")
        return False

    def block_ip(self, ip_address: str, reason: str = "suspicious_activity") -> bool:
        logger.warning(f"IPBlocklistManager: Blocking IP {ip_address} due to {reason}.")
        from core import services

        if (
            hasattr(services, "redis_queue")
            and services.redis_queue
            and services.redis_queue.configured
        ):
            redis_key = f"blocklist:ip:{ip_address}"
            try:
                services.redis_queue.set(redis_key, f"blocked:{reason}", ex=self.cooldown_seconds)
                return True
            except Exception as e:
                logger.error(f"Redis connection failed during block_ip: {e}")
        return False

    def release_ip(self, ip_address: str) -> bool:
        logger.info(f"IPBlocklistManager: Releasing block on IP {ip_address}.")
        from core import services

        if (
            hasattr(services, "redis_queue")
            and services.redis_queue
            and services.redis_queue.configured
        ):
            redis_key = f"blocklist:ip:{ip_address}"
            try:
                services.redis_queue.set(redis_key, "", ex=1)
                return True
            except Exception as e:
                logger.error(f"Redis connection failed during release_ip: {e}")
        return False


# Primary alias for backward compatibility
RulesMutator = IPBlocklistManager
