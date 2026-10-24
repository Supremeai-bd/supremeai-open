import re
import uuid
from typing import Any, ClassVar

import httpx

from core.config import settings
from core.logging_config import logger


class ResourceCatalog:
    """Searches open-source resource catalogs for external tool entries."""

    AWESOME_SELFHOSTED_URL = (
        "https://raw.githubusercontent.com/awesome-selfhosted/awesome-selfhosted/master/README.md"
    )
    AWESOME_PYTHON_URL: ClassVar[Any] = (
        "https://raw.githubusercontent.com/vinta/awesome-python/master/README.md"
    )
    GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
    LIBRARIES_IO_SEARCH_URL = "https://libraries.io/api/search"

    _MARKDOWN_ENTRY_RE = re.compile(
        r"^- \[(?P<name>[^\]]+)\]\((?P<link>https?://[^\)]+)\)\s*-\s*(?P<description>.*)",
        re.IGNORECASE,
    )

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self.http_client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._managed_client = http_client is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        await self.close()

    async def close(self) -> None:
        if self._managed_client and self.http_client is not None:
            await self.http_client.aclose()

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SupremeAI-ResourceCatalog/2.0",
        }
        github_token = getattr(settings, "github_api_token", "")
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        return headers

    def _parse_awesome_markdown(
        self, markdown: str, query: str, limit: int, source_name: str
    ) -> list[dict[str, Any]]:
        query_lower = query.strip().lower()
        results: list[dict[str, Any]] = []

        for line in markdown.splitlines():
            if not line.startswith("- ["):
                continue
            match = self._MARKDOWN_ENTRY_RE.match(line)
            if not match:
                continue

            name = match.group("name").strip()
            url = match.group("link").strip()
            description = match.group("description").strip()
            if query_lower in name.lower() or query_lower in description.lower():
                results.append(
                    {
                        "id": str(uuid.uuid4()),
                        "name": name,
                        "version": "0.0.0",
                        "description": description,
                        "url": url,
                        "dependencies": None,
                        "installed": False,
                        "source": source_name,
                    }
                )
                if len(results) >= limit:
                    break
        return results

    async def search_awesome_selfhosted(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            response = await self.http_client.get(self.AWESOME_SELFHOSTED_URL)
            response.raise_for_status()
            return self._parse_awesome_markdown(
                response.text, query, limit, source_name="awesome-selfhosted"
            )
        except Exception as exc:
            logger.warning(
                f"ResourceCatalog: failed to search awesome-selfhosted for '{query}': {exc}"
            )
            return []

    async def search_awesome_python(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            response = await self.http_client.get(self.AWESOME_PYTHON_URL)
            response.raise_for_status()
            return self._parse_awesome_markdown(
                response.text, query, limit, source_name="awesome-python"
            )
        except Exception as exc:
            logger.warning(f"ResourceCatalog: failed to search awesome-python for '{query}': {exc}")
            return []

    async def search_github_repos(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            params = {
                "q": f"{query} in:name,description",
                "sort": "stars",
                "order": "desc",
                "per_page": limit,
            }
            response = await self.http_client.get(
                self.GITHUB_SEARCH_URL,
                params=params,
                headers=self._build_headers(),
            )
            response.raise_for_status()
            payload = response.json()
            results: list[dict[str, Any]] = []
            for item in payload.get("items", []):
                results.append(
                    {
                        "id": str(uuid.uuid4()),
                        "name": item.get("full_name", ""),
                        "version": item.get("default_branch", ""),
                        "description": item.get("description") or "",
                        "url": item.get("html_url"),
                        "dependencies": None,
                        "installed": False,
                        "source": "ossinsight",
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "quality_score": self._score_repo(item),
                    }
                )
            return results
        except Exception as exc:
            logger.warning(f"ResourceCatalog: failed to search ossinsight for '{query}': {exc}")
            return []

    async def search_libraries_io(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        try:
            params = {
                "q": query,
                "platforms": "PyPI",
                "per_page": limit,
            }
            api_key = getattr(settings, "libraries_io_api_key", "")
            if api_key:
                params["api_key"] = api_key

            response = await self.http_client.get(self.LIBRARIES_IO_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            results: list[dict[str, Any]] = []
            for item in payload:
                results.append(
                    {
                        "id": str(uuid.uuid4()),
                        "name": item.get("name", ""),
                        "version": item.get("latest_release_number", ""),
                        "description": item.get("description") or "",
                        "url": item.get("homepage_url") or item.get("repository_url"),
                        "dependencies": (
                            ", ".join(item.get("dependencies", []))
                            if item.get("dependencies")
                            else None
                        ),
                        "installed": False,
                        "source": "libraries.io",
                        "stars": item.get("rank", 0),
                    }
                )
            return results
        except Exception as exc:
            logger.warning(f"ResourceCatalog: failed to search libraries.io for '{query}': {exc}")
            return []

    def _score_repo(self, repo_json: dict) -> float:
        stars = max(0, int(repo_json.get("stargazers_count", 0)))
        forks = max(0, int(repo_json.get("forks_count", 0)))
        issues = max(0, int(repo_json.get("open_issues_count", 0)))
        watchers = max(0, int(repo_json.get("watchers_count", 0)))
        score = min(
            100.0,
            stars / 100.0 + forks / 50.0 + max(0.0, 20.0 - issues) + min(20.0, watchers / 100.0),
        )
        return round(score, 2)

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        sources = sources or ["awesome-selfhosted", "awesome-python"]
        results: list[dict[str, Any]] = []

        if "awesome-selfhosted" in sources:
            results.extend(await self.search_awesome_selfhosted(query, limit=limit))

        if "awesome-python" in sources:
            remaining = max(limit - len(results), 0)
            if remaining > 0:
                results.extend(await self.search_awesome_python(query, limit=remaining))

        if "ossinsight" in sources:
            remaining = max(limit - len(results), 0)
            if remaining > 0:
                results.extend(await self.search_github_repos(query, limit=remaining))

        if "libraries.io" in sources:
            remaining = max(limit - len(results), 0)
            if remaining > 0:
                results.extend(await self.search_libraries_io(query, limit=remaining))

        return results[:limit]
