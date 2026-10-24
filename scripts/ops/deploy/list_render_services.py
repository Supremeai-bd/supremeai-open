"""List Render services: "Name: <name> -> ID: <id>" per line (DRY Phase 2-C3).

Migrated onto scripts/lib/render_client.py (drops the requests dependency).
Per dry-gate convention: exits 1 on API failure instead of printing and
silently exiting 0.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

try:
    services = RenderClient(api_key=os.environ.get("RENDER_API_KEY", "")).list_services()
    for s in services:
        print(f"Name: {s['service']['name']} -> ID: {s['service']['id']}")
except RenderApiError as e:
    print(f"Failed to fetch services: {e} {e.body}".rstrip())
    sys.exit(1)
