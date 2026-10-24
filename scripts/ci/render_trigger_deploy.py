#!/usr/bin/env python3
"""
Shared Render deploy trigger script used by all CI deploy jobs
(Core / Worker / Scraper / MCP Control Tower).

Reads configuration from environment variables so no secret interpolation
or f-string quoting inside a `python -c "..."` YAML block is ever needed:

    RENDER_API_KEY   - Render API key (required to actually trigger a deploy)
    RENDER_SVC_ID    - Render service ID to deploy (if unset, the job is skipped)

Note: For the Service Modularization/OOM Mitigation feature, ensure that the
Render Dashboard is configured with the `SUPREMEAI_SERVICE_ROLE` environment
variable for each respective service (`core`, `worker`, `scraper`).

Exits 0 when a deploy is skipped (missing service id) or successfully
triggered. Exits non-zero after exhausting retries on failure.

DRY Phase 2-C3: transport migrated onto scripts/lib/render_client.py —
the retry policy (5 attempts / 10 s) stays here because it is this job's
own concern; auth/URL/error normalization is the client's.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from render_client import RenderApiError, RenderClient  # noqa: E402

MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 10

# Epic #1850 Phase C / issue #1855: opt-in wait-to-terminal-state mode. The old
# behavior (POST and exit — fire-and-forget) is why the */5 deploy-doctor poller
# existed; in-run terminal-state detection replaces it. Enabled by the
# render-deploy-status composite via RENDER_WAIT=1.
RENDER_WAIT = os.environ.get("RENDER_WAIT", "").strip().lower() in ("1", "true", "yes")
POLL_INTERVAL_SECONDS = 15
POLL_TIMEOUT_SECONDS = int(os.environ.get("RENDER_WAIT_TIMEOUT_SECONDS", "660"))
FAIL_STATES = {"build_failed", "update_failed", "deactivated", "canceled"}
OK_STATES = {"live"}


def main() -> int:
    svc_id = os.environ.get("RENDER_SVC_ID", "").strip()
    api_key = os.environ.get("RENDER_API_KEY", "").strip()

    if not svc_id:
        print("Skipping Render deploy - service ID not set")
        return 0

    if not api_key:
        print("Skipping Render deploy - RENDER_API_KEY not set")
        return 0

    client = RenderClient(api_key=api_key, service_id=svc_id)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            body = client.trigger_deploy(svc_id)
            print("Deploy triggered:", body)
            if not RENDER_WAIT:
                return 0
            return wait_for_terminal_state(client, svc_id, body)
        except RenderApiError as exc:
            print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed with HTTP {exc.status}: {exc.body or exc}")
            if attempt == MAX_ATTEMPTS:
                return 1
            time.sleep(RETRY_DELAY_SECONDS)
        except Exception as exc:  # noqa: BLE001 - intentional retry-all policy
            print(f"Attempt {attempt}/{MAX_ATTEMPTS} unexpected transport error: {exc}")
            if attempt == MAX_ATTEMPTS:
                return 1
            time.sleep(RETRY_DELAY_SECONDS)

    return 1


def wait_for_terminal_state(client: "RenderClient", svc_id: str, trigger_body: dict) -> int:
    """Poll the triggered deploy to a terminal state (issue #1855).

    live -> 0. build_failed/update_failed/deactivated/canceled -> 1 (the enclosing
    job fails -> the event-driven deploy-doctor arm + notify-failure fire IN-RUN).
    Timeout: exit 1 unless the deploy already reached pre_live (deploy essentially
    complete; loud warning instead of a false failure).
    """
    deploy_id = (trigger_body or {}).get("id")
    if not deploy_id:
        print("Deploy trigger response carried no id — cannot poll; treating as triggered (legacy behavior)")
        return 0

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last = None
    while time.monotonic() < deadline:
        try:
            deploy = client.get_deploy(deploy_id, svc_id)
        except Exception as exc:  # noqa: BLE001 - transient poll errors are retried
            print(f"poll error (will retry): {exc}")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        last = deploy.get("status") or deploy.get("deploy", {}).get("status") if isinstance(deploy, dict) else None
        if last in OK_STATES:
            print(f"Deploy {deploy_id} reached terminal state: live ✓")
            return 0
        if last in FAIL_STATES:
            print(f"Deploy {deploy_id} reached terminal FAILURE state: {last}")
            return 1
        print(f"Deploy {deploy_id} status: {last} (polling every {POLL_INTERVAL_SECONDS}s)...")
        time.sleep(POLL_INTERVAL_SECONDS)

    if last == "pre_live":
        print(f"::warning::Deploy {deploy_id} still pre_live after {POLL_TIMEOUT_SECONDS}s — build finished, traffic promotion pending; treating as success.")
        return 0
    print(f"::error::Deploy {deploy_id} did not reach a terminal state within {POLL_TIMEOUT_SECONDS}s (last: {last}).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
