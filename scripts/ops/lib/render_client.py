"""Shared Render API client — DRY Phase 2-C1.

কেন: audit-এ ১৫টি আলাদা hand-rolled Render API client পাওয়া গেছে
(scripts/deploy/*, scripts/ci/*, backend/services) — প্রতিটায় আলাদাভাবে
token lookup + auth header + pagination লেখা; API বদলালে ১৫ জায়গায় ধরতে
হয়। এই module-টাই এখন একক সত্যের উৎস (SSOT):

    from render_client import RenderClient   # scripts/lib on sys.path
    client = RenderClient()
    client.list_deploys(limit=5)             # primary service
    client.trigger_deploy(clear_cache="do_not_clear")
    client.get_service()                     # primary service details

নতুন Render script লেখার আগে এখানে method যোগ করুন — অন্য script কপি
করে auth boilerplate লেখা নিষিদ্ধ (dry-gate philosophy)।

stdlib-only (urllib) — কোনো requests dependency নেই, তাই CI runner-এও
নির্ভরতাহীন। ধাপে ধাপে বাকি script-গুলো এখানে migrate হবে; প্রথম slice-এ
check_render.py, check_render_svc.py, trigger_render_deploy.py করা হয়েছে।
Phase 2-C3 slice: update_render_image, update_render_env2, list_render_services,
create_render_service, check_render_auto_deploy, render_trigger_deploy,
render_build_budget_guard, render_deploy_preflight, deploy_all_services,
verify_render_env — এখন সবাই এই client ব্যবহার করে (backend services পরে)।
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

RENDER_API_BASE = "https://api.render.com/v1"

# ঐতিহাসিক primary service — ৯টি পুরনো script-এ hardcoded ছিল; এখন এক জায়গায়।
# Override: RENDER_SERVICE_ID env var।
DEFAULT_PRIMARY_SERVICE_ID = "srv-da666f8u01pc739bm3t0"


class RenderApiError(RuntimeError):
    """Render API কল ব্যর্থ (non-2xx) বা credentials অনুপস্থিত।"""

    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class RenderClient:
    """Single-sourced Render REST client (stdlib-only, fail-fast)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        service_id: Optional[str] = None,
        api_base: str = RENDER_API_BASE,
    ):
        self.api_key = api_key or os.environ.get("RENDER_API_KEY", "")
        if not self.api_key:
            raise RenderApiError(
                "RENDER_API_KEY is not set (export it or pass api_key=...)"
            )
        self.default_service_id = service_id or os.environ.get(
            "RENDER_SERVICE_ID", DEFAULT_PRIMARY_SERVICE_ID
        )
        self.api_base = api_base.rstrip("/")

    # ── core transport ────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.api_base}{path}"
        if query:
            from urllib.parse import urlencode

            url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
        req = urllib.request.Request(
            url,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            with urllib.request.urlopen(req) as response:
                payload = response.read().decode()
            return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:  # non-2xx
            detail = exc.read().decode(errors="replace") if exc.fp else ""
            raise RenderApiError(
                f"Render API {method} {path} failed: HTTP {exc.code}",
                status=exc.code,
                body=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise RenderApiError(f"Render API {method} {path} unreachable: {exc.reason}") from exc

    # ── pagination helper (এক জায়গায় — আগে প্রতিটা script নিজে করত) ──
    def paginate(self, path: str, page_size: int = 20, max_pages: int = 10) -> Iterator[List[Dict[str, Any]]]:
        """Yield per-page lists; Render uses cursor pagination via the last item id."""
        after_id: Optional[str] = None
        for _ in range(max_pages):
            query = {"limit": page_size}
            if after_id:
                query["after"] = after_id
            items = self._request("GET", path, query=query) or []
            yield items
            if len(items) < page_size:
                break
            after_id = (items[-1] or {}).get("id") or (items[-1] or {}).get("deploy", {}).get("id")
            if not after_id:
                break

    # ── domain operations (সবগুলো script এগুলোই করত) ──────────────────
    def list_services(self, name: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        return self._request("GET", "/services", query={"name": name, "limit": limit}) or []

    def get_service(self, service_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", f"/services/{service_id or self.default_service_id}")

    def get_deploy(self, deploy_id: str, service_id: Optional[str] = None) -> Dict[str, Any]:
        """GET /v1/services/{id}/deploys/{deploy_id} — poll a single deploy's state.

        Added for epic #1850 Phase C / issue #1855: the render-deploy-status path
        polls a triggered deploy to a terminal state instead of fire-and-forget.
        """
        return self._request(
            "GET",
            f"/services/{service_id or self.default_service_id}/deploys/{deploy_id}",
        )

    def list_deploys(self, service_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        return self._request(
            "GET",
            f"/services/{service_id or self.default_service_id}/deploys",
            query={"limit": limit},
        ) or []

    def trigger_deploy(
        self,
        service_id: Optional[str] = None,
        clear_cache: str = "do_not_clear",
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/services/{service_id or self.default_service_id}/deploys",
            body={"clearCache": clear_cache},
        )

    # ── Phase 2-C3 operations (remaining scripts migrate onto these) ──
    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Public escape hatch — arbitrary Render API call through the single
        transport. নতুন endpoint-এর জন্য আগে domain method যোগ করার চেষ্টা করুন;
        শুধু তখনই এটা ব্যবহার করুন যখন সেটা এক script-এর একবারের প্রয়োজন।"""
        return self._request(method, path, body=body, query=query)

    def list_owners(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/owners") or []

    def create_service(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/services", body=payload)

    def delete_service(self, service_id: str) -> None:
        self._request("DELETE", f"/services/{service_id}")

    def update_service(self, service_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/services/{service_id}", body=body)

    def get_env_vars(self, service_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        return self._request(
            "GET", f"/services/{service_id}/env-vars", query={"limit": limit}
        ) or []

    def update_env_vars(
        self, service_id: str, env_vars: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        return self._request(
            "PUT", f"/services/{service_id}/env-vars", body=env_vars
        ) or []
