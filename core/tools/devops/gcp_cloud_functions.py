from datetime import UTC, datetime
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class GCPCloudFunctionClient:
    """HTTP trigger client for SupremeAI Google Cloud Functions."""

    def __init__(
        self,
        project_id: str | None = None,
        region: str | None = None,
        function_name: str | None = None,
        base_url: str | None = None,
        bearer_token: str | None = None,
        timeout: float = 30.0,
    ):
        self.project_id = (
            project_id
            or getattr(settings, "gcp_project_id", None)
            or getattr(settings, "google_cloud_project", None)
        )
        self.region = region or getattr(settings, "gcp_region", "us-central1")
        self.function_name = function_name or getattr(settings, "gcp_cloud_function_name", None)
        self.base_url = (base_url or getattr(settings, "gcp_cloud_function_url", "")).rstrip("/")
        self.bearer_token = bearer_token or getattr(
            settings, "gcp_cloud_function_bearer_token", None
        )
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.function_url)

    @property
    def function_url(self) -> str | None:
        if self.base_url:
            return self.base_url
        if self.project_id and self.function_name:
            return (
                f"https://{self.region}-{self.project_id}.cloudfunctions.net/{self.function_name}"
            )
        return None

    def trigger(
        self,
        payload: dict[str, Any],
        endpoint: str | None = None,
        method: str = "POST",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = self._url_for(endpoint)
        if not url:
            return {
                "success": False,
                "provider": "gcp_cloud_functions",
                "error": "GCP Cloud Function URL is not configured",
            }

        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        started = datetime.now(UTC)
        try:
            with httpx.Client(timeout=timeout or self.timeout) as client:
                response = client.request(method, url, json=payload, headers=headers)
            latency_ms = (datetime.now(UTC) - started).total_seconds() * 1000
            return {
                "success": 200 <= response.status_code < 300,
                "provider": "gcp_cloud_functions",
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "function_url": url,
                "data": self._safe_json(response),
            }
        except Exception as exc:
            logger.error(f"GCP Cloud Function trigger failed: {exc}")
            return {
                "success": False,
                "provider": "gcp_cloud_functions",
                "function_url": url,
                "error": str(exc),
            }

    def trigger_ocr(
        self, image_urls, project_id: str, user_id: str, languages=None
    ) -> dict[str, Any]:
        payload = {
            "imageUrls": image_urls,
            "projectId": project_id,
            "userId": user_id,
            "languages": languages or ["en", "bn"],
        }
        return self.trigger(payload, endpoint="processOCR")

    def get_config(self) -> dict[str, Any]:
        return {
            "provider": "gcp_cloud_functions",
            "project_id": self.project_id,
            "region": self.region,
            "function_name": self.function_name,
            "function_url": self.function_url,
            "configured": self.is_configured,
            "timeout": self.timeout,
        }

    def _url_for(self, endpoint: str | None) -> str | None:
        base = self.function_url
        if not base or not endpoint:
            return base
        return f"{base}/{endpoint.lstrip('/')}"

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return {"text": response.text}
