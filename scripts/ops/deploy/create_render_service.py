"""Find the supremeai-backend-v2 service id by name (DRY Phase 2-C3).

Migrated onto scripts/lib/render_client.py. Output format preserved:
"FOUND!" + id, or "Not found yet" + first page pretty-printed.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

try:
    data = RenderClient(api_key=os.environ.get("RENDER_API_KEY", "")).list_services(limit=10)
    for s in data:
        if s.get("service", {}).get("name") == "supremeai-backend-v2":
            print("FOUND!")
            print(s["service"]["id"])
            break
    else:
        print("Not found yet")
        print(json.dumps(data[:1], indent=2))
except RenderApiError as e:
    print(f"Failed: {e}")
