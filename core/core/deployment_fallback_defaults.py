"""Deployment fallback defaults.

Centralized, non-secret default values exposed via the public `/config/public`
endpoint. Intentionally metadata-only and free of any hardcoded deployment
hostname (see scripts/ci/check_hardcoded_deployment_config.py) — the actual
value always comes from the canonical `SUPREMEAI_USER_BACKEND_URL` /
`USER_BACKEND_URL` environment variables, configured per-environment in
deployment settings.
"""

from __future__ import annotations

import os

from core.config import settings

# বাংলা মন্তব্য: এখানে কোনো ডোমেইন হার্ডকোড করা হয় না — ক্যানোনিকাল env var
# থেকে রানটাইমে মান নেওয়া হয়, না থাকলে খালি স্ট্রিং (frontend তখন নিজস্ব
# ডিফল্ট/রিলেটিভ পাথ ব্যবহার করবে)।
BACKEND_URL_DEFAULT: str = (
    os.getenv("SUPREMEAI_USER_BACKEND_URL")
    or os.getenv("USER_BACKEND_URL")
    or settings.backend_url
    or ""
)

# বাংলা মন্তব্য: ADMIN_URL / SCRAPER_URL — একই নীতি: কোনো হোস্টনেম হার্ডকোড নেই।
# Audit fix (this session): এই দুটি কনস্ট্যান্ট অনুপস্থিত ছিল, ফলে
# `api/routes/health_aggregation.py` ও `api/routes/service_topology.py`
# ImportError-এ লোড হতে ব্যর্থ হচ্ছিল — health-aggregation রাউটটি নিবন্ধিত
# থাকা সত্ত্বেও অ্যাপে মাউন্টই হতো না (silent dead route)।
ADMIN_URL_DEFAULT: str = settings.admin_url or ""

SCRAPER_URL_DEFAULT: str = settings.scraper_service_url or ""
