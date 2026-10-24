import re
from typing import Any

from core.logging_config import logger


class BandwidthOptimizer:
    def __init__(self, cache_size: int = 100):
        self.cache_size = cache_size
        self._cache: dict[str, Any] = {}
        logger.info("Initialized BandwidthOptimizer")

    def compress_prompt(self, prompt: str, target_ratio: float = 0.5) -> str:
        original_len = len(prompt)
        compressed = prompt
        compressed = re.sub(r"\s+", " ", compressed)
        compressed = re.sub(r"[^\x00-\x7F]+", "", compressed)
        compressed = compressed.strip()
        new_len = len(compressed)
        if new_len > original_len * max(target_ratio, 0.1):
            truncated = compressed[: int(original_len * target_ratio)]
            compressed = truncated.rstrip() + "..."
        logger.debug(f"Compressed prompt from {original_len} to {len(compressed)} chars")
        return compressed

    def generate_delta_update(
        self, old_state: dict[str, Any], new_state: dict[str, Any]
    ) -> dict[str, Any]:
        delta: dict[str, Any] = {}
        for k, v in new_state.items():
            if k not in old_state or old_state[k] != v:
                delta[k] = v
        return delta

    def optimize_request(
        self, method: str, url: str, headers: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"method": method, "url": url, "headers": headers or {}}

    def cache_response(self, url: str, data: Any):
        if len(self._cache) >= self.cache_size:
            # simple LRU eviction by clearing oldest item (insertion order in Python 3.7+)
            self._cache.pop(next(iter(self._cache)))
        self._cache[url] = data

    def get_cached(self, url: str) -> Any | None:
        return self._cache.get(url)
