#!/usr/bin/env python3
"""Render Rollback Engine — Deploy Train Station 4 (#2421 seq:3, 2026-09-28)।

ক্যানারি (Station 3: post-deploy smoke) ব্যর্থ হলে instant rollback — আগের
স্থিতিশীল deploy-এর commitId দিয়ে নতুন deploy ট্রিগার করে এবং টার্মিনাল স্টেট
পর্যন্ত poll করে। SSOT চুক্তি: সব Render API কল `scripts/lib/render_client.py`
দিয়ে (নতুন auth boilerplate নিষিদ্ধ — dry-gate philosophy)।

ব্যর্থতা-চুক্তি (fail-closed):
  - স্থিতিশীল পূর্বসূরি deploy না পাওয়া গেলে রোলব্যাক চেষ্টা নয় — অ্যাডমিনের
    নাটাইয়ে (AGENTS.md: কোনো অন্ধ auto-revert নয়)।
  - commitId অজানা auto-deploy-এ অন্ধ রোলব্যাক নয় — স্পষ্ট ব্যর্থতা।
  - poll-timeout-এ স্পষ্ট লাল — নীরব ভুয়া সবুজ নয়।

ব্যবহার:
    python scripts/deploy/render_rollback.py --dry-run      # পরিকল্পনা-শুধু
    python scripts/deploy/render_rollback.py                 # প্রকৃত রোলব্যাক
    python scripts/deploy/render_rollback.py --service-id srv-xxx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# বাংলা মন্তব্য: scripts/lib SSOT client-এর জন্য রিপো-রুট sys.path-এ।
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from render_client import RenderApiError, RenderClient

# বাংলা মন্তব্য (#2624): সাসপেনশন-সিদ্ধান্ত লজিক এক SSOT — guard ও rollback উভয়ে
# একই pure ফাংশন ব্যবহার করে (script-dir sys.path[0]-এ থাকায় সরাসরি import)।
from render_suspension_guard import suspension_reason

TERMINAL_OK = {"live"}
TERMINAL_BAD = {"build_failed", "canceled", "deactivated", "pre_deploy_failed"}


class RollbackPlanner:
    """পূর্বসূরি স্থিতিশীল deploy শনাক্তকরণ — বিশুদ্ধ লজিক, টেস্টযোগ্য।"""

    def __init__(self, deploys: list[dict[str, Any]]):
        self.deploys = deploys

    def _status(self, d: dict[str, Any]) -> str:
        # বাংলা মন্তব্য: Render API-র status কাঠামো দুই রকম হতে পারে — দুটোই সামলাই।
        st = d.get("status")
        if isinstance(st, dict):
            return str(st.get("value") or "")
        return str(st or "")

    def _commit_id(self, d: dict[str, Any]) -> str | None:
        commit = d.get("commit") or {}
        cid = commit.get("id") if isinstance(commit, dict) else None
        return cid or d.get("commitId") or None

    def find_rollback_target(self, exclude_deploy_id: str | None = None) -> dict[str, Any]:
        """সর্বশেষ live deploy-কে বাদ দিয়ে তার আগের সর্বশেষ live deploy দিন।"""
        live = [d for d in self.deploys if self._status(d) == "live"]
        if exclude_deploy_id:
            live = [d for d in live if d.get("id") != exclude_deploy_id]
        if not live:
            raise RuntimeError(
                "রোলব্যাক টার্গেট নেই: তালিকায় কোনো স্থিতিশীল (live) পূর্বসূরি deploy নেই — "
                "অন্ধ auto-revert নিষিদ্ধ; অ্যাডমিন সিদ্ধান্ত প্রয়োজন"
            )
        # বাংলা মন্তব্য: list_deploys সাধারণত নতুন-আগে আসে; তবু createdAt-তে sort
        # করে নির্ভরযোগ্য করা হলো (ISO timestamp lexicographic sort = সঠিক ক্রম)।
        live.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
        return live[0]

    def pick_bad_deploy(self) -> str | None:
        """সবচেয়ে নতুন live deploy-এর id (এটাই 'খারাপ' — এটাকে বাদ দিয়ে রোলব্যাক)।"""
        live = [d for d in self.deploys if self._status(d) == "live"]
        if len(live) < 2:
            return None
        live.sort(key=lambda d: str(d.get("createdAt") or ""), reverse=True)
        return live[0].get("id")


def execute_rollback(
    client: RenderClient,
    service_id: str | None,
    dry_run: bool,
    poll_timeout_sec: int,
    poll_interval_sec: int = 10,
) -> dict[str, Any]:
    """রোলব্যাক পরিকল্পনা + (dry-run না হলে) প্রকৃত ট্রিগার ও যাচাই।"""
    # বাংলা মন্তব্য (#2624): সাসপেন্ডেড সার্ভিসে রোলব্যাক অসম্ভব — প্রমাণ: Deploy
    # Train run 36695632388-এ "রোলব্যাক টার্গেট নেই" ছিল আসলে ফ্রি-টিয়ার কোটা-
    # শেষ সাসপেনশনের লক্ষণ। আগে সেটাই শনাক্ত করে সুনির্দিষ্ট বার্তা দেওয়া হলো —
    # জেনেরিক "no live predecessor" বিভ্রান্তি নয়, অ্যাকশনেবল নির্দেশনা।
    service_state = client.get_service(service_id)
    suspended_reason = suspension_reason(service_state)
    if suspended_reason:
        raise RuntimeError(
            f"রোলব্যাক অসম্ভব — Render সার্ভিস suspended ({suspended_reason}) — "
            "unsuspend/কোটা পুনরুদ্ধার ছাড়া কোনো deploy লাইভ হতে পারে না; "
            "অ্যাডমিন সিদ্ধান্ত প্রয়োজন"
        )

    deploys: list[dict[str, Any]] = client.list_deploys(
        service_id=service_id, limit=10
    )
    planner = RollbackPlanner(deploys)
    bad_id = planner.pick_bad_deploy()
    target = planner.find_rollback_target(exclude_deploy_id=bad_id)
    target_commit = RollbackPlanner([])._commit_id(target)

    plan = {
        "service_id": service_id or client.default_service_id,
        "bad_deploy_id": bad_id,
        "rollback_to_deploy_id": target.get("id"),
        "rollback_to_commit": target_commit,
        "rollback_to_created_at": target.get("createdAt"),
        "dry_run": dry_run,
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    if not target_commit:
        raise RuntimeError(
            "রোলব্যাক টার্গেটের commitId অজানা — অন্ধ রোলব্যাক নিষিদ্ধ (fail-closed)"
        )
    if dry_run:
        plan["result"] = "DRY-RUN — কোনো write হয়নি"
        return plan

    # বাংলা মন্তব্য: আগের স্থিতিশীল commit-এ নতুন deploy — এটাই Render-এর
    # ক্যানোনিকাল রোলব্যাক পথ (পুরনো deploy-কে 'live' করার direct API নেই)।
    new_deploy = client.request(
        "POST",
        f"/services/{plan['service_id']}/deploys",
        body={"commitId": target_commit, "clearCache": "do_not_clear"},
    )
    new_id = new_deploy.get("id")
    plan["rollback_deploy_id"] = new_id

    deadline = time.time() + poll_timeout_sec
    while time.time() < deadline:
        snap = client.get_deploy(new_id, service_id=plan["service_id"])
        st = RollbackPlanner([snap])._status(snap)
        print(f"[rollback] deploy {new_id} status={st}")
        if st in TERMINAL_OK:
            plan["result"] = f"ROLLBACK OK — deploy {new_id} live (commit {target_commit})"
            return plan
        if st in TERMINAL_BAD:
            raise RuntimeError(
                f"রোলব্যাক deploy {new_id} টার্মিনাল-ব্যর্থ ({st}) — অ্যাডমিন অ্যালার্ট প্রয়োজন"
            )
        time.sleep(poll_interval_sec)
    raise RuntimeError(f"রোলব্যাক poll-timeout ({poll_timeout_sec}s) — অ্যাডমিন যাচাই প্রয়োজন")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Rollback Engine (Deploy Train Station 4)")
    ap.add_argument("--service-id", default=os.environ.get("RENDER_SERVICE_ID"))
    ap.add_argument("--api-key", default=os.environ.get("RENDER_API_KEY"))
    ap.add_argument("--dry-run", action="store_true", help="কোনো write নয় — শুধু পরিকল্পনা")
    ap.add_argument("--poll-timeout", type=int, default=900, help="rollback deploy poll timeout (সেকেন্ড)")
    ap.add_argument("--poll-interval", type=int, default=10)
    args = ap.parse_args()

    try:
        client = RenderClient(api_key=args.api_key, service_id=args.service_id)
        result = execute_rollback(
            client,
            service_id=args.service_id,
            dry_run=args.dry_run,
            poll_timeout_sec=args.poll_timeout,
            poll_interval_sec=args.poll_interval,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (RuntimeError, RenderApiError) as err:
        # বাংলা মন্তব্য: ব্যর্থতা স্পষ্ট ও লাল — নীরব ভুয়া সবুজ কখনো নয়।
        print(f"::error::ROLLBACK FAILED: {err}", file=sys.stderr)
        print(f"ROLLBACK FAILED: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
