import logging
from typing import Any

from .mcp_security import MCPSecurityGuard

logger = logging.getLogger(__name__)


class PluginSecurityScanner:
    """
    Scans submitted community plugins for V1 compliance.
    V1 rules:
    - Must be purely declarative (no AST/Python code execution locally)
    - Must use HTTPS MCP URLs
    - Must not request core system capabilities (e.g., 'system.admin')
    """

    FORBIDDEN_CAPABILITIES = {"system.admin", "db.write_raw", "agent.core_memory"}

    @staticmethod
    def scan_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        """
        Runs the V1 security checks against a submitted manifest.
        """
        report = {"passed": True, "violations": []}

        # 1. Source check
        if manifest.get("source") != "mcp":
            report["passed"] = False
            report["violations"].append("V1 community plugins must be MCP-based (source='mcp').")

        # 2. URL check (if present)
        mcp_url = manifest.get("mcp_url")
        if mcp_url:
            if not MCPSecurityGuard.is_safe_url(mcp_url, enforce_https=True):
                report["passed"] = False
                report["violations"].append(f"Unsafe MCP URL: {mcp_url}")

        # 3. Capability boundary check
        requested_caps = manifest.get("permission_schema", [])
        for cap_req in requested_caps:
            if cap_req.get("name") in PluginSecurityScanner.FORBIDDEN_CAPABILITIES:
                report["passed"] = False
                report["violations"].append(
                    f"Forbidden capability requested: {cap_req.get('name')}"
                )

        return report
