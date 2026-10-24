"""ResearchAssistant — real research-paper search, summarization and citation.

ERR-H06 FIX (2026-09-16): ``backend/api/routes/agents.py`` imported
``agents.research_assistant`` which did not exist anywhere in the repository,
so ``POST /api/agents/research/{search,summarize,cite}`` failed with an
unconditional HTTP 500. This module implements the missing capability for
real — no fabricated results, no canned papers:

- ``search()``      → live arXiv Atom API query (stdlib urllib + ElementTree);
                      network/API failures raise with the verbatim error so
                      the route can surface an honest 502.
- ``summarize()``   → extractive summarization (term-frequency sentence
                      scoring) of the supplied abstract/paper text — a real
                      deterministic algorithm, not an LLM stub.
- ``citations()``   → deterministic citation formatting (APA/MLA/IEEE/
                      BibTeX) from real paper metadata.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_API = "https://export.arxiv.org/api/query"
_REQUEST_TIMEOUT_S = 15

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")


class ResearchSourceError(RuntimeError):
    """Raised when the upstream research source cannot be reached/parsed."""


class ResearchAssistant:
    """Search arXiv, summarize text, and format citations — all for real."""

    # ------------------------------------------------------------------ search

    def search(
        self, query: str, source: str = "arxiv", max_results: int = 5
    ) -> list[dict[str, Any]]:
        """Query a real research source. Only ``arxiv`` is supported today;
        anything else is rejected explicitly (never silently fabricated)."""
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if source != "arxiv":
            raise ValueError(f"unsupported research source {source!r}: only 'arxiv' is implemented")
        max_results = max(1, min(int(max_results), 50))

        url = f"{_ARXIV_API}?{urllib.parse.urlencode({'search_query': f'all:{query.strip()}', 'start': 0, 'max_results': max_results})}"
        try:
            with urllib.request.urlopen(url, timeout=_REQUEST_TIMEOUT_S) as resp:  # noqa: S310 — fixed https endpoint
                body = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 — verbatim reason surfaces via HTTP 502
            raise ResearchSourceError(f"arXiv API request failed: {exc}") from exc

        papers: list[dict[str, Any]] = []
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise ResearchSourceError(f"arXiv API returned unparseable XML: {exc}") from exc

        for entry in root.findall(f"{_ATOM_NS}entry"):
            title = (entry.findtext(f"{_ATOM_NS}title") or "").strip().replace("\n", " ")
            link = ""
            for href in entry.findall(f"{_ATOM_NS}id"):
                link = (href.text or "").strip()
                break
            authors = [
                (a.findtext(f"{_ATOM_NS}name") or "").strip()
                for a in entry.findall(f"{_ATOM_NS}author")
            ]
            papers.append(
                {
                    "title": title,
                    "authors": [a for a in authors if a],
                    "published": (entry.findtext(f"{_ATOM_NS}published") or "").strip(),
                    "summary": (entry.findtext(f"{_ATOM_NS}summary") or "").strip(),
                    "url": link,
                    "arxiv_id": link.rsplit("/abs/", 1)[-1] if "/abs/" in link else "",
                    "source": "arxiv",
                }
            )
        return papers

    # --------------------------------------------------------------- summarize

    def summarize(self, paper: dict[str, Any]) -> dict[str, Any]:
        """Extractive summarization of the paper text (term-frequency scoring).

        Accepts any of ``text`` / ``summary`` / ``abstract`` keys plus optional
        ``title``. Returns the top sentences in original order, salience
        scores, and the dominant keywords — all derived from the input.
        """
        if not isinstance(paper, dict):
            raise ValueError("paper must be an object with a text/summary/abstract field")
        text = str(paper.get("text") or paper.get("summary") or paper.get("abstract") or "").strip()
        if not text:
            raise ValueError("paper must contain a non-empty text/summary/abstract field")

        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        if not sentences:
            sentences = [text]

        stop = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "of",
            "to",
            "in",
            "on",
            "for",
            "with",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "that",
            "this",
            "these",
            "those",
            "we",
            "our",
            "it",
            "its",
            "as",
            "at",
            "by",
            "from",
            "not",
            "can",
            "will",
        }
        freq: dict[str, int] = {}
        for word in _WORD.findall(text.lower()):
            if word not in stop and len(word) > 2:
                freq[word] = freq.get(word, 0) + 1

        def score(sentence: str) -> float:
            words = [w for w in _WORD.findall(sentence.lower()) if w not in stop and len(w) > 2]
            if not words:
                return 0.0
            return sum(freq.get(w, 0) for w in words) / (len(words) ** 0.5)

        ranked = sorted(range(len(sentences)), key=lambda i: score(sentences[i]), reverse=True)
        keep = max(1, min(5, len(sentences) // 3 or 1))
        chosen = sorted(ranked[:keep])
        keywords = [w for w, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:8]]

        return {
            "title": paper.get("title") or "",
            "summary": " ".join(sentences[i] for i in chosen),
            "key_sentences": [sentences[i] for i in chosen],
            "keywords": keywords,
            "compression": {"original_sentences": len(sentences), "kept": keep},
            "method": "extractive-term-frequency",
        }

    # --------------------------------------------------------------- citations

    def citations(self, paper: dict[str, Any], style: str = "apa") -> str:
        """Format a citation from real metadata. Deterministic; unknown
        styles are rejected explicitly."""
        if not isinstance(paper, dict):
            raise ValueError("paper must be an object with title/authors metadata")
        title = str(paper.get("title") or "").strip()
        if not title:
            raise ValueError("paper.title is required for citation formatting")
        authors = [str(a).strip() for a in (paper.get("authors") or []) if str(a).strip()]
        year = str(paper.get("year") or "").strip()
        if not year and paper.get("published"):
            match = re.match(r"(\d{4})", str(paper["published"]))
            year = match.group(1) if match else ""
        venue = str(paper.get("venue") or paper.get("source") or "arXiv").strip()
        url = str(paper.get("url") or "").strip()
        style = (style or "apa").lower()

        if style == "apa":
            names = self._apa_names(authors)
            return f"{names} ({year or 'n.d.'}). {title}. {venue}." + (f" {url}" if url else "")
        if style == "mla":
            names = self._mla_names(authors)
            tail = f" {venue}," + (f" {year}," if year else "") + (" " + url if url else "") + "."
            return f'{names} "{title}."{tail}'
        if style == "ieee":
            names = self._ieee_names(authors)
            tail = f", {year}." if year else "."
            return f'{names} "{title}," {venue}{tail}' + (
                f" [Online]. Available: {url}" if url else ""
            )
        if style == "bibtex":
            key = (authors[0].split()[-1].lower() if authors else "unknown") + (year or "")
            lines = [
                f"@misc{{{key},",
                f"  title = {{{title}}},",
                f"  author = {{{' and '.join(authors)}}},",
                f"  year = {{{year or 'n.d.'}}},",
                f"  howpublished = {{{venue}}},",
            ]
            if url:
                lines.append(f"  url = {{{url}}},")
            lines.append("}")
            return "\n".join(lines)
        raise ValueError(f"unsupported citation style {style!r}: use apa|mla|ieee|bibtex")

    @staticmethod
    def _apa_names(authors: list[str]) -> str:
        if not authors:
            return "Anonymous"
        if len(authors) == 1:
            return authors[0]
        if len(authors) == 2:
            return f"{authors[0]} & {authors[1]}"
        return f"{authors[0]} et al."

    @staticmethod
    def _mla_names(authors: list[str]) -> str:
        if not authors:
            return "Anonymous"
        if len(authors) == 1:
            return authors[0]
        if len(authors) == 2:
            return f"{authors[0]}, and {authors[1]}"
        return f"{authors[0]}, et al"

    @staticmethod
    def _ieee_names(authors: list[str]) -> str:
        if not authors:
            return "Anonymous"
        return f"{authors[0]} et al." if len(authors) > 1 else authors[0]
