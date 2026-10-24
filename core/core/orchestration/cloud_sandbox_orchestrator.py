"""
Cloud Sandbox Orchestrator
==========================

Manages ephemeral but persistent cloud environments (VMs/pods) for complex,
long-running AI tasks.
Integrates 'Freebuff CLI' as a zero-cost headless AI worker.
"""

import asyncio
import datetime
import os
from dataclasses import dataclass
from typing import Any

import httpx

from core.config_proxy import DynamicConfigProxy
from core.health.self_healer import SelfHealerService
from core.logging_config import logger
from utils.firestore_helpers import get_firestore_db


class CloudSandboxOrchestrator:
    """
    Orchestrates ephemeral cloud sandboxes (VMs) for code execution and delegates tasks to Freebuff.
    """

    def __init__(self, provider: str = "runpod"):
        self.provider = provider.lower()
        self.api_key = os.getenv(f"{self.provider.upper()}_API_KEY")

        self.base_url = self._get_base_url()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=60.0,
        )
        self._active_sandboxes = {}
        logger.info(f"Initialized CloudSandboxOrchestrator (Provider: {self.provider})")

    def _get_base_url(self) -> str:
        from core.config import settings

        if self.provider == "runpod":
            # বাংলা মন্তব্য: Hardcoded "https://api.runpod.io/v2" রিমুভ করা হলো
            return settings.runpod_api_url or "https://api.runpod.io/v2"
        elif self.provider == "modal":
            return getattr(settings, "modal_api_url", "https://api.modal.com")
        elif self.provider == "local":
            # Local mode is an explicit dry-run provider used by the API when no
            # remote sandbox credentials are configured.
            if (
                getattr(settings, "env", "") == "local"
                or getattr(settings, "environment", "") == "local"
                or settings.is_local()
            ):
                return "http://127.0.0.1"  # is_local()
            raise ValueError("Local sandbox provider is not permitted in production environments")
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def create_sandbox(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        if not self.api_key:
            logger.warning(
                "Cannot create sandbox: API key is missing. Running in mock/dry-run mode."
            )
            mock_id = f"mock-sandbox-id-{os.urandom(4).hex()}"
            self._active_sandboxes[mock_id] = {
                "created_at": datetime.datetime.now(datetime.UTC),
                "status": "running",
            }
            return {
                "id": mock_id,
                "status": "running",
                "provider": self.provider,
                "mock": True,
            }

        endpoint = self._get_endpoint("create")
        payload = self._prepare_creation_payload(spec)

        try:
            logger.info(f"Requesting new sandbox creation with spec: {spec}")
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            sandbox_id = data.get("id")
            if sandbox_id:
                self._active_sandboxes[sandbox_id] = {
                    "created_at": datetime.datetime.now(datetime.UTC),
                    "status": "running",
                }
            logger.success(f"Successfully created sandbox with ID: {sandbox_id}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to create sandbox. Status: {e.response.status_code}, Body: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred during sandbox creation: {e}")

        return None

    async def get_sandbox_status(self, sandbox_id: str) -> dict[str, Any] | None:
        if not self.api_key:
            logger.info(f"Dry-run: Fetching status for sandbox {sandbox_id}")
            return {
                "id": sandbox_id,
                "status": "running",
                "provider": self.provider,
                "mock": True,
            }

        endpoint = self._get_endpoint("status", sandbox_id)
        try:
            response = await self.client.get(endpoint)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to get status for sandbox {sandbox_id}. Status: {e.response.status_code}"
            )
        return None

    async def run_command(
        self, sandbox_id: str, command: str, timeout: int = 300
    ) -> dict[str, Any] | None:
        if not self.api_key:
            # বাংলা মন্তব্য: আগে ভুয়া "COMPLETED, exitCode 0, Mock output" ফেরত হতো —
            # mock flag উপেক্ষা করা caller সফল এক্সিকিউশন দেখত (audit B-07 fix,
            # 2026-09-17)। এখন সৎ non-success স্টেটাস — কমান্ড আসলে চলেনি।
            logger.warning(
                f"Dry-run: command '{command}' NOT executed in sandbox {sandbox_id} — "
                "provider credentials missing (audit B-07). Returning honest non-success."
            )
            return {
                "status": "MOCK_NOT_EXECUTED",
                "exitCode": None,
                "stdout": "",
                "stderr": (
                    "Sandbox provider credentials are missing, so the command was NOT "
                    "executed. Set the provider API key (e.g. RUNPOD_API_KEY) to enable "
                    "real execution."
                ),
                "mock": True,
            }

        endpoint = self._get_endpoint("run", sandbox_id)
        payload = {"input": {"command": command, "timeout": timeout}}

        try:
            logger.info(f"Running command in sandbox {sandbox_id}: {command}")
            response = await self.client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to run command in sandbox {sandbox_id}. Status: {e.response.status_code}"
            )
        return None

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        if not self.api_key:
            logger.warning(f"Dry-run: Destroying sandbox {sandbox_id}")
            return True

        endpoint = self._get_endpoint("destroy", sandbox_id)
        try:
            logger.warning(f"Destroying sandbox {sandbox_id}...")
            response = await self.client.post(endpoint)
            response.raise_for_status()
            logger.success(f"Sandbox {sandbox_id} destroyed successfully.")
            if sandbox_id in self._active_sandboxes:
                del self._active_sandboxes[sandbox_id]
            return True
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to destroy sandbox {sandbox_id}. Status: {e.response.status_code}"
            )
        return False

    async def auto_destroy_worker(self, tenant_id: str):
        """
        Background worker that checks TTL and terminates idle/crashed sandboxes.
        Integrates with SelfHealer to log errors if termination is due to a crash or timeout.
        """
        logger.info("Started Sandbox Auto-Destroy Worker")
        db = get_firestore_db()
        config_proxy = DynamicConfigProxy(tenant_id, db) if db else None

        while True:
            try:
                # Default 10 minutes TTL
                ttl_minutes = (
                    await config_proxy.get("SANDBOX_TTL_MINUTES", 10) if config_proxy else 10
                )
                ttl_delta = datetime.timedelta(minutes=ttl_minutes)
                now = datetime.datetime.now(datetime.UTC)

                for sandbox_id, data in list(self._active_sandboxes.items()):
                    created_at = data.get("created_at")
                    if created_at and (now - created_at) > ttl_delta:
                        logger.warning(
                            f"Sandbox {sandbox_id} exceeded TTL of {ttl_minutes}m. Terminating..."
                        )

                        # If we assume it timed out or crashed, notify SelfHealer
                        if db:
                            healer = SelfHealerService(db)
                            await healer.propose_fix(
                                tenant_id=tenant_id,
                                error_pattern=f"SandboxTimeout: Sandbox {sandbox_id} was active for > {ttl_minutes}m",
                                proposed_fix="# Recommend analyzing sandbox logs or increasing TTL for task.",
                                impact_score=0.3,
                                dependency_tree=["core.cloud_sandbox_orchestrator"],
                            )

                        await self.destroy_sandbox(sandbox_id)

                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Auto-Destroy Worker encountered an error: {e}")
                await asyncio.sleep(60)

    # ------------------------------------------------------------------------
    # 🤖 FREEBUFF AI WORKER INTEGRATION
    # ------------------------------------------------------------------------
    async def delegate_to_freebuff(self, prompt: str, working_dir: str = ".") -> dict[str, Any]:
        """
        বাংলা মন্তব্য: Freebuff CLI-কে অসিঙ্ক্রোনাস সাব-প্রসেস হিসেবে কল করে জিরো-কস্টে কোডিং টাস্ক এক্সিকিউট করা হচ্ছে।
        এটি SupremeAI-এর জন্য সম্পূর্ণ ফ্রি এআই ডেভেলপার হিসেবে কাজ করবে।
        """
        logger.info(f"🚀 Delegating task to Freebuff AI Worker in directory: {working_dir}")
        try:
            # বাংলা মন্তব্য: asyncio.create_subprocess_exec ব্যবহার করা হচ্ছে যাতে মূল ইভেন্ট লুপ ব্লক না হয়
            # উইন্ডোজের জন্য .cmd সাফিক্স হ্যান্ডলিং করা হয়েছে
            cmd = "freebuff.cmd" if os.name == "nt" else "freebuff"
            process = await asyncio.create_subprocess_exec(
                cmd,
                "--cwd",
                working_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # প্রম্পট ইনপুট হিসেবে পাঠানো হচ্ছে
            stdout, stderr = await process.communicate(input=prompt.encode("utf-8"))

            if process.returncode == 0:
                logger.success("✅ Freebuff task completed successfully.")
                return {"status": "success", "output": stdout.decode("utf-8")}
            else:
                logger.error(f"❌ Freebuff task failed: {stderr.decode('utf-8')}")
                return {"status": "error", "error": stderr.decode("utf-8")}

        except FileNotFoundError:
            logger.error(
                "🚨 Freebuff CLI not found. Please ensure it is installed globally (npm install -g freebuff)."
            )
            return {"status": "error", "error": "Freebuff CLI not installed."}
        except Exception as e:
            logger.error(f"⚠️ Unexpected error running Freebuff: {e}")
            return {"status": "error", "error": str(e)}

    # --- Provider-specific helpers ---
    def _get_endpoint(self, action: str, sandbox_id: str = "") -> str:
        if self.provider == "runpod":
            endpoints = {
                "create": "/",
                "status": f"/{sandbox_id}",
                "run": f"/{sandbox_id}/run",
                "destroy": f"/{sandbox_id}/terminate",
            }
            return endpoints[action]
        raise NotImplementedError(f"Endpoints for provider '{self.provider}' not implemented.")

    def _prepare_creation_payload(self, spec: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "runpod":
            return {"pod": spec}
        raise NotImplementedError(
            f"Payload preparation for provider '{self.provider}' not implemented."
        )


@dataclass
class SandboxSession:
    """Represents an active or provisioned session in a persistent cloud sandbox."""

    session_id: str
    sandbox_id: str
    status: str = "running"
    created_at: Any = None


class PersistentSandbox:
    """
    Manages persistent stateful cloud sandbox environments with attached volumes and session tracking.
    """

    def __init__(self, provider: str = "runpod"):
        self.provider = provider.lower()
        self.sessions: dict[str, SandboxSession] = {}
        self.api_key = os.getenv(f"{self.provider.upper()}_API_KEY")

    def _get_base_url(self) -> str:
        from core.config import settings

        if self.provider == "runpod":
            return settings.runpod_api_url or "https://api.runpod.io/v2"
        elif self.provider == "modal":
            return getattr(settings, "modal_api_url", "https://api.modal.com")
        return "https://api.runpod.io/v2"

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._get_base_url(),
            headers=self._get_headers(),
            timeout=60.0,
        )

    async def create_with_volume(
        self, image: str, volume_size_gb: int = 10, ttl_hours: int = 24
    ) -> SandboxSession:
        client = self._get_client()
        payload = {
            "image": image,
            "volume_size_gb": volume_size_gb,
            "ttl_hours": ttl_hours,
        }
        res = client.post(f"/{self.provider}/persistent_volume", json=payload)
        if asyncio.iscoroutine(res):
            res = await res
        data = res.json() if hasattr(res, "json") else {}
        session_id = data.get("session_id", f"session_{os.urandom(4).hex()}")
        sandbox_id = data.get("id", f"sandbox_{os.urandom(4).hex()}")
        status = data.get("status", "running")
        session = SandboxSession(
            session_id=session_id,
            sandbox_id=sandbox_id,
            status=status,
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        self.sessions[session_id] = session
        return session

    async def execute_in_session(self, session_id: str, command: str) -> dict[str, Any]:
        client = self._get_client()
        res = client.post(f"/sessions/{session_id}/execute", json={"command": command})
        if asyncio.iscoroutine(res):
            res = await res
        return res.json() if hasattr(res, "json") else {"status": "FAILED", "exitCode": 1}

    async def install_dependency(self, session_id: str, manager: str, package: str) -> bool:
        client = self._get_client()
        res = client.post(
            f"/sessions/{session_id}/install",
            json={"manager": manager, "package": package},
        )
        if asyncio.iscoroutine(res):
            res = await res
        data = res.json() if hasattr(res, "json") else {}
        return data.get("status") == "COMPLETED" or data.get("exitCode") == 0

    async def upload_file(self, session_id: str, path: str, content: str) -> bool:
        client = self._get_client()
        res = client.post(
            f"/sessions/{session_id}/upload",
            json={"path": path, "content": content},
        )
        if asyncio.iscoroutine(res):
            res = await res
        data = res.json() if hasattr(res, "json") else {}
        return (
            data.get("status") in ("success", "COMPLETED")
            or getattr(res, "status_code", 200) == 200
        )

    async def download_file(self, session_id: str, path: str) -> bytes:
        client = self._get_client()
        res = client.get(f"/sessions/{session_id}/download", params={"path": path})
        if asyncio.iscoroutine(res):
            res = await res
        if hasattr(res, "json"):
            try:
                data = res.json()
                if isinstance(data, dict) and "content" in data:
                    val = data["content"]
                    return val.encode("utf-8") if isinstance(val, str) else bytes(val)
            except Exception as exc:
                # বাংলা: JSON বডি না পারলে raw-bytes fallback — কিন্তু নীরবে নয়,
                # diagnosable হতে হবে (False-Assurance doctrine: silent swallow নিষিদ্ধ)।
                logger.debug(
                    f"download_file: response body is not JSON "
                    f"({type(exc).__name__}: {exc}); falling back to raw bytes"
                )
        if hasattr(res, "content"):
            return (
                res.content if isinstance(res.content, bytes) else str(res.content).encode("utf-8")
            )
        return b""

    async def destroy_sandbox(self, session_id: str) -> bool:
        client = self._get_client()
        res = client.post(f"/sessions/{session_id}/destroy")
        if asyncio.iscoroutine(res):
            res = await res
        if session_id in self.sessions:
            del self.sessions[session_id]
        return True

    async def list_sessions(self) -> list[SandboxSession]:
        return list(self.sessions.values())
