"""Fetch details of the primary Render service (DRY Phase 2-C1).

আগে urllib + auth header নিজে লিখত; এখন RenderClient.get_service() —
আউটপুট আগের মতোই (indented JSON)।
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
        service = RenderClient().get_service(service_id=SERVICE_ID)
    except RenderApiError as exc:
        print(f"Error fetching service details: {exc}")
        return 1
    print(json.dumps(service, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
