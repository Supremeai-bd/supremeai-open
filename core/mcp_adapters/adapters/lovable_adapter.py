"""Lovable adapter — official API/MCP client, no scraping (issue #943, MESH-5).

বাংলা সারসংক্ষেপ:
------------------
Lovable-এর সাথে সংযোগ **অফিসিয়াল API/ MCP endpoint** দিয়ে — স্ক্র্যাপিং নয়
(issue-র স্পষ্ট নির্দেশ)। httpx-ভিত্তিক, নেটওয়ার্ক ব্যর্থতা নীরবে গিলে না —
(status, payload) টুপল ফেরত।

Env: `LOVABLE_API_TOKEN` (required লেখা অপারেশনে), `LOVABLE_API_BASE`
(default https://api.lovable.dev)।
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from core.logging_config import logger


class LovableAdapter:
    """Lovable প্রজেক্ট/প্রম্পট অপারেশন — অফিসিয়াল API ক্লায়েন্ট।"""

    def __init__(self, api_base: str | None = None, api_token: str | None = None) -> None:
        self.api_base = (
            api_base or os.getenv("LOVABLE_API_BASE", "") or "https://api.lovable.dev"
        ).rstrip("/")
        self.api_token = api_token or os.getenv("LOVABLE_API_TOKEN", "")

    @property
    def configured(self) -> bool:
        """লেখা অপারেশনে টোকেন লাগবেই — না থাকলে fail-closed।"""
        return bool(self.api_token)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        """একটি API কল — কখনো raise নয়, (status_code, parsed) রিটার্ন।"""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.request(
                    method, f"{self.api_base}{path}", json=json_body, headers=self._headers()
                )
            try:
                return resp.status_code, resp.json()
            except ValueError:
                return resp.status_code, {"detail": resp.text[:200]}
        except httpx.HTTPError as exc:
            logger.warning(f"[LovableAdapter] {method} {path} failed: {exc}")
            return 0, {"detail": f"lovable unreachable: {exc}"}

    # ── High-level ops ───────────────────────────────────────────────────────
    async def create_project(self, name: str, prompt: str) -> tuple[int, Any]:
        """নতুন Lovable project — spec/prompt দিয়ে।"""
        if not self.configured:
            return 401, {"detail": "LOVABLE_API_TOKEN not configured (fail-closed)"}
        return await self.request("POST", "/v1/projects", {"name": name, "prompt": prompt})

    async def push_update(self, project_id: str, prompt: str) -> tuple[int, Any]:
        """একটি বিদ্যমান project-এ পরিবর্তন-নির্দেশ পাঠাও।"""
        if not self.configured:
            return 401, {"detail": "LOVABLE_API_TOKEN not configured (fail-closed)"}
        return await self.request("POST", f"/v1/projects/{project_id}/updates", {"prompt": prompt})

    async def get_project(self, project_id: str) -> tuple[int, Any]:
        """প্রজেক্ট বিবরণ — পড়া অপারেশন।"""
        return await self.request("GET", f"/v1/projects/{project_id}")


__all__ = ["LovableAdapter"]
