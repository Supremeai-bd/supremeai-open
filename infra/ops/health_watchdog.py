"""
SupremeAI Federation Multi-Satellite Health Watchdog
Periodic automated prober monitoring endpoints across federation satellites.
"""

import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("infra.health_watchdog")


@dataclass
class EndpointStatus:
    name: str
    url: str
    healthy: bool
    status_code: int
    latency_ms: float
    consecutive_failures: int = 0
    last_checked_iso: str = ""
    error_message: str | None = None


@dataclass
class WatchdogAlert:
    satellite_name: str
    endpoint_url: str
    consecutive_failures: int
    severity: str
    title: str
    details: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


DEFAULT_ENDPOINTS = {
    "mcp-tower-health": "http://localhost:3000/health",
    "mcp-tower-mcp": "http://localhost:3000/mcp",
    "gateway-models": "http://localhost:8080/v1/models",
    "studio-dashboard": "http://localhost:5173/",
}


class FederationWatchdog:
    """Multi-satellite health watchdog with configurable alert thresholds."""

    def __init__(
        self,
        endpoints: dict[str, str] | None = None,
        failure_threshold: int = 3,
        timeout_seconds: float = 5.0,
        probe_fn: Callable[[str], tuple[bool, int, float, str | None]] | None = None,
    ):
        self.endpoints = endpoints or dict(DEFAULT_ENDPOINTS)
        self.failure_threshold = max(1, failure_threshold)
        self.timeout_seconds = timeout_seconds
        self._probe_fn = probe_fn or self._default_http_probe
        self.statuses: dict[str, EndpointStatus] = {
            name: EndpointStatus(
                name=name,
                url=url,
                healthy=True,
                status_code=0,
                latency_ms=0.0,
                consecutive_failures=0,
            )
            for name, url in self.endpoints.items()
        }
        self.alerts: list[WatchdogAlert] = []

    def _default_http_probe(self, url: str) -> tuple[bool, int, float, str | None]:
        """Standard library HTTP GET probe."""
        start = datetime.now(timezone.utc)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SupremeAI-Infrastructure-Guardian/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0
                return (200 <= resp.status < 400, resp.status, elapsed, None)
        except urllib.error.HTTPError as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0
            return (False, e.code, elapsed, str(e.reason))
        except (
            urllib.error.URLError,
            OSError,
            TimeoutError,
            ConnectionError,
            ValueError,
        ) as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0
            return (False, 0, elapsed, str(e))

    def probe_endpoint(self, name: str) -> EndpointStatus:
        """Probes a single endpoint and updates internal telemetry."""
        url = self.endpoints.get(name)
        if not url:
            raise KeyError(f"Endpoint '{name}' not registered in watchdog.")

        healthy, status_code, latency_ms, error = self._probe_fn(url)
        now_iso = datetime.now(timezone.utc).isoformat()
        current = self.statuses[name]

        if healthy:
            current.consecutive_failures = 0
            current.healthy = True
            current.status_code = status_code
            current.latency_ms = latency_ms
            current.error_message = None
            current.last_checked_iso = now_iso
        else:
            current.consecutive_failures += 1
            current.healthy = False
            current.status_code = status_code
            current.latency_ms = latency_ms
            current.error_message = error
            current.last_checked_iso = now_iso

            if current.consecutive_failures >= self.failure_threshold:
                alert = WatchdogAlert(
                    satellite_name=name,
                    endpoint_url=url,
                    consecutive_failures=current.consecutive_failures,
                    severity="CRITICAL"
                    if current.consecutive_failures >= 5
                    else "HIGH",
                    title=f"[SATELLITE_DOWN] {name} failed {current.consecutive_failures} consecutive probes",
                    details=(
                        f"Satellite {name} ({url}) returned status {status_code} "
                        f"with error: {error}. Threshold is {self.failure_threshold}."
                    ),
                    created_at_iso=now_iso,
                )
                self.alerts.append(alert)

        return current

    def probe_all(self) -> dict[str, EndpointStatus]:
        """Probes all registered satellite endpoints sequentially."""
        for name in self.endpoints:
            self.probe_endpoint(name)
        return self.statuses

    def get_unhealthy(self) -> list[EndpointStatus]:
        """Returns all currently unhealthy endpoints."""
        return [s for s in self.statuses.values() if not s.healthy]

    def build_incident_report(self) -> str:
        """Generates markdown incident report payload for supremeai-open issue creation."""
        unhealthy = self.get_unhealthy()
        if not unhealthy and not self.alerts:
            return "## Multi-Satellite Health Check: ALL SYSTEMS OPERATIONAL\n\nAll endpoints are healthy."

        lines = [
            "## 🚨 Infrastructure Guardian Incident Report",
            "",
            f"**Timestamp:** `{datetime.now(timezone.utc).isoformat()}`",
            f"**Active Alerts:** {len(self.alerts)}",
            "",
            "### Unhealthy Endpoints",
            "| Satellite | URL | Status Code | Failures | Latency | Error |",
            "|---|---|---|---|---|---|",
        ]
        for ep in unhealthy:
            lines.append(
                f"| `{ep.name}` | `{ep.url}` | {ep.status_code} | "
                f"**{ep.consecutive_failures}** | {ep.latency_ms:.1f}ms | {ep.error_message or 'None'} |"
            )

        return "\n".join(lines)
