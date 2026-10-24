"""Shared httpx.AsyncClient singleton (#2719 slice-3 — hot request-path churn fix).

সমস্যা: hot request-path (backend/api/routes + backend/services) প্রতি রিকোয়েস্টে
`async with httpx.AsyncClient(timeout=X)` করত — প্রতিবার নতুন connection-pool
তৈরি + ধ্বংস (TLS handshake, FD churn, latency)। প্যাটার্ন-সার্ভে: ২৭টি সাইট,
১৭টি hot ফাইল — headers সবই per-request-এ পাঠায়, তাই shared client + per-request
timeout override (httpx native: `client.get(..., timeout=X)`) নিরাপদ।

সৎ-সীমাবদ্ধতা (ডকুমেন্টেড ডিজাইন-সিদ্ধান্ত):
- **Cold-path (tools/integrations) এই মডিউল ব্যবহার করবে না** — সেখানে per-call
  lifecycle অনেক ক্ষেত্রেই ইচ্ছাকৃত (প্রতি টুল-কলে আলাদা proxy/base_url/auth)।
- Shared client **কখনো request-scoped কোড থেকে close করা যাবে না** —
  `async with get_shared_async_client()` নিষিদ্ধ (aexit ক্লায়েন্ট বন্ধ করে দেবে)।
  App-shutdown-এ `close_shared_async_client()` ডাকার জায়গা আছে (lifespan)।
- Per-site timeout হারায় না: কনস্ট্রাকশনের বদলে কল-সাইটে `timeout=X` যায়।

Tests: `backend/tests/core/test_shared_http_client_2719.py` — identity, reset,
source-scan regression guard (১৭ hot-path ফাইলে কনস্ট্রাকশন নিষিদ্ধ)।
"""

from __future__ import annotations

import threading

import httpx

# বাংলা মন্তব্য: default timeout — সবচেয়ে বেশি দেখা যাওয়া per-site মানগুলোর
# মাঝামাঝি (10-30s)। প্রতিটি মাইগ্রেটেড সাইট নিজের timeout per-request-এ
# পাঠায়, তাই এটি শুধু পুরোনো কনস্ট্রাকশন-কনফিগ না-থাকা কলারদের জন্য নিরাপত্তা।
DEFAULT_TIMEOUT = httpx.Timeout(30.0)

# বাংলা মন্তব্য: connection limits — hot-path-এ একযোগে বেশি রিকোয়েস্ট থাকতে
# পারে; per-request নতুন pool-এর চেয়ে বাউন্ডেড shared pool সবসময় সস্তা।
DEFAULT_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
)

_shared_client: httpx.AsyncClient | None = None
_shared_client_lock = threading.Lock()


def get_shared_async_client() -> httpx.AsyncClient:
    """Process-wide shared httpx.AsyncClient (lazy singleton, thread-safe)।

    প্রথম কলে তৈরি হয়, পরের সব কলে একই instance — connection-pool পুনঃব্যবহৃত।
    কলার **কখনো এটি close করবে না** (app-lifespan শাটডাউনে
    `close_shared_async_client()` ছাড়া)।
    """
    global _shared_client
    if _shared_client is None:
        with _shared_client_lock:
            if _shared_client is None:
                _shared_client = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    limits=DEFAULT_LIMITS,
                )
    return _shared_client


def reset_shared_client() -> None:
    """Test hook — singleton রেফারেন্স সাফ (close নয়, শুধু ভোলা); পরের
    get_shared_async_client() কলে নতুন instance তৈরি হয়।"""
    global _shared_client
    with _shared_client_lock:
        _shared_client = None


async def close_shared_async_client() -> None:
    """App-shutdown hook — shared client বন্ধ + রেফারেন্স সাফ।

    বাংলা মন্তব্য: lifespan/shutdown ছাড়া কেউ ডাকবে না — চলমান রিকোয়েস্টের
    shared client বন্ধ করলে সেগুলো ভেঙে যাবে।
    """
    global _shared_client
    with _shared_client_lock:
        client, _shared_client = _shared_client, None
    if client is not None:
        await client.aclose()
