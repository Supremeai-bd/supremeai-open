"""
পরিবেশ সনাক্তকরণ ইউটিলিটি — টেস্ট এনভায়রনমেন্ট চেক এবং অ্যাডমিন অথেন্টিকেশন
যাচাইয়ের জন্য একক উৎস (single source of truth)।

আগে প্রতিটি মডিউলে `"pytest" in sys.modules or os.getenv("ENV") == "test"` এবং
`os.getenv("ADMIN_AUTHORIZED", "false").lower() == "true"` বারবার লেখা হতো।
এখন এই শেয়ার্ড ফাংশনগুলো ব্যবহার করলে কোড DRY এবং রক্ষণাবেক্ষণযোগ্য হবে।
"""

import os
import sys

from core.config import settings


def is_test_environment() -> bool:
    """বর্তমান প্রসেসটি টেস্ট এনভায়রনমেন্টে চলছে কিনা তা যাচাই করে।

    প্রোডাকশন বা স্টেজিং এনভায়রনমেন্ট হলে সরাসরি False রিটার্ন করবে।
    অন্যথায় pytest লোডেড থাকলে True রিটার্ন করে।
    """
    if os.getenv("ENV", "").lower() in {"production", "staging"}:
        return False
    return "pytest" in sys.modules or os.getenv("TESTING", "").lower() in {
        "1",
        "true",
        "yes",
    }


def is_admin_authorized() -> bool:
    """অ্যাডমিন অপারেশনের অনুমোদন আছে কিনা তা যাচাই করে।

    ADMIN_AUTHORIZED এনভায়রনমেন্ট ভ্যারিয়েবলের ভিত্তিতে সিদ্ধান্ত নেয়।
    """
    if "ADMIN_AUTHORIZED" in os.environ:
        return os.environ.get("ADMIN_AUTHORIZED", "").strip().lower() in ("true", "1", "yes")
    return bool(getattr(settings, "admin_authorized", False))


def is_autofix_authorized() -> bool:
    """স্বয়ংক্রিয় ফিক্স অপারেশনের অনুমোদন আছে কিনা তা যাচাই করে।

    AUTOFIX_AUTHORIZED এনভায়রনমেন্ট ভ্যারিয়েবলের ভিত্তিতে সিদ্ধান্ত নেয়।
    """
    if "AUTOFIX_AUTHORIZED" in os.environ:
        return os.environ.get("AUTOFIX_AUTHORIZED", "").strip().lower() in ("true", "1", "yes")
    return bool(getattr(settings, "autofix_authorized", False))
