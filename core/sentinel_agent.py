"""This module defines the `SentinelAgent`, an autonomous background agent crucial for the SupremeAI project's system observability and self-healing capabilities. It periodically monitors the health and performance of configured API endpoints, audits system dependencies, and provides event-driven hooks to record system incidents, thereby ensuring the overall reliability and stability of the AI ecosystem by proactively identifying and logging potential issues.

Key Components:
- `SentinelAgent`: The core class implementing an autonomous agent responsible for system health monitoring, dependency auditing, and incident management.
- `monitor_endpoints()`: Asynchronously polls configured API endpoints, records their latency and status, and logs critical `SystemIncident` entries for failures or high latency.
- `audit_dependencies()`: Performs periodic auditing of system dependencies, updating their last audit time (currently a placeholder for more complex version checking logic).
- `trigger_event()`: Provides an event-driven interface to immediately record `SystemIncident` entries based on external triggers or middleware events.
- `run_periodic_loop()`: The main asynchronous loop that orchestrates the periodic execution of endpoint monitoring and dependency auditing tasks, designed to run as part of the application's lifespan.
- `sentinel`: A global singleton instance of the `SentinelAgent` for consistent access and management throughout the application.

Dependencies:
- `asyncio`: For asynchronous programming and managing the agent's periodic execution loop.
- `datetime`: For handling timestamps, calculating latencies, and managing UTC times.
- `httpx`: An asynchronous HTTP client used for polling external and internal API endpoints.
- `loguru`: For structured and flexible logging of agent activities and errors.
- `sqlalchemy`: For asynchronous ORM interactions with the database, specifically for `ApiEndpoint`, `SystemDependency`, and `SystemIncident` models.
- `database.session`: Internal module providing the asynchronous database session factory (`AsyncSessionLocal`).
- `models.sentinel`: Internal module defining the ORM models (`ApiEndpoint`, `SystemDependency`, `SystemIncident`) used by the agent for data persistence.
"""

import asyncio
import os
import shutil
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from core.config import settings
from core.logging_config import logger
from database.session import AsyncSessionLocal
from models.sentinel import ApiEndpoint, SystemDependency, SystemIncident


