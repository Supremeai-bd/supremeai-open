"""Append FORCE_FIRESTORE_ADC to the primary service env vars (DRY Phase 2-C3).

Migrated onto scripts/lib/render_client.py. Behavior preserved: reads current
env vars, appends the flag, PUTs the full list back.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

SERVICE_ID = "srv-da666f8u01pc739bm3t0"
token = os.environ.get("RENDER_API_KEY", "")

try:
    client = RenderClient(api_key=token)

    # Get current env vars
    current_vars = client.get_env_vars(SERVICE_ID)

    env_vars = [
        {"key": v["envVar"]["key"], "value": v["envVar"]["value"]} for v in current_vars
    ]

    # Add FORCE_FIRESTORE_ADC
    env_vars.append({"key": "FORCE_FIRESTORE_ADC", "value": "1"})

    # Update env vars
    client.update_env_vars(SERVICE_ID, env_vars)
    print("Updated Render env vars with FORCE_FIRESTORE_ADC successfully!")
except RenderApiError as e:
    print(f"Error updating env vars: {e}")
    if e.body:
        print(e.body)
