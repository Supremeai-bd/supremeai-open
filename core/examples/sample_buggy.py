# ruff: noqa
"""Intentionally buggy file used to exercise every pyerrorfix detector.

Run:  python -m pyerrorfix analyze examples/sample_buggy.py --fix --format console
"""

import asyncio
import hashlib
from core.logging_config import logger
import pickle  # noqa: F401  (used by security detector)
import subprocess
import time

import httpx as requests

import os

# --- hardcoded secret (security) - resolved via environment ---
API_KEY = os.getenv("API_KEY", "")

# --- unused import + wildcard already above (unused-import) ---
import json  # noqa: F401  (unused, used by detector demo)

# --- mutable shared global mutated from async (concurrency) ---
_cache: dict = {}


async def fetch(url: str) -> str:
    await asyncio.sleep(0.1)
    return "data"


async def handler():
    # missing await (asyncio)
    result = fetch("https://x")  # should be `await fetch(...)`

    # blocking call in async function
    await asyncio.sleep(2)

    # requests (blocking) in async
    requests.get("https://x")

    # mutable shared state mutated without lock
    _cache["x"] = result

    # f-string in logging
    logger.info(f"got {result} for {url}")

    return result


def divide(a, b):
    # zero-division risk if b == 0
    return a / b


def read_config(path):
    # open() without `with`
    f = open(path)
    return f.read()


def find_user(users, idx):
    # unbound local: x used before assignment in branch
    if idx > 0:
        x = users[idx]
    return x  # UnboundLocalError when idx == 0


def get_one(session):
    # NoResultFound risk
    return session.query(User).one()


def unsafe(sql, user_id):
    # SQL injection
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")


def load_trusted(data: bytes):
    # unsafe deserialization
    return pickle.loads(data)


def run_cmd(user_input: str):
    # shell injection
    subprocess.run(f"ls {user_input}", shell=True)


def hash_password(pw: str) -> str:
    # weak hash
    return hashlib.md5(pw.encode()).hexdigest()


# --- deprecated API (deprecation) ---
def legacy():
    import imp  # removed in 3.12

    return imp.find_module("os")


# --- broad except (logging) ---
def swallow():
    try:
        do_something()
    except:  # TODO(final-test-7a): intentionally kept bare — this file is the pyerrorfix E722 detector fixture; narrowing it would defeat the demo
        print("something failed")  # print in production


# --- pydantic v1 deprecation (web-api) ---
class Model:
    def to_dict(self):
        return {}


def serialize(m: Model):
    return m.dict()  # should be model_dump()


# --- NoneType access (typing) ---
def maybe_none():
    x = {"k": "v"}.get("missing")
    return x.upper()  # AttributeError if x is None


# --- assert in production ---
def validate_age(age):
    assert age >= 0  # stripped under python -O


# --- bare raise outside except ---
def bad_raise():
    raise  # RuntimeError: No active exception


# --- missing type hints (typing) ---
def add(a, b):
    return a + b


# ─── NEW: Network & I/O errors (category 1 expanded) ─────────────────────────


def fetch_user(user_id):
    # missing timeout → TimeoutError / ReadTimeout risk
    resp = requests.get(f"https://api.x.com/users/{user_id}")
    # json.loads without try → JSONDecodeError if API returns HTML error page
    return json.loads(resp.text)


# ─── NEW: Linter & Code-Quality (category 2) ────────────────────────────────
def process_pairs(a, b):
    # B905: zip without strict
    for x, y in zip(a, b, strict=False):
        pass


def is_active(flag):
    # E712: comparison to bool literal
    if flag is True:
        return True
    else:
        return False


def deeply_nested(data):
    # C901: nested if/else (depth 4)
    if data:
        if isinstance(data, dict):
            if "items" in data:
                if len(data["items"]) > 0:
                    return data["items"][0]
    return None


# ─── NEW: Auth & Security (category 7 expanded) ──────────────────────────────
import jwt
from fastapi import HTTPException


def decode_token(token):
    # CRITICAL: verify_signature=False accepts forged tokens
    return jwt.decode(token, options={"verify_signature": False})


def login_required(user):
    if not user:
        # manual 401 — should use Depends(get_current_user)
        raise HTTPException(401, "unauthorized")


# ─── NEW: Testing (category 10 expanded) ────────────────────────────────────
from unittest.mock import Mock


def test_something():
    # dead mock: created but never used
    Mock()
    # assert without message (hard to debug)
    assert 1 + 1 == 2


# ─── NEW: nested-if style + ternary style ────────────────────────────────────
def get_label(score):
    # ternary style: this should be a one-liner
    if score > 80:
        label = "high"
    else:
        label = "low"
    return label


if __name__ == "__main__":
    asyncio.run(handler())
