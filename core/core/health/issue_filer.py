"""Error-event → GitHub issue self-filing bridge (issue #2527).

বাংলা মন্তব্য: production error এখন পর্যন্ত শুধু heal/log হতো — tracker-এ
পৌঁছাতো না। এই মডিউল `error_event_bus`-এর উপর একটি listener বসিয়ে
সিস্টেমের নিজের সমস্যা নিজে report করার লুপ ("self-filing") চালু করে:

    error_event_bus.emit(ErrorEvent(...))
        └─► _issue_filer_listener            (severity ফিল্টার: CRITICAL/ERROR/HIGH)
              └─► signature = sha256(module:error_type)[:12]
                    ├─► in-memory dedup: প্রতি signature ২৪ঘণ্টায় ১ ইস্যু (burst guard)
                    ├─► daily cap: দিনে সর্বোচ্চ N ইস্যু (নয়েজ-গার্ড, #1810 শিক্ষা)
                    └─► GitHub-side dedup: open issue-গুলোতে marker-line ম্যাচ
                          └─► httpx POST /repos/{repo}/issues (REST — gh CLI লাগে না)

Graceful degradation (সংবিধান Rule ৩): token না থাকলে বা GitHub অগম্য হলে
মডিউল নিঃশব্দে skip করে (একবার warn) — error bus-এর মূল প্রবাহ কখনো ভাঙে না।
Listener-isolation-ও আছে (event_bus._safe_invoke) — এখানে raise করলেও বাকি
listeners নিরাপদ।

Env knobs (সবই optional, ন্যায্য default):
    ISSUE_FILER_ENABLED          default "true"
    ISSUE_FILER_REPO             default "SaifulHaqueNiloy/supremeai"
    ISSUE_FILER_SEVERITIES       default "CRITICAL,ERROR,HIGH"
    ISSUE_FILER_MIN_INTERVAL_H   default 24 (ঘণ্টা; প্রতি-signature কুলডাউন)
    ISSUE_FILER_DAILY_CAP        default 20 (দৈনিক সর্বোচ্চ ইস্যু)
    ISSUE_FILER_STARTUP_QUIET_S  default 120 (বুটের পর এত সেকেন্ড নীরব —
                                  restart-storm রোধ; বুট-টাইম পুরনো error
                                  বার্স্ট যেন ইস্যু-বন্যা না ঘটায়)
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from core.logging_config import logger

from ..messaging.event_bus import ErrorEvent, error_event_bus

# ─── Config (env-driven, import-time snapshot) ─────────────────────────────

_REPO = os.getenv("ISSUE_FILER_REPO", "SaifulHaqueNiloy/supremeai")
_SEVERITIES = {
    s.strip().upper()
    for s in os.getenv("ISSUE_FILER_SEVERITIES", "CRITICAL,ERROR,HIGH").split(",")
    if s.strip()
}
_MIN_INTERVAL_S = float(os.getenv("ISSUE_FILER_MIN_INTERVAL_H", "24")) * 3600.0
_DAILY_CAP = int(os.getenv("ISSUE_FILER_DAILY_CAP", "20"))
_STARTUP_QUIET_S = float(os.getenv("ISSUE_FILER_STARTUP_QUIET_S", "120"))

# ─── Dedup state (in-process; restart-এ GitHub-side marker ম্যাচ ব্যাকস্টপ) ──

_last_filed_at: dict[str, float] = {}
_filed_today: dict[str, int] = defaultdict(int)  # "YYYY-MM-DD" (UTC) → count
_module_boot_ts = time.monotonic()
_warned_no_token = False


def _signature(event: ErrorEvent) -> str:
    """Error-signature — dedup key (module + error_type, message-নিরপেক্ষ)।

    বাংলা: একই ত্রুটির ভিন্ন বার্তা (যেমন ভিন্ন timeout মান) একই ইস্যুতে জমা
    হোক — signature শুধু ত্রুটির *শ্রেণি* ধরে, নির্দিষ্ট বার্তা নয়।
    """
    raw = f"{event.module}:{event.error_type}".encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def _marker(sig: str) -> str:
    """ইস্যু-body-র শেষে বসানো machine-readable marker — GitHub-side dedup এটা খোঁজে।"""
    return f"error-signature: {sig}"


def _today_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _github_token() -> str | None:
    """Token সংগ্রহ — vault/Infisical pull-এর পরে env-এ থাকে।"""
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("SUPREMEAI_GITHUB_TOKEN")


def _should_file(event: ErrorEvent, now: float = time.monotonic()) -> bool:
    """Pure gate — টেস্টে সরাসরি যাচাইযোগ্য।"""
    if event.severity.upper() not in _SEVERITIES:
        return False
    # বুট-কুলডাউন: restart-এর পর জমে থাকা বার্স্ট ইস্যু-বন্যা করবে না।
    if now - _module_boot_ts < _STARTUP_QUIET_S:
        return False
    # দৈনিক ক্যাপ।
    if _filed_today[_today_key()] >= _DAILY_CAP:
        return False
    # প্রতি-signature কুলডাউন (২৪ঘণ্টা ডিফল্ট)।
    sig = _signature(event)
    last = _last_filed_at.get(sig)
    if last is not None and (time.time() - last) < _MIN_INTERVAL_S:
        return False
    return True


def _build_issue_payload(event: ErrorEvent, sig: str) -> dict[str, Any]:
    """ইস্যু টাইটেল/বডি/লেবেল — create_issue.py --type discovery-র স্কিমা অনুসরণে।"""
    title = f"[self-filed] {event.module}: {event.error_type} — {event.severity} production error"
    # বাংলা মন্তব্য: context-section আগেই বানিয়ে রাখি — Python 3.11-এ f-string-এর
    # expression-part-এ backslash নিষিদ্ধ, তাই nested f-string এড়ানো হলো।
    context_section = ""
    if getattr(event, "context", None):
        context_section = "## Context\n```json\n" + str(event.context) + "\n```\n"
    body = f"""**সারসংক্ষেপ (Banglish):** `error_event_bus` self-filer — production error tracker-এ auto-filed (#2527)।

## Error Event
| Field | Value |
|---|---|
| module | `{event.module}` |
| error_type | `{event.error_type}` |
| severity | `{event.severity}` |
| timestamp (event) | {getattr(event, "timestamp", "n/a")} |

## Message
```
{str(event.message)[:1500]}
```
{context_section}
## ফিক্স দিকনির্দেশ
- SelfHealer-এর heal-log-এর পাশাপাশি এই ইস্যুটি fleet-এর work queue-তে এসেছে
- Dedup: একই signature ({sig}) ২৪ঘণ্টায় নতুন ইস্যু খুলবে না — নতুন ঘটনা কমেন্টে জমা হবে

---
{_marker(sig)}
*Auto-filed by `backend/core/health/issue_filer.py` (#2527)*"""
    return {
        "title": title[:300],
        "body": body,
        "labels": [
            "type:reliability",
            "status:unclaimed",
            "discovered-by:self-filer",
            "auto-filed",
        ],
    }


async def _find_open_issue_with_marker(http: httpx.AsyncClient, token: str, sig: str) -> int | None:
    """GitHub-side dedup — open issue-গুলোর body-তে marker লাইন খোঁজে (REST, read-your-writes)।

    বাংলা: search API eventually-consistent (#2603 শিক্ষা) — তাই সরাসরি
    `GET /issues?state=open` লিস্টিং + লোকাল ম্যাচ; PR-এন্ট্রি (`pull_request`
    কী) বাদ।
    """
    url = f"https://api.github.com/repos/{_REPO}/issues"
    seen = 0
    for page in range(1, 4):  # ৩ পৃষ্ঠা × ১০০ — যথেষ্ট ব্যাকস্টপ
        resp = await http.get(
            url,
            params={"state": "open", "per_page": 100, "page": page},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if resp.status_code != 200:
            return None  # dedup যাচাই ব্যর্থ → ফাইলিং skip (fail-safe, duplicate > miss নয়)
        items = resp.json()
        for item in items:
            if "pull_request" in item:
                continue
            if _marker(sig) in (item.get("body") or ""):
                return int(item["number"])
        seen += len(items)
        if len(items) < 100:
            break
    return None


async def _file_issue(event: ErrorEvent, sig: str) -> int | None:
    """একটি ইস্যু খোলে; সফল হলে issue number ফেরায়।"""
    global _warned_no_token
    token = _github_token()
    if not token:
        if not _warned_no_token:
            _warned_no_token = True
            logger.warning(
                "[issue-filer] GitHub token নেই (GITHUB_TOKEN/GH_TOKEN) — self-filing নিষ্ক্রিয়, "
                "error bus স্বাভাবিক থাকবে (Rule ৩ graceful degradation)"
            )
        return None
    payload = _build_issue_payload(event, sig)
    async with httpx.AsyncClient(timeout=15.0) as http:
        existing = await _find_open_issue_with_marker(http, token, sig)
        if existing is not None:
            logger.info(
                f"[issue-filer] signature {sig} already tracked in #{existing} — নতুন ইস্যু নয়"
            )
            _last_filed_at[sig] = time.time()  # কুলডাউন রিসেট — বার্স্ট মেটে না
            return None
        resp = await http.post(
            f"https://api.github.com/repos/{_REPO}/issues",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if resp.status_code == 201:
            number = resp.json().get("number")
            logger.info(
                f"[issue-filer] ✅ ইস্যু #{number} self-filed ({event.module}:{event.error_type}, sig {sig})"
            )
            return int(number) if number is not None else None
        logger.warning(
            f"[issue-filer] GitHub create failed HTTP {resp.status_code}: {resp.text[:200]} — ইভেন্ট স্টোরে থাকলো, পরের ইভেন্টে আবার চেষ্টা"
        )
        return None


async def _issue_filer_listener(event: ErrorEvent) -> None:
    """`error_event_bus` listener — '*' চ্যানেলে সব ইভেন্ট পায়, gate ভেতরে।

    বাংলা: কখনো raise করে না (event_bus-এর _safe_invoke-ও আছে, তবু সতর্ক) —
    filing ব্যর্থতা error bus-এর অন্য ভোক্তাদের ছুঁবে না।
    """
    try:
        if os.getenv("ISSUE_FILER_ENABLED", "true").lower() != "true":
            return
        if not _should_file(event):
            return
        sig = _signature(event)
        number = await _file_issue(event, sig)
        # সফল ফাইলিং হলেই dedup-state আপডেট (ব্যর্থতায় পরের ইভেন্টে পুনরায় চেষ্টা)।
        if number is not None:
            _last_filed_at[sig] = time.time()
            _filed_today[_today_key()] += 1
        else:
            # GitHub-side existing পেলেও কুলডাউন চালু (ভেতরে সেট হয়েছে);
            # এখানে শুধু নিশ্চিত করি sig-এর এন্ট্রি আছে।
            _last_filed_at.setdefault(sig, time.time())
    except Exception as exc:  # noqa: BLE001 — listener boundary: কখনো প্রপাগেট নয়
        logger.warning(f"[issue-filer] listener ব্যর্থ (নিঃশব্দে উপেক্ষা): {exc}")


_listener_registered: bool = False


def register_issue_filer_listener() -> None:
    """Lifespan/startup-এ স্পষ্ট কল করতে হবে (self_healer-প্যাটার্ন, import side-effect নয়)।"""
    global _listener_registered
    if _listener_registered:
        return
    if os.getenv("ISSUE_FILER_ENABLED", "true").lower() != "true":
        logger.info("[issue-filer] ISSUE_FILER_ENABLED=false — self-filing বন্ধ (env)")
        _listener_registered = True
        return
    error_event_bus.register_listener(_issue_filer_listener)
    _listener_registered = True
    logger.info(
        f"✅ Issue-filer listener registered (#2527) — repo={_REPO}, severities={sorted(_SEVERITIES)}, "
        f"cooldown={_MIN_INTERVAL_S / 3600:.0f}h, daily-cap={_DAILY_CAP}, startup-quiet={_STARTUP_QUIET_S:.0f}s"
    )


def reset_filer_state_for_tests(boot_offset_s: float = -10_000.0) -> None:
    """টেস্ট হেল্পার — dedup state + startup-quiet উইন্ডো রিসেট।"""
    global _module_boot_ts, _warned_no_token
    _last_filed_at.clear()
    _filed_today.clear()
    _warned_no_token = False
    _module_boot_ts = time.monotonic() + boot_offset_s  # ঋণাত্মক = quiet-window পেরিয়ে গেছে


__all__ = [
    "ErrorEvent",
    "_build_issue_payload",
    "_marker",
    "_should_file",
    "_signature",
    "register_issue_filer_listener",
    "reset_filer_state_for_tests",
]
