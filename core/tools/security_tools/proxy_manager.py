import json
import os

from core.config import settings
from core.logging_config import logger


class ProxyManager:
    """
    Manages and rotates proxies for stealth requests.
    Supports config loading and round-robin scheduling.
    """

    def __init__(self, config_path: str = "config/proxy_list.json"):
        self.config_path = config_path
        self.proxies: list[str] = []
        self.index = 0
        self._load_proxies()

    def _load_proxies(self) -> None:
        # বাংলা মন্তব্য: সেটিংস ও পরিবেশ ভেরিয়েবল উভয়ের ফলব্যাক প্রক্সি রিড করার জন্য অস.এনভাইরন যোগ করা হলো।
        env_proxies = getattr(settings, "supremeai_proxies", None) or os.environ.get(
            "SUPREMEAI_PROXIES"
        )
        if env_proxies:
            self.proxies = [p.strip() for p in env_proxies.split(",") if p.strip()]
            logger.info(f"Loaded {len(self.proxies)} proxies from environment.")
            return

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    data = json.load(f)
                    self.proxies = data.get("proxies", [])
                    logger.info(f"Loaded {len(self.proxies)} proxies from {self.config_path}.")
            except Exception as e:
                logger.error(f"Failed to read proxy config: {e}")

        # Fallback empty list
        if not self.proxies:
            logger.warning("No proxies configured. Requests will route via host IP directly.")

    def get_next_proxy(self) -> str | None:
        if not self.proxies:
            return None
        # Round-robin selection
        # বাংলা মন্তব্য: রাউন্ড-রবিন শিডিউলিংয়ের মাধ্যমে পরবর্তী প্রক্সি নির্বাচন করা হচ্ছে
        proxy = self.proxies[self.index]
        self.index = (self.index + 1) % len(self.proxies)
        return proxy

    def report_failed_proxy(self, proxy: str) -> None:
        logger.warning(f"Proxy failed execution: {proxy}. Rotating connection next step.")
