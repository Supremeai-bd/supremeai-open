from __future__ import annotations

from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class UpstashRedisQueue:
    def __init__(
        self,
        rest_url: str | None = None,
        token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.rest_url = (rest_url or getattr(settings, "upstash_redis_rest_url", "") or "").rstrip(
            "/"
        )
        self.token = token or getattr(settings, "upstash_redis_rest_token", "") or ""
        self.timeout = timeout
        # বাংলা মন্তব্য: Upstash Rest Queue ক্লায়েন্টে সর্বোচ্চ ১০টি কানেকশন এবং ৫টি কিপ-অলাইভ কানেকশনের সীমা যুক্ত করা হলো।
        self._client = (
            httpx.Client(
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                timeout=self.timeout,
            )
            if (self.rest_url and self.token)
            or (hasattr(settings, "upstash_redis_rest_pool") and settings.upstash_redis_rest_pool)
            else None
        )
        self._active_pool_idx = 0

    @property
    def configured(self) -> bool:
        return bool(self._client)

    def _request(self, *args: str) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError(
                "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are not configured"
            )

        # Issue #754 (MA-04): multi-account federation failover across all 5 Upstash instances
        pool = getattr(settings, "upstash_redis_rest_pool", [])
        endpoints = (
            pool
            if pool
            else ([(self.rest_url, self.token)] if (self.rest_url and self.token) else [])
        )
        if not endpoints:
            raise RuntimeError("No configured Upstash Redis REST endpoints available")

        last_err: Exception | None = None
        for i in range(len(endpoints)):
            idx = (self._active_pool_idx + i) % len(endpoints)
            target_url, target_token = endpoints[idx]
            try:
                response = self._client.post(
                    target_url,
                    headers={"Authorization": f"Bearer {target_token}"},
                    json=list(args),
                )
                response.raise_for_status()
                if idx != self._active_pool_idx:
                    self._active_pool_idx = idx
                return response.json()
            except Exception as exc:
                last_err = exc
                logger.warning(f"Upstash Redis REST instance {idx} failed ({exc}); failing over...")

        if last_err:
            raise last_err
        return {}

    # বাংলা মন্তব্য: SET NX EX মেকানিজম ইমপ্লিমেন্ট করা হলো যা শুধুমাত্র কী না থাকলে লক সেট করবে
    def set_nx(self, key: str, value: str, ex: int | None = None) -> bool:
        if not self.configured:
            return False
        try:
            command: list[Any] = ["SET", key, value, "NX"]
            if ex:
                command.extend(["EX", str(ex)])
            response = self._request(*command)
            # Upstash REST-এর ক্ষেত্রে সেট সফল হলে {"result": "OK"} অন্যথায় {"result": null} আসে
            return response.get("result") == "OK"
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis SET NX failed: {exc}")
            return False

    # বাংলা মন্তব্য: Lua Script এক্সিকিউট করার জন্য EVAL কমান্ড সাপোর্ট যুক্ত করা হলো
    def eval(self, script: str, numkeys: int, *args: str) -> Any:
        if not self.configured:
            return None
        try:
            command: list[Any] = ["EVAL", script, str(numkeys)]
            command.extend(args)
            response = self._request(*command)
            return response.get("result")
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis EVAL failed: {exc}")
            return None

    def get(self, key: str) -> str | None:
        if not self.configured:
            return None
        try:
            return self._request("GET", key).get("result")
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis GET failed: {exc}")
            return None

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        if not self.configured:
            return False
        try:
            command: list[Any] = ["SET", key, value]
            if ex:
                command.extend(["EX", ex])
            self._request(*command)
            return True
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis SET failed: {exc}")
            return False

    def incr(self, key: str) -> int | None:
        if not self.configured:
            return None
        try:
            result = self._request("INCR", key).get("result")
            return int(result) if result is not None else None
        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            RuntimeError,
            ValueError,
        ) as exc:
            logger.error(f"Upstash Redis INCR failed: {exc}")
            return None

    def decr(self, key: str) -> int | None:
        if not self.configured:
            return None
        try:
            result = self._request("DECR", key).get("result")
            return int(result) if result is not None else None
        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            RuntimeError,
            ValueError,
        ) as exc:
            logger.error(f"Upstash Redis DECR failed: {exc}")
            return None

    def expire(self, key: str, ttl: int) -> bool:
        if not self.configured:
            return False
        try:
            self._request("EXPIRE", key, str(ttl))
            return True
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis EXPIRE failed: {exc}")
            return False

    def publish(self, channel: str, message: str) -> bool:
        if not self.configured:
            return False
        try:
            self._request("PUBLISH", channel, message)
            return True
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis PUBLISH failed: {exc}")
            return False

    def lpush(self, key: str, value: str) -> int | None:
        if not self.configured:
            return None
        try:
            result = self._request("LPUSH", key, value).get("result")
            return int(result) if result is not None else None
        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            RuntimeError,
            ValueError,
        ) as exc:
            logger.error(f"Upstash Redis LPUSH failed: {exc}")
            return None

    def rpop(self, key: str) -> str | None:
        if not self.configured:
            return None
        try:
            return self._request("RPOP", key).get("result")
        except (httpx.RequestError, httpx.HTTPStatusError, RuntimeError) as exc:
            logger.error(f"Upstash Redis RPOP failed: {exc}")
            return None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
