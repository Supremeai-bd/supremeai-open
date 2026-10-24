# backend/core/llm/llm_gateway/resilience.py
"""Circuit-breaker integration + 429 rate-limit handling.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py into
the ResilienceMixin used by LLMGateway (core/llm/llm_gateway/gateway.py).
"""

import asyncio
import random

import httpx

from core.logging_config import logger

from ...resilience.circuit_breaker import (
    CircuitBreaker,  # Fixed import path - using relative import
)


class ResilienceMixin:
    """Circuit-breaker + rate-limit methods for LLMGateway (verbatim move)."""

    def _get_or_create_circuit_breaker(self, current_model: str) -> CircuitBreaker:
        # Use the centralized circuit breaker manager
        return self._circuit_breaker_manager(current_model)

    async def _handle_rate_limit_error(
        self, current_model: str, exc: httpx.HTTPStatusError
    ) -> bool:
        """Handle 429 rate limit errors by reading Retry-After header and pausing appropriately."""
        if exc.response.status_code == 429:
            logger.warning(
                f"[LLMGateway] Rate limit hit for {current_model}, reading Retry-After header..."
            )

            # Extract Retry-After header
            retry_after = exc.response.headers.get("Retry-After")
            if retry_after:
                try:
                    pause_seconds = int(retry_after)
                except ValueError:
                    # If Retry-After is in date format, calculate difference
                    try:
                        import time
                        from email.utils import parsedate_to_datetime

                        retry_time = parsedate_to_datetime(retry_after)
                        pause_seconds = int(retry_time.timestamp() - time.time())
                        pause_seconds = max(pause_seconds, 1)  # Ensure at least 1 second
                    except (ValueError, TypeError):
                        # Default fallback if parsing fails
                        pause_seconds = 60
            else:
                # Default pause if no Retry-After header
                pause_seconds = 60

            logger.info(
                f"[LLMGateway] Pausing {current_model} for {pause_seconds}s due to rate limit"
            )

            # Update free tier tracker to mark rate limit
            try:
                from core.llm.free_tier_tracker import get_tracker

                tracker = get_tracker()
                # Map model name to provider key for the tracker
                provider_key = (
                    current_model.split("/")[0] if "/" in current_model else current_model
                )
                tracker.mark_rate_limited(provider_key, pause_seconds=pause_seconds)
            except Exception as tracker_exc:
                logger.warning(
                    f"[LLMGateway] Could not update tracker for rate limit: {tracker_exc}"
                )

            # Fail-fast OmniRoute logic: If pause is too long, skip to next model
            if pause_seconds > 3:
                logger.warning(
                    f"[LLMGateway] Rate limit pause ({pause_seconds}s) is too long for {current_model}. Skipping to next model in combo."
                )
                return False

            # Apply jittered backoff to avoid thundering herd
            jitter = random.uniform(0.1, 0.3) * pause_seconds  # Add 10-30% jitter
            backoff_time = pause_seconds + jitter
            logger.info(
                f"[LLMGateway] Applying backoff with jitter: {backoff_time:.2f}s for {current_model}"
            )
            await asyncio.sleep(backoff_time)
            return True
        return False
