"""Set the core service to a prebuilt container image (DRY Phase 2-C3).

Migrated onto scripts/lib/render_client.py — the single-sourced Render API
client. Behavior preserved: prints "Success!" + body, or "Failed: ..." + body.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

SERVICE_ID = "srv-da5i4frm8hqs73cpp5hg"
api_key = os.environ.get("RENDER_API_KEY", "")

# Try to set env to image and provide imagePath
PAYLOAD = {
    "serviceDetails": {
        "env": "image",
        "envSpecificDetails": {
            "imagePath": "ghcr.io/saifulhaqueniloy/supremeai/supremeai-core:main"
        },
    }
}

try:
    result = RenderClient(api_key=api_key).update_service(SERVICE_ID, PAYLOAD)
    print("Success!")
    print(result)
except RenderApiError as e:
    print(f"Failed: {e}")
    if e.body:
        print(e.body)
