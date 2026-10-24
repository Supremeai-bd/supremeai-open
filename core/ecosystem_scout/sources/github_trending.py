"""GitHub trending source (#4055).

বাংলা: GitHub trending page-থেকে repos fetch করে। GitHub API-এ trending endpoint
নেই, তাই scrape করতে হয় বা alternative (gh-trending API) ব্যবহার করতে হয়।
এই prototype-এ mock data + optional real fetch দুটোই আছে।
"""

from __future__ import annotations

import json
from typing import Any

from ..models import FindingSource, ScoutFinding, make_finding


def fetch_github_trending(
    language: str = "",
    since: str = "daily",
    limit: int = 10,
    use_mock: bool = True,
) -> list[ScoutFinding]:
    """Fetch trending repos from GitHub.

    Args:
        language: filter by language (e.g., "python", "")
        since: "daily", "weekly", "monthly"
        limit: max number of findings
        use_mock: if True, return mock data (prototype); if False, attempt real fetch

    Returns:
        list of ScoutFinding objects
    """
    if use_mock:
        return _mock_trending(limit)

    # Real fetch would use httpx to scrape https://github.com/trending
    # or use a third-party API. Prototype uses mock for safety.
    try:
        return _fetch_real_trending(language, since, limit)
    except Exception:
        # Fall back to mock on any error
        return _mock_trending(limit)


def _mock_trending(limit: int) -> list[ScoutFinding]:
    """Return mock trending data for prototype/testing."""
    mock_repos = [
        (
            "browser-use/browser-use",
            "AI-agent browser automation",
            117000,
            "python",
            ["ai", "browser", "automation"],
        ),
        (
            "All-Hands-AI/OpenHands",
            "Autonomous coding agent",
            45000,
            "python",
            ["ai", "coding", "agent"],
        ),
        (
            "Cerebras/cerebras-python",
            "Speed-optimized LLM inference",
            5000,
            "python",
            ["llm", "inference", "fast"],
        ),
        (
            "OpenViking/openviking",
            "Hierarchical context for agents",
            2000,
            "python",
            ["context", "memory", "agents"],
        ),
        (
            "agent-reach/agent-reach",
            "Agent discovery platform",
            1500,
            "typescript",
            ["discovery", "agents"],
        ),
        (
            "Memanto/memanto",
            "Memory governance with TTL",
            800,
            "python",
            ["memory", "governance", "ttl"],
        ),
        (
            "duckdb/duckdb",
            "In-process analytics database",
            25000,
            "c++",
            ["analytics", "database", "olap"],
        ),
        (
            "Strata/strata",
            "Layered model staging for local inference",
            600,
            "python",
            ["llm", "local", "vram"],
        ),
    ]
    findings = []
    for repo_name, desc, stars, lang, topics in mock_repos[:limit]:
        findings.append(
            make_finding(
                source=FindingSource.GITHUB_TRENDING,
                repo_name=repo_name,
                repo_url=f"https://github.com/{repo_name}",
                description=desc,
                stars=stars,
                language=lang,
                topics=topics,
            )
        )
    return findings


def _fetch_real_trending(language: str, since: str, limit: int) -> list[ScoutFinding]:
    """Attempt to fetch real trending data (prototype — may fail)."""
    import httpx

    # Use a third-party GitHub trending API (unofficial)
    url = f"https://gh-trending-api.herokuapp.com/repositories?since={since}"
    if language:
        url += f"&language={language}"

    resp = httpx.get(url, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()

    findings = []
    for item in data[:limit]:
        findings.append(
            make_finding(
                source=FindingSource.GITHUB_TRENDING,
                repo_name=item.get("author", "") + "/" + item.get("name", ""),
                repo_url=item.get("url", ""),
                description=item.get("description", ""),
                stars=item.get("stars", 0),
                language=item.get("language", ""),
                topics=item.get("currentPeriodStars", []),
            )
        )
    return findings