class SentinelAgent:
    """
    Sentinel Agent: Background autonomous agent for system observability and self-healing.
    Runs periodically and is also callable via event-driven hooks.
    """

    def __init__(self):
        self.running = True
        # Track if single worker lock is engaged
        self._is_active = False

    def _validate_endpoint_url(self, url: str) -> bool:
        """Validate URL to prevent SSRF attacks - blocks metadata IPs and disallowed schemes."""
        import re
        from urllib.parse import urlparse

        from core.config import settings

        try:
            parsed = urlparse(url)
            # Block dangerous schemes
            if parsed.scheme in {"file", "gopher", "ftp", "sftp"}:
                return False
            # Block cloud metadata IPs (AWS, GCP, Azure)
            hostname = parsed.hostname or ""
            if re.match(r"^(169\.254\.169\.|10\.\d+\.|172\.(1[6-9]|2[0-9]|3[01])\.)", hostname):
                return False
            # Block localhost access in production unless it targets the backend port 8080
            # বাংলা মন্তব্য: প্রোডাকশনে লোকালহোস্ট ব্লক করা হচ্ছে, কিন্তু আমাদের নিজস্ব ব্যাকএন্ড পোর্ট ৮০৮০ মনিটর করার জন্য পোলিং এলাও করা হলো।
            if settings.env in {"production", "staging"}:
                if "localhost" in hostname or "127.0.0.1" in hostname:  # is_local()
                    if parsed.port != 8080:
                        return False
            return True
        except (ValueError, TypeError):
            return False

    async def monitor_endpoints(self):
        """
        Polls configured ApiEndpoints and logs SystemIncident if latency is high or status fails.
        """
        try:
            async with AsyncSessionLocal() as session:
                # Get all endpoints
                result = await session.execute(select(ApiEndpoint))
                endpoints = result.scalars().all()

                if not endpoints:
                    return

                async with httpx.AsyncClient(timeout=10.0) as client:
                    for ep in endpoints:
                        start_time = datetime.now(UTC)
                        try:
                            # Secure URL construction with SSRF protection
                            if ep.path.startswith("http"):
                                url = ep.path
                            else:
                                # Internal endpoints should use loopback to bypass external TLS proxy issues
                                port = os.environ.get("PORT", "8080")
                                base = f"http://0.0.0.0:{port}"
                                url = f"{base}{ep.path}"

                            # SSRF protection
                            if not self._validate_endpoint_url(url):
                                logger.critical(f"SSRF Blocked: Attempted access to {url}")
                                continue

                            # Make the request only after SSRF validation
                            resp = await client.request(ep.method, url)
                            latency = (datetime.now(UTC) - start_time).total_seconds() * 1000

                            ep.latency_ms = int(latency)
                            ep.last_check_at = datetime.now(UTC)

                            if resp.status_code != ep.expected_status:
                                ep.last_ping_status = "down"
                                if ep.is_critical:
                                    # Create Incident
                                    incident = SystemIncident(
                                        incident_type="api_endpoint_failure",
                                        severity="critical",
                                        remediation_log=f"Endpoint {ep.path} returned {resp.status_code} instead of {ep.expected_status}.",
                                    )
                                    session.add(incident)
                            else:
                                ep.last_ping_status = "up"

                        except Exception as e:
                            ep.last_ping_status = "down"
                            ep.last_check_at = datetime.now(UTC)

                            # Safely extract hostname for logging without exposing full URL paths
                            from urllib.parse import urlparse

                            parsed_url = urlparse(url)
                            sanitized_host = parsed_url.hostname or "unknown-host"

                            logger.error(
                                f"[SentinelAgent] TLS/Connection error for {sanitized_host}: {e!s}"
                            )

                            incident = SystemIncident(
                                incident_type="api_endpoint_unreachable",
                                severity="critical" if ep.is_critical else "warning",
                                remediation_log=f"Exception connecting to {sanitized_host} (path: {ep.path}): {e!s}",
                            )
                            session.add(incident)

                await session.commit()
        except Exception as e:
            logger.exception(f"[SentinelAgent] Error during monitor_endpoints: {e}")

    async def audit_dependencies(self):
        """
        Runs heavy auditing logic (e.g., pip-audit / pip list --outdated)
        and updates SystemDependency status dynamically.

        বাংলা মন্তব্য: আগে এখানে শুধু ডামি রিলেশন টাচ করে টাইমস্ট্যাম্প আপডেট করা হতো।
        এখন এটি pip-audit/pip command রান করে অরফ্যানড বা আউটডেটেড প্যাকেজ সনাক্ত করে
        সিস্টেমের ডিপেনডেন্সি ডাটাবেস আপডেট করে।
        """
        import asyncio
        import json

        logger.info("[SentinelAgent] Running dependency audit via system environment tools...")

        # Check if pip-audit is available, fallback to pip list --outdated
        audit_cmd = None
        if shutil.which("pip-audit"):
            audit_cmd = ["pip-audit", "--format=json"]
        elif shutil.which("pip"):
            audit_cmd = ["pip", "list", "--outdated", "--format=json"]

        vulnerabilities = []
        if audit_cmd:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *audit_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode in (0, 1) and stdout:
                    vulnerabilities = json.loads(stdout.decode("utf-8"))
            except Exception as e:
                logger.warning(f"[SentinelAgent] Failed executing audit process: {e}")

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(SystemDependency))
                deps = result.scalars().all()
                for dep in deps:
                    dep.last_audit_at = datetime.now(UTC)
                    # Check if package is flagged as vulnerable in scan report
                    # Depending on command output structure (dict or list)
                    is_vuln = False
                    if isinstance(vulnerabilities, list):
                        is_vuln = any(
                            v.get("name", "").lower() == dep.package_name.lower()
                            for v in vulnerabilities
                        )
                    elif isinstance(vulnerabilities, dict):
                        is_vuln = dep.package_name in vulnerabilities.get("dependencies", {})

                    if is_vuln:
                        dep.status = "vulnerable"
                        # Trigger immediate remediation alert
                        logger.error(
                            f"[SentinelAgent] Flagged security risk: package {dep.package_name} is vulnerable!"
                        )
                        await self.trigger_event(
                            "SECURITY_RISK",
                            f"Dependency {dep.package_name} failed security scan.",
                        )
                    else:
                        dep.status = "secure"
                await session.commit()
        except Exception as e:
            logger.exception(f"[SentinelAgent] Error during audit_dependencies: {e}")

    async def trigger_event(self, event_type: str, details: str):
        """
        Event-driven hook for middleware to immediately trigger an incident review.
        """
        try:
            async with asyncio.timeout(5):
                async with AsyncSessionLocal() as session:
                    incident = SystemIncident(
                        incident_type=event_type,
                        severity="warning",
                        remediation_log=details,
                    )
                    session.add(incident)
                    await session.commit()
                    logger.info(f"[SentinelAgent] Event-driven incident recorded: {event_type}")
        except TimeoutError:
            logger.warning(f"[SentinelAgent] Event trigger timed out for: {event_type}")
        except Exception as e:
            logger.exception(f"[SentinelAgent] Error triggering event: {e}")

    def _zero_cost_ready(self) -> bool:
        """True when the Zero-Cost orchestrator is initialized (issue #1830).

        Checked cheaply and defensively — if the subsystem is absent or dark,
        the sentinel keeps its legacy direct-probe path.
        """
        try:
            from core.zero_cost_architecture.zero_cost_patch_phase1_4 import get_orchestrator

            return bool(getattr(get_orchestrator(), "_initialized", False))
        except Exception:
            return False

    async def _resilient_probe(self) -> None:
        """Run one monitor cycle through the Zero-Cost resilience layer.

        Feeds task_success/task_duration metrics into the learning engine so
        /zero-cost/recommendations reflects real workload data.
        """
        from core.zero_cost_architecture.zero_cost_patch_phase1_4 import get_orchestrator

        await get_orchestrator().execute_with_resilience(
            self.monitor_endpoints,
            circuit_breaker="sentinel_monitor",
            timeout=55.0,
        )

    async def run_periodic_loop(self):
        """
        The main async loop to be attached to FastAPI lifespan.
        Uses a basic active flag to prevent multiple executions if workers > 1.
        """
        if self._is_active:
            logger.warning("[SentinelAgent] Agent already active, skipping duplicate startup.")
            return

        self._is_active = True
        logger.info("[SentinelAgent] Starting Periodic Loop (Heartbeat: 60s, Audit: 12h)...")

        audit_counter = 0

        try:
            while self.running:
                # 1. Quick Heartbeat (60 seconds) — routed through the
                # Zero-Cost resilience layer when it is initialized (issue
                # #1830): every probe now feeds task_success/task_duration
                # metrics into the learning engine, so /zero-cost/recommendations
                # becomes data-derived instead of a hardcoded constant. The
                # probe stays fail-soft: any resilience-layer failure falls
                # back to a direct call so monitoring never stops.
                probe_ok = False
                if self._zero_cost_ready():
                    try:
                        await self._resilient_probe()
                        probe_ok = True
                    except Exception as exc:
                        logger.warning(f"[SentinelAgent] Resilient probe failed: {exc}")
                if not probe_ok:
                    await self.monitor_endpoints()

                # 2. Long Audit (Every 12 hours) - 12h = 720 minutes = 720 iterations of 60s
                if audit_counter >= 720:
                    await self.audit_dependencies()
                    audit_counter = 0

                audit_counter += 1
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("[SentinelAgent] Periodic Loop cancelled. Shutting down gracefully.")
            self._is_active = False
            raise


# Global singleton instance
sentinel = SentinelAgent()
