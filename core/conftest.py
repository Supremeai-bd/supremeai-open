# backend/conftest.py
# Test configuration and fixtures for SupremeAI backend
import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest

# ROOT-CAUSE FIX: pytest collection phase-এ tests/api/*.py, tests/core/*.py-র
# অনেক ফাইল module-level-এই route/app মডিউল import করে, যেগুলো
# api/routes/api_keys.py-র মতো জায়গায় module-level singleton
# `limiter = AsyncRateLimiter()` তৈরি করে দেয় -- আর AsyncRateLimiter.__init__()
# তখনই os.getenv("RATE_LIMIT_ENABLED") পড়ে নেয়, tests/conftest.py-র `app`
# fixture রান হওয়ারও অনেক আগে। backend/conftest.py হলো pytest rootdir
# (backend/)-এর সবচেয়ে উপরের conftest, তাই এখানে module-level-এই env var
# সেট করা হচ্ছে -- এটাই collection শুরুর আগে guaranteed সবচেয়ে আগে চলে।
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment variables.

    বাংলা: আগের মান সংরক্ষণ করে টেস্ট শেষে রিস্টোর করা হয়।
    এতে টেস্টের মধ্যে env var 'bleed' হয় না।
    """
    _SENTINEL = object()
    _keys = ("TESTING", "ENV", "DATABASE_URL", "REDIS_URL")
    _defaults = ("True", "test", "sqlite:///./test.db", "redis://mocked-redis-url")

    # Save originals before overriding
    originals = {k: os.environ.get(k, _SENTINEL) for k in _keys}

    for k, v in zip(_keys, _defaults, strict=False):
        os.environ.setdefault(k, v)

    yield

    # Restore exactly what was there before — don't blindly delete
    for k in _keys:
        original = originals[k]
        if original is _SENTINEL:
            os.environ.pop(k, None)
        else:
            os.environ[k] = original


@pytest.fixture
def mock_redis():
    """Provide a mocked Redis instance for tests."""
    with patch("redis.asyncio.from_url") as mock_redis_constructor:
        mock_connection = MagicMock()
        mock_connection.ping = MagicMock(return_value=True)
        mock_connection.set = MagicMock(return_value=True)
        mock_connection.get = MagicMock(return_value=None)
        mock_redis_constructor.return_value = mock_connection
        yield mock_connection


@pytest.fixture
def mock_async_redis():
    """Provide an async Redis mock for async tests."""
    with patch("redis.asyncio.from_url") as mock_redis_constructor:
        mock_instance = MagicMock()
        mock_instance.ping = asyncio.Future()
        mock_instance.ping.set_result(True)
        mock_instance.set = asyncio.Future()
        mock_instance.set.set_result(True)
        mock_instance.get = asyncio.Future()
        mock_instance.get.set_result(None)
        mock_redis_constructor.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=True)
def mock_external_apis():
    """Mock external API calls to prevent network requests during tests."""
    with (
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("requests.put") as mock_put,
        patch("requests.delete") as mock_delete,
    ):
        # Configure mocks to return successful responses
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {}
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {}

        yield {"get": mock_get, "post": mock_post, "put": mock_put, "delete": mock_delete}


# বাংলা: event_loop fixture সরানো হয়েছে।
# pyproject.toml-এ asyncio_mode = "auto" সেট থাকায় pytest-asyncio নিজেই
# event loop ম্যানেজ করে। manual event_loop fixture pytest-asyncio 0.21+ এ
# DeprecationWarning দেয় এবং filterwarnings="error" এর কারণে টেস্ট ফেল করে।
