"""List recent deploys for the primary Render service (DRY Phase 2-C1).

এই script-টি আগে Render API auth + URL + output সব নিজে করত; এখন শেয়ার্ড
RenderClient ব্যবহার করে (scripts/lib/render_client.py)। আউটপুট ফরম্যাট
আগের মতোই — downstream CI log-parsers অক্ষত।
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from render_client import RenderApiError, RenderClient  # noqa: E402

SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "srv-da666f8u01pc739bm3t0")


def main() -> int:
    try:
        deploys = RenderClient().list_deploys(service_id=SERVICE_ID, limit=5)
    except RenderApiError as exc:
        print(f"Error fetching deploys: {exc}")
        return 1
    for deploy in deploys:
        d = deploy["deploy"]
        commit_id = d.get("commit") or {}
        print(
            f"ID: {d['id']} | Status: {d['status']} | Created: {d['createdAt']}"
            f" | Finished: {d.get('finishedAt', 'N/A')} | Commit: {commit_id.get('id', 'N/A')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
