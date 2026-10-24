from __future__ import annotations

import hashlib
import re
import traceback


def _normalize_message(msg: str) -> str:
    """বাংলা মন্তব্য: এরর মেসেজ থেকে dynamic মান (IP, UUID, সংখ্যা, hex আইডি)
    সরিয়ে ফেলা হচ্ছে যাতে একই root-cause error বারবার একই fingerprint পায় (Patch 22 fix)।
    """
    msg = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b", "<IP>", msg)
    msg = re.sub(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "<UUID>",
        msg,
    )
    msg = re.sub(r"\b0x[0-9a-fA-F]+\b", "<HEX>", msg)
    msg = re.sub(r"\d+(\.\d+)?", "<N>", msg)
    return msg


def make_fingerprint(exc: Exception) -> str:
    """
    বাংলা মন্তব্য: এক্সেপশনের টাইপ, মডিউল, ফাংশন নেম এবং মেসেজকে নরমালাইজ করে একটি অনন্য SHA-256 ফিঙ্গারপ্রিন্ট তৈরি করে।
    """
    exc_type = type(exc).__name__

    # Traceback থেকে মডিউল এবং ফাংশন নাম এক্সট্র্যাক্ট করা
    tb = exc.__traceback__
    module_name = "unknown"
    func_name = "unknown"

    if tb:
        summary = traceback.extract_tb(tb)
        if summary:
            last_frame = summary[-1]
            module_name = last_frame.filename
            func_name = last_frame.name

    # সিগনেচার নরমালাইজ করা
    msg = _normalize_message(str(exc))
    raw_sig = f"{exc_type}:{module_name}:{func_name}:{msg}"
    return hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()
