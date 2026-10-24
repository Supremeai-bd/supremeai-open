"""SupremeAI 2.0 — Custom core logging module.

বাংলা মন্তব্য: প্রজেক্টে loguru-এর উপরে ভিত্তি করে সাধারণ লগিং র‍্যাপার সরবরাহ করা হচ্ছে।
"""

from typing import Any

from core.logging_config import logger


def get_logger(name: str) -> Any:
    """Returns the standardized loguru logger instance.

    বাংলা মন্তব্য: নির্দিষ্ট মডিউলের জন্য loguru-এর স্ট্যান্ডার্ড লগার রিটার্ন করার ফাংশন।
    """
    return logger
