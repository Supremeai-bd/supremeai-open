#!/usr/bin/env python3
"""Render Suspension Guard — Deploy Train fail-fast preflight (#2624)।

প্রমাণ (Deploy Train run 36695632388, 2026-09-30): ফ্রি-টিয়ার instance-hour
কোটা শেষ হলে Render সার্ভিস **suspend** করে — তখন health 503 "Service
Suspended", পুরনো সব deploy `deactivated`। সেই অবস্থায় deploy ট্রিগার করা
অর্থহীন (বিভ্রান্তিকর লাল canary/rollback স্টেশন তৈরি করে)। এই গার্ড প্রতিটি
Render-deploy জবের ট্রিগারের **আগে** চলে:

  - সার্ভিস suspended → স্পষ্ট অ্যাকশনেবল বার্তাসহ লাল (অ্যাডমিন সিদ্ধান্ত প্রয়োজন —
    unsuspend / কোটা রিসেট / পেইড প্ল্যান)। অন্ধ deploy চেষ্টা নয়।
  - সার্ভিস স্বাভাবিক → exit 0, ডিপ্লয় চলবে।
  - Render API নিজেই নাগালের বাইরে → fail-closed (ডিপ্লয় তবু ব্যর্থই হতো —
    নীরব ভুয়া সবুজ নয়)।

চুক্তি (SSOT): সব Render API কল `scripts/lib/render_client.py` দিয়ে — নতুন
auth boilerplate নিষিদ্ধ (dry-gate philosophy)। pure-লজিক অংশ
(`suspension_reason`) stdlib-only — AST-extract টেস্টযোগ্য
(backend/tests/scripts/test_render_suspension_guard.py)।

ব্যবহার:
    python scripts/deploy/render_suspension_guard.py                 # env-driven
    python scripts/deploy/render_suspension_guard.py --service-id srv-xxx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# বাংলা মন্তব্য: scripts/lib SSOT client-এর জন্য রিপো-রুট sys.path-এ।
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from render_client import RenderApiError, RenderClient  # noqa: E402


# বাংলা মন্তব্য: Render-এর suspended ফিল্ড বিভিন্ন শেপে আসতে পারে — bool,
# string ফ্ল্যাগ, বা আলাদা suspended_reasons তালিকা। সব শেপ এক জায়গায় সামলানো
# হলো যাতে guard/rollback/canary সবাই একই সিদ্ধান্ত-লজিক ব্যবহার করে।
def suspension_reason(service: dict[str, Any] | None) -> str | None:
    """সার্ভিস অবজেক্ট থেকে সাসপেনশন-কারণ বের করে — স্বাভাবিক হলে None।

    বাংলা মন্তব্য: এটা pure ফাংশন — নেটওয়ার্ক/I/O নেই, ফলে AST-extract টেস্টে
    হুবহু shipped বডিই চলে (backend/tests/scripts প্যাটার্ন, #2620 প্রেসিডেন্ট)।
    ধ্রুবকগুলো ফাংশনের ভেতরেই — বডি স্বয়ংসম্পূর্ণ (self-contained)।
    """
    truthy_strings = {"true", "yes", "1", "suspended", "user_initiated", "billing"}
    if not isinstance(service, dict):
        return None

    reasons: list[str] = []

    suspended = service.get("suspended")
    if isinstance(suspended, bool):
        if suspended:
            reasons.append("suspended=true")
    elif isinstance(suspended, str) and suspended.strip().lower() in truthy_strings:
        reasons.append(f"suspended={suspended.strip().lower()}")

    raw_reasons = service.get("suspended_reasons") or service.get("suspendedReasons")
    if isinstance(raw_reasons, (list, tuple)):
        reasons.extend(str(item) for item in raw_reasons if str(item).strip())
    elif isinstance(raw_reasons, str) and raw_reasons.strip():
        reasons.append(raw_reasons.strip())

    if not reasons:
        return None
    return "; ".join(reasons)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render সার্ভিস সাসপেনশন গার্ড — সাসপেন্ডেড হলে fail-fast"
    )
    parser.add_argument(
        "--service-id",
        default=None,
        help="Render service id (ডিফল্ট: RENDER_SVC_ID বা RenderClient ডিফল্ট)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("RENDER_API_KEY", "")
    if not api_key:
        print(
            "::error::RENDER_API_KEY নেই — suspension guard যাচাই করতে পারবে না "
            "(fail-closed; অন্ধ deploy নয়)।"
        )
        return 1

    client = RenderClient(api_key=api_key)
    service_id = args.service_id or os.environ.get("RENDER_SVC_ID")

    try:
        service = client.get_service(service_id)
    except RenderApiError as error:
        print(
            f"::error::Render API থেকে সার্ভিস স্টেট যাচাই ব্যর্থ (fail-closed) — "
            f"{error.status}: {str(error)[:200]}"
        )
        return 1
    except (OSError, ValueError) as error:
        print(
            f"::error::Render API কলে অপ্রত্যাশিত ব্যর্থতা (fail-closed) — {error!s:.200}"
        )
        return 1

    name = str(service.get("name") or service_id or "unknown")
    reason = suspension_reason(service)
    evidence = {
        "service_id": service_id or client.default_service_id,
        "service_name": name,
        "suspended": bool(reason),
        "reason": reason,
        "guard": "render_suspension_guard",
    }
    print(json.dumps(evidence, ensure_ascii=False))

    if reason:
        print(
            f"::error::Render সার্ভিস '{name}' SUSPENDED ({reason}) — ফ্রি-টিয়ার কোটা "
            f"শেষ বা অ্যাডমিন-সাসপেন্ড। ডিপ্লয় ট্রিগার বাতিল (fail-fast): আগে সার্ভিস "
            f"unsuspend করুন / কোটা রিসেট (পরবর্তী বিলিং-পিরিয়ড) / পেইড প্ল্যান — "
            f"অ্যাডমিন সিদ্ধান্ত প্রয়োজন।"
        )
        return 1

    print(f"✓ সার্ভিস '{name}' স্বাভাবিক — ডিপ্লয় অনুমোদিত")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
