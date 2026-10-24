import enum
from typing import Any, TypeVar

from core.logging_config import logger

T = TypeVar("T", bound=enum.Enum)


class EnumGuardError(ValueError):
    """🛡️ এন্টারপ্রাইজ ভল্ট: এনাম টাইপ মিসম্যাচের জন্য এক্সপ্লোসিভ এক্সেপশন"""

    pass


class EnumGuard:
    @staticmethod
    def validate_and_parse(enum_cls: type[T], value: Any, context: str = "General") -> T:
        """🛡️ অডিটর ফিক্স: সাইলেন্ট স্ট্রিং ফলব্যাক চিরতরে বন্ধ।
        ভ্যালু ইনভ্যালিড হলে সাইলেন্টলি পাস না করে প্রপার টাইপ-সেফটি এবং এরর থ্রো করবে।
        """
        if isinstance(value, enum_cls):
            return value

        # যদি স্ট্রিং বা অন্য কোনো ফরম্যাটে থাকে, ম্যাচ করানোর চেষ্টা
        if isinstance(value, str):
            # কেস-ইনসেনসিটিভ ম্যাচিং সাপোর্ট
            normalized_value = value.strip().upper()
            for member in enum_cls:
                if (
                    member.name.upper() == normalized_value
                    or str(member.value).upper() == normalized_value
                ):
                    return member

        # 🚨 সাইলেন্ট ড্রপ প্রতিরোধ: ইনভ্যালিড ভ্যালু পেলে সাথে সাথে এক্সপ্লোসিভ এক্সেপশন থ্রো
        err_msg = f"Invalid enum value '{value}' for type '{enum_cls.__name__}' inside context: [{context}]."
        logger.error(f"🚨 [ENUM_GUARD_VIOLATION]: {err_msg}")
        raise EnumGuardError(err_msg)

    @staticmethod
    def safe_fallback(enum_cls: type[T], value: Any, fallback: T, context: str = "General") -> T:
        """যদি গ্রেসফুল ফলব্যাক লজিক্যালি এক্সপেক্টেড হয়, তবে সাইলেন্টলি না করে লগার ট্রেসসহ ফলব্যাক দেবে।"""
        try:
            return EnumGuard.validate_and_parse(enum_cls, value, context)
        except EnumGuardError:
            logger.warning(
                f"⚠️ Fallback applied for '{value}' -> using '{fallback.name}' in {context}"
            )
            return fallback
