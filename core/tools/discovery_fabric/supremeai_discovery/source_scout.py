from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


@dataclass
class Candidate:
    source: str
    title: str
    url: str
    summary: str = ""
    license: str | None = None
    stars: int | None = None
    downloads: int | None = None
    updated_at: str | None = None
    trust: float = 0.0
    relevance: float = 0.0
    maturity: float = 0.0
    freshness: float = 0.0
    risk: float = 0.0
    score: float = 0.0
    evidence: list[str] | None = None


def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = Request(url, headers={"User-Agent": "SupremeAI-DiscoveryFabric/1.0", **(headers or {})})
    with urlopen(req, timeout=12) as r:
        return json.load(r)


def _github(q: str, limit: int = 10) -> list[Candidate]:
    url = f"https://api.github.com/search/repositories?q={quote_plus(q)}&sort=stars&order=desc&per_page={limit}"
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    data = _get_json(url, headers)
    out: list[Candidate] = []
    for x in data.get("items", []):
        text = f"{x.get('name','')} {x.get('description','') or ''}".lower()
        out.append(Candidate(
            source="github",
            title=x.get("full_name", x.get("name", "")),
            url=x.get("html_url", ""),
            summary=x.get("description", "") or "",
            license=(x.get("license") or {}).get("spdx_id"),
            stars=x.get("stargazers_count"),
            updated_at=x.get("updated_at"),
            relevance=_keyword_relevance(q, text),
            maturity=min(1.0, (x.get("stargazers_count") or 0) / 5000),
            evidence=["GitHub repository metadata"],
        ))
    return out


def _npm(q: str, limit: int = 10) -> list[Candidate]:
    url = f"https://registry.npmjs.org/-/v1/search?text={quote_plus(q)}&size={limit}"
    data = _get_json(url)
    out: list[Candidate] = []
    for x in data.get("objects", []):
        p = x.get("package", {})
        out.append(Candidate(
            source="npm",
            title=p.get("name", ""),
            url=p.get("links", {}).get("npm", ""),
            summary=p.get("description", "") or "",
            license=p.get("license"),
            downloads=x.get("downloads", {}).get("weekly"),
            updated_at=p.get("date"),
            relevance=_keyword_relevance(q, f"{p.get('name','')} {p.get('description','') or ''}".lower()),
            maturity=min(1.0, (x.get("downloads", {}).get("weekly") or 0) / 1_000_000),
            evidence=["npm registry metadata"],
        ))
    return out


def _pypi(q: str, limit: int = 8) -> list[Candidate]:
    # PyPI has no rich official text-search endpoint. Use configured search API when available.
    base = os.getenv("PYPI_SEARCH_URL")
    if not base:
        return []
    data = _get_json(base.format(query=quote_plus(q), limit=limit))
    out: list[Candidate] = []
    for x in data.get("results", data if isinstance(data, list) else []):
        name = x.get("name", "")
        out.append(Candidate(
            source="pypi",
            title=name,
            url=x.get("project_url") or f"https://pypi.org/project/{name}/",
            summary=x.get("description", "") or "",
            license=x.get("license"),
            updated_at=x.get("last_release"),
            relevance=_keyword_relevance(q, f"{name} {x.get('description','') or ''}".lower()),
            maturity=min(1.0, (x.get("downloads", {}).get("last_month") or 0) / 1_000_000),
            evidence=["PyPI-compatible search endpoint"],
        ))
    return out


def _hf(q: str, limit: int = 10) -> list[Candidate]:
    url = f"https://huggingface.co/api/models?search={quote_plus(q)}&limit={limit}&sort=downloads&direction=-1"
    data = _get_json(url)
    out: list[Candidate] = []
    for x in data if isinstance(data, list) else []:
        out.append(Candidate(
            source="huggingface",
            title=x.get("id", ""),
            url=f"https://huggingface.co/{x.get('id','')}",
            summary="Hugging Face model",
            stars=x.get("likes"),
            downloads=x.get("downloads"),
            updated_at=x.get("lastModified"),
            relevance=_keyword_relevance(q, str(x.get("id", "")).lower()),
            maturity=min(1.0, (x.get("downloads") or 0) / 1_000_000),
            evidence=["Hugging Face Hub model metadata"],
        ))
    return out


def _keyword_relevance(query: str, text: str) -> float:
    terms = {x for x in re.findall(r"[a-z0-9_-]+", query.lower()) if len(x) > 2}
    if not terms:
        return 0.0
    hits = sum(1 for t in terms if t in text)
    return hits / len(terms)


def _freshness(updated_at: str | None) -> float:
    if not updated_at:
        return 0.35
    try:
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        days = max(0, (datetime.now(timezone.utc) - ts).days)
        return max(0.05, 1.0 - min(days, 3650) / 3650)
    except Exception:
        return 0.35


def rank(candidates: Iterable[Candidate], *, prefer_open_source: bool = True) -> list[Candidate]:
    ranked: list[Candidate] = []
    for c in candidates:
        c.trust = {"github": 0.82, "huggingface": 0.78, "npm": 0.72, "pypi": 0.72}.get(c.source, 0.55)
        c.freshness = _freshness(c.updated_at)
        license_ok = c.license not in {"NOASSERTION", ""} if c.license is not None else 0.55
        c.risk = 0.0 if license_ok else 0.35
        c.score = round(
            0.30 * c.trust
            + 0.28 * c.relevance
            + 0.18 * c.maturity
            + 0.16 * c.freshness
            + 0.08 * (1.0 - c.risk),
            4,
        )
        ranked.append(c)
    return sorted(ranked, key=lambda x: x.score, reverse=True)


def scout(query: str, limit_per_source: int = 8) -> dict[str, Any]:
    providers = []
    for fn in (_github, _npm, _pypi, _hf):
        try:
            providers.extend(fn(query, limit_per_source))
        except Exception as exc:
            providers.append(Candidate(source=fn.__name__, title="SOURCE_ERROR", url="", summary=str(exc), risk=1.0, evidence=["source query failed"]))
    return {
        "query": query,
        "generated_at": time.time(),
        "candidates": [asdict(x) for x in rank(providers)],
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="SupremeAI Solution Discovery Fabric")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    result = scout(args.query, args.limit)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
