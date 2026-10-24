"""Dump the primary Render service details as pretty JSON (DRY Phase 2-C3).

Migrated onto scripts/lib/render_client.py (drops the requests dependency).
Per dry-gate convention: exits 1 on API failure instead of silently exiting 0.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

SERVICE_ID = "srv-da666f8u01pc739bm3t0"

try:
    data = RenderClient(api_key=os.environ.get("RENDER_API_KEY", "")).get_service(SERVICE_ID)
    print(json.dumps(data, indent=2))
except RenderApiError as e:
    print(f"Failed to fetch service: {e} {e.body}".rstrip())
    sys.exit(1)
