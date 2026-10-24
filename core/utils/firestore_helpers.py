"""
Firestore ক্লায়েন্ট ইনিশিয়ালাইজেশন ইউটিলিটি — ডুপ্লিকেট `firestore.Client()` কল
এবং ইম্পোর্ট গার্ড প্যাটার্ন দূর করতে কেন্দ্রীয় ফ্যাক্টরি।

আগে প্রতিটি মডিউলে আলাদাভাবে try/except দিয়ে firestore ইম্পোর্ট করা হতো
এবং প্রতিবার `firestore.Client()` কল করা হতো। এখন এই একটি মডিউল থেকে
`get_firestore_db()` কল করলেই সঠিকভাবে কনফিগার করা ক্লায়েন্ট পাওয়া যাবে।
"""

import os
from typing import Any

from core.logging_config import logger

from .environment import (
    is_test_environment,  # Fixed import path - using relative import
)

# Firestore SDK প্রাপ্যতা যাচাই — একবারই চেক হয়, বারবার try/except লাগে না
try:
    from google.cloud import firestore  # type: ignore[import-untyped]

    FIRESTORE_AVAILABLE = True
except ImportError:
    firestore = None  # type: ignore[assignment]
    FIRESTORE_AVAILABLE = False


# সিঙ্গলটন ক্যাশ — একই প্রজেক্টের জন্য বারবার নতুন Client তৈরি হবে না
_client_cache: dict[str, Any] = {}


def get_firestore_db(project_id: str | None = None) -> Any | None:
    """Firestore ক্লায়েন্ট রিটার্ন করে, টেস্ট এনভায়রনমেন্টে None দেয়।

    সিঙ্গলটন প্যাটার্ন ব্যবহার করে — একই project_id-র জন্য একটিই Client তৈরি হয়।
    Firestore SDK না থাকলে বা কানেকশন ফেইল করলে None রিটার্ন করে।

    Args:
        project_id: GCP প্রজেক্ট আইডি। না দিলে এনভায়রনমেন্ট ভ্যারিয়েবল থেকে নেয়।

    Returns:
        firestore.Client অথবা None।
    """
    # টেস্ট এনভায়রনমেন্টে কখনো রিয়েল Firestore ক্লায়েন্ট তৈরি করা উচিত না
    if is_test_environment():
        return None

    if not FIRESTORE_AVAILABLE:
        return None

    resolved_project = (
        project_id
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or "supremeai-a"
    )

    # ক্যাশ চেক — আগেই তৈরি থাকলে সেটাই রিটার্ন
    if resolved_project in _client_cache:
        return _client_cache[resolved_project]

    try:
        from core.config import settings

        # FIX (final-test 2026-09-13): SA JSON আগে resolve করো — env var অথবা
        # Infisical-backed settings দুই উৎস থেকেই। আগের কোডে env-var গেট
        # (`has_gcp_creds`) সবসময়ের আগে চলত, কিন্তু Render-এ secrets env var
        # হিসেবে নেই (Infisical vault-এ থাকে) — ফলে গেট সবসময় None ফেরত দিত এবং
        # tenant_db.py-এর ADC fallback (`firestore.Client()`) Render-এ ব্যর্থ হত
        # → সব tenant endpoint (get_completion/stream_chat) প্রোডাকশনে 500 দিত।
        # এখন vault-backed SA JSON গেটের আগেই ধরা হয়।
        credentials = None
        sa_json_str = (
            os.getenv("GCP_SERVICE_ACCOUNT_JSON")
            or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            or getattr(settings, "firebase_service_account_json", "")
        )
        if sa_json_str:
            import json

            from google.oauth2 import service_account

            try:
                sa_info = json.loads(sa_json_str)
                credentials = service_account.Credentials.from_service_account_info(sa_info)
            except (ValueError, TypeError) as sa_err:
                logger.warning(f"Failed to parse service account JSON: {sa_err}")
                credentials = None

        has_gcp_creds = credentials is not None or any(
            os.getenv(k)
            for k in (
                "GOOGLE_APPLICATION_CREDENTIALS",
                "GCP_SERVICE_ACCOUNT_JSON",
                "FIREBASE_SERVICE_ACCOUNT_JSON",
                "FIREBASE_SERVICE_ACCOUNT",
                "FIREBASE_ADMIN_CREDENTIALS",
                "K_SERVICE",
            )
        )
        if not has_gcp_creds and not os.getenv("FORCE_FIRESTORE_ADC"):
            return None

        client = firestore.Client(project=resolved_project, credentials=credentials)
        _client_cache[resolved_project] = client
        logger.info(f"Firestore client initialized for project: {resolved_project}")
        return client
    except Exception as exc:
        logger.warning(f"Firestore client initialization failed: {exc}")
        return None


def is_firestore_available() -> bool:
    """Firestore SDK ইন্সটল আছে কিনা তা রিটার্ন করে।"""
    return FIRESTORE_AVAILABLE
