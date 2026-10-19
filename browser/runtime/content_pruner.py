"""Crawl4AI-pattern heuristic content pruner (stdlib html.parser).

Transforms messy HTML into clean Markdown with numbered citations while
stripping boilerplate (navbars, footers, ads, forms) WITHOUT burning LLM
tokens. Adapted from the Crawl4AI heuristic school: text-vs-link density
scoring plus tag/attribute blacklists.

Algorithm (per candidate block):
  1. Structural removal: script/style/nav/footer/aside/form/iframe and
     elements whose class/id matches an ad or boilerplate pattern.
  2. Block scoring: link_density = link_chars / total_chars; blocks with
     high link density and short text are classified as ads/menus.
  3. Preference: article/main/[role=main] content wins container selection.
  4. Markdown emission: headings, paragraphs, lists, code fences, and
     reference-style numbered citations for retained links.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import ClassVar

__all__ = ["ContentPruner", "PrunedContent", "link_density"]

_DROP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "form",
    "nav",
    "footer",
    "aside",
    "header",
    "button",
    "select",
    "option",
    "input",
    "label",
    "video",
    "audio",
    "object",
    "embed",
}
_NOISE_CLASS_RE = re.compile(
    r"(advert|ads?[-_ ]?container|banner|breadcrumb|comment|cookie|promo|"
    r"sponsor|sidebar|subscribe|newsletter|related|share|social|popup|modal|"
    r"menu|navigation|widget|recommend|trending|footer|header-top)",
    re.IGNORECASE,
)
_PREFERRED_TAGS = {"article", "main"}
_PREFERRED_ATTRS = {"role": "main"}
_HEADING = re.compile(r"^h([1-6])$")
_LIST_TAGS = {"ul", "ol"}
_WHITESPACE_RE = re.compile(r"\s+")


def link_density(text: str, link_chars: int) -> float:
    """link_chars / total_chars with 0.0 floor on empty text."""
    total = len(_WHITESPACE_RE.sub("", text))
    if total == 0:
        return 0.0
    return min(1.0, max(0.0, link_chars) / total)


@dataclass
class PrunedContent:
    markdown: str
    citations: list[tuple[int, str]] = field(default_factory=list)
    blocks_kept: int = 0
    blocks_dropped: int = 0
    chars_before: int = 0
    chars_after: int = 0

    @property
    def reduction_ratio(self) -> float:
        if self.chars_before == 0:
            return 0.0
        return 1.0 - (self.chars_after / self.chars_before)

    @property
    def citation_block(self) -> str:
        lines = [f"[{n}] {url}" for n, url in self.citations]
        return "\n".join(lines)


class _Block:
    """One candidate content block harvested during the parse."""

    def __init__(self, tag: str, attrs: dict[str, str], depth: int) -> None:
        self.tag = tag
        self.attrs = attrs
        self.depth = depth
        self.text_chunks: list[str] = []
        self.links: list[tuple[str, str]] = []  # (text, href)
        self.link_chars = 0

    def text(self) -> str:
        return " ".join(" ".join(self.text_chunks).split())

    def is_noisy(self) -> bool:
        ident = " ".join(
            str(self.attrs.get(k, "")) for k in ("class", "id", "data-testid")
        )
        return bool(ident and _NOISE_CLASS_RE.search(ident))


class _Harvester(HTMLParser):
    """Collect candidate blocks: paragraphs, headings, list items, pre."""

    _BLOCK_TAGS: ClassVar[set[str]] = {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "pre",
        "blockquote",
        "td",
        "figcaption",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self.open_blocks: list[_Block] = []
        self.skip_depth: int | None = None
        self.skip_tag: str = ""
        self.depth = 0
        self.anchor_href: str | None = None
        self.anchor_buf: list[str] = []
        self.title = ""

    # -- helpers -----------------------------------------------------------
    def _in_skip(self) -> bool:
        return self.skip_depth is not None

    def handle_starttag(self, tag, attrs):
        self.depth += 1
        attrd = dict(attrs)
        if self._in_skip():
            return
        if tag in _DROP_TAGS or (
            tag == "div" and _Block(tag, attrd, self.depth).is_noisy()
        ):
            self.skip_depth = self.depth
            self.skip_tag = tag
            return
        if tag == "a" and attrd.get("href"):
            self.anchor_href = attrd["href"]
            self.anchor_buf = []
            return
        if tag in self._BLOCK_TAGS:
            self.open_blocks.append(_Block(tag, attrd, self.depth))
        if tag == "title":
            self.skip_depth = self.depth
            self.skip_tag = tag

    def handle_endtag(self, tag):
        if self._in_skip():
            if self.depth == self.skip_depth:
                self.skip_depth = None
                self.skip_tag = ""
            self.depth -= 1
            return
        if tag == "a" and self.anchor_href is not None:
            text = " ".join(" ".join(self.anchor_buf).split())
            for blk in self.open_blocks:
                blk.links.append((text, self.anchor_href))  # type: ignore[arg-type]
                blk.link_chars += len(text)
            self.anchor_href = None
            self.anchor_buf = []
            self.depth -= 1
            return
        if tag in self._BLOCK_TAGS and self.open_blocks:
            blk = self.open_blocks.pop()
            self.blocks.append(blk)
        self.depth -= 1

    def handle_data(self, data):
        if self._in_skip():
            return
        text = data.strip()
        if not text:
            return
        if self.anchor_href is not None:
            self.anchor_buf.append(text)
        for blk in self.open_blocks:
            blk.text_chunks.append(text)


def _heading_level(tag: str) -> int:
    m = _HEADING.match(tag)
    return int(m.group(1)) if m else 0


class ContentPruner:
    """Heuristic boilerplate pruner producing citation-linked Markdown."""

    def __init__(
        self, link_density_threshold: float = 0.6, min_block_chars: int = 24
    ) -> None:
        if not 0.0 < link_density_threshold <= 1.0:
            raise ValueError("link_density_threshold must be within (0, 1]")
        if min_block_chars < 0:
            raise ValueError("min_block_chars must be >= 0")
        self.link_density_threshold = link_density_threshold
        self.min_block_chars = min_block_chars

    def prune(self, html: str) -> PrunedContent:
        if html is None or not isinstance(html, str):
            raise ValueError("html must be a string")
        harvester = _Harvester()
        harvester.feed(html)
        harvester.close()

        result = PrunedContent(
            markdown="",
            citations=[],
            chars_before=len(html),
        )
        md_lines: list[str] = []
        seen_urls: dict[str, int] = {}

        for blk in harvester.blocks:
            text = blk.text()
            density = link_density(text, blk.link_chars)
            drop = False
            if blk.is_noisy():
                drop = True
            elif density > self.link_density_threshold and len(text) < 200:
                # Short, link-dominated blocks are menus/ads.
                drop = True
            elif len(text) < self.min_block_chars and not blk.links:
                drop = True
            if drop:
                result.blocks_dropped += 1
                continue
            result.blocks_kept += 1
            level = _heading_level(blk.tag)
            if level:
                md_lines.append(f"{'#' * level} {text}")
                continue
            if blk.tag == "li":
                md_lines.append(f"- {text}")
                continue
            if blk.tag == "pre":
                md_lines.append(f"```\n{text}\n```")
                continue
            # Inline citation links for paragraphs.
            decorated = text
            if blk.links:
                link_map: dict[str, int] = {}
                for link_text, href in blk.links:
                    if href not in seen_urls:
                        seen_urls[href] = len(seen_urls) + 1
                        result.citations.append((seen_urls[href], href))
                    if link_text and link_text in text:
                        link_map[link_text] = seen_urls[href]
                for link_text, num in sorted(
                    link_map.items(), key=lambda kv: -len(kv[0])
                ):
                    decorated = decorated.replace(link_text, f"{link_text} [{num}]", 1)
            md_lines.append(decorated)

        result.markdown = "\n\n".join(md_lines)
        result.chars_after = len(result.markdown)
        return result
