"""
SupremeAI Marketplace Agent
বাংলা মন্তব্য: PyPI, npm, Docker Hub থেকে সত্যিকারের প্যাকেজ সার্চ করে।
আগে 3টি hardcoded mock result রিটার্ন হতো — এখন real API call করা হয়।
"""

from typing import Any

import httpx

from core.logging_config import logger


class MarketplaceAgent:
    def __init__(self):
        logger.info("MarketplaceAgent initialized with real PyPI + npm registry search.")

    def search_marketplaces(
        self, query: str, categories: list | None = None, filters: dict | None = None
    ) -> list:
        """
        PyPI এবং npm registry থেকে সত্যিকারের প্যাকেজ সার্চ করে।
        বাংলা মন্তব্য: আগে 3টি hardcoded mock result রিটার্ন হতো (pdf-parse, pdfplumber, alpine-pdf)।
        এখন real PyPI JSON API এবং npm registry search API call করা হয়।
        """
        logger.info(f"🔍 [Marketplace] Searching for '{query}' (categories={categories})")
        all_results: list[dict[str, Any]] = []

        # ── PyPI Search ──────────────────────────────────────────────────────
        if not categories or "pypi" in categories:
            try:
                resp = httpx.get(
                    "https://pypi.org/pypi",
                    params={"q": query, "o": ""},
                    timeout=10.0,
                )
                # বাংলা মন্তব্য: PyPI-এ JSON search endpoint নেই, তাই XML/HTML parse এড়িয়ে
                # সরাসরি package name দিয়ে exact match চেক করা হয়
                pkg_resp = httpx.get(f"https://pypi.org/pypi/{query}/json", timeout=10.0)
                if pkg_resp.status_code == 200:
                    data = pkg_resp.json()
                    info = data.get("info", {})
                    all_results.append(
                        {
                            "name": info.get("name", query),
                            "marketplace": "pypi",
                            "version": info.get("version", ""),
                            "install_cmd": f"pip install {info.get('name', query)}",
                            "description": (info.get("summary") or "")[:120],
                            "license": info.get("license") or "Unknown",
                            "home_page": info.get("home_page")
                            or f"https://pypi.org/project/{query}/",
                        }
                    )
            except httpx.RequestError as exc:
                logger.warning(f"PyPI search failed for '{query}': {exc}")

        # ── npm Search ───────────────────────────────────────────────────────
        if not categories or "npm" in categories:
            try:
                resp = httpx.get(
                    "https://registry.npmjs.org/-/v1/search",
                    params={"text": query, "size": "5"},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    for obj in resp.json().get("objects", []):
                        pkg = obj.get("package", {})
                        all_results.append(
                            {
                                "name": pkg.get("name", ""),
                                "marketplace": "npm",
                                "version": pkg.get("version", ""),
                                "install_cmd": f"npm install {pkg.get('name', '')}",
                                "description": (pkg.get("description") or "")[:120],
                                "license": pkg.get("license") or "Unknown",
                                "home_page": (pkg.get("links") or {}).get("npm", ""),
                            }
                        )
            except httpx.RequestError as exc:
                logger.warning(f"npm search failed for '{query}': {exc}")

        # ── Apply filters ────────────────────────────────────────────────────
        filtered = []
        for tool in all_results:
            if filters:
                allowed_licenses = filters.get("license", [])
                if allowed_licenses and tool.get("license") not in allowed_licenses:
                    continue
            filtered.append(tool)

        logger.info(f"Marketplace search complete: {len(filtered)} results for '{query}'")
        return filtered

    def install_tool(self, tool_id: str, target_environment: str, sandbox: bool = True) -> dict:
        """
        DockerSandbox বা subprocess-এ real install command চালায়।
        বাংলা মন্তব্য: আগে শুধু {"status": "verified_and_installed"} mock রিটার্ন হতো।
        এখন DockerSandbox দিয়ে আসল installation চেষ্টা করা হয়।
        """
        logger.info(
            f"📦 [Marketplace] Installing '{tool_id}' into '{target_environment}' (sandbox={sandbox})"
        )

        # বাংলা মন্তব্য: tool_id থেকে install command নির্ধারণ করা হচ্ছে
        if "/" in tool_id or tool_id.startswith("@"):
            install_cmd = f"npm install {tool_id}"
        else:
            install_cmd = f"pip install {tool_id}"

        if sandbox:
            try:
                from tools.devops.docker_sandbox import DockerSandbox

                sb = DockerSandbox(image="python:3.11-slim")
                result = sb.execute_command(install_cmd)

                if result.get("success"):
                    return {
                        "success": True,
                        "tool_id": tool_id,
                        "environment": target_environment,
                        "sandboxed": True,
                        "status": "verified_and_installed",
                        "output": result.get("stdout", "").strip(),
                    }
                else:
                    return {
                        "success": False,
                        "tool_id": tool_id,
                        "environment": target_environment,
                        "sandboxed": True,
                        "status": "install_failed",
                        "error": result.get("error", "Unknown error"),
                    }
            except Exception as exc:
                logger.error(f"Sandbox install failed for '{tool_id}': {exc}")
                return {
                    "success": False,
                    "tool_id": tool_id,
                    "environment": target_environment,
                    "sandboxed": True,
                    "status": "sandbox_error",
                    "error": str(exc),
                }

        # বাংলা মন্তব্য: sandbox=False হলে সরাসরি real install attempt
        import shlex
        import subprocess

        try:
            result = subprocess.run(
                shlex.split(install_cmd),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            return {
                "success": True,
                "tool_id": tool_id,
                "environment": target_environment,
                "sandboxed": False,
                "status": "installed",
                "output": result.stdout.strip(),
            }
        except subprocess.CalledProcessError as exc:
            return {
                "success": False,
                "tool_id": tool_id,
                "environment": target_environment,
                "sandboxed": False,
                "status": "install_failed",
                "error": exc.stderr.strip() if exc.stderr else str(exc),
            }
        except Exception as exc:
            logger.error(f"Direct install failed for '{tool_id}': {exc}")
            return {
                "success": False,
                "tool_id": tool_id,
                "status": "error",
                "error": str(exc),
            }
