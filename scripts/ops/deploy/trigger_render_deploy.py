"""Trigger a deploy of the primary Render service (DRY Phase 2-C1).

আগে requests + headers নিজে লিখত; এখন RenderClient.trigger_deploy() —
সফল হলে আগের মতোই 'Deploy triggered successfully! Deploy ID: ...' প্রিন্ট
করে (downstream log-parsers অক্ষত), ব্যর্থ হলে stderr-এ body + exit 1।
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from render_client import RenderApiError, RenderClient  # noqa: E402

SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "srv-da666f8u01pc739bm3t0")


def main() -> int:
    try:
        data = RenderClient().trigger_deploy(service_id=SERVICE_ID)
    except RenderApiError as exc:
        print(f"Failed to trigger deploy: {exc.body or exc}")
        return 1
    print(f"Deploy triggered successfully! Deploy ID: {data['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
