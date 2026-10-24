from core.config import settings
from core.logging_config import logger

from .interfaces import MessagingProvider
from .models import MessageEvent, MessageResult


class MockMessagingAdapter:
    """Explicit no-provider fallback for local development.

    Register 7.2 / ERR-M01 follow-up (2026-09-16): this adapter used to
    return ``success=True`` with a fresh message id while contacting NO
    provider — fabricated delivery. It now reports the truth: the message
    was NOT sent, with an explicit error naming the missing configuration.
    """

    async def send(self, event: MessageEvent) -> MessageResult:
        logger.warning(
            "MockMessagingAdapter: NOT sending message to %s — no messaging "
            "provider is configured (telegram/email unset). Delivery "
            "fabrication is disabled.",
            event.recipient,
        )
        return MessageResult(
            success=False,
            message_id=None,
            provider="mock",
            error="No messaging provider configured — message was NOT delivered.",
        )


class MessagingDispatcher:
    """
    Routes messaging operations to the configured MessagingProvider.

    Plan Section 14: existing Telegram ও Email implementations এখন
    MessagingProvider adapter হিসেবে wrapped। Dispatcher settings-এর উপর
    ভিত্তি করে adapter select করে:
      1. Telegram (যদি telegram configured)
      2. Email (যদি email configured)
      3. Mock (fallback — local dev এর জন্য)

    সব provider optional — কোনোটা configured না থাকলে Mock fallback।
    """

    _instance = None
    _provider: MessagingProvider | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_provider()
        return cls._instance

    def _initialize_provider(self) -> None:
        """
        Plan Section 14: adapter selection logic।
        প্রতিটি adapter optional — import/initialize fail করলে পরেরটা try করে।
        """
        # 1. Try Appwrite messaging (if enabled)
        if getattr(settings, "appwrite_enabled", False):
            # If we had an AppwriteMessagingAdapter, we would load it here.
            # try:
            #     from core.providers.appwrite.messaging_adapter import AppwriteMessagingAdapter
            #     self._provider = AppwriteMessagingAdapter()
            #     logger.info("MessagingDispatcher initialized with AppwriteMessagingAdapter.")
            #     return
            # except ImportError as e:
            #     logger.warning(f"Could not load AppwriteMessagingAdapter: {e}")
            pass

        # 2. Try Telegram adapter (Plan Section 14: wrap existing Telegram)
        telegram_token = getattr(settings, "telegram_bot_token", "") or ""
        if telegram_token:
            try:
                from .adapters import TelegramMessagingAdapter

                self._provider = TelegramMessagingAdapter()
                if self._provider._handler is not None:
                    logger.info("MessagingDispatcher initialized with TelegramMessagingAdapter.")
                    return
                else:
                    logger.warning("TelegramMessagingAdapter init failed — trying next provider")
                    self._provider = None
            except Exception as e:
                logger.warning(f"Could not load TelegramMessagingAdapter: {e}")

        # 3. Try Email adapter (Plan Section 14: wrap existing Email)
        email_api_key = getattr(settings, "resend_api_key", "") or ""
        if email_api_key:
            try:
                from .adapters import EmailMessagingAdapter

                self._provider = EmailMessagingAdapter()
                if self._provider._service is not None:
                    logger.info("MessagingDispatcher initialized with EmailMessagingAdapter.")
                    return
                else:
                    logger.warning("EmailMessagingAdapter init failed — trying next provider")
                    self._provider = None
            except Exception as e:
                logger.warning(f"Could not load EmailMessagingAdapter: {e}")

        # 4. Fallback to mock adapter
        self._provider = MockMessagingAdapter()
        logger.info("MessagingDispatcher initialized with MockMessagingAdapter (fallback).")

    async def send(self, event: MessageEvent) -> MessageResult:
        if not self._provider:
            return MessageResult(
                success=False, provider="none", error="No messaging provider configured"
            )
        return await self._provider.send(event)

    def get_active_provider_name(self) -> str:
        """সবচেয়ে active provider-এর নাম (observability)।"""
        if not self._provider:
            return "none"
        return getattr(self._provider, "provider", self._provider.__class__.__name__)


messaging_dispatcher = MessagingDispatcher()
