"""Worker entrypoint shim for Render deploy compatibility.

বাংলা: রেন্ডার ডিপ্লয়মেন্ট কম্প্যাটিবিলিটি শিম। রেন্ডার স্টার্ট কমান্ড
`uvicorn worker:app --host 0.0.0.0 --port 8080` যাতে সরাসরি `core/worker_service.py`
এর FastAPI `app` ইনস্ট্যান্স খুঁজে পায়।
"""

from __future__ import annotations

from core.worker_service import app

__all__ = ["app"]
