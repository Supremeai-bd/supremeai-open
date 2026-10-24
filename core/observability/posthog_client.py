import os

import posthog

from core.logging_config import logger


class PostHogClient:
    def __init__(self):
        self.api_key = os.getenv("POSTHOG_API_KEY", "")
        self.host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
        self.enabled = bool(self.api_key)

        if self.enabled:
            try:
                posthog.project_api_key = self.api_key
                posthog.host = self.host
                logger.info("Initialized PostHog Analytics Client")
            except (ConnectionError, ValueError, RuntimeError) as e:
                # সুনির্দিষ্ট নেটওয়ার্ক বা ভ্যালুয়েশন ত্রুটি ক্যাচ করা হলো
                logger.error(f"Failed to initialize PostHog: {e}")
                self.enabled = False
        else:
            logger.info("POSTHOG_API_KEY not set. PostHog analytics running in mock/log mode.")

    def capture(self, distinct_id: str, event: str, properties: dict | None = None):
        if self.enabled:
            try:
                posthog.capture(distinct_id, event, properties or {})
            except (ConnectionError, ValueError, RuntimeError) as e:
                # সুনির্দিষ্ট ত্রুটি ক্যাচ করা হলো, যাতে কোনো ক্রিটিকাল এরর চাপা না পড়ে
                logger.error(f"PostHog capture failed: {e}")
        else:
            logger.debug(
                f"[Mock Analytics] User: {distinct_id} | Event: {event} | Props: {properties}"
            )


posthog_client = PostHogClient()
