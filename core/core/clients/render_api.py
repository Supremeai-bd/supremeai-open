"""Single-sourced Render REST transport for backend services (DRY Phase 2-C4).

কেন: `services/render_account_service.py` ও `services/render_preflight_service.py`
দুটোই আলাদাভাবে hand-roll করত — URL construction + Bearer auth headers +
urlopen + JSON decode। API বদলালে দুই জায়গায় ধরতে হতো। এই module-ই এখন
backend-এর একক transport:

    from core.clients.render_api import render_get_json, RENDER_API_BASE

    payload = render_get_json(f"/services/{service_id}/deploys", api_key=key,
                              query={"limit": 100})

Error semantics: raises `urllib.error.HTTPError` / `urllib.error.URLError`
verbatim — callers keep their own business policy (e.g. preflight-এর
429 → cooldown). এখানে কোনো retry/policy নেই, শুধু একক transport।

stdlib-only — scripts/lib/render_client.py-এর সাথে সামঞ্জস্যপূর্ণ; তবে
backend package boundary রক্ষা করতে scripts থেকে import করা হয়নি।
"""

from __future__ import annotations

import json
import urllib.error  # noqa: F401 — re-exported for caller convenience
import urllib.parse
import urllib.request
from typing import Any

RENDER_API_BASE = "https://api.render.com/v1"


def render_get_json(
    path: str,
    api_key: str | None = None,
    query: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    """Perform a GET against the Render REST API and return the parsed body.

    - `path` must start with "/" (relative to RENDER_API_BASE).
    - `api_key` becomes a Bearer Authorization header when provided.
    - `query` items with None values are dropped (urlencode-compatible).
    - Raises `urllib.error.HTTPError` / `urllib.error.URLError` unchanged.
    """
    url = f"{RENDER_API_BASE}{path}"
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})

    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
